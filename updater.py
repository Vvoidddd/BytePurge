import os
import sys
import requests
import shutil
import re
from packaging.version import Version

REPO_USER = "Vvoidddd"
REPO_NAME = "BytePurge"
BRANCH = "Main"
FILES = ["main.py", "scanner.py", "remover.py"]
REMOTE_RAW_BASE = f"https://raw.githubusercontent.com/{REPO_USER}/{REPO_NAME}/{BRANCH}/"
VERSION_PATTERN = re.compile(r"__version__\s*=\s*['\"]([^'\"]+)['\"]")
TIMEOUT = 10

def fetch_remote_version():
    url = REMOTE_RAW_BASE + "main.py"
    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    m = VERSION_PATTERN.search(r.text)
    if not m:
        raise RuntimeError("No __version__ found remotely in main.py")
    return m.group(1)

def fetch_local_version():
    with open("main.py", "r", encoding="utf-8") as f:
        content = f.read()
    m = VERSION_PATTERN.search(content)
    if not m:
        raise RuntimeError("No __version__ found locally in main.py")
    return m.group(1)

def download_file(filename):
    url = REMOTE_RAW_BASE + filename
    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return r.content

def main():
    try:
        remote_ver = Version(fetch_remote_version())
        local_ver = Version(fetch_local_version())
    except Exception as e:
        print(f"Version error: {e}")
        sys.exit(1)

    if remote_ver <= local_ver:
        print(f"Up-to-date (v{local_ver}). No update needed.")
        return

    print(f"Updating from v{local_ver} → v{remote_ver}...")

    for fn in FILES:
        print(f"- Fetching {fn}")
        data = download_file(fn)
        bak = fn + ".old"
        if os.path.exists(fn):
            shutil.copy2(fn, bak)
        with open(fn, "wb") as f:
            f.write(data)

    print("Update complete. Please restart the application.")

if __name__ == "__main__":
    main()
