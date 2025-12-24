import sys, os
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QTableWidget, QTableWidgetItem,
    QLabel, QProgressBar, QMessageBox, QCheckBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from scanner import scan_folder
from remover import remove_paths, human_size
from config import load_config

class DeleteWorker(QThread):
    finished = pyqtSignal(dict)

    def __init__(self, paths, dry_run, recycle):
        super().__init__()
        self.paths = paths
        self.dry_run = dry_run
        self.recycle = recycle

    def run(self):
        result = remove_paths(self.paths, dry_run=self.dry_run, recycle=self.recycle)
        self.finished.emit(result)

class BytePurgeUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BytePurge")
        self.resize(1200, 650)

        self.config = load_config()
        self.folder_paths = []

        layout = QVBoxLayout(self)

        self.status = QLabel("Idle")
        layout.addWidget(self.status)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Name", "Size (MB)", "Last Modified", "Score", "Risk", "Full Path"])
        self.table.setSortingEnabled(True)
        layout.addWidget(self.table)

        self.progress = QProgressBar()
        layout.addWidget(self.progress)

        controls = QHBoxLayout()
        self.chk_dry = QCheckBox("Dry-Run"); self.chk_dry.setChecked(True)
        self.chk_recycle = QCheckBox("Recycle Bin"); self.chk_recycle.setChecked(True)
        controls.addWidget(self.chk_dry); controls.addWidget(self.chk_recycle)

        for name, fn in [("Select Folder", self.select_folder), ("Scan", self.scan), ("Delete Selected", self.delete_selected), ("Exit", self.close)]:
            b = QPushButton(name); b.clicked.connect(fn); controls.addWidget(b)

        layout.addLayout(controls)

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder", os.path.expanduser("~"))
        if folder: self.folder_paths = [folder]; self.status.setText(f"Selected: {folder}")

    def scan(self):
        self.table.setRowCount(0)
        if not self.folder_paths:
            QMessageBox.warning(self, "No Folder", "Select a folder first."); return
        self.status.setText("Scanning...")
        results = scan_folder(self.folder_paths, self.config)
        for r in results:
            row = self.table.rowCount(); self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(r["Name"]))
            self.table.setItem(row, 1, QTableWidgetItem(str(r["SizeMB"])))
            self.table.setItem(row, 2, QTableWidgetItem(r["LastModified"]))
            self.table.setItem(row, 3, QTableWidgetItem(str(r["Score"])))
            risk = "High" if r["Score"] >= 15 else "Medium" if r["Score"] >= 7 else "Low"
            self.table.setItem(row, 4, QTableWidgetItem(risk))
            self.table.setItem(row, 5, QTableWidgetItem(r["FullPath"]))
        self.status.setText(f"Scan complete: {len(results)} files")

    def delete_selected(self):
        rows = sorted({i.row() for i in self.table.selectedItems()}, reverse=True)
        if not rows: QMessageBox.warning(self, "No Selection", "Select files to delete."); return
        paths = [self.table.item(r, 5).text() for r in rows]
        self.worker = DeleteWorker(paths, self.chk_dry.isChecked(), self.chk_recycle.isChecked())
        self.worker.finished.connect(self.delete_complete)
        self.worker.start()

    def delete_complete(self, result):
        QMessageBox.information(self, "Delete Summary",
            f"Removed: {len(result['removed'])}\nFailed: {len(result['failed'])}\nFreed: {human_size(result['bytes_freed'])}\nMode: {'DRY-RUN' if result['dry_run'] else 'LIVE'}"
        )

if __name__ == "__main__":
    app = QApplication(sys.argv)
    ui = BytePurgeUI(); ui.show()
    sys.exit(app.exec())
