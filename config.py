import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".bytepurge"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "folders": [],
    "aggressive": False,
    "min_age": 0,
    "min_size": 0,
    "dark_mode": False,
    "show_full_path": True,
    "dry_run": True,
    "recycle_bin": True,
    "strict_game_exclusion": True,
    "extension_weights": {
        ".log": 5,
        ".tmp": 10,
        ".zip": 8,
        ".rar": 8,
        ".exe": 6,
        ".msi": 6
    },
    "excluded_paths": []
}

def load_config():
    CONFIG_DIR.mkdir(exist_ok=True)
    if not CONFIG_FILE.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_config(cfg):
    CONFIG_DIR.mkdir(exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
