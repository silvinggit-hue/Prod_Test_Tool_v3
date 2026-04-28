from __future__ import annotations

import ipaddress

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)


class AddDeviceWindow(QDialog):
    rows_submitted = pyqtSignal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Device")
        self.resize(420, 220)
        self._build_ui()

    def _build_ui(self) -> None:
        self.start_ip_edit = QLineEdit()
        self.start_ip_edit.setPlaceholderText("192.168.10.101")

        self.end_ip_edit = QLineEdit()
        self.end_ip_edit.setPlaceholderText("192.168.10.200")

        self.port_spin = QSpinBox()
        self.port_spin.setRange(0, 65535)
        self.port_spin.setValue(0)
        self.port_spin.setSpecialValueText("Auto")

        self.note_edit = QLineEdit()
        self.note_edit.setPlaceholderText("optional note")

        self.count_label = QLabel("0 device(s)")

        self.add_rows_button = QPushButton("Add Rows")
        self.close_button = QPushButton("Close")

        form = QFormLayout()
        form.addRow("Start IP", self.start_ip_edit)
        form.addRow("End IP", self.end_ip_edit)
        form.addRow("Port", self.port_spin)
        form.addRow("Note", self.note_edit)
        form.addRow("Count", self.count_label)

        buttons = QHBoxLayout()
        buttons.addWidget(self.add_rows_button)
        buttons.addWidget(self.close_button)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addStretch(1)
        root.addLayout(buttons)

        self.start_ip_edit.textChanged.connect(self._update_count_text)
        self.end_ip_edit.textChanged.connect(self._update_count_text)
        self.add_rows_button.clicked.connect(self._on_add_rows_clicked)
        self.close_button.clicked.connect(self.close)

    def _expand_ip_range(self) -> list[str]:
        start_raw = self.start_ip_edit.text().strip()
        end_raw = self.end_ip_edit.text().strip()

        if not start_raw or not end_raw:
            raise ValueError("Start IP / End IP를 입력하세요.")

        start_ip = ipaddress.ip_address(start_raw)
        end_ip = ipaddress.ip_address(end_raw)

        if start_ip.version != end_ip.version:
            raise ValueError("IP 버전이 서로 다릅니다.")

        if int(start_ip) > int(end_ip):
            raise ValueError("Start IP는 End IP보다 작거나 같아야 합니다.")

        return [str(ipaddress.ip_address(v)) for v in range(int(start_ip), int(end_ip) + 1)]

    def _update_count_text(self) -> None:
        try:
            count = len(self._expand_ip_range())
            self.count_label.setText(f"{count} device(s)")
        except Exception:
            self.count_label.setText("0 device(s)")

    def _on_add_rows_clicked(self) -> None:
        try:
            ips = self._expand_ip_range()
        except Exception as exc:
            QMessageBox.warning(self, "Add Device", str(exc))
            return

        note = self.note_edit.text().strip()
        port = int(self.port_spin.value())

        rows = [
            {
                "ip": ip,
                "port": port,
                "note": note,
            }
            for ip in ips
        ]
        self.rows_submitted.emit(rows)
        self.accept()