#!/usr/bin/env python3
"""Merge drafted rewrites into fragment-rewrite.csv and mark them rewritten.

Input is a JSON array of objects with fragment_type, fragment_id,
rewrite_content, rewrite_content_short, rewrite_key_points (list), and
optional review_note. Every fragment_id must already exist; approved rows are
never overwritten. All rows in one batch are validated before the file is
replaced. fact rows need 200-300 characters, highlight rows 80-300.

Usage:
    python scripts/merge_rewrites.py --batch .local/rewrite/batch-1.json
"""

import argparse
import csv
import json
import os
import tempfile
from pathlib import Path

TABLE = "docs/data/fragment-rewrite.csv"
CONTENT_LIMITS = {"fact": (200, 300), "highlight": (80, 300)}
MAX_SHORT = 80
MIN_POINTS = 3
MAX_POINTS = 5
MAX_POINT_LEN = 20


def load_table(path: Path) -> list:
    """Return rewrite-table rows decoded as UTF-8 (BOM tolerated)."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def validate_item(item: dict) -> list:
    """Return human-readable problems for one batch item."""
    problems = []
    content = (item.get("rewrite_content") or "").strip()
    short = (item.get("rewrite_content_short") or "").strip()
    points = item.get("rewrite_key_points")
    limits = CONTENT_LIMITS.get(item.get("fragment_type"))
    if limits is None:
        problems.append(f"unsupported fragment_type: {item.get('fragment_type')}")
    elif not limits[0] <= len(content) <= limits[1]:
        problems.append(f"content length {len(content)} not in {limits[0]}-{limits[1]}")
    if not short or len(short) > MAX_SHORT:
        problems.append(f"short length {len(short)} not in 1-{MAX_SHORT}")
    if not isinstance(points, list) or not MIN_POINTS <= len(points) <= MAX_POINTS:
        problems.append(f"key_points must be a list of {MIN_POINTS}-{MAX_POINTS}")
    else:
        long_points = [p for p in points if not p.strip() or len(p) > MAX_POINT_LEN]
        if long_points:
            problems.append(f"key_points over {MAX_POINT_LEN} chars: {long_points[:3]}")
    return problems


def merge(rows: list, batch: list) -> list:
    """Apply the batch in place and return the updated rows."""
    by_id = {row["fragment_id"]: row for row in rows}
    for item in batch:
        fragment_id = item["fragment_id"]
        if fragment_id not in by_id:
            raise SystemExit(f"unknown fragment_id: {fragment_id}")
        row = by_id[fragment_id]
        if row["status"] in ("approved", "rejected"):
            raise SystemExit(f"refusing to overwrite {row['status']} row: {fragment_id}")
        row["rewrite_content"] = item["rewrite_content"].strip()
        row["rewrite_content_short"] = item["rewrite_content_short"].strip()
        row["rewrite_key_points"] = json.dumps(item["rewrite_key_points"],
                                               ensure_ascii=False)
        row["status"] = "rewritten"
        if item.get("review_note"):
            row["review_note"] = item["review_note"].strip()
    return rows


def main() -> None:
    """Validate and merge one rewrite batch into the table."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", required=True, help="JSON array of rewrite items")
    parser.add_argument("--table", default=TABLE)
    args = parser.parse_args()

    table = Path(args.table)
    batch = json.loads(Path(args.batch).read_text(encoding="utf-8"))
    problems = []
    for item in batch:
        for problem in validate_item(item):
            problems.append(f"{item.get('fragment_id')}: {problem}")
    if problems:
        raise SystemExit("batch rejected:\n" + "\n".join(problems))

    rows = merge(load_table(table), batch)
    handle, temp_path = tempfile.mkstemp(suffix=".csv", dir=table.parent)
    os.close(handle)
    with open(temp_path, "w", encoding="utf-8-sig", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temp_path, table)
    print(f"merged {len(batch)} rows into {table}")


if __name__ == "__main__":
    main()
