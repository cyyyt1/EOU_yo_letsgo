#!/usr/bin/env python3
"""Run end-to-end checks on the distribution SQLite and its import artifacts.

Validates schema version/columns, row constraints, staging-to-DB consistency,
rebuild determinism, checksum reproducibility, and database integrity.

Usage:
    python scripts/validate_dist.py
    python scripts/validate_dist.py --db docs/data/schema-dist.sqlite --data docs/data
"""

import argparse
import csv
import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile
from contextlib import closing
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

FRAGMENT_TYPES = {"fact", "legend", "poetry", "highlight", "trivia", "practical", "spatial"}
CONFIDENCES = {"auto", "review", "manual"}
SOURCE_EXCLUDED = ("百度百科", "马蜂窝", "携程", "大众点评", "知乎", "小红书")
PLACE_ID = re.compile(r"hz-(?:b[0-9a-z]{9}(?:-[0-9]+)?|h[0-9a-f]{10})")
NAME_CHAR = re.compile(r"[\u4e00-\u9fffA-Za-z]")
FRAGMENT_FIELDS = (
    "fragment_id", "place_id", "title", "fragment_type", "content", "content_short",
    "key_points", "keywords", "valid_to", "verified_at", "source_title", "source_url",
    "attribution", "allow_cloud_llm",
)
CHECKSUM_TABLES = {
    "place": ("place_id", "parent_id", "level", "name", "lat", "lon", "candidate_radius_m"),
    "place_alias": ("place_id", "alias", "confidence"),
    "fragment": FRAGMENT_FIELDS,
}
IMPORT_ORDER = ("place-import.sql", "place-alias-import.sql", "fragment-import.sql")


class Report:
    """Collect pass/fail checks and print a summary."""

    def __init__(self) -> None:
        """Initialize an empty report."""
        self.failures = 0

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        """Record one check and print its result."""
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
        if not ok:
            self.failures += 1


