import os
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils import hash_file, is_system_path

MAX_WORKERS = min(os.cpu_count() or 4, 8)

GAME_KEYWORDS = {
    "steamapps", "epic games", "battle.net", "riot games",
    "gog galaxy", "blizzard", "ubisoft", "rockstar"
}

def is_game_related(path: Path, strict: bool) -> bool:
    if not strict:
        return False
    p = str(path).lower()
    return any(k in p for k in GAME_KEYWORDS)

def score_file(path: Path, stat, aggressive, weights):
    age_days = (time.time() - stat.st_mtime) / 86400
    score = min(age_days / 30, 10) * 5
    score += weights.get(path.suffix.lower(), 0)
    if aggressive:
        score += 5
    return round(score, 1)

def scan_folder(folders, config, progress_cb=None, cancel_flag=None):
    results = []
    seen_hashes = {}
    files = []

    if isinstance(folders, (str, Path)):
        folders = [folders]

    for folder in folders:
        for root, _, fs in os.walk(folder):
            for f in fs:
                p = Path(root) / f
                if is_system_path(p):
                    continue
                files.append(p)

    total = len(files)

    def worker(path):
        if cancel_flag and cancel_flag():
            return None
        try:
            if is_game_related(path, config.get("strict_game_exclusion", True)):
                return None
            stat = path.stat()
            size_mb = stat.st_size / (1024 ** 2)
            if size_mb < config.get("min_size", 0):
                return None
            age_days = (time.time() - stat.st_mtime) / 86400
            if age_days < config.get("min_age", 0):
                return None

            dup = None
            if size_mb >= 50:
                h = hash_file(path)
                dup = seen_hashes.get(h)
                seen_hashes[h] = str(path)

            return {
                "Name": path.name,
                "FullPath": str(path),
                "SizeMB": round(size_mb, 2),
                "LastModified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
                "Score": score_file(path, stat, config.get("aggressive", False), config.get("extension_weights", {})),
                "DuplicateOf": dup
            }
        except Exception:
            return None

    with ThreadPoolExecutor(MAX_WORKERS) as pool:
        futures = [pool.submit(worker, f) for f in files]
        for i, fut in enumerate(as_completed(futures), 1):
            if progress_cb and i % 50 == 0:
                progress_cb(i, total)
            r = fut.result()
            if r:
                results.append(r)

    return sorted(results, key=lambda x: -x["Score"])
