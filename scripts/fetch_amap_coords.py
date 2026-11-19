#!/usr/bin/env python3
"""Fetch Amap POI candidates for Hangzhou scenic spots.

Reads official_name/grade/address from an input CSV, queries Amap place/text
with several keyword variants, scores name matches, and writes a candidate CSV
for manual review.

Usage:
    python scripts/fetch_amap_coords.py --input <csv> --output <csv>
    python scripts/fetch_amap_coords.py --input <csv> --limit 10

Key lookup order: AMAP_KEY, gaodemap, GAODEMAP environment variables, then
~/.config/amap.key. The key must be a Web Service key with place/text permission.
"""

import argparse
import csv
import difflib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

API_URL = "https://restapi.amap.com/v3/place/text"
PREFIXES = ("杭州市", "杭州", "浙江省", "浙江")
SUFFIXES = ("风景名胜区", "旅游度假区", "风景区", "旅游区", "度假区", "景区", "公园")
DISTRICT_PREFIXES = ("临安", "淳安", "建德", "桐庐", "富阳", "萧山", "余杭", "临平")
GENERIC_EXTRAS = {
    "景区", "风景区", "风景名胜区", "公园", "旅游区", "度假区",
    "自然保护区", "国家级", "景点", "国家级景点",
}
SUB_POI_MARKERS = (
    "儿童馆", "展厅", "索道", "水塘", "广场", "码头", "游客中心",
    "停车场", "分馆", "登山处", "观鸟区", "多功能厅",
)
ABORT_CODES = {"10001", "10003", "10009", "10044"}
QPS_CODES = {"10004", "10021"}
STATUS_RANK = {"auto": 3, "review": 2, "no_coord": 1, "no_result": 0}
LAST_REQUEST_AT = 0.0
OUTPUT_FIELDS = [
    "official_name", "grade", "address", "status", "score", "margin", "note",
    "amap_name", "amap_address", "amap_lng", "amap_lat", "amap_adcode",
    "amap_cityname", "amap_adname", "amap_type", "amap_id", "query",
]


def load_key() -> str:
    """Return the Amap Web Service key from env or ~/.config/amap.key."""
    for name in ("AMAP_KEY", "gaodemap", "GAODEMAP"):
        key = os.environ.get(name, "").strip()
        if key:
            return key
    key = ""
    key_file = Path.home() / ".config" / "amap.key"
    if key_file.exists():
        key = key_file.read_text(encoding="utf-8").strip()
    if not key:
        raise SystemExit(
            "AMAP_KEY is not set. Set the environment variable or write the key to "
            f"{key_file}."
        )
    return key


def normalize_name(name: str) -> str:
    """Strip city prefixes, scenic suffixes, spaces, and punctuation from a name."""
    value = re.sub(r"[\s·.（）()\-—]", "", name or "")
    for prefix in PREFIXES:
        if value.startswith(prefix):
            value = value[len(prefix):]
    for suffix in SUFFIXES:
        if value.endswith(suffix):
            value = value[:-len(suffix)]
    return value


def strip_leading_district(name: str) -> str:
    """Remove a leading suburban district name so core tokens can match."""
    for district in DISTRICT_PREFIXES:
        if name.startswith(district) and len(name) > len(district) + 1:
            return name[len(district):]
    return name


def extract_district(address: str) -> str:
    """Extract a Hangzhou district or county name from an address string."""
    match = re.search(
        r"(西湖区|上城区|拱墅区|滨江区|萧山区|余杭区|临平区|钱塘区|富阳区|临安区|桐庐县|淳安县|建德市)",
        address or "",
    )
    return match.group(1) if match else ""


def is_subsequence(needle: str, haystack: str) -> bool:
    """Return True when every character of needle appears in order in haystack."""
    iterator = iter(haystack)
    return bool(needle) and all(char in iterator for char in needle)


def is_sub_poi(name: str) -> bool:
    """Return True when a POI name looks like a child POI of a scenic area."""
    return "-" in name or "（" in name or "(" in name or any(marker in name for marker in SUB_POI_MARKERS)


