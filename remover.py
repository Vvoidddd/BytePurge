import sys
import os
import argparse
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

def delete_file(path: Path, dry_run: bool):
    if dry_run:
        logging.info(f"[DRY-RUN] Would delete: {path}")
        return path, True
    try:
        if path.is_file():
            path.unlink()
            logging.info(f"Deleted: {path}")
            return path, True
    except Exception as e:
        logging.error(f"Failed to delete {path}: {e}")
    return path, False

def remove_files(paths, dry_run: bool, max_workers: int):
    removed, failed = [], []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for path_str, ok in pool.map(lambda p: delete_file(Path(p), dry_run), paths):
            (removed if ok else failed).append(str(path_str))
    return removed, failed

def main():
    parser = argparse.ArgumentParser(
        description="Delete specified files (optionally dry-run) and log results."
    )
    parser.add_argument(
        "files", nargs="+", help="Files to delete"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be deleted without removing"
    )
    parser.add_argument(
        "--log-deleted", metavar="LOGFILE", help="Append deletion results to LOGFILE"
    )
    parser.add_argument(
        "--workers", type=int, default=None, help="Number of parallel deletion threads"
    )
    args = parser.parse_args()

    # configure logging
    handlers = [logging.StreamHandler(sys.stderr)]
    if args.log_deleted:
        handlers.append(logging.FileHandler(args.log_deleted))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        handlers=handlers
    )

    max_workers = args.workers or max(1, os.cpu_count() // 2)
    removed, failed = remove_files(args.files, args.dry_run, max_workers)

    # summary to stdout
    print(f"Removed: {len(removed)}")
    if failed:
        print(f"Failed : {len(failed)}", file=sys.stderr)
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    main()
