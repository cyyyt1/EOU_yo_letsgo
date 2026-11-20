#!/usr/bin/env python3
"""Extract draft fragments from the scenic xlsx into a staging CSV.

Reads 景点总表, matches rows to place.name in the distribution SQLite, and
emits draft fragments with license/verification flags. Drafts are reference
material only: they must be rewritten and reviewed before import.

Usage:
    python scripts/build_fragments.py
    python scripts/build_fragments.py --xlsx datasets/raw/scenic.xlsx --db docs/data/schema-dist.sqlite
"""

import argparse
import csv
import json
import re
import sqlite3
from pathlib import Path

import openpyxl

DEFAULT_XLSX = "datasets/raw/scenic.xlsx"
DEFAULT_DB = "docs/data/schema-dist.sqlite"
DEFAULT_OUT = "docs/data/fragment-staging.csv"
DEFAULT_COVERAGE = "docs/data/fragment-coverage.csv"
REVIEWED_CSV = "docs/data/coord-reviewed.csv"
EXCLUSIONS_CSV = "docs/data/place-exclusions.csv"
HEADING_RE = re.compile(r"^##\s*(.+?)\s*$", re.M)
SENTENCE_RE = re.compile(r"(?<=[。！？])")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
TEXT_TYPES = ("fact", "highlight", "spatial", "trivia", "legend", "poetry")
FIELDS = [
    "fragment_id", "place_id", "official_name", "title", "fragment_type",
    "content", "content_short", "key_points", "keywords",
    "valid_to", "verified_at", "source_title", "source_url", "attribution",
    "allow_cloud_llm", "source_field", "review_status", "risk_note",
]


def clean_text(value) -> str:
    """Normalize whitespace and strip scraped UI artifacts from an xlsx cell."""
    text = str(value or "").replace("\r\n", "\n").replace("\u3000", " ")
    text = text.replace("查看更多", "").replace("合并图册", "").replace("†", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"(?<=[\u4e00-\u9fff])[ \t]+(?=[\u4e00-\u9fff])", "", text)
    text = re.sub(r"[ \t]+(?=[，。；：、！？）】」》])", "", text)
    return text.strip()


def is_wrong_entity(row: dict) -> bool:
    """Return True when the row describes a book instead of a scenic place."""
    text = clean_text(row.get("summary")) + clean_text(row.get("intro"))
    return "图书" in text and "出版" in text


def split_sentences(text: str) -> list:
    """Split cleaned text into non-empty sentences."""
    return [part.strip() for part in SENTENCE_RE.split(text) if len(part.strip()) >= 8]


def excerpt(text: str, limit: int) -> str:
    """Return whole sentences until the character limit is reached."""
    picked, size = [], 0
    for sentence in split_sentences(text):
        if picked and size + len(sentence) > limit:
            break
        picked.append(sentence)
        size += len(sentence)
        if size >= limit:
            break
    result = "".join(picked) or text.strip()
    return result[:limit]


def short_text(text: str, limit: int = 80) -> str:
    """Return the first two sentences, capped at the given length."""
    sentences = split_sentences(text)
    result = "".join(sentences[:2]) if sentences else text.strip()
    return result[:limit]


def parse_sections(body: str) -> dict:
    """Split a Baike body into an ordered heading -> text mapping."""
    matches = list(HEADING_RE.finditer(body))
    sections = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        heading = match.group(1).strip()
        sections[heading] = clean_text(body[match.end():end])
    return sections


def find_section(sections: dict, names: tuple):
    """Return (heading, text) for the first heading containing a name."""
    for heading, text in sections.items():
        if any(name in heading for name in names) and len(text) >= 30:
            return heading, text
    return None


def name_tokens(value) -> list:
    """Split a list-like cell into short Chinese item names."""
    result = []
    for part in re.split(r"[、，,；;\n]", clean_text(value)):
        part = part.strip("。；;，, ")
        part = re.sub(r"^\d+[\s、.．]*", "", part).strip()
        if 2 <= len(part) <= 16 and CJK_RE.search(part) and part not in result:
            result.append(part)
    return result


def keywords_for(name: str, grade: str, lemma_title: str) -> str:
    """Build a small JSON keyword list for a fragment."""
    items = [name, "杭州"]
    if grade:
        items.append(f"{grade}景区" if grade.endswith("A") else grade)
    if lemma_title and lemma_title not in name and name not in lemma_title:
        items.append(lemma_title)
    return json.dumps(list(dict.fromkeys(items))[:8], ensure_ascii=False)


def source_meta(row: dict) -> tuple:
    """Return (source_title, source_url, attribution) for a Baike row."""
    title = str(row.get("lemma_title") or row.get("official_name") or "").strip()
    lemma_id = str(row.get("lemma_id") or "").strip()
    url = str(row.get("url") or "").strip()
    return f"百度百科 · {title}", url, f"百度百科 lemma {lemma_id}"


