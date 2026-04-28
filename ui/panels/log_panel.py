from __future__ import annotations

from datetime import datetime

from PyQt5.QtWidgets import QGroupBox, QTextEdit, QVBoxLayout


class LogPanel(QGroupBox):
    def __init__(self, title: str = "System Log") -> None:
        super().__init__(title)

        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)

        layout = QVBoxLayout(self)
        layout.addWidget(self.text_edit)

    def append_line(self, text: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.text_edit.append(f"[{timestamp}] {text}")

    def clear(self) -> None:
        self.text_edit.clear()