def score_candidate(row: dict, poi: dict) -> int:
    """Score one Amap POI against a source row; higher is better."""
    wanted = strip_leading_district(normalize_name(row.get("official_name", "")))
    found = strip_leading_district(normalize_name(poi.get("name", "")))
    if not wanted or not found:
        return 0
    if wanted == found:
        score = 100
    elif wanted in found:
        extra = found.replace(wanted, "", 1)
        score = 90 if extra in GENERIC_EXTRAS else 60
        if found.startswith(wanted):
            score += 15
    elif found in wanted:
        extra = wanted.replace(found, "", 1)
        score = 70 if extra in GENERIC_EXTRAS else 55
    elif is_subsequence(wanted, found):
        score = 85
    else:
        score = int(difflib.SequenceMatcher(None, wanted, found).ratio() * 60)
    district = extract_district(row.get("address", ""))
    if district:
        if district in (poi.get("adname") or ""):
            score += 15
        else:
            score -= 30
    poi_type = poi.get("type") or ""
    if "国家级景点" in poi_type:
        score += 10
    elif "风景名胜" in poi_type:
        score += 5
    return max(0, score)


def query_variants(name: str) -> list:
    """Build deduplicated Amap query keywords from an official scenic name."""
    variants = [name]
    core = normalize_name(name)
    if core and core != name:
        variants.append(core)
    stripped = strip_leading_district(core)
    if stripped and stripped != core:
        variants.append(stripped)
    for part in re.split(r"[·.]", name):
        part = part.strip()
        if len(part) >= 2:
            variants.append(part)
    unique = []
    for variant in variants:
        if variant and variant not in unique:
            unique.append(variant)
    return unique[:4]


def wait_for_slot(interval: float) -> None:
    """Block until at least interval seconds have passed since the last request."""
    global LAST_REQUEST_AT
    wait = interval - (time.monotonic() - LAST_REQUEST_AT)
    if wait > 0:
        time.sleep(wait)
    LAST_REQUEST_AT = time.monotonic()


def request_pois(key: str, keyword: str, city: str, types: str, interval: float = 1.0) -> list:
    """Query Amap place/text and return the POI list, retrying transient errors."""
    params = {
        "key": key,
        "keywords": keyword,
        "city": city,
        "citylimit": "true",
        "offset": "10",
        "page": "1",
        "extensions": "base",
    }
    if types:
        params["types"] = types
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    headers = {"User-Agent": "Etemenanki-travel-demo/0.1"}
    last_error = None
    for attempt in range(4):
        wait_for_slot(interval)
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if payload.get("status") == "1":
                return payload.get("pois") or []
            code = str(payload.get("infocode", ""))
            if code in QPS_CODES:
                time.sleep(3.0 * (attempt + 1))
                last_error = f"QPS limit: {payload.get('info', '')}"
                continue
            if code in ABORT_CODES:
                raise SystemExit(f"Amap rejected the key/quota: {code} {payload.get('info', '')}")
            raise RuntimeError(f"Amap error {code}: {payload.get('info', '')}")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            last_error = str(error)
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Amap request failed after 3 attempts: {last_error}")


def fetch_candidates(row: dict, key: str, city: str, types: str, interval: float = 1.0) -> list:
    """Query keyword variants until a high-confidence POI is found."""
    collected = {}
    variants = query_variants(row.get("official_name", ""))
    override = (row.get("query") or "").strip()
    if override:
        variants = [override] + [item for item in variants if item != override]
    for query in variants:
        for poi in request_pois(key, query, city, types, interval):
            poi_id = poi.get("id") or ""
            score = score_candidate(row, poi)
            if poi_id and poi_id in collected and collected[poi_id][0] >= score:
                continue
            if poi_id:
                collected[poi_id] = (score, poi, query, is_sub_poi(poi.get("name", "")))
        if collected and max(item[0] for item in collected.values()) >= 85:
            break
    return list(collected.values())


def pick_candidates(row: dict, candidates: list) -> dict:
    """Pick the best POI and build one output row with match status."""
    output = {field: "" for field in OUTPUT_FIELDS}
    output.update(
        official_name=row.get("official_name", ""),
        grade=row.get("grade", ""),
        address=row.get("address", ""),
        query=row.get("official_name", ""),
    )
    if not candidates:
        output["status"] = "no_result"
        return output
    ranked = sorted(candidates, key=lambda item: item[0], reverse=True)
    best_score, best, used_query, sub_poi = ranked[0]
    second_score = ranked[1][0] if len(ranked) > 1 else 0
    margin = best_score - second_score
    if len(ranked) > 1 and margin < 10:
        first_name = strip_leading_district(normalize_name(best.get("name", "")))
        second_name = strip_leading_district(normalize_name(ranked[1][1].get("name", "")))
        same_place = first_name == second_name and best.get("adname") == ranked[1][1].get("adname")
        if same_place or (first_name and second_name.startswith(first_name)):
            margin = 100
    location = (best.get("location") or "").split(",")
    output.update(
        score=best_score,
        margin=margin,
        amap_name=best.get("name", ""),
        amap_address=best.get("address", ""),
        amap_lng=location[0] if len(location) == 2 else "",
        amap_lat=location[1] if len(location) == 2 else "",
        amap_adcode=best.get("adcode", ""),
        amap_cityname=best.get("cityname", ""),
        amap_adname=best.get("adname", ""),
        amap_type=best.get("type", ""),
        amap_id=best.get("id", ""),
    )
    notes = []
    if sub_poi:
        notes.append("sub_poi")
    if used_query != output["query"]:
        notes.append(f"variant:{used_query}")
    district = extract_district(output["address"])
    district_mismatch = bool(district and district not in (best.get("adname") or ""))
    if district_mismatch:
        notes.append("district_mismatch")
    output["note"] = "; ".join(notes)
    if not output["amap_lng"] or not output["amap_lat"]:
        output["status"] = "no_coord"
    elif sub_poi or district_mismatch:
        output["status"] = "review"
    elif (best_score >= 95 and margin >= 5) or (best_score >= 85 and margin >= 10):
        output["status"] = "auto"
    elif best_score >= 45:
        output["status"] = "review"
    else:
        output["status"] = "no_result"
        for field in OUTPUT_FIELDS[6:]:
            output[field] = ""
        output["note"] = "low_score"
    return output


