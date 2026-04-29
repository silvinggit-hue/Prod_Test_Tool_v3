from __future__ import annotations

from PyQt5.QtCore import QAbstractTableModel, QModelIndex, Qt

from domain.models.firmware_models import FirmwareRowModel


class FirmwareTableModel(QAbstractTableModel):
    COLUMN_KEYS: tuple[str, ...] = (
        "ip",
        "model",
        "state",
        "progress",
        "result",
        "updated_at",
        "elapsed",
    )

    COLUMN_LABELS: dict[str, str] = {
        "ip": "IP",
        "model": "모델명",
        "state": "상태",
        "progress": "진행 내용",
        "result": "결과",
        "updated_at": "갱신 시각",
        "elapsed": "경과",
    }

    def __init__(self) -> None:
        super().__init__()
        self._rows: list[FirmwareRowModel] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.COLUMN_KEYS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal and 0 <= section < len(self.COLUMN_KEYS):
            return self.COLUMN_LABELS[self.COLUMN_KEYS[section]]
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None

        row = self._rows[index.row()]
        key = self.COLUMN_KEYS[index.column()]

        if role == Qt.DisplayRole:
            if key == "ip":
                return row.ip
            if key == "model":
                return row.model
            if key == "state":
                return row.state_text
            if key == "progress":
                return row.progress_text
            if key == "result":
                if row.failure_code_text:
                    return f"{row.result_text} / {row.failure_code_text}"
                return row.result_text
            if key == "updated_at":
                return row.updated_at_text
            if key == "elapsed":
                return row.elapsed_text

        if role == Qt.TextAlignmentRole:
            if key in {"updated_at", "elapsed"}:
                return int(Qt.AlignCenter)
            return int(Qt.AlignVCenter | Qt.AlignLeft)

        return None

    def set_rows(self, rows: list[FirmwareRowModel]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()