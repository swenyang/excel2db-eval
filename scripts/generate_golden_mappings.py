"""Generate mapping.json files for all golden standard DBs.

Reads _golden_meta from each golden DB to build the mapping.
For source_col, examines the original Excel file to determine column positions.

Since we may not have the Excel files locally, we use the golden DB structure:
- source_sheet from _golden_meta
- source_col = column index in the golden table (0-indexed)
  This is a simplification — it assumes golden columns are in the same order
  as the original Excel columns (which they should be, by construction).
"""
import os
import sqlite3
import json

EVAL_DIR = os.path.dirname(os.path.dirname(__file__))
GOLDEN_DIRS = [
    os.path.join(EVAL_DIR, "golden_dbs", "references"),
    os.path.join(EVAL_DIR, "golden_dbs", "deliverables"),
]


def generate_mapping(db_path: str) -> dict | None:
    """Generate mapping.json content from a golden DB."""
    conn = sqlite3.connect(db_path)

    # Read meta
    try:
        meta = dict(conn.execute("SELECT key, value FROM _golden_meta").fetchall())
    except Exception:
        conn.close()
        return None

    # Get user tables
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall() if not r[0].startswith("_")]

    mapping = {"source_file": "", "tables": []}

    for tbl in tables:
        source_sheet = meta.get(f"table:{tbl}:source_sheet", "")
        cols = conn.execute(f'PRAGMA table_info([{tbl}])').fetchall()

        tbl_mapping = {
            "table_name": tbl,
            "source_sheet": source_sheet,
            "columns": [],
        }

        for col_info in cols:
            col_idx = col_info[0]  # cid = column index
            col_name = col_info[1]
            tbl_mapping["columns"].append({
                "column_name": col_name,
                "source_col": col_idx,
            })

        # Add row count info
        row_count = conn.execute(f"SELECT COUNT(*) FROM [{tbl}]").fetchone()[0]
        tbl_mapping["row_count"] = row_count

        mapping["tables"].append(tbl_mapping)

    conn.close()
    return mapping


def main():
    total = 0
    for gdir in GOLDEN_DIRS:
        if not os.path.isdir(gdir):
            continue
        for f in sorted(os.listdir(gdir)):
            if not f.endswith(".db"):
                continue
            db_path = os.path.join(gdir, f)
            mapping = generate_mapping(db_path)
            if mapping is None:
                print(f"  SKIP: {f} (no _golden_meta)")
                continue

            json_path = db_path.replace(".db", ".mapping.json")
            with open(json_path, "w", encoding="utf-8") as jf:
                json.dump(mapping, jf, indent=2, ensure_ascii=False)
            total += 1

    print(f"Generated {total} mapping.json files")


if __name__ == "__main__":
    main()
