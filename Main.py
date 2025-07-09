import sys
import os
import csv
import time
import psutil
import GPUtil
from io import StringIO
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog,
    QTableWidget, QTableWidgetItem, QLabel, QProgressBar, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QIcon

LOG_FILE = "bytepurge.log"
EXTENSIONS = {'.exe', '.msi', '.zip', '.rar', '.tmp', '.log'}

def log(msg):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")

def get_score(path: Path, stat) -> float:
    now = time.time()
    age_days = max(0.0, (now - stat.st_mtime) / 86400.0)
    score = min(age_days / 30.0, 10.0) * 5
    if path.suffix.lower() in EXTENSIONS:
        score += 10.0
    return score

def format_time(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')

def process_file(path: Path):
    try:
        stat = path.stat()
        return {
            "Name": path.name,
            "SizeMB": f"{stat.st_size / (1024 ** 2):.2f}",
            "LastModified": format_time(stat.st_mtime),
            "Score": f"{get_score(path, stat):.1f}"
        }
    except Exception:
        return None

def scan_folder(folder: str):
    files = [Path(root) / f for root, _, fs in os.walk(folder) for f in fs]
    results = []
    with ThreadPoolExecutor(max_workers=os.cpu_count()) as pool:
        futures = [pool.submit(process_file, p) for p in files]
        for fut in as_completed(futures):
            r = fut.result()
            if r:
                results.append(r)
    return results

class ScanWorker(QThread):
    progress = pyqtSignal(int)
    result = pyqtSignal(list, str)

    def __init__(self, folders):
        super().__init__()
        self.folders = folders

    def run(self):
        all_results = []
        total = len(self.folders)
        for idx, folder in enumerate(self.folders):
            try:
                log(f"Scanning: {folder}")
                results = scan_folder(folder)
                all_results.extend(results)
            except Exception as ex:
                log(f"Scan error: {repr(ex)}")
                self.result.emit([], str(ex))
                return
            self.progress.emit(int(((idx + 1) / total) * 100))
        self.result.emit(all_results, None)

class RemoveWorker(QThread):
    finished = pyqtSignal(list, list, str)

    def __init__(self, files):
        super().__init__()
        self.files = files

    def run(self):
        removed, failed = [], []
        for f in self.files:
            try:
                if os.path.isfile(f):
                    os.remove(f)
                    removed.append(f)
                else:
                    failed.append(f)
            except Exception:
                failed.append(f)
        self.finished.emit(removed, failed, None)

class BytePurgeUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowIcon(QIcon("BytePurge.png"))  # Set window icon here
        self.folder_paths = []
        self.setMinimumSize(900, 550)
        self.setWindowTitle("BytePurge - Smart Cleanup Assistant")

        self.title_timer = QTimer(self)
        self.title_timer.timeout.connect(self.update_title_with_usage)
        self.title_timer.start(1000)

        layout = QVBoxLayout()
        btns = QHBoxLayout()

        self.folder_label = QLabel("No folder(s) selected")
        self.folder_label.setStyleSheet("color: gray; font-style: italic;")

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Name", "Size (MB)", "Last Modified", "Score"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(self.table.SelectionMode.MultiSelection)

        self.progress_bar = QProgressBar()

        buttons = [
            ("Select Folder", self.select_folders),
            ("Scan", self.scan_folders),
            ("Select All", self.select_all),
            ("Deselect All", self.deselect_all),
            ("Delete Selected", self.delete_selected),
            ("Export Log", self.export_log),
            ("Clear Log", self.clear_log),
            ("Exit", self.close)
        ]
        for label, handler in buttons:
            btn = QPushButton(label)
            btn.clicked.connect(handler)
            btns.addWidget(btn)
        btns.addStretch()

        layout.addWidget(self.folder_label)
        layout.addLayout(btns)
        layout.addWidget(self.table)
        layout.addWidget(self.progress_bar)
        self.setLayout(layout)

    def update_title_with_usage(self):
        cpu = psutil.cpu_percent()
        gpus = GPUtil.getGPUs()
        gpu = gpus[0].load * 100 if gpus else 0
        self.setWindowTitle(f"BytePurge - Smart Cleanup Assistant | CPU {cpu:.0f}% | GPU {gpu:.0f}%")

    def select_folders(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder", os.path.expanduser("~"))
        if folder:
            self.folder_paths = [folder]
            self.folder_label.setText(f"Selected: {folder}")
            self.folder_label.setStyleSheet("color: black; font-weight: bold;")
            self.table.setRowCount(0)
            log(f"Folder selected: {folder}")

    def scan_folders(self):
        if not self.folder_paths:
            self.folder_label.setText("Select at least one folder first.")
            self.folder_label.setStyleSheet("color: red; font-weight: bold;")
            return

        self.progress_bar.setValue(0)
        self.table.setRowCount(0)
        self.folder_label.setText("Scanning...")
        self.folder_label.setStyleSheet("color: blue; font-weight: bold;")

        self.scan_thread = ScanWorker(self.folder_paths)
        self.scan_thread.progress.connect(self.progress_bar.setValue)
        self.scan_thread.result.connect(self.on_scan_complete)
        self.scan_thread.start()

    def on_scan_complete(self, files, error):
        if error:
            self.folder_label.setText(f"Scan error: {error}")
            self.folder_label.setStyleSheet("color: red; font-weight: bold;")
            return
        for f in files:
            self.add_file_row(f["Name"], f["SizeMB"], f["LastModified"], f["Score"])
        self.folder_label.setText(f"Scan complete: {len(files)} files.")
        self.folder_label.setStyleSheet("color: green; font-weight: bold;")
        log(f"Scan complete: {len(files)} files found.")

    def add_file_row(self, name, size, mod, score):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(name))
        self.table.setItem(row, 1, QTableWidgetItem(size))
        self.table.setItem(row, 2, QTableWidgetItem(mod))
        self.table.setItem(row, 3, QTableWidgetItem(score))

    def delete_selected(self):
        selected_rows = sorted({i.row() for i in self.table.selectedItems()}, reverse=True)
        if not selected_rows:
            QMessageBox.warning(self, "No Selection", "Select files to delete.")
            return
        folder = self.folder_paths[0] if self.folder_paths else None
        if not folder:
            return
        files = [os.path.join(folder, self.table.item(r, 0).text()) for r in selected_rows]
        confirm = QMessageBox.question(
            self, "Confirm Deletion", f"Delete {len(files)} files permanently?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self.remove_thread = RemoveWorker(files)
        self.remove_thread.finished.connect(self.on_delete_finished)
        self.remove_thread.start()
        self.folder_label.setText("Deleting files...")
        self.folder_label.setStyleSheet("color: blue; font-weight: bold;")
        self.progress_bar.setValue(0)

    def on_delete_finished(self, removed, failed, error):
        folder = self.folder_paths[0] if self.folder_paths else None
        for i in reversed(range(self.table.rowCount())):
            path = os.path.join(folder, self.table.item(i, 0).text())
            if path in removed:
                self.table.removeRow(i)
        self.progress_bar.setValue(100)
        msg = f"Deleted {len(removed)} files; Failed {len(failed)}."
        color = "green" if not failed else "orange"
        self.folder_label.setText(msg)
        self.folder_label.setStyleSheet(f"color: {color}; font-weight: bold;")
        for f in removed: log(f"Deleted: {f}")
        for f in failed: log(f"Failed to delete: {f}")

    def select_all(self):
        self.table.selectAll()

    def deselect_all(self):
        self.table.clearSelection()

    def export_log(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Log", "bytepurge_export.log")
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
            QMessageBox.information(self, "Log Cleared", "Log has been cleared.")
        except Exception as ex:
            QMessageBox.critical(self, "Clear Failed", str(ex))

if __name__ == "__main__":
    log("===== BytePurge Started =====")
    app = QApplication(sys.argv)
    ui = BytePurgeUI()
    ui.show()
    sys.exit(app.exec())
