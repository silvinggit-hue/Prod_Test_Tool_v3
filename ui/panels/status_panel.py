from __future__ import annotations

from PyQt5.QtWidgets import QFormLayout, QGroupBox, QLabel, QPushButton, QVBoxLayout

from ui.mappers.status_summary_mapper import map_status_summary


class StatusPanel(QGroupBox):
    def __init__(self) -> None:
        super().__init__("Status")

        self._labels: dict[str, QLabel] = {}

        form = QFormLayout()
        for field_name in map_status_summary(None).keys():
            value_label = QLabel("-")
            value_label.setWordWrap(True)
            self._labels[field_name] = value_label
            form.addRow(field_name, value_label)

        self.poll_status_button = QPushButton("Poll Status")

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(self.poll_status_button)

    def set_snapshot(self, snapshot) -> None:
        values = map_status_summary(snapshot)
        for key, value in values.items():
            label = self._labels.get(key)
            if label is not None:
                label.setText(value)

    def clear(self) -> None:
        self.set_snapshot(None)