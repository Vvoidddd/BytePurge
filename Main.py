__version__ = "1.4"

import sys
import os
import time
import psutil
import GPUtil
import requests
import shutil
import re
from packaging.version import Version
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog,
    QTableWidget, QTableWidgetItem, QLabel, QProgressBar, QMessageBox,
    QCheckBox, QSpinBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QPalette, QIcon

LOG_FILE = "bytepurge.log"
EXTENSIONS = {'.exe', '.msi', '.zip', '.rar', '.tmp', '.log'}

REPO_USER = "Vvoidddd"
REPO_NAME = "BytePurge"
BRANCH = "Main"
FILES = ["Main.py", "scanner.py", "remover.py"]
REMOTE_RAW_BASE = f"https://raw.githubusercontent.com/{REPO_USER}/{REPO_NAME}/{BRANCH}/"
VERSION_PATTERN = re.compile(r"__version__\s*=\s*['\"]([^'\"]+)['\"]")
TIMEOUT = 10

GAME_KEYWORDS = {
    "cod", "call of duty", "steamapps", "epic games", "battle.net", "origin",
    "riot games", "games", "game", "gog galaxy", "blizzard", "ubisoft", "rockstar games"
}

def log(msg: str) -> None:
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")

def format_time(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')

def fetch_remote_version() -> str:
    url = REMOTE_RAW_BASE + "Main.py"
    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    m = VERSION_PATTERN.search(r.text)
    if not m:
        raise RuntimeError("No __version__ found remotely in Main.py")
    return m.group(1)

def fetch_local_version() -> str:
    with open("Main.py", "r", encoding="utf-8") as f:
        content = f.read()
    m = VERSION_PATTERN.search(content)
    if not m:
        raise RuntimeError("No __version__ found locally in Main.py")
    return m.group(1)

def download_file(filename: str) -> bytes:
    url = REMOTE_RAW_BASE + filename
    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return r.content

def run_updater() -> None:
    try:
        remote_ver = Version(fetch_remote_version())
        local_ver = Version(fetch_local_version())
    except Exception as e:
        log(f"Updater error: {e}")
        return

    if remote_ver <= local_ver:
        log(f"Up-to-date (v{local_ver}). No update needed.")
        return

    log(f"Updating from v{local_ver} → v{remote_ver}...")

    for fn in FILES:
        log(f"Downloading {fn}...")
        data = download_file(fn)
        bak = fn + ".old"
        if os.path.exists(fn):
            shutil.copy2(fn, bak)
        with open(fn, "wb") as f:
            f.write(data)

    log("Update complete. Please restart the application.")
    print("Update complete. Please restart the application.")
    sys.exit(0)

def is_game_related(path: Path) -> bool:
    path_str = str(path).lower()
    return any(keyword in path_str for keyword in GAME_KEYWORDS)

def get_score(path: Path, stat, aggressive: bool = False) -> float:
    now = time.time()
    age_days = max(0.0, (now - stat.st_mtime) / 86400.0)
    score = min(age_days / 30.0, 10.0) * 5
    if path.suffix.lower() in EXTENSIONS or aggressive:
        score += 10.0
    return score

def process_file(path: Path, min_age_days: int, aggressive: bool, min_size_mb: int):
    try:
        if is_game_related(path):
            return None
        stat = path.stat()
        age_days = (time.time() - stat.st_mtime) / 86400.0
        if age_days < min_age_days:
            return None
        size_mb = stat.st_size / (1024 ** 2)
        if size_mb < min_size_mb:
            return None
        score = get_score(path, stat, aggressive)
        return {
            "FullPath": str(path),
            "Name": path.name,
            "SizeMB": f"{size_mb:.2f}",
            "LastModified": format_time(stat.st_mtime),
            "Score": score
        }
    except Exception:
        return None

def scan_folder(folder: str, min_age_days: int = 0, aggressive: bool = False, min_size_mb: int = 0):
    files = [Path(root) / f for root, _, fs in os.walk(folder) for f in fs]
    results = []
    with ThreadPoolExecutor(max_workers=os.cpu_count()) as pool:
        futures = [pool.submit(process_file, p, min_age_days, aggressive, min_size_mb) for p in files]
        for f in futures:
            r = f.result()
            if r:
                results.append(r)
    return results

def parallel_delete_files(file_paths: list[str]) -> tuple[list[str], list[str]]:
    removed, failed = [], []
    def delete(path):
        try:
            p = Path(path)
            if p.is_file():
                p.unlink()
                return (path, True)
        except Exception:
            pass
        return (path, False)
    with ThreadPoolExecutor(max_workers=os.cpu_count()) as pool:
        for path, ok in pool.map(delete, file_paths):
            (removed if ok else failed).append(path)
    return removed, failed

DARK_MODE = """
QWidget { background-color: #121212; color: #EEE; }
QTableWidget { background-color: #1E1E1E; color: #DDD; }
QHeaderView::section { background-color: #2C2C2C; color: #CCC; }
QPushButton { background-color: #2D2D2D; color: white; border: 1px solid #444; padding: 4px; }
QPushButton:hover { background-color: #444; }
QProgressBar { border: 1px solid #555; border-radius: 5px; background-color: #2D2D2D; text-align: center; }
QProgressBar::chunk { background-color: #3E9F3E; }
QLabel { color: #BBB; }
"""

class ScanWorker(QThread):
    progress = pyqtSignal(int)
    result = pyqtSignal(list, str)

    def __init__(self, folders: list[str], min_age: int, aggressive: bool, min_size: int):
        super().__init__()
        self.folders = folders
        self.min_age = min_age
        self.aggressive = aggressive
        self.min_size = min_size

    def run(self):
        all_results = []
        total = len(self.folders)
        for idx, folder in enumerate(self.folders):
            try:
                log(f"Scanning: {folder}")
                results = scan_folder(folder, self.min_age, self.aggressive, self.min_size)
                all_results.extend(results)
            except Exception as ex:
                log(f"Scan error: {repr(ex)}")
                self.result.emit([], str(ex))
                return
            self.progress.emit(int(((idx + 1) / total) * 100))
        self.result.emit(all_results, None)

class ColorBox(QLabel):
    def __init__(self, color: QColor, parent=None):
        super().__init__(parent)
        self.setFixedSize(20, 20)
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, color)
        self.setPalette(palette)
        self.setToolTip("Removal Probability Indicator")

class BytePurgeUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowIcon(QIcon("BytePurge.png"))
        self.setMinimumSize(1100, 600)
        self.setWindowTitle("BytePurge")

        self.folder_paths: list[str] = []
        self.entries: set[str] = set()

        self.title_timer = QTimer(self)
        self.title_timer.timeout.connect(self.update_title_with_usage)
        self.title_timer.start(1000)

        self.dark_mode_enabled = False

        layout = QVBoxLayout()
        btns = QHBoxLayout()

        self.folder_label = QLabel("No folder(s) selected")
        layout.addWidget(self.folder_label)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            "Name", "Size (MB)", "Last Modified", "Score", "Removal Probability", "Full Path"
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(self.table.SelectionMode.MultiSelection)
        layout.addWidget(self.table)

        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)

        for name, func in [
            ("Select Folder", self.select_folder),
            ("Scan", self.scan_folders),
            ("Select All", self.select_all),
            ("Deselect All", self.deselect_all),
            ("Delete Selected", self.delete_selected),
            ("Export Log", self.export_log),
            ("Clear Log", self.clear_log),
            ("Dark Mode", self.toggle_dark_mode),
            ("Exit", self.close)
        ]:
            b = QPushButton(name)
            b.clicked.connect(func)
            btns.addWidget(b)

        layout.addLayout(btns)

        filters = QHBoxLayout()
        self.chk_aggressive = QCheckBox("Aggressive Mode")
        self.chk_fullpath = QCheckBox("Show Full Path")
        self.chk_fullpath.setChecked(True)
        self.chk_fullpath.stateChanged.connect(self.toggle_fullpath_column)

        self.spin_age = QSpinBox()
        self.spin_age.setRange(0, 999)
        self.spin_age.setPrefix("Min Age (days): ")
        self.spin_size = QSpinBox()
        self.spin_size.setRange(0, 10000)
        self.spin_size.setPrefix("Min Size (MB): ")

        filters.addWidget(self.chk_aggressive)
        filters.addWidget(self.chk_fullpath)
        filters.addWidget(self.spin_age)
        filters.addWidget(self.spin_size)
        layout.addLayout(filters)

        self.setLayout(layout)

    def update_title_with_usage(self):
        cpu = psutil.cpu_percent()
        gpus = GPUtil.getGPUs()
        gpu = gpus[0].load * 100 if gpus else 0
        self.setWindowTitle(f"BytePurge | CPU {cpu:.0f}% | GPU {gpu:.0f}%")

    def toggle_dark_mode(self):
        self.dark_mode_enabled = not self.dark_mode_enabled
        self.setStyleSheet(DARK_MODE if self.dark_mode_enabled else "")

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder", os.path.expanduser("~"))
        if folder and folder not in self.folder_paths:
            self.folder_paths.append(folder)
            self.folder_label.setText(f"Selected: {'; '.join(self.folder_paths)}")
            log(f"Folder selected: {folder}")

    def scan_folders(self):
        if not self.folder_paths:
            self.folder_label.setText("Select at least one folder.")
            return
        self.entries.clear()
        self.table.setRowCount(0)
        self.progress_bar.setValue(0)
        self.scan_thread = ScanWorker(
            self.folder_paths,
            self.spin_age.value(),
            self.chk_aggressive.isChecked(),
            self.spin_size.value()
        )
        self.scan_thread.progress.connect(self.progress_bar.setValue)
        self.scan_thread.result.connect(self.scan_complete)
        self.scan_thread.start()

    def scan_complete(self, results, err):
        if err:
            self.folder_label.setText(f"Scan failed: {err}")
            return
        for f in results:
            if f["FullPath"] not in self.entries:
                self.entries.add(f["FullPath"])
                self.add_row(f)
        self.folder_label.setText(f"Scan complete: {len(results)} files")

    def add_row(self, data):
        row = self.table.rowCount()
        self.table.insertRow(row)

        self.table.setItem(row, 0, QTableWidgetItem(data["Name"]))
        self.table.setItem(row, 1, QTableWidgetItem(data["SizeMB"]))
        self.table.setItem(row, 2, QTableWidgetItem(data["LastModified"]))
        score_str = f"{data['Score']:.1f}"
        self.table.setItem(row, 3, QTableWidgetItem(score_str))

        score = data["Score"]
        if score >= 15:
            color = QColor(255, 0, 0)  # Red
        elif score >= 7:
            color = QColor(255, 165, 0)  # Orange
        else:
            color = None

        if color:
            self.table.setCellWidget(row, 4, ColorBox(color))
        else:
            self.table.setCellWidget(row, 4, QLabel(""))

        fullpath_text = data["FullPath"] if self.chk_fullpath.isChecked() else ""
        self.table.setItem(row, 5, QTableWidgetItem(fullpath_text))

    def toggle_fullpath_column(self):
        show = self.chk_fullpath.isChecked()
        col = 5
        self.table.setColumnHidden(col, not show)
        # Adjust full path cell texts if toggled
        for row in range(self.table.rowCount()):
            item = self.table.item(row, col)
            if item:
                if show and not item.text():
                    # restore full path stored in item's data (if any)
                    # but here we have no stored data, so do nothing
                    pass
                elif not show:
                    item.setText("")

    def delete_selected(self):
        rows = sorted({i.row() for i in self.table.selectedItems()}, reverse=True)
        if not rows:
            QMessageBox.warning(self, "No Selection", "Select files to delete.")
            return
        paths = [self.table.item(r, 5).text() for r in rows if self.table.item(r, 5)]
        if QMessageBox.question(self, "Confirm", f"Delete {len(paths)} files permanently?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        removed, failed = parallel_delete_files(paths)
        for r in rows:
            path = self.table.item(r, 5).text()
            if path in removed:
                self.table.removeRow(r)
        log(f"Deleted: {len(removed)} files; Failed: {len(failed)}")
        self.folder_label.setText(f"Deleted: {len(removed)}, Failed: {len(failed)}")

    def select_all(self):
        self.table.selectAll()

    def deselect_all(self):
        self.table.clearSelection()

    def export_log(self):
        name = f"bytepurge_export_{datetime.now():%Y%m%d_%H%M%S}.log"
        path, _ = QFileDialog.getSaveFileName(self, "Export Log", name)
        if path:
            try:
                with open(LOG_FILE, "r", encoding="utf-8") as src, open(path, "w", encoding="utf-8") as dst:
                    dst.write(src.read())
                QMessageBox.information(self, "Log Exported", f"Saved to: {path}")
            except Exception as ex:
                QMessageBox.critical(self, "Export Failed", str(ex))

    def clear_log(self):
        try:
            open(LOG_FILE, "w").close()
            log("Log cleared")
            QMessageBox.information(self, "Log Cleared", "Log cleared.")
        except Exception as ex:
            QMessageBox.critical(self, "Clear Failed", str(ex))


if __name__ == "__main__":
    log("===== BytePurge Started =====")
    run_updater()
    app = QApplication(sys.argv)
    ui = BytePurgeUI()
    ui.show()
    sys.exit(app.exec())
