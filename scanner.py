import os
import sys
import csv
import time
import io
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

EXTENSIONS = {'.exe', '.msi', '.zip', '.rar', '.tmp', '.log'}
MAX_WORKERS = max(4, os.cpu_count() or 1)

def get_score(path: Path, stat) -> float:
    now = time.time()
    age_days = max(0.0, (now - stat.st_mtime) / 86400.0)
    score = min(age_days / 30.0, 10.0) * 5
    if path.suffix.lower() in EXTENSIONS:
        score += 10.0
    return score

def format_time(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')

def process_file(path: Path):
    try:
        stat = path.stat()
        return {
            "Name": path.name,
            "SizeMB": f"{stat.st_size / (1024 ** 2):.2f}",
            "LastModified": format_time(stat.st_mtime),
            "Score": f"{get_score(path, stat):.1f}"
        }
    except Exception:
        return None

def scan_folder_parallel(folder: str):
    files = [Path(root) / f for root, _, fs in os.walk(folder) for f in fs]
    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(process_file, p) for p in files]
        for fut in as_completed(futures):
            r = fut.result()
            if r:
                results.append(r)
    return results

def main():
    if len(sys.argv) != 2:
        print("Usage: scanner.py <folder_path>", file=sys.stderr)
        sys.exit(1)

    folder = sys.argv[1]
    if not os.path.isdir(folder):
        print("Invalid folder path", file=sys.stderr)
        sys.exit(1)

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', newline='')
    writer = csv.DictWriter(sys.stdout, fieldnames=["Name", "SizeMB", "LastModified", "Score"])
    writer.writeheader()

    for row in scan_folder_parallel(folder):
        writer.writerow(row)

if __name__ == "__main__":
    main()
