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
GAME_KEYWORDS = {
    "cod", "call of duty", "steamapps", "epic games", "battle.net",
    "origin", "riot games", "games", "game", "gog galaxy",
    "blizzard", "ubisoft", "rockstar games"
}
MAX_WORKERS = max(4, os.cpu_count() or 1)

def is_game_related(path: Path) -> bool:
    lower = str(path).lower()
    return any(keyword in lower for keyword in GAME_KEYWORDS)

def format_time(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')

def get_score(path: Path, stat, aggressive: bool) -> float:
    age_days = max(0.0, (time.time() - stat.st_mtime) / 86400.0)
    score = min(age_days / 30.0, 10.0) * 5
    if aggressive or path.suffix.lower() in EXTENSIONS:
        score += 10.0
    return score

def process_file(path: Path, min_age: int, min_size: float, aggressive: bool):
    try:
        if is_game_related(path):
            return None
        stat = path.stat()
        age_days = (time.time() - stat.st_mtime) / 86400.0
        if age_days < min_age:
            return None
        size_mb = stat.st_size / (1024 ** 2)
        if size_mb < min_size:
            return None
        return {
            "Name": path.name,
            "FullPath": str(path),
            "SizeMB": round(size_mb, 2),
            "LastModified": format_time(stat.st_mtime),
            "Score": round(get_score(path, stat, aggressive), 1)
        }
    except Exception:
        return None

def scan_folder(folder: Path, min_age: int, min_size: float, aggressive: bool) -> list:
    all_files = [Path(root) / name for root, _, files in os.walk(folder) for name in files]
    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(process_file, f, min_age, min_size, aggressive) for f in all_files]
        for fut in as_completed(futures):
            r = fut.result()
            if r:
                results.append(r)
    return results

def main():
    parser = argparse.ArgumentParser(description="BytePurge CLI Scanner")
    parser.add_argument("folder", type=Path, help="Target folder to scan")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument("--min-score", type=float, default=0.0, help="Filter files below this score")
    parser.add_argument("--min-age", type=int, default=0, help="Minimum file age in days")
    parser.add_argument("--min-size", type=float, default=0.0, help="Minimum file size in MB")
    parser.add_argument("--aggressive", action="store_true", help="Score all extensions aggressively")
    args = parser.parse_args()

    folder = args.folder.resolve()
    if not folder.is_dir():
        sys.stderr.write(f"Error: '{folder}' is not a directory\n")
        sys.exit(1)

    results = scan_folder(folder, args.min_age, args.min_size, args.aggressive)
    results = [r for r in results if r["Score"] >= args.min_score]
    results.sort(key=lambda r: -r["Score"])

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
