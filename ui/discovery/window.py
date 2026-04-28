from __future__ import annotations

import ipaddress
from dataclasses import dataclass, replace

from PyQt5.QtCore import QAbstractTableModel, QModelIndex, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog,
    QFormLayout,
    QGridLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class DiscoveryRow:
    selected: bool = False
    ip: str = ""
    mac: str = "-"
    mac12: str = "-"
    model: str = "-"
    firmware: str = "-"
    lens: str = "-"
    note: str = "-"


class DiscoveryTableModel(QAbstractTableModel):
    COLUMN_KEYS: tuple[str, ...] = (
        "selected",
        "ip",
        "mac",
        "mac12",
        "model",
        "firmware",
        "lens",
        "note",
    )

    COLUMN_LABELS: dict[str, str] = {
        "selected": "Sel",
        "ip": "IP",
        "mac": "MAC",
        "mac12": "MAC12",
        "model": "Model",
        "firmware": "Firmware",
        "lens": "Lens",
        "note": "Note",
    }

    @staticmethod
    def _sort_rows_asc_by_ip(rows: list["DiscoveryRow"]) -> list["DiscoveryRow"]:
        def sort_key(row):
            ip = getattr(row, "ip", "")
            try:
                return (0, int(ipaddress.ip_address(ip)))
            except Exception:
                return (1, ip)

        return sorted(rows, key=sort_key)

    def __init__(self) -> None:
        super().__init__()
        self._rows: list[DiscoveryRow] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self.COLUMN_KEYS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal and 0 <= section < len(self.COLUMN_KEYS):
            return self.COLUMN_LABELS[self.COLUMN_KEYS[section]]
        return None

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.NoItemFlags
        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if self.COLUMN_KEYS[index.column()] == "selected":
            flags |= Qt.ItemIsUserCheckable
        return flags

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None

        row = self._rows[index.row()]
        key = self.COLUMN_KEYS[index.column()]

        if key == "selected" and role == Qt.CheckStateRole:
            return Qt.Checked if row.selected else Qt.Unchecked

        if role == Qt.DisplayRole:
            if key == "selected":
                return ""
            return getattr(row, key)

        if role == Qt.TextAlignmentRole:
            return int(Qt.AlignCenter) if key == "selected" else int(Qt.AlignVCenter | Qt.AlignLeft)

        return None

    def setData(self, index: QModelIndex, value, role: int = Qt.EditRole):
        if not index.isValid():
            return False
        key = self.COLUMN_KEYS[index.column()]
        if key != "selected" or role != Qt.CheckStateRole:
            return False

        checked = value == Qt.Checked
        self._rows[index.row()] = replace(self._rows[index.row()], selected=checked)
        self.dataChanged.emit(index, index, [Qt.CheckStateRole, Qt.DisplayRole])
        return True

    def clear_rows(self) -> None:
        self.beginResetModel()
        self._rows = []
        self.endResetModel()

    def set_rows(self, rows: list[DiscoveryRow]) -> None:
        self.beginResetModel()
        self._rows = self._sort_rows_asc_by_ip(list(rows))
        self.endResetModel()

    def selected_rows(self) -> list[DiscoveryRow]:
        return [row for row in self._rows if row.selected]

    def all_rows(self) -> list[DiscoveryRow]:
        return list(self._rows)

    def toggle_all(self) -> None:
        if not self._rows:
            return
        all_selected = all(row.selected for row in self._rows)
        self.beginResetModel()
        self._rows = [replace(row, selected=(not all_selected)) for row in self._rows]
        self.endResetModel()


class DiscoveryWindow(QDialog):
    scan_requested = pyqtSignal()
    stop_requested = pyqtSignal()
    add_selected_requested = pyqtSignal()
    add_all_requested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("IP Discovery")
        self.resize(980, 560)
        self._build_ui()

    def _build_ui(self) -> None:
        self.bind_ip_label = QLabel("Bind IP: 자동 선택")
        self.summary_label = QLabel("Discovery: UDP broadcast")

        self.scan_button = QPushButton("탐색 시작")
        self.stop_button = QPushButton("중지")
        self.stop_button.setEnabled(False)
        self.add_selected_button = QPushButton("Add Selected")
        self.add_all_button = QPushButton("Add All")
        self.close_button = QPushButton("Close")

        form = QFormLayout()
        form.addRow("Bind", self.bind_ip_label)
        form.addRow("Mode", self.summary_label)

        buttons = QGridLayout()
        buttons.addWidget(self.scan_button, 0, 0)
        buttons.addWidget(self.stop_button, 0, 1)
        buttons.addWidget(self.add_selected_button, 1, 0)
        buttons.addWidget(self.add_all_button, 1, 1)
        buttons.addWidget(self.close_button, 2, 0, 1, 2)

        self.table_model = DiscoveryTableModel()
        self.table_view = QTableView()
        self.table_view.setModel(self.table_model)
        self.table_view.setSelectionBehavior(QTableView.SelectRows)
        self.table_view.setSelectionMode(QTableView.ExtendedSelection)
        self.table_view.verticalHeader().setVisible(False)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.horizontalHeader().sectionClicked.connect(self._on_header_clicked)

        top = QWidget()
        top_layout = QGridLayout(top)
        top_layout.addLayout(form, 0, 0)
        top_layout.addLayout(buttons, 0, 1)

        root = QVBoxLayout(self)
        root.addWidget(top)
        root.addWidget(self.table_view)

        self.scan_button.clicked.connect(self.scan_requested.emit)
        self.stop_button.clicked.connect(self.stop_requested.emit)
        self.add_selected_button.clicked.connect(self.add_selected_requested.emit)
        self.add_all_button.clicked.connect(self.add_all_requested.emit)
        self.close_button.clicked.connect(self.close)

    def _on_header_clicked(self, section: int) -> None:
        if self.table_model.COLUMN_KEYS[section] == "selected":
            self.table_model.toggle_all()

    def set_bind_ip(self, ip: str | None) -> None:
        self.bind_ip_label.setText(f"Bind IP: {ip or '자동 선택 실패'}")

    def set_scanning(self, scanning: bool) -> None:
        self.scan_button.setEnabled(not scanning)
        self.stop_button.setEnabled(scanning)

    def clear_results(self) -> None:
        self.table_model.clear_rows()

    def set_results(self, rows: list[DiscoveryRow]) -> None:
        self.table_model.set_rows(rows)

    def selected_results(self) -> list[DiscoveryRow]:
        return self.table_model.selected_rows()

    def all_results(self) -> list[DiscoveryRow]:
        return self.table_model.all_rows()