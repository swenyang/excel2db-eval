"""Evaluation scorer v3: Mapping-based precise column matching.

Requires both golden and output DBs to have sidecar .mapping.json files
that declare the source Excel sheet and column index for each DB column.

Usage:
    python scripts/scorer.py <output_dir>
"""

import os
import json
import sqlite3
import argparse
import csv
from typing import Any

EVAL_DIR = os.path.dirname(os.path.dirname(__file__))
GOLDEN_DIRS = [
    os.path.join(EVAL_DIR, "golden_dbs", "references"),
    os.path.join(EVAL_DIR, "golden_dbs", "deliverables"),
]


def _normalize_value(val: Any) -> Any:
    """Normalize a cell value for comparison."""
    if val is None:
        return None
    if isinstance(val, float):
        if val == int(val) and abs(val) < 1e15:
            return int(val)
        return round(val, 4)
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None
        try:
            f = float(s)
            if f == int(f) and abs(f) < 1e15:
                return int(f)
            return round(f, 4)
        except ValueError:
            return s.lower()
    return val


def _values_match(golden_val: Any, script_val: Any) -> bool:
    """Compare two normalized values. Exact match after normalization, no tolerance."""
    g = _normalize_value(golden_val)
    s = _normalize_value(script_val)

    if g is None and s is None:
        return True
    if g is None or s is None:
        return False

    return g == s


def load_mapping(json_path: str) -> dict | None:
    """Load a mapping.json file. Returns None if not found."""
    if not os.path.exists(json_path):
        return None
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_db_column(conn: sqlite3.Connection, table_name: str, column_name: str) -> list:
    """Load all values for a specific column from a table."""
    try:
        rows = conn.execute(f'SELECT "{column_name}" FROM "{table_name}"').fetchall()
        return [r[0] for r in rows]
    except Exception:
        return []


def score_file(golden_db_path: str, golden_mapping: dict,
               script_db_path: str, script_mapping: dict) -> dict:
    """Score a single file by comparing columns matched via mappings."""

    golden_conn = sqlite3.connect(golden_db_path)
    script_conn = sqlite3.connect(script_db_path)

    # Build script lookup: (source_sheet_lower, source_col) -> (table_name, column_name)
    script_lookup = {}
    for tbl in script_mapping.get("tables", []):
        for col in tbl.get("columns", []):
            key = (tbl["source_sheet"].lower(), col["source_col"])
            script_lookup[key] = (tbl["table_name"], col["column_name"])

    column_scores = []
    column_details = []

    for g_tbl in golden_mapping.get("tables", []):
        g_sheet = g_tbl["source_sheet"]
        g_table_name = g_tbl["table_name"]

        for g_col in g_tbl.get("columns", []):
            g_col_name = g_col["column_name"]
            g_source_col = g_col["source_col"]

            # Find matching script column
            key = (g_sheet.lower(), g_source_col)
            script_match = script_lookup.get(key)

            if script_match is None:
                # Column not found in script output
                column_scores.append(0.0)
                column_details.append({
                    "golden_table": g_table_name,
                    "golden_column": g_col_name,
                    "source_sheet": g_sheet,
                    "source_col": g_source_col,
                    "status": "missing",
                    "score": 0.0,
                })
                continue

            s_table_name, s_col_name = script_match

            # Load values
            g_values = load_db_column(golden_conn, g_table_name, g_col_name)
            s_values = load_db_column(script_conn, s_table_name, s_col_name)

            if not g_values:
                column_scores.append(1.0)
                column_details.append({
                    "golden_table": g_table_name,
                    "golden_column": g_col_name,
                    "script_table": s_table_name,
                    "script_column": s_col_name,
                    "status": "empty_golden",
                    "score": 1.0,
                })
                continue

            # Compare values row by row (up to the shorter list)
            matches = 0
            total = len(g_values)

            min_rows = min(len(g_values), len(s_values))
            for i in range(min_rows):
                if _values_match(g_values[i], s_values[i]):
                    matches += 1

            # Rows in golden but not in script count as 0 (already in total)

            score = matches / total if total > 0 else 1.0
            column_scores.append(score)
            column_details.append({
                "golden_table": g_table_name,
                "golden_column": g_col_name,
                "script_table": s_table_name,
                "script_column": s_col_name,
                "status": "matched",
                "score": round(score, 4),
                "golden_rows": len(g_values),
                "script_rows": len(s_values),
                "matching_values": matches,
            })

    golden_conn.close()
    script_conn.close()

    file_score = sum(column_scores) / len(column_scores) if column_scores else 0.0

    return {
        "score": round(file_score, 4),
        "columns_total": len(column_scores),
        "columns_matched": sum(1 for d in column_details if d["status"] == "matched"),
        "columns_missing": sum(1 for d in column_details if d["status"] == "missing"),
        "column_details": column_details,
    }


def _find_files(golden_basename: str, script_dir: str) -> tuple[str | None, str | None]:
    """Find matching script DB and mapping.json."""
    stem = os.path.splitext(golden_basename)[0]
    candidates = [
        stem.replace(" ", "_"),
        stem,
    ]

    # Search in script_dir and its subdirectories
    search_dirs = [script_dir]
    for subdir in ["references", "deliverables"]:
        sub = os.path.join(script_dir, subdir)
        if os.path.isdir(sub):
            search_dirs.append(sub)

    for sdir in search_dirs:
        for name in candidates:
            db_path = os.path.join(sdir, name + ".db")
            map_path = os.path.join(sdir, name + ".mapping.json")
            if os.path.exists(db_path) and os.path.exists(map_path):
                return db_path, map_path

    return None, None