def load_csv(path: Path) -> list:
    """Return CSV rows decoded as UTF-8 (BOM tolerated)."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def package_checksum(db_path: str) -> str:
    """Hash the canonical dump of place, place_alias, and fragment."""
    lines = [json.dumps({"format": "hz-content-package-v1", "schema_user_version": 2},
                        ensure_ascii=False, separators=(",", ":"))]
    with closing(sqlite3.connect(db_path)) as connection:
        for table, columns in CHECKSUM_TABLES.items():
            order = "place_id, alias" if table == "place_alias" else columns[0]
            for row in connection.execute(
                    f"SELECT {', '.join(columns)} FROM {table} ORDER BY {order}"):
                lines.append(json.dumps({"table": table, **dict(zip(columns, row))},
                                        ensure_ascii=False, separators=(",", ":")))
    return hashlib.sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()


def rebuild_from_sql(data_dir: Path, apply_twice: bool = False) -> str:
    """Build a temp database from DDL and import SQL; return its path."""
    handle, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(handle)
    connection = sqlite3.connect(path)
    connection.executescript((data_dir / "schema-dist.sql").read_text(encoding="utf-8"))
    rounds = 2 if apply_twice else 1
    for _ in range(rounds):
        for name in IMPORT_ORDER:
            connection.executescript((data_dir / name).read_text(encoding="utf-8"))
    connection.commit()
    connection.close()
    return path


def check_schema(db: sqlite3.Connection, report: Report) -> None:
    """Validate table set, columns, version, and the confidence CHECK."""
    tables = {row[0] for row in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
    report.check("schema: 4 tables", tables ==
                 {"content_package", "place", "place_alias", "fragment"}, str(sorted(tables)))
    version = db.execute("PRAGMA user_version").fetchone()[0]
    report.check("schema: user_version = 2", version == 2, f"got {version}")
    columns = [row[1] for row in db.execute("PRAGMA table_info(place_alias)")]
    report.check("schema: place_alias columns", columns == ["place_id", "alias", "confidence"],
                 str(columns))
    indexes = {row[1] for row in db.execute("PRAGMA index_list(place_alias)")}
    report.check("schema: ux_place_alias index", "ux_place_alias" in indexes, str(indexes))
    place_id = db.execute("SELECT place_id FROM place LIMIT 1").fetchone()[0]
    try:
        db.execute("INSERT INTO place_alias (place_id, alias, confidence) VALUES (?, '校验', 'x')",
                   (place_id,))
        db.rollback()
        report.check("schema: confidence CHECK rejects bad value", False)
    except sqlite3.IntegrityError:
        db.rollback()
        report.check("schema: confidence CHECK rejects bad value", True)


def check_places(db: sqlite3.Connection, report: Report) -> None:
    """Validate place rows: IDs, coordinates, levels, radii, names."""
    rows = db.execute(
        "SELECT place_id, name, level, lat, lon, candidate_radius_m FROM place").fetchall()
    report.check("place: row count", len(rows) == 102, f"{len(rows)}")
    bad_ids = [r[0] for r in rows if not PLACE_ID.fullmatch(r[0])]
    report.check("place: ID format", not bad_ids, str(bad_ids[:5]))
    outside = [r[0] for r in rows if not (29.0 <= r[3] <= 30.7 and 118.2 <= r[4] <= 120.8)]
    report.check("place: coordinates in Hangzhou bbox", not outside, str(outside[:5]))
    levels = {r[2] for r in rows}
    report.check("place: levels", levels <= {"area", "site", "point"}, str(sorted(levels)))
    bad_radius = [r[0] for r in rows if not isinstance(r[5], int) or r[5] < 0]
    report.check("place: non-negative radius", not bad_radius, str(bad_radius[:5]))
    names = [r[1] for r in rows]
    report.check("place: names non-empty and unique",
                 all(names) and len(names) == len(set(names)),
                 f"{len(names) - len(set(names))} duplicates")


def check_aliases(db: sqlite3.Connection, rows: list, report: Report) -> None:
    """Validate alias coverage, uniqueness, confidence, and staging parity."""
    places = dict(db.execute("SELECT place_id, name FROM place"))
    db_rows = db.execute("SELECT place_id, alias, confidence FROM place_alias").fetchall()
    report.check("alias: row count", len(db_rows) == 253, f"{len(db_rows)}")
    unknown = [r for r in db_rows if r[0] not in places]
    report.check("alias: place_id resolvable", not unknown, str(unknown[:3]))
    aliases = [r[1] for r in db_rows]
    report.check("alias: globally unique", len(aliases) == len(set(aliases)),
                 f"{len(aliases) - len(set(aliases))} duplicates")
    bad_conf = [r for r in db_rows if r[2] not in CONFIDENCES]
    report.check("alias: confidence values", not bad_conf, str(bad_conf[:3]))
    bad_text = [a for a in aliases
                if not 2 <= len(a) <= 20 or not NAME_CHAR.search(a) or re.search(r"\s", a)]
    report.check("alias: text shape", not bad_text, str(bad_text[:5]))
    missing = [name for pid, name in places.items()
               if (pid, name) not in {(r[0], r[1]) for r in db_rows}]
    report.check("alias: every place has canonical alias", not missing, str(missing[:3]))
    expected = {(r["place_id"], r["alias"]): r["confidence"]
                for r in rows if r["status"] == "proposed"}
    actual = {(r[0], r[1]): r[2] for r in db_rows}
    report.check("alias: staging matches DB", expected == actual,
                 f"staging {len(expected)} vs db {len(actual)}")
    counts = {}
    for value in actual.values():
        counts[value] = counts.get(value, 0) + 1
    report.check("alias: confidence distribution",
                 counts == {"auto": 209, "manual": 44}, str(counts))


def expected_source(row: dict) -> tuple:
    """Return the (title, url, attribution) that should reach the package."""
    title = (row.get("source_title") or "").strip()
    if not title or title.startswith(SOURCE_EXCLUDED):
        return "团队原创改写", "", "原创内容"
    return (title, (row.get("source_url") or "").strip(),
            (row.get("attribution") or "").strip() or title)


def check_fragments(db: sqlite3.Connection, approved: list, report: Report) -> None:
    """Validate the published fragment set against approved rewrites."""
    places = {r[0] for r in db.execute("SELECT place_id FROM place")}
    db_rows = db.execute(f"SELECT {', '.join(FRAGMENT_FIELDS)} FROM fragment").fetchall()
    records = [dict(zip(FRAGMENT_FIELDS, r)) for r in db_rows]
    report.check("fragment: row count equals approved", len(records) == len(approved),
                 f"db {len(records)} vs approved {len(approved)}")
    report.check("fragment: place_id resolvable",
                 all(r["place_id"] in places for r in records))
    report.check("fragment: types",
                 {r["fragment_type"] for r in records} <= FRAGMENT_TYPES)
    types = {}
    for r in records:
        types[r["fragment_type"]] = types.get(r["fragment_type"], 0) + 1
    report.check("fragment: fact 103 + highlight 31 + trivia 49 + spatial 18 + legend 3",
                 types == {"fact": 103, "highlight": 31, "trivia": 49,
                           "spatial": 18, "legend": 3},
                 str(types))
    report.check("fragment: non-empty content/title",
                 all((r["content"] or "").strip() and (r["title"] or "").strip()
                     for r in records))
    report.check("fragment: validity fields only on practical",
                 all(not (r["valid_to"] or r["verified_at"])
                     for r in records if r["fragment_type"] != "practical"))
    report.check("fragment: allow_cloud_llm 0/1", all(r["allow_cloud_llm"] in (0, 1)
                                                      for r in records))
    bad_source = []
    cited = 0
    for r in records:
        title = (r["source_title"] or "").strip()
        url = (r["source_url"] or "").strip()
        attribution = (r["attribution"] or "").strip()
        if not title or not attribution:
            bad_source.append(r["fragment_id"])
        elif title == "团队原创改写":
            if url or attribution != "原创内容":
                bad_source.append(r["fragment_id"])
        else:
            cited += 1
            if title.startswith(SOURCE_EXCLUDED) or not url.startswith("http"):
                bad_source.append(r["fragment_id"])
    report.check("fragment: sources team-original or cited", not bad_source,
                 str(bad_source[:5]))
    report.check("fragment: cited source count", cited == 45, f"{cited}")
    bad_json = []
    for r in records:
        for field in ("key_points", "keywords"):
            try:
                if not isinstance(json.loads(r[field] or "[]"), list):
                    bad_json.append((r["fragment_id"], field))
            except json.JSONDecodeError:
                bad_json.append((r["fragment_id"], field))
    report.check("fragment: key_points/keywords JSON arrays", not bad_json, str(bad_json[:3]))
    expected = {r["fragment_id"]: r for r in approved}
    mismatch = []
    for r in records:
        source = expected.get(r["fragment_id"])
        if source is None:
            mismatch.append(r["fragment_id"])
            continue
        title, url, attribution = expected_source(source)
        if ((r["source_title"] or ""), (r["source_url"] or ""),
                (r["attribution"] or "")) != (title, url, attribution):
            mismatch.append(r["fragment_id"])
            continue
        for field, value in (
            ("place_id", source["place_id"]),
            ("title", source["title"]),
            ("fragment_type", source["fragment_type"]),
            ("content", source["rewrite_content"].strip()),
            ("content_short", source["rewrite_content_short"].strip()),
            ("key_points", source["rewrite_key_points"]),
        ):
            if (value or None) != r[field]:
                mismatch.append(r["fragment_id"])
                break
    report.check("fragment: DB matches approved rewrites",
                 not mismatch and len(expected) == len(records),
                 f"approved {len(expected)} vs db {len(records)}; diff {mismatch[:3]}")


def check_coverage(data_dir: Path, report: Report) -> None:
    """Validate the fragment coverage report totals."""
    rows = load_csv(data_dir / "fragment-coverage.csv")
    counts = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    expected = {"content_found": 102, "excluded_deleted": 11, "excluded_no_coord": 8}
    report.check("coverage: 121 decisions", len(rows) == 121, f"{len(rows)}")
    report.check("coverage: status totals", counts == expected, str(counts))


def check_exclusions(db: sqlite3.Connection, data_dir: Path, report: Report) -> None:
    """Validate the exclusion decision log against loaded places."""
    rows = load_csv(data_dir / "place-exclusions.csv")
    report.check("exclusions: 11 decisions", len(rows) == 11, f"{len(rows)}")
    names = {r["official_name"] for r in rows}
    loaded = {r[0] for r in db.execute("SELECT name FROM place")}
    report.check("exclusions: excluded names absent from place",
                 not (names & loaded), str(sorted(names & loaded)[:3]))


def check_rewrite(data_dir: Path, place_ids: set, report: Report) -> None:
    """Validate the in-scope rewrite table: coverage, status gate, drafts."""
    rows = load_csv(data_dir / "fragment-rewrite.csv")
    report.check("rewrite: row count", len(rows) == 208, f"{len(rows)}")
    ids = [row["fragment_id"] for row in rows]
    report.check("rewrite: fragment_id unique", len(ids) == len(set(ids)),
                 f"{len(ids) - len(set(ids))} duplicates")
    covered = {row["place_id"] for row in rows}
    report.check("rewrite: 102 places covered", len(covered) == 102, f"{len(covered)}")
    report.check("rewrite: place_id resolvable", covered <= place_ids,
                 str(sorted(covered - place_ids)[:3]))
    types = {}
    for row in rows:
        types[row["fragment_type"]] = types.get(row["fragment_type"], 0) + 1
    report.check("rewrite: fact 107 + highlight 31 + trivia 49 + spatial 18 + legend 3",
                 types == {"fact": 107, "highlight": 31, "trivia": 49,
                           "spatial": 18, "legend": 3},
                 str(types))
    per_place = {}
    for row in rows:
        key = (row["place_id"], row["fragment_type"])
        per_place[key] = per_place.get(key, 0) + 1
    missing = [pid for pid in covered if not 1 <= per_place.get((pid, "fact"), 0) <= 2]
    report.check("rewrite: one or two facts per place", not missing, str(missing[:3]))
    too_many = [pid for pid in covered if per_place.get((pid, "highlight"), 0) > 2]
    report.check("rewrite: at most two highlights per place", not too_many,
                 str(too_many[:3]))
    statuses = {row["status"] for row in rows}
    report.check("rewrite: status in draft/rewritten/approved/rejected",
                 statuses <= {"draft", "rewritten", "approved", "rejected"},
                 str(sorted(statuses)))
    rejected = [row for row in rows if row["status"] == "rejected"]
    report.check("rewrite: rejected rows carry review_note",
                 all((row["review_note"] or "").strip() for row in rejected),
                 str([r["fragment_id"] for r in rejected
                      if not (r["review_note"] or "").strip()][:3]))
    report.check("rewrite: rejected rows have no rewrite_content",
                 not [r["fragment_id"] for r in rejected
                      if (r["rewrite_content"] or "").strip()],
                 str([r["fragment_id"] for r in rejected
                      if (r["rewrite_content"] or "").strip()][:3]))
    approved = [row for row in rows if row["status"] == "approved"]
    empty_approved = [row["fragment_id"] for row in approved
                      if not (row["rewrite_content"] or "").strip()]
    report.check("rewrite: approved rows have rewrite_content", not empty_approved,
                 str(empty_approved[:3]))
    bad_points = []
    for row in approved:
        try:
            points = json.loads(row["rewrite_key_points"] or "[]")
        except json.JSONDecodeError:
            points = None
        if not isinstance(points, list) or not 3 <= len(points) <= 5:
            bad_points.append(row["fragment_id"])
    report.check("rewrite: approved rows have 3-5 key_points", not bad_points,
                 str(bad_points[:3]))
    empty_draft = [row["fragment_id"] for row in rows
                   if (row["draft_source"] or "").strip()
                   and not (row["draft_content"] or "").strip()]
    report.check("rewrite: sourced rows have draft_content", not empty_draft,
                 str(empty_draft[:3]))


def main() -> None:
    """Run every validation group and exit non-zero on any failure."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="docs/data/schema-dist.sqlite")
    parser.add_argument("--data", default="docs/data")
    args = parser.parse_args()
    data_dir = Path(args.data)
    report = Report()

    with closing(sqlite3.connect(args.db)) as db:
        db.execute("PRAGMA foreign_keys = ON")
        check_schema(db, report)
        check_places(db, report)
        check_aliases(db, load_csv(data_dir / "place-alias-staging.csv"), report)
        approved = [row for row in load_csv(data_dir / "fragment-rewrite.csv")
                    if row["status"] == "approved"]
        check_fragments(db, approved, report)
        check_coverage(data_dir, report)
        check_exclusions(db, data_dir, report)
        report.check("db: integrity_check",
                     db.execute("PRAGMA integrity_check").fetchone()[0] == "ok")
        report.check("db: foreign_key_check",
                     not db.execute("PRAGMA foreign_key_check").fetchall())
        packages = db.execute(
            "SELECT package_id, version, city_code, published_at, license_note, checksum_sha256 "
            "FROM content_package").fetchall()
        report.check("db: content_package at most one row", len(packages) <= 1, str(len(packages)))
        live_checksum = package_checksum(args.db)
        report.check("db: package row fields complete",
                     not packages or all(packages[0]),
                     str(packages[0]) if packages else "")
        report.check("db: package checksum matches content",
                     not packages or packages[0][5] == live_checksum,
                     f"{packages[0][5] if packages else ''} vs {live_checksum}")
        place_ids = {row[0] for row in db.execute("SELECT place_id FROM place")}
    check_rewrite(data_dir, place_ids, report)

    built = rebuild_from_sql(data_dir)
    twice = rebuild_from_sql(data_dir, apply_twice=True)
    try:
        with closing(sqlite3.connect(built)) as db:
            rebuilt_checksum = package_checksum(built)
            report.check("rebuild: same checksum as live", rebuilt_checksum == live_checksum,
                         rebuilt_checksum)
            report.check("rebuild: same counts", all(
                db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == expected
                for t, expected in (("place", 102), ("place_alias", 253),
                                    ("fragment", 204), ("content_package", 0))))
        with closing(sqlite3.connect(twice)) as db:
            report.check("rebuild: import SQL idempotent",
                         package_checksum(twice) == rebuilt_checksum and
                         db.execute("SELECT COUNT(*) FROM place_alias").fetchone()[0] == 253)
    finally:
        for path in (built, twice):
            os.remove(path)

    print(f"\nchecks failed: {report.failures}")
    raise SystemExit(1 if report.failures else 0)


if __name__ == "__main__":
    main()
