import os
import sys
import csv
import json
import time
import argparse
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

EXTENSIONS = {'.exe', '.msi', '.zip', '.rar', '.tmp', '.log'}
MAX_WORKERS = max(4, os.cpu_count() or 1)

def get_score(path: Path, stat, aggressive: bool) -> float:
    now = time.time()
    age_days = max(0.0, (now - stat.st_mtime) / 86400.0)
    score = min(age_days / 30.0, 10.0) * 5
    if aggressive or path.suffix.lower() in EXTENSIONS:
        score += 10.0
    return score

def format_time(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')

def process_file(path: Path, min_age: int, min_size: float, aggressive: bool):
    try:
        stat = path.stat()
    except Exception:
        return None
    age_days = (time.time() - stat.st_mtime) / 86400.0
    if age_days < min_age:
        return None
    size_mb = stat.st_size / (1024 ** 2)
    if size_mb < min_size:
        return None

    score = get_score(path, stat, aggressive)
    return {
        "Name": path.name,
        "FullPath": str(path),
        "SizeMB": round(size_mb, 2),
        "LastModified": format_time(stat.st_mtime),
        "Score": round(score, 1)
    }

def scan_folder(folder: Path, min_age: int, min_size: float, aggressive: bool):
    results = []
    all_files = [folder / f for root, _, files in os.walk(folder) for f in files for folder in [Path(root)]]
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [
            pool.submit(process_file, path, min_age, min_size, aggressive)
            for path in all_files
        ]
        for fut in as_completed(futures):
            r = fut.result()
            if r:
                results.append(r)
    return results

def main():
    parser = argparse.ArgumentParser(
        description="Scan a folder for files, score them by age/extension, and output CSV or JSON."
    )
    parser.add_argument("folder", type=Path, help="Path to folder to scan")
    parser.add_argument("--json", action="store_true", help="Output results in JSON")
    parser.add_argument("--min-score", type=float, default=0.0, help="Filter out files with score below this")
    parser.add_argument("--min-age", type=int, default=0, help="Only include files older than X days")
    parser.add_argument("--min-size", type=float, default=0.0, help="Only include files larger than X MB")
    parser.add_argument("--aggressive", action="store_true", help="Treat all extensions as high-priority")
    args = parser.parse_args()

    folder = args.folder.resolve()
    if not folder.is_dir():
        sys.stderr.write(f"Error: '{folder}' is not a valid directory\n")
        sys.exit(1)

    results = scan_folder(folder, args.min_age, args.min_size, args.aggressive)
    # apply min_score filter
    results = [r for r in results if r["Score"] >= args.min_score]

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        writer = csv.DictWriter(
            sys.stdout,
            fieldnames=["Name", "FullPath", "SizeMB", "LastModified", "Score"]
        )
        writer.writeheader()
        for row in results:
            writer.writerow(row)

if __name__ == "__main__":
    main()