def run_evaluation(script_output_dir: str) -> dict:
    """Run evaluation."""
    golden_files = []
    for gdir in GOLDEN_DIRS:
        if not os.path.isdir(gdir):
            continue
        category = "references" if "references" in gdir else "deliverables"
        for f in os.listdir(gdir):
            if f.endswith(".db"):
                golden_files.append((f, os.path.join(gdir, f), category))
    golden_files.sort()

    results = {
        "total_files": len(golden_files),
        "scored": 0,
        "skipped_no_output": 0,
        "skipped_no_mapping": 0,
        "file_results": [],
    }

    score_sum = 0.0

    for gf, golden_path, category in golden_files:
        golden_map_path = golden_path.replace(".db", ".mapping.json")

        golden_mapping = load_mapping(golden_map_path)
        if golden_mapping is None:
            results["file_results"].append({
                "file": gf, "category": category,
                "status": "error_no_golden_mapping", "score": None,
            })
            results["skipped_no_mapping"] += 1
            continue

        script_db, script_map_path = _find_files(gf, script_output_dir)

        if script_db is None:
            results["file_results"].append({
                "file": gf, "category": category,
                "status": "no_output", "score": 0.0,
            })
            results["skipped_no_output"] += 1
            score_sum += 0.0
            continue

        script_mapping = load_mapping(script_map_path)
        if script_mapping is None:
            results["file_results"].append({
                "file": gf, "category": category,
                "status": "error_no_script_mapping", "score": None,
            })
            results["skipped_no_mapping"] += 1
            continue

        file_result = score_file(golden_path, golden_mapping, script_db, script_mapping)
        file_result["file"] = gf
        file_result["category"] = category
        file_result["status"] = "scored"
        results["file_results"].append(file_result)
        results["scored"] += 1
        score_sum += file_result["score"]

    total_scorable = results["scored"] + results["skipped_no_output"]
    results["overall_score"] = round(score_sum / total_scorable, 4) if total_scorable > 0 else 0.0

    return results


def print_report(results: dict):
    total = results["total_files"]
    scored = results["scored"]
    no_output = results["skipped_no_output"]
    no_mapping = results["skipped_no_mapping"]

    print("=== EVALUATION REPORT ===")
    print(f"Files: {total} total")
    print(f"  Scored:              {scored}")
    print(f"  No output (score=0): {no_output}")
    print(f"  No mapping (skip):   {no_mapping}")
    print(f"\nOverall Score: {results['overall_score']:.4f}")
    print()

    # Grade distribution (only scored + no_output files)
    scorable = [r for r in results["file_results"] if r.get("score") is not None]
    grades = {"A (>=0.98)": 0, "B (0.95-0.98)": 0, "C (0.90-0.95)": 0, "D (0.80-0.90)": 0, "F (<0.80)": 0}
    for r in scorable:
        s = r["score"]
        if s >= 0.98: grades["A (>=0.98)"] += 1
        elif s >= 0.95: grades["B (0.95-0.98)"] += 1
        elif s >= 0.90: grades["C (0.90-0.95)"] += 1
        elif s >= 0.80: grades["D (0.80-0.90)"] += 1
        else: grades["F (<0.80)"] += 1

    print("Score Distribution:")
    for g, c in grades.items():
        print(f"  {g}: {c}")
    print()

    sorted_r = sorted(scorable, key=lambda x: x["score"])
    print("Worst 10:")
    for r in sorted_r[:10]:
        status = "(no output)" if r["status"] == "no_output" else f"(cols: {r.get('columns_matched',0)}/{r.get('columns_total',0)})"
        print(f"  {r['score']:.4f}  {r['file'][:55]}  {status}")
    print()
    print("Best 10:")
    for r in sorted_r[-10:]:
        tag = "(perfect)" if r["score"] >= 0.99 else f"(cols: {r.get('columns_matched',0)}/{r.get('columns_total',0)})"
        print(f"  {r['score']:.4f}  {r['file'][:55]}  {tag}")


def save_csv(results: dict, csv_path: str):
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Category", "File", "Status", "Score", "Columns_Total", "Columns_Matched", "Columns_Missing"])
        for r in sorted(results["file_results"], key=lambda x: (x.get("category", ""), -(x.get("score") or 0))):
            w.writerow([
                r.get("category", ""),
                r["file"],
                r["status"],
                f"{r['score']:.2f}" if r.get("score") is not None else "N/A",
                r.get("columns_total", ""),
                r.get("columns_matched", ""),
                r.get("columns_missing", ""),
            ])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate outputs against golden DBs using column mappings.")
    parser.add_argument("output_dir", help="Directory with output .db + .mapping.json files")
    args = parser.parse_args()

    results = run_evaluation(args.output_dir)
    print_report(results)

    json_path = os.path.join(EVAL_DIR, "eval_results.json")
    csv_path = os.path.join(EVAL_DIR, "eval_scores.csv")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    save_csv(results, csv_path)
    print(f"\nResults saved to:\n  {json_path}\n  {csv_path}")
