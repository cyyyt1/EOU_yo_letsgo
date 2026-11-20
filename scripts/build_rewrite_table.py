#!/usr/bin/env python3
"""Build the in-scope rewrite table from fragment drafts.

Only fact and highlight fragments are copied (their draft_* columns are
references); other types stay in the curation DB for later rounds. Rewrite
columns stay empty and status starts as draft until a reviewer marks it
approved. The script refuses to overwrite a table that already contains
rewrite work unless --force is passed.

Usage:
    python scripts/build_rewrite_table.py
"""

import argparse
import csv
import sqlite3
from pathlib import Path

DEFAULT_DB = "docs/data/schema-dist.sqlite"
DEFAULT_OUT = "docs/data/fragment-rewrite.csv"
IN_SCOPE = ("fact", "highlight")
TYPE_ORDER = {"fact": 0, "highlight": 1}
FIELDS = [
    "fragment_id", "place_id", "official_name", "title", "fragment_type",
    "draft_source", "draft_content", "draft_key_points",
    "rewrite_content", "rewrite_content_short", "rewrite_key_points",
    "source_title", "source_url", "attribution", "valid_to", "verified_at",
    "allow_cloud_llm", "status", "review_note",
]


def load_rows(db_path: str) -> list:
    """Return fact/highlight drafts with empty rewrite columns."""
    with sqlite3.connect(db_path) as connection:
        places = dict(connection.execute("SELECT place_id, name FROM place"))
        drafts = connection.execute(
            "SELECT fragment_id, place_id, title, fragment_type, source_title, "
            "source_url, attribution, content, key_points FROM fragment").fetchall()
    rows = []
    for (fragment_id, place_id, title, kind, source, source_url, attribution,
         content, key_points) in drafts:
        if kind not in IN_SCOPE:
            continue
        rows.append({
            "fragment_id": fragment_id,
            "place_id": place_id,
            "official_name": places[place_id],
            "title": title,
            "fragment_type": kind,
            "draft_source": source,
            "draft_content": content,
            "draft_key_points": key_points or "[]",
            "rewrite_content": "",
            "rewrite_content_short": "",
            "rewrite_key_points": "",
            "source_title": source or "",
            "source_url": source_url or "",
            "attribution": attribution or "",
            "valid_to": "",
            "verified_at": "",
            "allow_cloud_llm": "0",
            "status": "draft",
            "review_note": "",
        })
    rows.sort(key=lambda r: (r["place_id"], TYPE_ORDER[r["fragment_type"]], r["fragment_id"]))
    return rows


def has_rewrite_work(path: Path) -> bool:
    """Return True when an existing table holds any non-draft or rewritten row."""
    if not path.exists():
        return False
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return any(row["status"] != "draft" or (row["rewrite_content"] or "").strip()
                   for row in csv.DictReader(handle))


def main() -> None:
    """Write the rewrite table and print type/status totals."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--force", action="store_true", help="overwrite existing rewrite work")
    args = parser.parse_args()

    out = Path(args.out)
    if has_rewrite_work(out) and not args.force:
        raise SystemExit(f"{out} already has rewrite work; pass --force to overwrite")

    rows = load_rows(args.db)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    types, statuses = {}, {}
    for row in rows:
        types[row["fragment_type"]] = types.get(row["fragment_type"], 0) + 1
        statuses[row["status"]] = statuses.get(row["status"], 0) + 1
    print(f"rows: {len(rows)} -> {out}")
    print(f"types: {types}")
    print(f"status: {statuses}")
    print(f"places: {len({row['place_id'] for row in rows})}")


if __name__ == "__main__":
    main()
