# Scoring Methodology

## Overview

The scorer compares tool-generated SQLite databases against golden standard databases using **precise column mapping**. Both sides must provide a `.mapping.json` sidecar file that declares which output column came from which source Excel sheet and column. This eliminates all guesswork in matching.

**Score = average accuracy across all golden columns**

## Requirements

Every output DB must have a sidecar mapping file:

```
my_outputs/
├── report.db                    # Converted SQLite database
├── report.mapping.json          # Column mapping metadata (REQUIRED)
```

Without a `.mapping.json`, the file is skipped (not scored — it's an error, not a zero).

## mapping.json Schema

```json
{
  "source_file": "report.xlsx",
  "tables": [
    {
      "table_name": "weekly_costs",
      "source_sheet": "Sheet1",
      "columns": [
        {"column_name": "Team Member", "source_col": 0},
        {"column_name": "Week 1 Cost",  "source_col": 3},
        {"column_name": "Week 2 Cost",  "source_col": 4}
      ]
    }
  ]
}
```

| Field | Description |
|-------|-------------|
| `source_file` | Original Excel filename |
| `tables[].table_name` | Table name in the output SQLite DB |
| `tables[].source_sheet` | Original Excel sheet name |
| `tables[].columns[].column_name` | Column name in the output SQLite DB |
| `tables[].columns[].source_col` | 0-indexed column number in the original Excel sheet |

## How Scoring Works

### Step 1: Column Alignment

The scorer matches golden columns to output columns using the key `(source_sheet, source_col)`:

```
Golden:  (source_sheet="CPH_DATA", source_col=0)  → column "Employee Name"
Output:  (source_sheet="CPH_DATA", source_col=0)  → column "column_1"
→ MATCHED (same source location, names don't matter)
```

If a golden column has no matching output column → that column scores 0 (data missing).

### Step 2: Row-by-Row Value Comparison

For each matched column pair, compare values row by row (aligned by position):

```
Golden column:  ["Alice", "Bob", "Charlie", ...]
Output column:  ["Alice", "Bob", "Charlie", ...]
→ 3/3 = 1.0
```

### Step 3: Value Comparison Rules

| Golden | Output | Match? |
|--------|--------|--------|
| `NULL` | `NULL` | ✅ |
| `NULL` | `""` (empty string) | ✅ |
| `100` | `100` | ✅ |
| `100` | `"100"` | ✅ (normalized to same number) |
| `100.0` | `100` | ✅ (integer-like float) |
| `"Alice"` | `"alice"` | ✅ (case-insensitive) |
| `"Alice "` | `"Alice"` | ✅ (whitespace stripped) |
| `99.5` | `100` | ❌ (different values) |
| `100` | `NULL` | ❌ |
| `"Alice"` | `"Bob"` | ❌ |

Normalization:
- Numbers: integer-like floats → int (e.g., `100.0` → `100`); otherwise rounded to 4 decimal places for representation
- Strings: stripped and lowercased
- Empty strings → NULL
- **No tolerance**: values must match exactly after normalization

### Step 4: Compute Scores

```
column_score = matching_values / golden_values_count

table_score = average(column_scores)

file_score = average(table_scores)
```

### File Statuses

| Status | Meaning | Counted in overall? |
|--------|---------|-------------------|
| `scored` | Both mapping.json found, score computed | ✅ |
| `no_output` | No output DB found for this golden file | ✅ (score = 0) |
| `error_no_script_mapping` | Output DB exists but no mapping.json | ❌ (skipped) |
| `error_no_golden_mapping` | Golden DB has no mapping.json | ❌ (skipped) |

**Overall score** = average of all `scored` + `no_output` files.

## Running the Scorer

```bash
python scripts/scorer.py path/to/outputs/
```

The output directory can be flat or have `references/`/`deliverables/` subdirectories.

## Output Files

| File | Contents |
|------|----------|
| `eval_results.json` | Per-file details: score, column matches, value counts |
| `eval_scores.csv` | Summary table: Category, File, Status, Score, Columns stats |

### eval_scores.csv example

```csv
Category,File,Status,Score,Columns_Total,Columns_Matched,Columns_Missing
references,Raw Data for Branch Profitability Final.db,scored,1.00,27,27,0
deliverables,Dashboard Output.db,no_output,0.00,,,
references,report.db,error_no_script_mapping,N/A,,,
```

## Grade Scale

| Grade | Score | Interpretation |
|-------|-------|----------------|
| A | ≥ 0.98 | Production-ready — near-zero errors |
| B | 0.95–0.98 | Usable — very few errors, spot-check recommended |
| C | 0.90–0.95 | Risky — noticeable errors, manual review required |
| D | 0.80–0.90 | Unreliable — significant data quality issues |
| F | < 0.80 | Unusable — major data loss or corruption |

> Excel data demands high accuracy. A single wrong number in a financial report erodes trust in the entire dataset. The grading scale reflects this: anything below 95% accuracy needs human review.

## Design Rationale

### Why require mapping.json?

Without it, the scorer has to guess which output column corresponds to which golden column — using name matching (fails when names differ) or data-content matching (fails when common values overlap). The mapping.json removes all ambiguity: the tool explicitly declares "my column X came from Excel sheet Y, column Z."

### Why score by column, not by cell?

Scoring by column gives equal weight to each piece of information. A 2-column table and a 50-column table both contribute proportionally. If we scored by cell, wide tables would dominate the score.

### Why row-aligned comparison?

Since both golden and output extracted data from the same Excel rows (declared via source_sheet), the row order should be consistent. Row-aligned comparison is simpler and more precise than greedy row matching.
