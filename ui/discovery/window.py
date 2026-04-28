from __future__ import annotations

from dataclasses import dataclass, replace
from ipaddress import IPv4Address
from typing import Optional

from PyQt5.QtCore import QAbstractTableModel, QModelIndex, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
)


@dataclass(frozen=True)
class DiscoveryRow:
    selected: bool = False
    selection_order: int | None = None

    ip: str = ""
    new_ip: str = ""

    model: str = "-"
    firmware: str = "-"
    mac: str = "-"
    mac12: str = "-"

    status: str = "대기"
    note: str = "-"


class DiscoveryTableModel(QAbstractTableModel):
    rows_changed = pyqtSignal()

    COLUMN_KEYS: tuple[str, ...] = (
        "selected",
        "order",
        "ip",
        "new_ip",
        "model",
        "firmware",
        "mac",
        "mac12",
        "status",
        "note",
    )

    COLUMN_LABELS: dict[str, str] = {
        "selected": "선택",
        "order": "순번",
        "ip": "현재 IP",
        "new_ip": "변경할 IP",
        "model": "모델명",
        "firmware": "펌웨어",
        "mac": "MAC",
        "mac12": "MAC12",
        "status": "상태",
        "note": "비고",
    }

    EDITABLE_KEYS = {"new_ip"}

    def __init__(self) -> None:
        super().__init__()
        self._rows: list[DiscoveryRow] = []

    # ---------------------------------------------------------
    # basic
    # ---------------------------------------------------------
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

        if orientation == Qt.Horizontal:
            if 0 <= section < len(self.COLUMN_KEYS):
                key = self.COLUMN_KEYS[section]
                return self.COLUMN_LABELS.get(key, key)
            return None

        return str(section + 1)

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.NoItemFlags

        key = self.COLUMN_KEYS[index.column()]
        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable

        if key == "selected":
            flags |= Qt.ItemIsUserCheckable

        if key in self.EDITABLE_KEYS:
            flags |= Qt.ItemIsEditable

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
            if key == "order":
                return "" if row.selection_order is None else str(int(row.selection_order))
            if key == "ip":
                return row.ip
            if key == "new_ip":
                return row.new_ip
            if key == "model":
                return row.model
            if key == "firmware":
                return row.firmware
            if key == "mac":
                return row.mac
            if key == "mac12":
                return row.mac12
            if key == "status":
                return row.status
            if key == "note":
                return row.note

        if role == Qt.TextAlignmentRole:
            if key in {"selected", "order"}:
                return int(Qt.AlignCenter)
            return int(Qt.AlignVCenter | Qt.AlignLeft)

        return None

    def setData(self, index: QModelIndex, value, role: int = Qt.EditRole):
        if not index.isValid():
            return False

        row = self._rows[index.row()]
        key = self.COLUMN_KEYS[index.column()]

        if key == "selected" and role == Qt.CheckStateRole:
            checked = value == Qt.Checked
            updated = replace(row, selected=checked)
            self._rows[index.row()] = updated
            self.dataChanged.emit(index, index, [Qt.CheckStateRole, Qt.DisplayRole])
            self.rows_changed.emit()
            return True

        if key in self.EDITABLE_KEYS and role in (Qt.EditRole, Qt.DisplayRole):
            updated = replace(row, new_ip=str(value or "").strip())
            self._rows[index.row()] = updated
            self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
            self.rows_changed.emit()
            return True

        return False

    # ---------------------------------------------------------
    # row helpers
    # ---------------------------------------------------------
    def set_rows(self, rows: list[DiscoveryRow]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()
        self.rows_changed.emit()

    def clear_rows(self) -> None:
        self.set_rows([])

    def all_rows(self) -> list[DiscoveryRow]:
        return list(self._rows)

    def selected_rows(self) -> list[DiscoveryRow]:
        return [row for row in self._rows if row.selected]

    def row_count(self) -> int:
        return len(self._rows)

    def selected_count(self) -> int:
        return sum(1 for row in self._rows if row.selected)

    def toggle_all_selected(self) -> bool:
        if not self._rows:
            return False

        all_selected = all(row.selected for row in self._rows)
        new_state = not all_selected

        self.beginResetModel()
        self._rows = [replace(row, selected=new_state) for row in self._rows]
        self.endResetModel()
        self.rows_changed.emit()
        return new_state

    def replace_rows(self, rows: list[DiscoveryRow]) -> None:
        self.set_rows(rows)

    def update_row_by_mac12(self, mac12: str, **changes) -> None:
        target = (mac12 or "").strip().upper()
        if not target:
            return

        changed = False
        rows = self.all_rows()
        for idx, row in enumerate(rows):
            if (row.mac12 or "").strip().upper() == target:
                rows[idx] = replace(row, **changes)
                changed = True
                break

        if changed:
            self.set_rows(rows)


class DiscoveryWindow(QDialog):
    scan_requested = pyqtSignal()
    stop_requested = pyqtSignal()

    auto_fill_ip_requested = pyqtSignal()
    setip_requested = pyqtSignal()
    reset_requested = pyqtSignal()

    add_selected_requested = pyqtSignal()
    add_all_requested = pyqtSignal()

    select_all_toggled = pyqtSignal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("장비 검색 / IP 변경")
        self.resize(1180, 650)
        self._build_ui()

    # ---------------------------------------------------------
    # build
    # ---------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        # -------------------------------------------------
        # 장비 검색
        # -------------------------------------------------
        search_box = QGroupBox("장비 검색")
        search_form = QFormLayout(search_box)

        self.bind_ip_value = QLabel("자동 선택")
        self.state_value = QLabel("대기 중")
        self.result_value = QLabel("0대 발견 / 0대 선택")

        self.scan_button = QPushButton("검색 시작")
        self.stop_button = QPushButton("중지")
        self.stop_button.setEnabled(False)

        search_btn_row = QHBoxLayout()
        search_btn_row.addWidget(self.scan_button)
        search_btn_row.addWidget(self.stop_button)

        search_form.addRow("현재 PC IP", self.bind_ip_value)
        search_form.addRow("상태", self.state_value)
        search_form.addRow("결과", self.result_value)
        search_form.addRow("", search_btn_row)

        # -------------------------------------------------
        # IP 변경
        # -------------------------------------------------
        ip_box = QGroupBox("IP 변경")
        ip_form = QFormLayout(ip_box)

        self.base_ip_edit = QLineEdit()
        self.base_ip_edit.setPlaceholderText("예: 192.168.10.100")

        self.order_mode_combo = QComboBox()
        self.order_mode_combo.addItem("MAC 순서", "mac")
        self.order_mode_combo.addItem("선택한 순서", "selection")

        self.auto_fill_button = QPushButton("IP 자동 채우기")
        self.setip_button = QPushButton("IP 변경 실행")
        self.reset_button = QPushButton("선택 초기화")

        ip_btn_grid = QGridLayout()
        ip_btn_grid.addWidget(self.auto_fill_button, 0, 0)
        ip_btn_grid.addWidget(self.setip_button, 0, 1)
        ip_btn_grid.addWidget(self.reset_button, 1, 0, 1, 2)

        ip_form.addRow("시작 IP", self.base_ip_edit)
        ip_form.addRow("정렬 기준", self.order_mode_combo)
        ip_form.addRow("", ip_btn_grid)

        # -------------------------------------------------
        # 메인 반영
        # -------------------------------------------------
        main_box = QGroupBox("메인 반영")
        main_layout = QVBoxLayout(main_box)

        self.add_selected_button = QPushButton("선택 항목 추가")
        self.add_all_button = QPushButton("전체 추가")
        self.close_button = QPushButton("닫기")

        main_layout.addWidget(self.add_selected_button)
        main_layout.addWidget(self.add_all_button)
        main_layout.addWidget(self.close_button)
        main_layout.addStretch(1)

        top_row.addWidget(search_box, 2)
        top_row.addWidget(ip_box, 2)
        top_row.addWidget(main_box, 1)

        root.addLayout(top_row)

        self.table_model = DiscoveryTableModel()
        self.table_view = QTableView()
        self.table_view.setModel(self.table_model)
        self.table_view.setSelectionBehavior(QTableView.SelectRows)
        self.table_view.setSelectionMode(QTableView.ExtendedSelection)
        self.table_view.verticalHeader().setVisible(False)
        self.table_view.setAlternatingRowColors(True)

        header = self.table_view.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)
        header.sectionClicked.connect(self._on_header_clicked)

        root.addWidget(self.table_view, 1)

        self.scan_button.clicked.connect(self.scan_requested.emit)
        self.stop_button.clicked.connect(self.stop_requested.emit)

        self.auto_fill_button.clicked.connect(self.auto_fill_ip_requested.emit)
        self.setip_button.clicked.connect(self.setip_requested.emit)
        self.reset_button.clicked.connect(self.reset_requested.emit)

        self.add_selected_button.clicked.connect(self.add_selected_requested.emit)
        self.add_all_button.clicked.connect(self.add_all_requested.emit)
        self.close_button.clicked.connect(self.close)

        self.table_model.rows_changed.connect(self._refresh_count_text)

    # ---------------------------------------------------------
    # ui helpers
    # ---------------------------------------------------------
    def _on_header_clicked(self, section: int) -> None:
        key = self.table_model.COLUMN_KEYS[section]
        if key != "selected":
            return
        new_state = self.table_model.toggle_all_selected()
        self.select_all_toggled.emit(bool(new_state))

    def set_bind_ip(self, ip: str | None) -> None:
        self.bind_ip_value.setText((ip or "").strip() or "자동 선택 실패")

    def set_status_text(self, text: str) -> None:
        self.state_value.setText((text or "").strip() or "-")

    def set_scanning(self, scanning: bool) -> None:
        self.scan_button.setEnabled(not scanning)
        self.stop_button.setEnabled(scanning)

    def set_admin_busy(self, busy: bool) -> None:
        self.auto_fill_button.setEnabled(not busy)
        self.setip_button.setEnabled(not busy)
        self.reset_button.setEnabled(not busy)
        self.add_selected_button.setEnabled(not busy)
        self.add_all_button.setEnabled(not busy)

    def clear_results(self) -> None:
        self.table_model.clear_rows()
        self._refresh_count_text()

    def set_results(self, rows: list[DiscoveryRow]) -> None:
        self.table_model.set_rows(rows)
        self._refresh_count_text()

    def update_rows(self, rows: list[DiscoveryRow]) -> None:
        self.table_model.replace_rows(rows)
        self._refresh_count_text()

    def all_results(self) -> list[DiscoveryRow]:
        return self.table_model.all_rows()

    def selected_results(self) -> list[DiscoveryRow]:
        return self.table_model.selected_rows()

    def base_ip_text(self) -> str:
        return self.base_ip_edit.text().strip()

    def order_mode(self) -> str:
        return str(self.order_mode_combo.currentData() or "mac")

    def set_base_ip(self, ip: str) -> None:
        self.base_ip_edit.setText((ip or "").strip())

    def _refresh_count_text(self) -> None:
        self.result_value.setText(
            f"{self.table_model.row_count()}대 발견 / {self.table_model.selected_count()}대 선택"
        )

    @staticmethod
    def is_valid_ipv4(text: str) -> bool:
        try:
            IPv4Address((text or "").strip())
            return True
        except Exception:
            return False