def better_result(old: dict, new: dict) -> dict:
    """Return whichever candidate row is stronger: higher status rank, then score."""
    old_rank = STATUS_RANK.get(old.get("status", ""), 0)
    new_rank = STATUS_RANK.get(new.get("status", ""), 0)
    if new_rank != old_rank:
        return new if new_rank > old_rank else old
    try:
        old_score = float(old.get("score") or 0)
        new_score = float(new.get("score") or 0)
    except ValueError:
        return old
    return new if new_score > old_score else old


def write_csv(rows: list, path: Path) -> None:
    """Write result rows to a UTF-8 CSV that opens cleanly in Excel."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    """Run the Amap coordinate candidate pipeline."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", help="input CSV path")
    parser.add_argument("--retry-from", help="previous output CSV; retry its non-auto rows")
    parser.add_argument("--query-map", help="CSV with official_name,query override rows to retry")
    parser.add_argument("--output", default="docs/data/coord-candidates.csv", help="output CSV path")
    parser.add_argument("--limit", type=int, default=0, help="only process the first N rows")
    parser.add_argument("--sleep", type=float, default=1.0, help="minimum seconds between Amap requests")
    parser.add_argument("--city", default="杭州", help="Amap city filter")
    parser.add_argument("--types", default="110000|110100", help="Amap POI type codes; empty means all")
    args = parser.parse_args()
    if not args.input and not args.retry_from:
        parser.error("one of --input or --retry-from is required")

    key = load_key()
    previous = []
    replace_all = False
    if args.retry_from:
        with Path(args.retry_from).open(encoding="utf-8-sig", newline="") as handle:
            previous = list(csv.DictReader(handle))
        rows = [row for row in previous if row.get("status") != "auto"]
        if args.query_map:
            with Path(args.query_map).open(encoding="utf-8-sig", newline="") as handle:
                overrides = {item["official_name"]: item["query"] for item in csv.DictReader(handle)}
            rows = [row for row in rows if row.get("official_name", "") in overrides]
            for row in rows:
                row["query"] = overrides[row["official_name"]]
            replace_all = True
    else:
        with Path(args.input).open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    if args.limit:
        rows = rows[: args.limit]
    for row in rows:
        row["address"] = row.get("address") or row.get("地址") or ""

    retried = {}
    for index, row in enumerate(rows, 1):
        candidates = fetch_candidates(row, key, args.city, args.types, args.sleep)
        retried[row.get("official_name", "")] = pick_candidates(row, candidates)
        if index % 10 == 0 or index == len(rows):
            print(f"fetched {index}/{len(rows)}")

    if previous:
        results = [
            (retried[row.get("official_name", "")] if replace_all else better_result(row, retried[row.get("official_name", "")]))
            if row.get("official_name", "") in retried
            else row
            for row in previous
        ]
    else:
        results = [retried[row.get("official_name", "")] for row in rows]

    output_path = Path(args.output)
    write_csv(results, output_path)
    counts = Counter(item["status"] for item in results)
    duplicate_ids = [
        poi_id
        for poi_id, count in Counter(
            item["amap_id"] for item in results if item["amap_id"] and item["status"] != "no_result"
        ).items()
        if count > 1
    ]
    print(f"status: {dict(counts)}")
    print(f"duplicate amap_id groups: {len(duplicate_ids)} -> {duplicate_ids}")
    print(f"output: {output_path}")


if __name__ == "__main__":
    main()