def make_fragment(pid: str, row: dict, meta: tuple, ftype: str, title: str,
                  content: str, source_field: str, status: str, risk: str,
                  key_points: list = None) -> dict:
    """Assemble one staging row with shared defaults."""
    fragment_id = f"f-{pid}-{ftype}-01"
    content = content.strip().lstrip("”\"’ \n")
    return {
        "fragment_id": fragment_id,
        "place_id": pid,
        "official_name": clean_text(row.get("official_name")),
        "title": title,
        "fragment_type": ftype,
        "content": content,
        "content_short": short_text(content),
        "key_points": json.dumps(key_points or [], ensure_ascii=False),
        "keywords": keywords_for(clean_text(row.get("official_name")), str(row.get("grade") or ""),
                                 str(row.get("lemma_title") or "")),
        "valid_to": "",
        "verified_at": "",
        "source_title": meta[0],
        "source_url": meta[1],
        "attribution": meta[2],
        "allow_cloud_llm": 0,
        "source_field": source_field,
        "review_status": status,
        "risk_note": risk,
    }


def fact_fragment(row: dict, pid: str, meta: tuple, sections: dict):
    """Draft a fact fragment from the longer of intro and summary."""
    intro = clean_text(row.get("intro"))
    summary = clean_text(row.get("summary"))
    source_text = intro if len(intro) >= len(summary) else summary
    content = excerpt(source_text, 600)
    if len(content) < 40:
        return None
    points = name_tokens(row.get("famous_for"))[:5]
    return make_fragment(pid, row, meta, "fact", "概览", content,
                         "intro" if source_text == intro else "summary",
                         "draft", "百科原文待改写；来源为百科正文", points)


def highlight_fragment(row: dict, pid: str, meta: tuple, sections: dict):
    """Draft a highlight fragment from attractions or famous_for."""
    content = excerpt(clean_text(row.get("attractions")), 400)
    points = name_tokens(row.get("famous_for"))
    if len(content) < 40:
        content = "代表性看点：" + "、".join(points[:8]) if points else ""
    if len(content) < 20:
        return None
    if len(points) < 3:
        points = name_tokens(row.get("attractions"))[:5]
    return make_fragment(pid, row, meta, "highlight", "主要看点", content,
                         "attractions", "draft", "百科原文待改写；需压缩为看点列表", points)


def section_fragment(row: dict, pid: str, meta: tuple, sections: dict, ftype: str,
                     names: tuple, fallback_title: str, risk: str):
    """Draft a fragment from a named body section."""
    found = find_section(sections, names)
    if not found:
        return None
    heading, text = found
    content = excerpt(text, 400)
    if len(content) < 40:
        return None
    return make_fragment(pid, row, meta, ftype, heading or fallback_title, content,
                         f"body:{heading}", "draft", risk)


def sentence_fragment(row: dict, pid: str, meta: tuple, sections: dict, ftype: str,
                      pattern: str, title: str, risk: str):
    """Draft a fragment from non-overlapping body sentences matching a pattern."""
    wanted = re.compile(pattern)
    picked = []
    for text in sections.values():
        for sentence in split_sentences(text):
            if not wanted.search(sentence):
                continue
            if any(sentence in other or other in sentence for other in picked):
                continue
            picked.append(sentence)
            if len(picked) == 2:
                break
        if len(picked) == 2:
            break
    if not picked:
        return None
    return make_fragment(pid, row, meta, ftype, title, "".join(picked),
                         f"body:{pattern}", "needs_verification", risk, [])


POEM_RE = re.compile(r"[“\"]([^”\"]{10,80})[”\"]")
POETRY_CONTEXT = re.compile(r"诗句|诗云|诗曰|题诗|赋诗|吟诗|七绝|绝句|律诗|五律|诗作|诗词")


def sentence_bounds(text: str, start: int, end: int) -> tuple:
    """Return the start and end offsets of the sentence range covering a match."""
    begin, finish = 0, len(text)
    for mark in "。！？":
        begin = max(begin, text.rfind(mark, 0, start) + 1)
        position = text.find(mark, end)
        if position != -1:
            finish = min(finish, position + 1)
    return begin, finish


def poetry_fragment(row: dict, pid: str, meta: tuple, sections: dict):
    """Draft a poetry fragment from a quoted verse with poetry context."""
    for heading, text in sections.items():
        for match in POEM_RE.finditer(text):
            window = text[max(0, match.start() - 80):match.end() + 20]
            if not POETRY_CONTEXT.search(window):
                continue
            begin, end = sentence_bounds(text, match.start(), match.end())
            content = text[begin:end].strip().lstrip("”\"’ \n")[:300]
            if len(content) < 15:
                continue
            return make_fragment(pid, row, meta, "poetry", "诗文", content,
                                 f"body:{heading}", "needs_verification",
                                 "诗文引用需核对作者与出处", [])
    return None


def practical_fragment(row: dict, pid: str, meta: tuple, sections: dict):
    """Draft a practical fragment from opening hours, tickets, and tips."""
    parts = []
    for label, key in (("开放时间", "open_time"), ("门票", "ticket"), ("游览提示", "tour_info")):
        value = clean_text(row.get(key))
        if value:
            parts.append(f"{label}：{value[:300]}")
    if not parts:
        return None
    content = "\n".join(parts)
    return make_fragment(pid, row, meta, "practical", "实用信息", content,
                         "open_time/ticket/tour_info", "needs_verification",
                         "时效信息未核验；核验前不得进入发行包", [])


