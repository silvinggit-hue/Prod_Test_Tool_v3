from __future__ import annotations

from PyQt5.QtWidgets import QFormLayout, QGroupBox, QLabel, QPushButton, QVBoxLayout

from ui.mappers.info_summary_mapper import map_info_summary


class InfoPanel(QGroupBox):
    def __init__(self) -> None:
        super().__init__("Device Info")

        self._labels: dict[str, QLabel] = {}

        form = QFormLayout()
        for field_name in map_info_summary(None).keys():
            value_label = QLabel("-")
            value_label.setWordWrap(True)
            self._labels[field_name] = value_label
            form.addRow(field_name, value_label)

        self.load_info_button = QPushButton("Load Info")

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(self.load_info_button)

    def set_snapshot(self, snapshot) -> None:
        values = map_info_summary(snapshot)
        for key, value in values.items():
            label = self._labels.get(key)
            if label is not None:
                label.setText(value)

    def clear(self) -> None:
        self.set_snapshot(None)