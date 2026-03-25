"""Download source Excel files from the OpenAI gdpval dataset on HuggingFace.

Usage:
    pip install datasets
    python scripts/download_source_files.py
"""
import os
import urllib.parse
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
OUTPUT_DIRS = {
    "references": os.path.join(REPO_ROOT, "source_files", "references"),
    "deliverables": os.path.join(REPO_ROOT, "source_files", "deliverables"),
}


def main():
    try:
        from datasets import load_dataset
    except ImportError:
        print("Please install the datasets library: pip install datasets")
        return

    print("Loading gdpval dataset from HuggingFace...")
    ds = load_dataset("openai/gdpval", split="train")

    # Collect all Excel URLs by category
    files_to_download = []  # (url, category)
    for row in ds:
        for url in (row.get("reference_file_urls") or []):
            if url and any(ext in url.lower() for ext in [".xls", ".xlsx", ".xlsm"]):
                files_to_download.append((url, "references"))
        for url in (row.get("deliverable_file_urls") or []):
            if url and any(ext in url.lower() for ext in [".xls", ".xlsx", ".xlsm"]):
                files_to_download.append((url, "deliverables"))

    # Deduplicate by filename
    seen = set()
    unique = []
    for url, cat in files_to_download:
        fname = urllib.parse.unquote(url.split("/")[-1])
        if fname not in seen:
            seen.add(fname)
            unique.append((url, cat, fname))
    files_to_download = unique

    print(f"Found {len(files_to_download)} Excel files to download")

    for cat in OUTPUT_DIRS:
        os.makedirs(OUTPUT_DIRS[cat], exist_ok=True)

    ok = 0
    skipped = 0
    failed = 0
    for i, (url, cat, fname) in enumerate(sorted(files_to_download, key=lambda x: x[2])):
        dest = os.path.join(OUTPUT_DIRS[cat], fname)
        if os.path.exists(dest):
            skipped += 1
            continue
        try:
            urllib.request.urlretrieve(url, dest)
            ok += 1
            if (ok + skipped) % 20 == 0:
                print(f"  {ok + skipped}/{len(files_to_download)} done...")
        except Exception as e:
            failed += 1
            print(f"  FAIL: {fname}: {e}")

    print(f"\nDone: {ok} downloaded, {skipped} already existed, {failed} failed")
    for cat, d in OUTPUT_DIRS.items():
        count = len([f for f in os.listdir(d) if f.endswith((".xlsx", ".xls", ".xlsm"))])
        print(f"  {cat}: {count} files")


if __name__ == "__main__":
    main()
