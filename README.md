# excel2db-eval

Evaluation benchmark for Excel-to-SQLite conversion tools. 151 real-world Excel files with hand-crafted golden standard SQLite databases and an automated scoring system.

## What's Inside

```
excel2db-eval/
├── README.md                          # This file
├── GOLDEN_DB_GUIDE.md                 # How golden DBs were created
├── SCORING_GUIDE.md                   # Scoring methodology details
├── golden_dbs/
│   ├── references/                    # 86 golden DBs + mapping.json files
│   └── deliverables/                  # 65 golden DBs + mapping.json files
├── scripts/
│   ├── download_source_files.py       # Download source Excel files from HuggingFace
│   ├── generate_golden_mappings.py    # Generate mapping.json for golden DBs
│   ├── scorer.py                      # Evaluation scoring system
│   └── golden_builder.py             # Helper for creating golden DBs
├── eval_results.json                  # Latest scoring results (generated)
└── eval_scores.csv                    # Latest scoring summary (generated)
```

## Quick Start

### 1. Download source Excel files

The source Excel files come from the [OpenAI gdpval dataset](https://huggingface.co/datasets/openai/gdpval) and are not included in this repo. Download them with:

```bash
pip install datasets
python scripts/download_source_files.py
```

This creates:
```
source_files/
├── references/    (86 Excel files)
└── deliverables/  (65 Excel files)
```

### 2. Generate your tool's output

Convert the source Excel files to SQLite using your tool and place the output `.db` files in a directory:

```bash
# Example with table2db:
pip install table2db
python -c "
import os, shutil
from table2db import TableConverter
converter = TableConverter()
for subdir in ['references', 'deliverables']:
    os.makedirs(f'my_outputs/{subdir}', exist_ok=True)
    for f in os.listdir(f'source_files/{subdir}'):
        if not f.endswith(('.xlsx', '.xls')):
            continue
        try:
            result = converter.convert(f'source_files/{subdir}/{f}')
            base = os.path.splitext(f)[0].replace(' ', '_')
            shutil.copy2(result.db_path, f'my_outputs/{subdir}/{base}.db')
            result.cleanup()
        except Exception as e:
            print(f'SKIP: {f}: {e}')
"
```

### 3. Run evaluation

```bash
# Score against a flat output directory
python scripts/scorer.py my_outputs/

# Score against a structured output directory (references/deliverables)
python scripts/scorer.py my_outputs/
```

### 4. Check results

```bash
cat eval_scores.csv     # Per-file scores
cat eval_results.json   # Detailed results with matching info
```

## Dataset Source

151 Excel files from [OpenAI gdpval](https://huggingface.co/datasets/openai/gdpval) (`train` split):

- **86 reference files**: Input data provided to task performers (financial reports, inventory lists, scheduling data, etc.)
- **65 deliverable files**: Output data created by task performers (analysis results, formatted reports, etc.)

These cover real-world Excel complexity: merged cells, multi-level headers, subtotal rows, mixed types, templates, Gantt charts, and more.

## Scoring Overview

The scorer uses **precise column mapping** — both golden and output DBs declare which output column came from which Excel sheet and column via a `.mapping.json` sidecar file.

```
Score = average accuracy across all golden columns
        (row-by-row value comparison, with numeric tolerance)
```

No name matching, no guessing. The mapping.json tells the scorer exactly which columns to compare.

### Required output format

```
my_outputs/
├── report.db              # Your SQLite output
├── report.mapping.json    # Column mapping (REQUIRED for scoring)
```

See [SCORING_GUIDE.md](SCORING_GUIDE.md) for the mapping.json schema and detailed scoring rules.

## License

- **Golden DBs, scorer, and documentation**: MIT
- **Source Excel files**: From [OpenAI gdpval dataset](https://huggingface.co/datasets/openai/gdpval) — download directly from HuggingFace
