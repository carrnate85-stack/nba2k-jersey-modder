from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal, Slot
from PySide6.QtWidgets import QMessageBox, QWidget


class WorkerSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class Worker(QRunnable):
    def __init__(self, callback) -> None:
        super().__init__(); self.callback = callback; self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self.callback()
        except Exception as exc:
            try: self.signals.failed.emit(str(exc))
            except RuntimeError: pass
            return
        try: self.signals.finished.emit(result)
        except RuntimeError: pass


class FeaturePage(QWidget):
    def show_error(self, title: str, error: object) -> None:
        QMessageBox.critical(self, title, str(error))

    def show_info(self, title: str, text: str) -> None:
        QMessageBox.information(self, title, text)
