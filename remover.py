import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

try:
    from send2trash import send2trash
except ImportError:
    send2trash = None

MAX_WORKERS = min(os.cpu_count() or 4, 8)

def delete_single(path: Path, *, dry_run: bool, recycle: bool):
    try:
        if not path.exists():
            return str(path), False, 0, "Path does not exist"

        size = path.stat().st_size if path.is_file() else 0

        if dry_run:
            return str(path), True, 0, None

        if recycle and send2trash:
            send2trash(str(path))
        else:
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                for child in path.rglob("*"):
                    if child.is_file():
                        child.unlink()
                path.rmdir()

        return str(path), True, size, None
    except Exception as e:
        return str(path), False, 0, str(e)

def remove_paths(paths, *, dry_run: bool, recycle: bool, workers=MAX_WORKERS):
    results = {"removed": [], "failed": [], "bytes_freed": 0, "dry_run": dry_run}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(delete_single, Path(p), dry_run=dry_run, recycle=recycle) for p in paths]

        for fut in futures:
            path, ok, freed, err = fut.result()
            if ok:
                results["removed"].append(path)
                results["bytes_freed"] += freed
            else:
                results["failed"].append({"path": path, "error": err})

    return results

def human_size(num: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num < 1024:
            return f"{num:.2f} {unit}"
        num /= 1024
    return "∞"
