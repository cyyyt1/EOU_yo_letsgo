#!/usr/bin/env python3
"""Build the place_alias staging CSV from place names and Amap variants.

Applies prefix/suffix stripping, separator splitting, Amap-name filtering,
manual semantic overrides, and global uniqueness checks. Staging only; no
database writes.

Usage:
    python scripts/build_aliases.py
    python scripts/build_aliases.py --db docs/data/schema-dist.sqlite --out docs/data/place-alias-staging.csv
"""

import argparse
import csv
import difflib
import re
import sqlite3
import unicodedata
from collections import defaultdict
from pathlib import Path

DEFAULT_DB = "docs/data/schema-dist.sqlite"
DEFAULT_REVIEWED = "docs/data/coord-reviewed.csv"
DEFAULT_OVERRIDES = "docs/data/place-alias-overrides.csv"
DEFAULT_OUT = "docs/data/place-alias-staging.csv"
DISTRICTS = ("西湖区", "上城区", "拱墅区", "滨江区", "萧山区", "余杭区", "临平区",
             "钱塘区", "富阳区", "临安区", "桐庐县", "淳安县", "建德市",
             "临安", "淳安", "建德", "桐庐", "富阳", "萧山", "余杭", "临平")
PREFIXES = tuple(sorted(("浙江省", "杭州市", "浙江", "杭州") + DISTRICTS, key=len, reverse=True))
SUFFIXES = tuple(sorted(("国家森林公园", "风景旅游区", "旅游度假区", "风景名胜区",
                         "历史文化特色街区", "风景区", "旅游区", "度假区", "景区", "公园"),
                        key=len, reverse=True))
STOP = {
    "景区", "风景区", "旅游区", "公园", "乐园", "小镇", "博物馆", "美术馆", "纪念馆",
    "图书馆", "古城", "古街", "湿地", "运河", "浙江省", "杭州市", "浙江", "杭州",
    "杭州段", "杭州景区", "高德地理编码", "用户手填",
}
MARKERS = (
    "游客中心", "服务中心", "停车场", "码头", "会客厅", "设计中心", "文创馆",
    "咖啡馆", "民宿", "饭店", "酒店", "公交站", "地铁站", "放映点", "售票处",
    "入口", "出口", "水上乐园", "越野车", "暂停开放",
)
RULE_ORDER = {"S0": 0, "S3": 1, "S1": 2, "S2": 3, "S4": 4, "S5": 5, "S7": 6}
FIELDS = ["alias", "alias_norm", "place_id", "official_name",
          "source_rule", "confidence", "status", "note"]


def normalize_alias(alias: str) -> str:
    """Normalize an alias for uniqueness checks and lookup."""
    text = unicodedata.normalize("NFKC", alias).strip()
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"(?<=[\u4e00-\u9fff])\.(?=[\u4e00-\u9fff])", "·", text)
    return text.lower()


def strip_prefix(name: str, min_rest: int = 2):
    """Return the name without its longest administrative prefix, if any."""
    for prefix in PREFIXES:
        if name.startswith(prefix) and len(name) - len(prefix) >= min_rest:
            return name[len(prefix):]
    return None


def strip_suffix(name: str, min_rest: int = 2):
    """Return the name without its longest scenic suffix, if any."""
    for suffix in SUFFIXES:
        if name.endswith(suffix) and len(name) - len(suffix) >= min_rest:
            return name[:-len(suffix)]
    return None


def core_name(name: str) -> str:
    """Strip one prefix and one suffix, returning the shortest form."""
    reduced = strip_prefix(name) or name
    return strip_suffix(reduced) or reduced


def is_valid_alias(alias: str) -> bool:
    """Return True when an alias passes length, charset, and noise filters."""
    if not 2 <= len(alias) <= 20 or alias in STOP:
        return False
    if any(marker in alias for marker in MARKERS):
        return False
    if re.search(r"[·（）().,，、;；:：!！?？]", alias):
        return False
    return bool(re.search(r"[\u4e00-\u9fffA-Za-z]", alias))


def make_row(alias: str, place: tuple, rule: str, confidence: str) -> dict:
    """Build one staging row with proposed status."""
    return {
        "alias": alias.strip(),
        "alias_norm": normalize_alias(alias),
        "place_id": place[0],
        "official_name": place[1],
        "source_rule": rule,
        "confidence": confidence,
        "status": "proposed",
        "note": "",
    }


