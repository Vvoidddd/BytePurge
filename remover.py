import os
import sys
from pathlib import Path

def remove_files(file_paths):
    removed = []
    failed = []
    for file_path in file_paths:
        try:
            p = Path(file_path)
            if p.is_file():
                p.unlink()
                removed.append(file_path)
            else:
                failed.append(file_path)
        except Exception:
            failed.append(file_path)
    return removed, failed

def main():
    if len(sys.argv) < 2:
        print("Usage: remover.py <file1> <file2> ...", file=sys.stderr)
        sys.exit(1)

    files = sys.argv[1:]
    removed, failed = remove_files(files)

    for f in removed:
        print(f"Deleted: {f}")
    for f in failed:
        print(f"Failed: {f}", file=sys.stderr)

    sys.exit(0 if not failed else 1)

if __name__ == "__main__":
    main()