def build_place_fragments(row: dict, place: tuple) -> list:
    """Build all draft fragments for one matched place."""
    pid, _grade = place
    sections = parse_sections(clean_text(row.get("body")))
    meta = source_meta(row)
    drafts = [
        fact_fragment(row, pid, meta, sections),
        highlight_fragment(row, pid, meta, sections),
        section_fragment(row, pid, meta, sections, "spatial",
                         ("方位布局", "景区布局", "地理环境", "位置境域"),
                         "方位", "百科原文待改写；只保留方位与到达关系"),
        section_fragment(row, pid, meta, sections, "trivia",
                         ("命名", "相关文化", "文化"), "文化",
                         "百科原文待改写；需与概览查重"),
        sentence_fragment(row, pid, meta, sections, "legend",
                          r"传说|相传|典故", "传说与典故",
                          "传说内容需核实，不得作为史实"),
        poetry_fragment(row, pid, meta, sections),
        practical_fragment(row, pid, meta, sections),
    ]
    results, seen = [], set()
    for draft in drafts:
        if draft and draft["content"] not in seen:
            results.append(draft)
            seen.add(draft["content"])
    return results


def load_places(db_path: str) -> dict:
    """Return name -> (place_id, level) for all distribution places."""
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute("SELECT name, place_id, level FROM place").fetchall()
    return {name: (place_id, level) for name, place_id, level in rows}


def load_excluded(path: str) -> set:
    """Return official names removed from the distribution package."""
    if not Path(path).exists():
        return set()
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return {row["official_name"] for row in csv.DictReader(handle)}


def load_xlsx(path: str) -> list:
    """Return 景点总表 rows as dictionaries keyed by header."""
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheet = workbook["景点总表"]
    rows = list(sheet.iter_rows(values_only=True))
    header = rows[0]
    return [dict(zip(header, row)) for row in rows[1:]]


def write_csv(rows: list, path: Path, fields: list) -> None:
    """Write rows to a UTF-8 CSV with the given field order."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def build_coverage(places: dict, source_names: set, counts: dict,
                   wrong_names: set, fact_names: set, excluded_names: set) -> list:
    """Build a 121-row coverage report from the reviewed coordinate table."""
    rows = []
    with Path(REVIEWED_CSV).open(encoding="utf-8-sig", newline="") as handle:
        for item in csv.DictReader(handle):
            name = item["official_name"]
            in_place = name in places
            if name in excluded_names:
                status = "excluded_deleted"
            elif item["decision"] == "clear" or not in_place:
                status = "excluded_no_coord"
            elif name in wrong_names:
                status = "source_mismatch"
            elif name not in source_names:
                status = "no_content"
            else:
                status = "content_found"
            rows.append({
                "official_name": name,
                "decision": item["decision"],
                "in_place": int(in_place),
                "in_xlsx": int(name in source_names),
                "fragment_count": counts.get(name, 0),
                "has_fact": int(name in fact_names),
                "status": status,
            })
    return rows


def main() -> None:
    """Run the fragment extraction and write staging plus coverage CSVs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xlsx", default=DEFAULT_XLSX, help="scenic xlsx path")
    parser.add_argument("--db", default=DEFAULT_DB, help="distribution SQLite path")
    parser.add_argument("--out", default=DEFAULT_OUT, help="staging CSV path")
    parser.add_argument("--coverage", default=DEFAULT_COVERAGE, help="coverage CSV path")
    parser.add_argument("--exclusions", default=EXCLUSIONS_CSV, help="excluded names CSV")
    args = parser.parse_args()

    places = load_places(args.db)
    excluded_names = load_excluded(args.exclusions)
    source_rows = load_xlsx(args.xlsx)
    source_names = {clean_text(row.get("official_name")) for row in source_rows}
    staging, counts, wrong_names = [], {}, set()
    for row in source_rows:
        name = clean_text(row.get("official_name"))
        if name not in places:
            continue
        if is_wrong_entity(row):
            wrong_names.add(name)
            continue
        fragments = build_place_fragments(row, places[name])
        staging.extend(fragments)
        counts[name] = len(fragments)

    write_csv(staging, Path(args.out), FIELDS)
    fact_names = {item["official_name"] for item in staging if item["fragment_type"] == "fact"}
    coverage = build_coverage(places, source_names, counts, wrong_names, fact_names,
                              excluded_names)
    write_csv(coverage, Path(args.coverage),
              ["official_name", "decision", "in_place", "in_xlsx",
               "fragment_count", "has_fact", "status"])
    types = {}
    for item in staging:
        types[item["fragment_type"]] = types.get(item["fragment_type"], 0) + 1
    print(f"places matched: {len(counts)}")
    print(f"fragments: {len(staging)} -> {args.out}")
    print(f"by type: {types}")
    print(f"coverage: {args.coverage}")


if __name__ == "__main__":
    main()