def generate_candidates(name: str, amap: str, place: tuple) -> list:
    """Generate alias candidates for one place in rule priority order."""
    rows, seen = [], set()

    def add(alias: str, rule: str, confidence: str) -> None:
        if not alias or not is_valid_alias(alias):
            return
        norm = normalize_alias(alias)
        if norm in seen or alias == name:
            return
        seen.add(norm)
        if confidence == "auto" and len(norm) == 2:
            confidence = "review"
        rows.append(make_row(alias, place, rule, confidence))

    combined = strip_suffix(strip_prefix(name, 3) or "", 2) if strip_prefix(name, 3) else None
    if combined:
        add(combined, "S3", "auto")
    prefix_rest = strip_prefix(name, 3)
    if prefix_rest:
        add(prefix_rest, "S1", "auto")
    suffix_rest = strip_suffix(name, 3)
    if suffix_rest:
        add(suffix_rest, "S2", "auto")
    for part in re.split(r"[·（）()]", name):
        part = part.strip()
        if len(part) < 3:
            continue
        add(core_name(part), "S4", "review")
        add(part, "S4", "review")
    if amap and is_valid_alias(amap) and "-" not in amap and "（" not in amap:
        ratio = difflib.SequenceMatcher(None, core_name(name), core_name(amap)).ratio()
        if ratio >= 0.75:
            add(amap, "S5", "review")
    return rows


def load_places(db_path: str) -> dict:
    """Return name -> (place_id, name) for all distribution places."""
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute("SELECT place_id, name FROM place ORDER BY place_id").fetchall()
    return {name: (place_id, name) for place_id, name in rows}


def load_amap_names(path: Path) -> dict:
    """Return official_name -> Amap name for rows that have coordinates."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {
            row["official_name"]: row.get("amap_name", "")
            for row in csv.DictReader(handle)
            if row["lng"] and row["lat"]
        }


def load_overrides(path: Path) -> list:
    """Return manual alias overrides, or an empty list when absent."""
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def apply_overrides(rows: list, overrides: list, places: dict) -> list:
    """Apply assign/reject overrides with priority over generated rows."""
    for item in overrides:
        norm = normalize_alias(item["alias"])
        matches = [row for row in rows if row["alias_norm"] == norm]
        if item["action"] == "reject":
            for row in matches:
                row["status"] = "rejected"
                row["note"] = item["note"]
            continue
        place_id = item["place_id"]
        if place_id not in {value[0] for value in places.values()}:
            raise SystemExit(f"override points to unknown place_id: {place_id}")
        place = next(value for value in places.values() if value[0] == place_id)
        rows = [row for row in rows if row["alias_norm"] != norm]
        manual = make_row(item["alias"], place, "S7", "manual")
        manual["note"] = item["note"]
        rows.append(manual)
    return rows


def mark_conflicts(rows: list) -> list:
    """Mark aliases that still map to multiple places or another canonical name."""
    active = [row for row in rows if row["status"] == "proposed"]
    owners = defaultdict(set)
    for row in active:
        owners[row["alias_norm"]].add(row["place_id"])
    canonical = {
        row["alias_norm"]: row["place_id"] for row in rows if row["source_rule"] == "S0"
    }
    for row in active:
        names = owners[row["alias_norm"]]
        if len(names) > 1:
            row["status"] = "conflict"
            row["note"] = "同一别名指向多个点位: " + ", ".join(sorted(names))
        elif row["alias_norm"] in canonical and canonical[row["alias_norm"]] != row["place_id"]:
            row["status"] = "conflict"
            row["note"] = "与另一地点官方名冲突"
    return rows


def write_csv(rows: list, path: Path) -> None:
    """Write staging rows sorted by place and rule priority."""
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(rows, key=lambda row: (row["place_id"], RULE_ORDER[row["source_rule"]],
                                            row["alias"]))
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(ordered)


def main() -> None:
    """Generate the alias staging CSV and print a summary."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DEFAULT_DB, help="distribution SQLite path")
    parser.add_argument("--reviewed", default=DEFAULT_REVIEWED, help="reviewed coordinate CSV")
    parser.add_argument("--overrides", default=DEFAULT_OVERRIDES, help="manual override CSV")
    parser.add_argument("--out", default=DEFAULT_OUT, help="staging output CSV")
    args = parser.parse_args()

    places = load_places(args.db)
    amap_names = load_amap_names(Path(args.reviewed))
    rows = []
    for name, place in places.items():
        rows.append(make_row(name, place, "S0", "auto"))
        rows.extend(generate_candidates(name, amap_names.get(name, ""), place))
    rows = apply_overrides(rows, load_overrides(Path(args.overrides)), places)
    rows = mark_conflicts(rows)
    write_csv(rows, Path(args.out))

    by_rule, by_status = defaultdict(int), defaultdict(int)
    for row in rows:
        by_rule[row["source_rule"]] += 1
        by_status[row["status"]] += 1
    covered = {row["place_id"] for row in rows if row["status"] == "proposed"}
    print(f"rows: {len(rows)} -> {args.out}")
    print(f"by rule: {dict(sorted(by_rule.items()))}")
    print(f"by status: {dict(by_status)}")
    print(f"places proposed: {len(covered)}/{len(places)}")


if __name__ == "__main__":
    main()
