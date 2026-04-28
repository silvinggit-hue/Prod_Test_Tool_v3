from __future__ import annotations

from PyQt5.QtWidgets import QGridLayout, QGroupBox, QPushButton


class ControlPanel(QGroupBox):
    def __init__(self) -> None:
        super().__init__("Control")

        self.reboot_button = QPushButton("Reboot Selected")
        self.sync_rtc_button = QPushButton("Sync RTC Selected")

        layout = QGridLayout(self)
        layout.addWidget(self.reboot_button, 0, 0)
        layout.addWidget(self.sync_rtc_button, 0, 1)