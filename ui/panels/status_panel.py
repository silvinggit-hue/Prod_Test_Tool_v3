from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHeaderView,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ui.mappers.status_summary_mapper import map_status_summary


class _SummaryTable(QTableWidget):
    def __init__(self, row_labels: list[str], *, min_height: int = 260) -> None:
        super().__init__(len(row_labels), 2)

        self._row_labels = list(row_labels)

        self.setHorizontalHeaderLabels(["Key", "Value"])
        self.verticalHeader().setVisible(False)

        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setFocusPolicy(Qt.NoFocus)

        self.setAlternatingRowColors(True)
        self.setWordWrap(True)
        self.setShowGrid(True)
        self.setCornerButtonEnabled(False)

        self.setMinimumHeight(min_height)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFrameShape(QTableWidget.StyledPanel)

        header = self.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setDefaultAlignment(Qt.AlignCenter)

        for row, key in enumerate(self._row_labels):
            key_item = QTableWidgetItem(key)
            key_item.setFlags(Qt.ItemIsEnabled)
            key_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.setItem(row, 0, key_item)

            value_item = QTableWidgetItem("-")
            value_item.setFlags(Qt.ItemIsEnabled)
            value_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.setItem(row, 1, value_item)

        self.resizeRowsToContents()

    def set_values(self, values: dict[str, str]) -> None:
        for row, key in enumerate(self._row_labels):
            text = str(values.get(key, "-") or "-")
            item = self.item(row, 1)
            if item is None:
                item = QTableWidgetItem()
                item.setFlags(Qt.ItemIsEnabled)
                item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                self.setItem(row, 1, item)

            item.setText(text)
            item.setToolTip(text)

        self.resizeRowsToContents()


class StatusPanel(QGroupBox):
    def __init__(self) -> None:
        super().__init__("Status")

        self._row_labels = list(map_status_summary(None).keys())
        self._build_ui()

    def _build_ui(self) -> None:
        self.status_table = _SummaryTable(self._row_labels, min_height=270)

        self.poll_status_button = QPushButton("Reload Status")
        self.poll_status_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.poll_status_button.setMinimumHeight(26)
        self.poll_status_button.setMaximumHeight(26)
        self.poll_status_button.setStyleSheet(
            """
            QPushButton {
                padding: 0px 6px;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 6, 4, 6)
        root.setSpacing(5)
        root.addWidget(self.status_table)
        root.addWidget(self.poll_status_button)

    def set_snapshot(self, snapshot) -> None:
        values = map_status_summary(snapshot)
        self.status_table.set_values(values)

    def clear(self) -> None:
        self.set_snapshot(None)