# How Golden Standard DBs Were Created

## Overview

Each of the 151 golden standard SQLite databases was created by an AI agent (Claude) that:

1. Read the original Excel file with openpyxl
2. Analyzed the structure of every visible sheet
3. Made decisions about table boundaries, column names, data types, and which rows to include/exclude
4. Constructed the ideal SQLite database

This document describes the rules and process used.

## The Analysis Process

For each Excel file, the agent performed these steps:

### Step 1: Initial Reconnaissance
```python
wb = openpyxl.load_workbook("file.xlsx", data_only=True)
# List all sheets, their sizes, and visibility
```

### Step 2: Explore Each Sheet
- Read the first 8 rows to identify the top structure (titles, headers, data start)
- Read the last 3 rows to check for totals/summaries
- Check for bold rows (potential subtotals)
- Check for merged cells (multi-level headers)
- Check for color-coded cells (Gantt charts, status matrices)
- Sample a mid-point row to verify structure consistency

### Step 3: Make Structural Decisions
Based on the exploration, decide for each table region:
- Table name (descriptive snake_case)
- Header row(s) and column names
- Data row range (start and end)
- Rows to skip (titles, annotations, subtotals)
- Column types (INTEGER, REAL, TEXT)

### Step 4: Build and Verify
Construct the SQLite DB and cross-check row counts and sample values against the original Excel.

## Rules Applied

These rules were applied consistently across all 151 files:

### 1. Every visible sheet → at least one table
Unless the sheet is truly empty or contains only charts. Hidden sheets are skipped.

### 2. Column names must be semantic
Use the actual header text from Excel, cleaned up:
- Strip whitespace and newlines
- Multi-level headers: combine as `"Parent_Child"` (e.g., `"Personal Info_Name"`)
- Numeric headers (e.g., Week 1, 2, 3): name as `"Week 1"`, `"Week 2"`, etc.
- Never use `column_1`, `column_2` if the Excel has any header text

### 3. Title/subtitle rows → skip
Rows like `"Monthly Sales Report Q1 2025"` in row 0 are not part of the data. Identified by:
- Very low fill rate (1-2 cells in a wide sheet)
- Merged cells spanning the full width
- Content is a descriptive title, not column names

### 4. Annotation rows → skip
Rows between headers and data that contain explanatory text (not column names). Identified by:
- Only 1-2 cells filled in an otherwise wide table
- Text describes the data below rather than naming columns

### 5. Subtotal/total rows → exclude
Identified by:
- Keywords: "Total", "Subtotal", "Grand Total", "Sum", "合计", "小计"
- Bold formatting different from data rows
- Values that equal the sum of rows above
- Located at the end of data groups or at the very bottom

### 6. ALL data rows included
Zero data loss. Every actual data row is preserved. Row counts were verified against the original Excel.

### 7. Types are correct
- Numbers (integers, decimals) → INTEGER or REAL
- Text → TEXT
- Dates → TEXT in ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
- Boolean → INTEGER (1/0)
- Excel error values (#REF!, #N/A, etc.) → NULL

### 8. Merged cells expanded
The top-left cell's value is filled into all positions in the merged range. This applies to both:
- **Label merges**: "Group A" spanning 3 rows → all 3 rows get "Group A"
- **Numeric merges**: A subtotal spanning 3 rows → all 3 rows get the value

### 9. Multiple tables in one sheet → separate DB tables
When a single Excel sheet contains multiple distinct data regions (separated by empty row gaps or different column structures), each region becomes a separate table.

### 10. Empty separator columns → remove
Columns that are entirely NULL (used as visual separators in Excel) are excluded.

### 11. Template/form sheets → 0-row table
Sheets that have a header structure but no actual data (blank templates) get a table with the column structure preserved and 0 data rows. The description notes it's a template.

## Golden DB Structure

Each golden DB contains:

### Data tables
Named descriptively (e.g., `employee_weekly_performance`, `bonus_accrual_2401`).

### `_golden_meta` table
Key-value metadata:
```sql
CREATE TABLE _golden_meta (key TEXT, value TEXT);

-- For each table:
-- table:{name}:source_sheet  → original Excel sheet name
-- table:{name}:description   → what the table contains
-- table:{name}:row_count     → number of data rows
```

## Common Patterns Encountered

| Pattern | Frequency | Handling |
|---------|-----------|---------|
| Simple single-table sheet | ~60% | Straightforward extraction |
| Title rows before header | ~30% | Skip first 1-3 rows |
| Subtotal/total rows | ~25% | Exclude from data |
| Multi-level headers | ~10% | Combine parent_child |
| Multiple tables per sheet | ~8% | Split into separate DB tables |
| Blank templates | ~5% | 0-row table with structure |
| Numeric/date headers | ~5% | Semantic naming (Week 1, 2025-01-01) |
| Color-coded data (Gantt) | ~3% | Noted in description |

## Reproducing

To regenerate a golden DB:

```python
import sys
sys.path.insert(0, "scripts")
from golden_builder import create_golden_db

create_golden_db("golden_dbs/references/My File.db", {
    "my_table": {
        "columns": [
            {"name": "ID", "type": "INTEGER"},
            {"name": "Name", "type": "TEXT"},
            {"name": "Amount", "type": "REAL"},
        ],
        "rows": [
            [1, "Alice", 100.50],
            [2, "Bob", 200.75],
        ],
        "source_sheet": "Sheet1",
        "description": "Customer transactions",
    }
})
```

See [GOLDEN_DB_GUIDE.md](GOLDEN_DB_GUIDE.md) for the full process used to create these golden DBs.
