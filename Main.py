__version__ = "1.3"

import sys
import os
import time
import psutil
import GPUtil
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog,
    QTableWidget, QTableWidgetItem, QLabel, QProgressBar, QMessageBox,
    QCheckBox, QSpinBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QIcon

LOG_FILE = "bytepurge.log"
EXTENSIONS = {'.exe', '.msi', '.zip', '.rar', '.tmp', '.log'}

def log(msg):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")

def format_time(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')

def get_score(path: Path, stat, aggressive=False) -> float:
    now = time.time()
    age_days = max(0.0, (now - stat.st_mtime) / 86400.0)
    score = min(age_days / 30.0, 10.0) * 5
    if path.suffix.lower() in EXTENSIONS or aggressive:
        score += 10.0
    return score

def process_file(path: Path, min_age_days, aggressive, min_size_mb):
    try:
        stat = path.stat()
        age_days = (time.time() - stat.st_mtime) / 86400.0
        if age_days < min_age_days:
            return None
        size_mb = stat.st_size / (1024 ** 2)
        if size_mb < min_size_mb:
            return None
        return {
            "FullPath": str(path),
            "Name": path.name,
            "SizeMB": f"{size_mb:.2f}",
            "LastModified": format_time(stat.st_mtime),
            "Score": f"{get_score(path, stat, aggressive):.1f}"
        }
    except Exception:
        return None

def scan_folder(folder: str, min_age_days=0, aggressive=False, min_size_mb=0):
    files = [Path(root) / f for root, _, fs in os.walk(folder) for f in fs]
    results = []
    with ThreadPoolExecutor(max_workers=os.cpu_count()) as pool:
        futures = [pool.submit(process_file, p, min_age_days, aggressive, min_size_mb) for p in files]
        for f in futures:
            r = f.result()
            if r:
                results.append(r)
    return results

def parallel_delete_files(file_paths):
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

    def __init__(self, folders, min_age, aggressive, min_size):
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

class BytePurgeUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowIcon(QIcon("BytePurge.png"))
        self.setMinimumSize(1000, 600)
        self.setWindowTitle("BytePurge")

        self.folder_paths = []
        self.entries = set()

        self.title_timer = QTimer(self)
        self.title_timer.timeout.connect(self.update_title_with_usage)
        self.title_timer.start(1000)

        self.dark_mode_enabled = False

        layout = QVBoxLayout()
        btns = QHBoxLayout()

        self.folder_label = QLabel("No folder(s) selected")
        layout.addWidget(self.folder_label)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Name", "Size (MB)", "Last Modified", "Score", "Full Path"])
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
        self.table.setItem(row, 3, QTableWidgetItem(data["Score"]))
        self.table.setItem(row, 4, QTableWidgetItem(data["FullPath"] if self.chk_fullpath.isChecked() else ""))

    def delete_selected(self):
        rows = sorted({i.row() for i in self.table.selectedItems()}, reverse=True)
        if not rows:
            QMessageBox.warning(self, "No Selection", "Select files to delete.")
            return
        paths = [self.table.item(r, 4).text() for r in rows]
        if QMessageBox.question(self, "Confirm", f"Delete {len(paths)} files permanently?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        removed, failed = parallel_delete_files(paths)
        for r in rows:
            path = self.table.item(r, 4).text()
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
    app = QApplication(sys.argv)
    ui = BytePurgeUI()
    ui.show()
    sys.exit(app.exec())
