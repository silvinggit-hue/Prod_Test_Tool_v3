from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QWidget

from domain.models.app_snapshot import AppSnapshot


class MainStatusBarWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(12)

        self.total_label = QLabel("Total: 0")
        self.connected_label = QLabel("Connected: 0")
        self.busy_label = QLabel("Busy: 0")
        self.failed_label = QLabel("Failed: 0")
        self.selected_label = QLabel("Selected: 0")
        self.page_label = QLabel("Page: 1")
        self.mode_label = QLabel("Mode: normal")

        for label in (
            self.total_label,
            self.connected_label,
            self.busy_label,
            self.failed_label,
            self.selected_label,
            self.page_label,
            self.mode_label,
        ):
            layout.addWidget(label)

        layout.addStretch(1)

    def update_from_snapshot(self, snapshot: AppSnapshot) -> None:
        self.total_label.setText(f"Total: {snapshot.total_count}")
        self.connected_label.setText(f"Connected: {snapshot.connected_count}")
        self.busy_label.setText(f"Busy: {snapshot.busy_count}")
        self.failed_label.setText(f"Failed: {snapshot.failed_count}")
        self.selected_label.setText(f"Selected: {snapshot.selected_count}")
        self.page_label.setText(f"Page: {snapshot.current_video_page + 1}")
        self.mode_label.setText(f"Mode: {snapshot.app_mode.value}")