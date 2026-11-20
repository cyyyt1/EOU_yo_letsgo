#!/usr/bin/env python3
"""Build fragment import SQL from the staging CSV and optionally load it.

Validates type/JSON/foreign-key constraints, writes fragment-import.sql, and
can apply it to the distribution SQLite. Staging drafts are imported as-is;
publication still requires rewrite and practical verification.

Usage:
    python scripts/build_fragment_sql.py
    python scripts/build_fragment_sql.py --db docs/data/schema-dist.sqlite
"""

import argparse
import csv
import json
import sqlite3
from pathlib import Path

DEFAULT_STAGING = "docs/data/fragment-staging.csv"
DEFAULT_OUT = "docs/data/fragment-import.sql"
DEFAULT_DB = "docs/data/schema-dist.sqlite"
FRAGMENT_TYPES = {"fact", "legend", "poetry", "highlight", "trivia", "practical", "spatial"}
FIELDS = [
    "fragment_id", "place_id", "title", "fragment_type", "content",
    "content_short", "key_points", "keywords", "valid_to", "verified_at",
    "source_title", "source_url", "attribution", "allow_cloud_llm",
]


def load_staging(path: Path) -> list:
    """Return staging rows in file order."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_place_ids(db_path: str) -> set:
    """Return the set of place_id values present in the database."""
    with sqlite3.connect(db_path) as connection:
        return {row[0] for row in connection.execute("SELECT place_id FROM place")}


def validate_row(row: dict, place_ids: set, seen_ids: set) -> list:
    """Return a list of constraint violations for one staging row."""
    errors = []
    fragment_id = row.get("fragment_id", "")
    if not fragment_id or fragment_id in seen_ids:
        errors.append(f"fragment_id missing or duplicated: {fragment_id}")
    if row.get("place_id") not in place_ids:
        errors.append(f"unknown place_id: {row.get('place_id')}")
    if row.get("fragment_type") not in FRAGMENT_TYPES:
        errors.append(f"bad fragment_type: {row.get('fragment_type')}")
    if not (row.get("content") or "").strip():
        errors.append("empty content")
    for field in ("key_points", "keywords"):
        try:
            if not isinstance(json.loads(row.get(field) or "[]"), list):
                errors.append(f"{field} is not a JSON array")
        except json.JSONDecodeError:
            errors.append(f"{field} is not valid JSON")
    if row.get("fragment_type") != "practical" and (row.get("valid_to") or row.get("verified_at")):
        errors.append("validity fields only allowed on practical")
    if row.get("allow_cloud_llm") not in ("0", "1"):
        errors.append("allow_cloud_llm must be 0 or 1")
    return errors


def sql_literal(value) -> str:
    """Quote one value for SQLite, escaping single quotes."""
    if value is None or value == "":
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def build_sql(rows: list) -> str:
    """Render the INSERT script with a status summary header."""
    status_counts = {}
    for row in rows:
        status_counts[row["review_status"]] = status_counts.get(row["review_status"], 0) + 1
    lines = [
        "-- 由 scripts/build_fragment_sql.py 从 fragment-staging.csv 生成，勿手改",
        f"-- 行数: {len(rows)}; 审核状态: {status_counts}",
        "-- 草稿内容含百科原文，仅限本地库使用；发布前必须改写并核验 practical",
        "PRAGMA foreign_keys = ON;",
        "BEGIN;",
    ]
    for row in rows:
        values = ", ".join(
            str(int(row[field])) if field == "allow_cloud_llm" else sql_literal(row[field])
            for field in FIELDS
        )
        columns = ", ".join(FIELDS)
        lines.append(f"INSERT OR REPLACE INTO fragment ({columns}) VALUES ({values});")
    lines.append("COMMIT;")
    return "\n".join(lines) + "\n"


def report(rows: list, db_path: str, sql_path: Path) -> None:
    """Print import status counts and database verification results."""
    types, statuses = {}, {}
    for row in rows:
        types[row["fragment_type"]] = types.get(row["fragment_type"], 0) + 1
        statuses[row["review_status"]] = statuses.get(row["review_status"], 0) + 1
    print(f"rows: {len(rows)} -> {sql_path}")
    print(f"types: {types}")
    print(f"review_status: {statuses}")
    with sqlite3.connect(db_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM fragment").fetchone()[0]
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
    print(f"fragment rows in db: {count}; foreign_key_check: {len(violations)}")


def main() -> None:
    """Validate staging rows, write SQL, and optionally apply it."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staging", default=DEFAULT_STAGING, help="staging CSV path")
    parser.add_argument("--out", default=DEFAULT_OUT, help="output SQL path")
    parser.add_argument("--db", default="", help="optional SQLite path to apply the SQL")
    args = parser.parse_args()

    rows = load_staging(Path(args.staging))
    db_path = args.db or DEFAULT_DB
    place_ids = load_place_ids(db_path)
    errors, seen_ids = [], set()
    for row in rows:
        errors.extend(validate_row(row, place_ids, seen_ids))
        seen_ids.add(row.get("fragment_id", ""))
    if errors:
        print(f"validation failed: {len(errors)} issues")
        for item in errors[:10]:
            print(f"  - {item}")
        raise SystemExit(1)

    sql = build_sql(rows)
    sql_path = Path(args.out)
    sql_path.parent.mkdir(parents=True, exist_ok=True)
    sql_path.write_text(sql, encoding="utf-8")
    if args.db:
        with sqlite3.connect(args.db) as connection:
            connection.executescript(sql)
            connection.commit()
    report(rows, db_path, sql_path)


if __name__ == "__main__":
    main()
