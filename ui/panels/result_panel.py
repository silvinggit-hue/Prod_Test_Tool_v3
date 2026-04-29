from __future__ import annotations

from PyQt5.QtWidgets import QGroupBox, QTextEdit, QVBoxLayout, QSizePolicy


class ResultPanel(QGroupBox):
    def __init__(self) -> None:
        super().__init__("Result")

        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setMinimumHeight(78)
        self.text_edit.setMaximumHeight(90)
        self.text_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        layout.addWidget(self.text_edit)

    def set_text(self, text: str) -> None:
        self.text_edit.setPlainText(text)

    def append_text(self, text: str) -> None:
        current = self.text_edit.toPlainText().strip()
        if current:
            self.text_edit.append(text)
        else:
            self.text_edit.setPlainText(text)

    def clear(self) -> None:
        self.text_edit.clear()