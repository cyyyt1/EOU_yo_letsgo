#!/usr/bin/env python3
"""Build the publishable fragment import SQL from approved rewrites.

Only rows with status=approved enter the distribution database. The output
replaces the whole fragment table, so unpublished Baike drafts and rejected
rows never reach the package. Keywords are carried over from the draft
staging. Approved rows with a citable non-excluded source keep that source;
rows whose draft came from excluded sources are marked as team-original.

Usage:
    python scripts/build_rewrite_sql.py
    python scripts/build_rewrite_sql.py --apply
"""

import argparse
import csv
import json
import sqlite3
from pathlib import Path

DEFAULT_REWRITE = "docs/data/fragment-rewrite.csv"
DEFAULT_STAGING = "docs/data/fragment-staging.csv"
DEFAULT_OUT = "docs/data/fragment-import.sql"
DEFAULT_DB = "docs/data/schema-dist.sqlite"
CONTENT_LIMITS = {"fact": (200, 300), "highlight": (80, 300),
                  "trivia": (120, 300), "spatial": (120, 300),
                  "legend": (120, 300)}
SOURCE_TITLE = "团队原创改写"
ATTRIBUTION = "原创内容"
EXCLUDED_SOURCE_PREFIXES = ("百度百科", "马蜂窝", "携程", "大众点评", "知乎", "小红书")
FIELDS = [
    "fragment_id", "place_id", "title", "fragment_type", "content",
    "content_short", "key_points", "keywords", "valid_to", "verified_at",
    "source_title", "source_url", "attribution", "allow_cloud_llm",
]


def load_csv(path: Path) -> list:
    """Return CSV rows decoded as UTF-8 with BOM tolerated."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def validate_row(row: dict, place_ids: set, staging_ids: set, seen: set) -> list:
    """Return constraint problems for one approved rewrite row."""
    problems = []
    fragment_id = row.get("fragment_id", "")
    if not fragment_id or fragment_id in seen:
        problems.append(f"fragment_id missing or duplicated: {fragment_id}")
    if fragment_id not in staging_ids:
        problems.append(f"fragment_id not in staging: {fragment_id}")
    if row.get("place_id") not in place_ids:
        problems.append(f"unknown place_id: {row.get('place_id')}")
    limits = CONTENT_LIMITS.get(row.get("fragment_type"))
    if limits is None:
        problems.append(f"unsupported fragment_type: {row.get('fragment_type')}")
        return problems
    content = (row.get("rewrite_content") or "").strip()
    short = (row.get("rewrite_content_short") or "").strip()
    if not limits[0] <= len(content) <= limits[1]:
        problems.append(f"content length {len(content)} not in {limits[0]}-{limits[1]}")
    if not short or len(short) > 80:
        problems.append(f"content_short length {len(short)} not in 1-80")
    try:
        points = json.loads(row.get("rewrite_key_points") or "[]")
    except json.JSONDecodeError:
        points = None
    if (not isinstance(points, list) or not 3 <= len(points) <= 5
            or any(not isinstance(p, str) or not p or len(p) > 20 for p in points)):
        problems.append("rewrite_key_points must be 3-5 strings of at most 20 chars")
    return problems


def sql_literal(value) -> str:
    """Quote one value for SQLite, escaping single quotes."""
    if value is None or value == "":
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def build_row(row: dict, keywords_by_id: dict) -> dict:
    """Map an approved rewrite row onto distribution fragment columns."""
    source_title = (row.get("source_title") or "").strip()
    if not source_title or source_title.startswith(EXCLUDED_SOURCE_PREFIXES):
        source_title, source_url, attribution = SOURCE_TITLE, "", ATTRIBUTION
    else:
        source_url = (row.get("source_url") or "").strip()
        attribution = (row.get("attribution") or "").strip() or source_title
    return {
        "fragment_id": row["fragment_id"],
        "place_id": row["place_id"],
        "title": row["title"],
        "fragment_type": row["fragment_type"],
        "content": row["rewrite_content"].strip(),
        "content_short": row["rewrite_content_short"].strip(),
        "key_points": row["rewrite_key_points"],
        "keywords": keywords_by_id[row["fragment_id"]],
        "valid_to": "",
        "verified_at": "",
        "source_title": source_title,
        "source_url": source_url,
        "attribution": attribution,
        "allow_cloud_llm": 0,
    }


def build_sql(rows: list) -> str:
    """Render the replace-all INSERT script for the fragment table."""
    lines = [
        "-- 由 scripts/build_rewrite_sql.py 从 fragment-rewrite.csv 的 approved 行生成，勿手改",
        f"-- 行数: {len(rows)}; 类型: fact/highlight/trivia/spatial/legend; 来源: 原创改写（含官方来源）",
        "PRAGMA foreign_keys = ON;",
        "BEGIN;",
        "DELETE FROM fragment;",
    ]
    columns = ", ".join(FIELDS)
    for row in rows:
        values = ", ".join(
            str(int(row[field])) if field == "allow_cloud_llm" else sql_literal(row[field])
            for field in FIELDS
        )
        lines.append(f"INSERT INTO fragment ({columns}) VALUES ({values});")
    lines.append("COMMIT;")
    return "\n".join(lines) + "\n"


def main() -> None:
    """Validate approved rewrites, write the SQL, and optionally apply it."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rewrite", default=DEFAULT_REWRITE, help="rewrite table CSV")
    parser.add_argument("--staging", default=DEFAULT_STAGING, help="draft staging CSV")
    parser.add_argument("--out", default=DEFAULT_OUT, help="output SQL path")
    parser.add_argument("--db", default=DEFAULT_DB, help="distribution SQLite path")
    parser.add_argument("--apply", action="store_true", help="execute the SQL on --db")
    args = parser.parse_args()

    approved = [row for row in load_csv(Path(args.rewrite))
                if row["status"] == "approved"]
    if not approved:
        raise SystemExit("no approved rows; refusing to replace the fragment table")
    staging = {row["fragment_id"]: row for row in load_csv(Path(args.staging))}
    with sqlite3.connect(args.db) as connection:
        place_ids = {row[0] for row in connection.execute("SELECT place_id FROM place")}

    problems, seen, staging_ids = [], set(), set(staging)
    for row in approved:
        for problem in validate_row(row, place_ids, staging_ids, seen):
            problems.append(f"{row['fragment_id']}: {problem}")
        seen.add(row["fragment_id"])
    if problems:
        raise SystemExit("approved rows rejected:\n" + "\n".join(problems))

    keywords_by_id = {fid: item["keywords"] for fid, item in staging.items()}
    rows = [build_row(row, keywords_by_id) for row in approved]
    sql = build_sql(rows)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(sql, encoding="utf-8")

    if args.apply:
        with sqlite3.connect(args.db) as connection:
            connection.executescript(sql)
            connection.commit()

    types = {}
    for row in rows:
        types[row["fragment_type"]] = types.get(row["fragment_type"], 0) + 1
    print(f"rows: {len(rows)} -> {out}")
    print(f"types: {types}")
    print(f"places: {len({row['place_id'] for row in rows})}")
    if args.apply:
        with sqlite3.connect(args.db) as connection:
            count = connection.execute("SELECT COUNT(*) FROM fragment").fetchone()[0]
            violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        print(f"fragment rows in db: {count}; foreign_key_check: {len(violations)}")


if __name__ == "__main__":
    main()
