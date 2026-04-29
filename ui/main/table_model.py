from __future__ import annotations

from dataclasses import replace

from PyQt5.QtCore import QAbstractTableModel, QModelIndex, Qt, pyqtSignal

from domain.models.device_snapshot import DeviceSnapshot
from ui.mappers.device_row_mapper import DeviceRow, map_device_row


class DeviceTableModel(QAbstractTableModel):
    selection_toggled = pyqtSignal(str, bool)

    COLUMN_KEYS: tuple[str, ...] = (
        "selected",
        "ip",
        "connected",
        "state",
        "mac_address",
        "model",
        "firmware",
        "type_text",
        "module_version",
        "ptz_fw",
        "linkdown_num",
        "local_ip_mode",
        "power_type",
        "startup_time",
        "disk",
        "ai_version",
        "rcv_version",
        "cds",
        "current_y",
        "primary",
        "secondary",
        "rtc_time",
        "ethernet",
        "board_temp",
        "fan_status",
        "air_wiper",
        "ethernet_speed_rate",
        "sensor",
        "alarm",
        "result",
    )

    COLUMN_LABELS: dict[str, str] = {
        "selected": "Sel",
        "ip": "IP",
        "connected": "Conn",
        "state": "State",
        "mac_address": "MAC address",
        "model": "Model",
        "firmware": "Firmware",
        "type_text": "Type",
        "module_version": "Module version",
        "ptz_fw": "PTZ F/W",
        "linkdown_num": "LD",
        "local_ip_mode": "Local IP mode",
        "power_type": "Power Type",
        "startup_time": "Start up time",
        "disk": "Disk",
        "ai_version": "AI version",
        "rcv_version": "RCV version",
        "cds": "CDS",
        "current_y": "Current Y",
        "primary": "Primary",
        "secondary": "Secondary",
        "rtc_time": "RTC Time",
        "ethernet": "Ethernet",
        "board_temp": "Board Temp",
        "fan_status": "Fan Status",
        "air_wiper": "Air Wiper",
        "ethernet_speed_rate": "Ethernet Speed Rate",
        "sensor": "Sensor",
        "alarm": "Alarm",
        "result": "Result",
    }

    def __init__(self) -> None:
        super().__init__()
        self._snapshots: list[DeviceSnapshot] = []
        self._rows: list[DeviceRow] = []

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
        return flags

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None

        row = self._rows[index.row()]
        key = self.COLUMN_KEYS[index.column()]

        if key == "selected" and role == Qt.CheckStateRole:
            return Qt.Checked if row.selected else Qt.Unchecked

        if role == Qt.DisplayRole:
            value = self._display_value(row, key)
            return value

        if role == Qt.TextAlignmentRole:
            if key in {"selected", "connected", "sensor", "alarm"}:
                return int(Qt.AlignCenter)
            return int(Qt.AlignVCenter | Qt.AlignLeft)

        if role == Qt.UserRole:
            return self._snapshots[index.row()]

        if role == Qt.UserRole + 1:
            if key == "sensor":
                return row.sensor_raw
            if key == "alarm":
                return row.alarm_raw
            return None

        return None

    def setData(self, index: QModelIndex, value, role: int = Qt.EditRole):
        if not index.isValid():
            return False

        key = self.COLUMN_KEYS[index.column()]
        if key != "selected" or role != Qt.CheckStateRole:
            return False

        snapshot = self._snapshots[index.row()]
        checked = value == Qt.Checked
        updated_snapshot = replace(snapshot, selected=checked)

        self._snapshots[index.row()] = updated_snapshot
        self._rows[index.row()] = map_device_row(updated_snapshot)
        self.dataChanged.emit(index, index, [Qt.CheckStateRole, Qt.DisplayRole])

        self.selection_toggled.emit(snapshot.ip, checked)
        return True

    def _display_value(self, row: DeviceRow, key: str):
        if key == "selected":
            return ""
        if key == "ip":
            return row.ip
        if key == "connected":
            return row.connected
        if key == "state":
            return row.state
        if key == "mac_address":
            return row.mac_address
        if key == "model":
            return row.model
        if key == "firmware":
            return row.firmware
        if key == "type_text":
            return row.type_text
        if key == "module_version":
            return row.module_version
        if key == "ptz_fw":
            return row.ptz_fw
        if key == "linkdown_num":
            return row.linkdown_num
        if key == "local_ip_mode":
            return row.local_ip_mode
        if key == "power_type":
            return row.power_type
        if key == "startup_time":
            return row.startup_time
        if key == "disk":
            return row.disk
        if key == "ai_version":
            return row.ai_version
        if key == "rcv_version":
            return row.rcv_version
        if key == "cds":
            return row.cds
        if key == "current_y":
            return row.current_y
        if key == "primary":
            return row.primary
        if key == "secondary":
            return row.secondary
        if key == "rtc_time":
            return row.rtc_time
        if key == "ethernet":
            return row.ethernet
        if key == "board_temp":
            return row.board_temp
        if key == "fan_status":
            return row.fan_status
        if key == "air_wiper":
            return row.air_wiper
        if key == "ethernet_speed_rate":
            return row.ethernet_speed_rate
        if key == "sensor":
            return row.sensor_text
        if key == "alarm":
            return row.alarm_text
        if key == "result":
            return row.result
        return None

    def set_snapshots(self, snapshots: list[DeviceSnapshot]) -> None:
        self.beginResetModel()
        self._snapshots = list(snapshots)
        self._rows = [map_device_row(snapshot) for snapshot in self._snapshots]
        self.endResetModel()

    def snapshot_at_row(self, row: int) -> DeviceSnapshot | None:
        if 0 <= row < len(self._snapshots):
            return self._snapshots[row]
        return None

    def row_for_ip(self, ip: str) -> int:
        for idx, snapshot in enumerate(self._snapshots):
            if snapshot.ip == ip:
                return idx
        return -1

    def column_index(self, key: str) -> int:
        try:
            return self.COLUMN_KEYS.index(key)
        except ValueError:
            return -1

    def all_selected(self) -> bool:
        return bool(self._snapshots) and all(snapshot.selected for snapshot in self._snapshots)