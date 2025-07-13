import sys
import os
import argparse
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

def delete_path(path: Path, dry_run: bool, recursive: bool):
    if dry_run:
        logging.info(f"[DRY-RUN] Would delete: {path}")
        return str(path), True

    try:
        if path.is_file():
            path.unlink()
            logging.info(f"Deleted file: {path}")
            return str(path), True
        elif path.is_dir() and recursive:
            for child in path.rglob("*"):
                if child.is_file():
                    try:
                        child.unlink()
                    except Exception as e:
                        logging.error(f"Failed to delete {child}: {e}")
            path.rmdir()
            logging.info(f"Deleted directory: {path}")
            return str(path), True
        else:
            logging.warning(f"Skipped (not a file or missing --recursive): {path}")
    except Exception as e:
        logging.error(f"Failed to delete {path}: {e}")
    return str(path), False

def remove_files(paths: list[str], dry_run: bool, recursive: bool, max_workers: int):
    removed, failed = [], []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for path, ok in pool.map(lambda p: delete_path(Path(p), dry_run, recursive), paths):
            (removed if ok else failed).append(path)
    return removed, failed

def print_summary(removed, failed):
    print(f"\n\033[92mRemoved: {len(removed)}\033[0m")
    if removed:
        for f in removed:
            print(f"  \033[92m✔ {f}\033[0m")
    if failed:
        print(f"\n\033[91mFailed : {len(failed)}\033[0m", file=sys.stderr)
        for f in failed:
            print(f"  \033[91m✘ {f}\033[0m", file=sys.stderr)

def main():
    parser = argparse.ArgumentParser(
        description="Delete files or directories. Supports dry-run, logging, and multithreading."
    )
    parser.add_argument("files", nargs="+", help="Paths to delete")
    parser.add_argument("--dry-run", action="store_true", help="Only show what would be deleted")
    parser.add_argument("--recursive", action="store_true", help="Allow recursive folder deletion")
    parser.add_argument("--force", action="store_true", help="Skip confirmation prompt")
    parser.add_argument("--log-deleted", metavar="LOGFILE", help="Append deletion log to file")
    parser.add_argument("--workers", type=int, default=os.cpu_count(), help="Max parallel threads")

    args = parser.parse_args()

    if not args.force:
        confirm = input(f"Delete {len(args.files)} path(s)? This cannot be undone. Proceed? [y/N] ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            sys.exit(0)

    handlers = [logging.StreamHandler(sys.stderr)]
    if args.log_deleted:
        handlers.append(logging.FileHandler(args.log_deleted))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        handlers=handlers
    )

    removed, failed = remove_files(args.files, args.dry_run, args.recursive, args.workers)
    print_summary(removed, failed)

    sys.exit(1 if failed else 0)

if __name__ == "__main__":
    main()
