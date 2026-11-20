#!/usr/bin/env python3
"""Build place_alias import SQL from the staging CSV and optionally load it.

Keeps only status=proposed rows, checks uniqueness, confidence values, and
canonical coverage, then writes place-alias-import.sql that rebuilds the table
including confidence (schema v2). No alias is overwritten: plain INSERT fails on
ux_place_alias conflicts.

Usage:
    python scripts/build_alias_sql.py
    python scripts/build_alias_sql.py --db docs/data/schema-dist.sqlite
"""

import argparse
import csv
import re
import sqlite3
from pathlib import Path

DEFAULT_STAGING = "docs/data/place-alias-staging.csv"
DEFAULT_OUT = "docs/data/place-alias-import.sql"
DEFAULT_DB = "docs/data/schema-dist.sqlite"
RULE_ORDER = {"S0": 0, "S1": 1, "S2": 2, "S3": 3, "S4": 4, "S5": 5, "S7": 6}
CONFIDENCES = {"auto", "review", "manual"}
NAME_CHARS = re.compile(r"[\u4e00-\u9fffA-Za-z]")


def load_staging(path: Path) -> list:
    """Return staging rows with status proposed or rejected."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_places(db_path: str) -> dict:
    """Return place_id -> name for all distribution places."""
    with sqlite3.connect(db_path) as connection:
        return {
            row[0]: row[1]
            for row in connection.execute("SELECT place_id, name FROM place ORDER BY place_id")
        }


def validate_rows(rows: list, places: dict) -> list:
    """Return constraint violations for the proposed alias rows."""
    errors, aliases = [], {}
    for row in rows:
        alias, place_id = row["alias"].strip(), row["place_id"]
        if place_id not in places:
            errors.append(f"unknown place_id: {place_id}")
            continue
        if not 2 <= len(alias) <= 20 or not NAME_CHARS.search(alias):
            errors.append(f"bad alias: {alias!r}")
        if row["confidence"] not in CONFIDENCES:
            errors.append(f"bad confidence: {row['confidence']} ({alias})")
        if alias in aliases and aliases[alias] != place_id:
            errors.append(f"alias on multiple places: {alias} -> {aliases[alias]}, {place_id}")
        aliases.setdefault(alias, place_id)
    for place_id, name in places.items():
        if aliases.get(name) != place_id:
            errors.append(f"missing canonical alias: {name} ({place_id})")
    for alias, place_id in aliases.items():
        owner = places.get(alias)
        if owner and owner != place_id:
            errors.append(f"alias equals other place name: {alias} ({place_id} != {owner})")
    return errors


def sql_literal(value: str) -> str:
    """Quote one text value for SQLite, escaping single quotes."""
    return "'" + str(value).replace("'", "''") + "'"


def build_sql(rows: list) -> str:
    """Render the rebuild script with a status summary header."""
    ordered = sorted(
        rows,
        key=lambda r: (r["place_id"], RULE_ORDER.get(r["source_rule"], 9), r["alias"]),
    )
    review = sum(1 for r in ordered if r["confidence"] == "review")
    manual = sum(1 for r in ordered if r["confidence"] == "manual")
    lines = [
        "-- 由 scripts/build_alias_sql.py 从 place-alias-staging.csv 生成，勿手改",
        f"-- 行数: {len(ordered)}; 覆盖点位: {len({r['place_id'] for r in ordered})}",
        f"-- 置信度: review {review} / manual {manual}（review 行待人工确认后方可分发包）",
        "-- 整表重建：先清空再插入；普通 INSERT，唯一索引冲突即回滚",
        "PRAGMA foreign_keys = ON;",
        "BEGIN;",
        "DELETE FROM place_alias;",
    ]
    for row in ordered:
        place_id = sql_literal(row["place_id"])
        alias = sql_literal(row["alias"])
        confidence = sql_literal(row["confidence"])
        rule = row["source_rule"]
        lines.append(
            "INSERT INTO place_alias (place_id, alias, confidence) "
            f"VALUES ({place_id}, {alias}, {confidence}); -- {rule}"
        )
    lines.append("COMMIT;")
    return "\n".join(lines) + "\n"


def report(rows: list, db_path: str, sql_path: Path) -> None:
    """Print rule counts and database verification results."""
    rules = {}
    for row in rows:
        rules[row["source_rule"]] = rules.get(row["source_rule"], 0) + 1
    print(f"rows: {len(rows)} -> {sql_path}")
    print(f"by rule: {rules}")
    with sqlite3.connect(db_path) as connection:
        total = connection.execute("SELECT COUNT(*) FROM place_alias").fetchone()[0]
        places = connection.execute("SELECT COUNT(DISTINCT place_id) FROM place_alias").fetchone()[0]
        confidence = dict(connection.execute(
            "SELECT confidence, COUNT(*) FROM place_alias GROUP BY confidence"))
        dup = connection.execute(
            "SELECT alias FROM place_alias GROUP BY alias HAVING COUNT(*) > 1"
        ).fetchall()
        missing = connection.execute(
            "SELECT COUNT(*) FROM place p WHERE NOT EXISTS ("
            "SELECT 1 FROM place_alias a WHERE a.place_id = p.place_id AND a.alias = p.name)"
        ).fetchone()[0]
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
    print(f"place_alias rows: {total}; places: {places}")
    print(f"confidence in db: {confidence}")
    print(f"duplicate alias: {len(dup)}; places missing canonical: {missing}")
    print(f"foreign_key_check: {len(violations)}")


def main() -> None:
    """Validate staging rows, write SQL, and optionally apply it."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staging", default=DEFAULT_STAGING, help="staging CSV path")
    parser.add_argument("--out", default=DEFAULT_OUT, help="output SQL path")
    parser.add_argument("--db", default="", help="optional SQLite path to apply the SQL")
    args = parser.parse_args()

    db_path = args.db or DEFAULT_DB
    staging = load_staging(Path(args.staging))
    rows = [row for row in staging if row["status"] == "proposed"]
    places = load_places(db_path)
    errors = validate_rows(rows, places)
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
    print(f"rejected in staging: {sum(1 for r in staging if r['status'] == 'rejected')}")


if __name__ == "__main__":
    main()
