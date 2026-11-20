#!/usr/bin/env python3
"""Build place-table INSERT SQL from the reviewed coordinate table.

Reads docs/data/coord-reviewed.csv, assigns place_id/level/candidate_radius_m,
and writes docs/data/place-import.sql. Rows without coordinates are skipped.

Usage:
    python scripts/build_places.py
    python scripts/build_places.py --input <csv> --output <sql> --db <sqlite>
"""

import argparse
import csv
import hashlib
from pathlib import Path

DEFAULT_INPUT = "docs/data/coord-reviewed.csv"
DEFAULT_EXCLUSIONS = "docs/data/place-exclusions.csv"
DEFAULT_OUTPUT = "docs/data/place-import.sql"
GRADE_RADIUS = {"5A": 1500, "4A": 1000, "3A": 800, "2A": 500}
POINT_KEYWORDS = (
    "博物馆", "博物院", "美术馆", "纪念馆", "图书馆", "旧址", "故居", "古城墙", "窑址",
)


def load_rows(path: Path) -> list:
    """Return reviewed rows that carry both lng and lat."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [row for row in csv.DictReader(handle) if row["lng"] and row["lat"]]


def load_excluded(path: Path) -> set:
    """Return official names listed for exclusion, or an empty set when absent."""
    if not path.exists():
        return set()
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {row["official_name"] for row in csv.DictReader(handle)}


def assign_ids(rows: list) -> list:
    """Attach stable place_id values from amap_id, or a name hash when absent."""
    seen = {}
    for row in rows:
        base = place_base_id(row)
        seen[base] = seen.get(base, 0) + 1
        row["place_id"] = base if seen[base] == 1 else f"{base}-{seen[base]}"
    return rows


def place_base_id(row: dict) -> str:
    """Return hz-<amap_id>, or hz-h<sha256(name) prefix> when amap_id is missing."""
    amap_id = (row.get("amap_id") or "").strip().lower()
    if amap_id:
        return f"hz-{amap_id}"
    digest = hashlib.sha256(row["official_name"].encode("utf-8")).hexdigest()[:10]
    return f"hz-h{digest}"


def level_for(row: dict) -> str:
    """Return 'point' for single-building sites, otherwise 'site'."""
    name = row["official_name"]
    if any(keyword in name for keyword in POINT_KEYWORDS):
        return "point"
    return "site"


def radius_for(row: dict, level: str) -> int:
    """Return candidate radius in meters; point rows stay small."""
    if level == "point":
        return 400
    if "世界遗产" in row["grade"]:
        return 1500
    return GRADE_RADIUS.get(row["grade"], 800)


def sql_literal(value) -> str:
    """Quote a value for SQLite, escaping single quotes."""
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def build_sql(rows: list) -> str:
    """Render the full INSERT script for the place table."""
    lines = [
        "-- 由 scripts/build_places.py 从 coord-reviewed.csv 生成，勿手改",
        "PRAGMA foreign_keys = ON;",
        "BEGIN;",
    ]
    for row in rows:
        level = level_for(row)
        values = (
            row["place_id"], level, row["official_name"],
            float(row["lat"]), float(row["lng"]), radius_for(row, level),
        )
        lines.append(
            "INSERT OR REPLACE INTO place "
            "(place_id, level, name, lat, lon, candidate_radius_m) VALUES ("
            + ", ".join(sql_literal(value) for value in values) + ");"
        )
    lines.append("COMMIT;")
    return "\n".join(lines) + "\n"


def main() -> None:
    """Generate the SQL file and optionally load it into a SQLite database."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=DEFAULT_INPUT, help="reviewed CSV path")
    parser.add_argument("--exclusions", default=DEFAULT_EXCLUSIONS, help="excluded names CSV")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="output SQL path")
    parser.add_argument("--db", default="", help="optional SQLite path to apply the SQL")
    args = parser.parse_args()

    excluded = load_excluded(Path(args.exclusions))
    rows = [row for row in load_rows(Path(args.input))
            if row["official_name"] not in excluded]
    rows = assign_ids(rows)
    sql = build_sql(rows)
    output = Path(args.output)
    output.write_text(sql, encoding="utf-8")
    print(f"rows: {len(rows)} -> {output}; excluded: {len(excluded)}")

    if args.db:
        import sqlite3

        with sqlite3.connect(args.db) as connection:
            connection.executescript(sql)
            count = connection.execute("SELECT COUNT(*) FROM place").fetchone()[0]
        print(f"loaded into {args.db}, place rows: {count}")


if __name__ == "__main__":
    main()
