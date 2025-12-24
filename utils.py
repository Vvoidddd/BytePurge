import hashlib
from pathlib import Path

SYSTEM_PATHS = [
    "windows", "system32", "program files", "program files (x86)",
    "/proc", "/sys"
]

def is_system_path(path: Path) -> bool:
    p = str(path).lower()
    return any(s in p for s in SYSTEM_PATHS)

def hash_file(path: Path, chunk=1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while b := f.read(chunk):
            h.update(b)
    return h.hexdigest()
