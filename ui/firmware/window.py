from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QCloseEvent
from PyQt5.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from domain.models.firmware_models import FirmwareBatchSnapshot
from ui.firmware.table_model import FirmwareTableModel


class FirmwareWindow(QMainWindow):
    close_requested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Firmware")
        self.resize(1200, 780)

        self._build_ui()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        self.target_count_label = QLabel("대상 장비 0대")

        self.firmware_path_edit = QLineEdit()
        self.firmware_path_edit.setPlaceholderText("펌웨어 파일 경로")
        self.browse_button = QPushButton("찾기")

        self.start_button = QPushButton("시작")
        self.retry_failed_button = QPushButton("실패 장비만 재시도")
        self.close_button = QPushButton("닫기")
        self.close_button.clicked.connect(self.close_requested.emit)

        top_box = QGroupBox("실행")
        top_layout = QGridLayout(top_box)
        top_layout.addWidget(QLabel("대상"), 0, 0)
        top_layout.addWidget(self.target_count_label, 0, 1, 1, 3)
        top_layout.addWidget(QLabel("파일"), 1, 0)
        top_layout.addWidget(self.firmware_path_edit, 1, 1)
        top_layout.addWidget(self.browse_button, 1, 2)
        top_layout.addWidget(self.start_button, 1, 3)
        top_layout.addWidget(self.retry_failed_button, 1, 4)
        top_layout.addWidget(self.close_button, 1, 5)

        summary_box = QGroupBox("진행 요약")
        summary_layout = QHBoxLayout(summary_box)

        self.total_label = QLabel("전체 0")
        self.uploading_label = QLabel("업로드 중 0")
        self.rebooting_label = QLabel("재부팅 중 0")
        self.reconnecting_label = QLabel("다시 연결 확인 중 0")
        self.success_label = QLabel("완료 0")
        self.failed_label = QLabel("실패 0")

        for label in (
            self.total_label,
            self.uploading_label,
            self.rebooting_label,
            self.reconnecting_label,
            self.success_label,
            self.failed_label,
        ):
            summary_layout.addWidget(label)
        summary_layout.addStretch(1)

        self.table_model = FirmwareTableModel()
        self.table_view = QTableView()
        self.table_view.setModel(self.table_model)
        self.table_view.verticalHeader().setVisible(False)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table_view.horizontalHeader().setStretchLastSection(True)

        log_box = QGroupBox("로그")
        log_layout = QVBoxLayout(log_box)
        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        log_layout.addWidget(self.log_edit)

        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)
        root.addWidget(top_box)
        root.addWidget(summary_box)
        root.addWidget(self.table_view, 1)
        root.addWidget(log_box, 1)

    def choose_firmware_file(self) -> str:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "펌웨어 파일 선택",
            "",
            "Firmware Files (*.tus);;All Files (*)",
        )
        if path:
            self.firmware_path_edit.setText(path)
        return path

    def firmware_path(self) -> str:
        return self.firmware_path_edit.text().strip()

    def set_target_count(self, count: int) -> None:
        self.target_count_label.setText(f"대상 장비 {int(count)}대")

    def update_summary(self, snapshot: FirmwareBatchSnapshot | None) -> None:
        if snapshot is None:
            self.total_label.setText("전체 0")
            self.uploading_label.setText("업로드 중 0")
            self.rebooting_label.setText("재부팅 중 0")
            self.reconnecting_label.setText("다시 연결 확인 중 0")
            self.success_label.setText("완료 0")
            self.failed_label.setText("실패 0")
            return

        self.total_label.setText(f"전체 {snapshot.total_count}")
        self.uploading_label.setText(f"업로드 중 {snapshot.uploading_count}")
        self.rebooting_label.setText(f"재부팅 중 {snapshot.rebooting_count}")
        self.reconnecting_label.setText(f"다시 연결 확인 중 {snapshot.reconnecting_count}")
        self.success_label.setText(f"완료 {snapshot.success_count}")
        self.failed_label.setText(f"실패 {snapshot.failed_count}")

    def set_rows(self, rows) -> None:
        self.table_model.set_rows(rows)

    def append_logs(self, lines: list[str]) -> None:
        if not lines:
            return
        self.log_edit.appendPlainText("\n".join(lines))

    def confirm_hide_while_running(self) -> bool:
        answer = QMessageBox.question(
            self,
            "Firmware",
            "작업 중입니다. 창을 닫으면 현재 진행 상황은 숨겨지지만 작업은 계속 진행됩니다.\n창을 숨기시겠습니까?",
        )
        return answer == QMessageBox.Yes

    def closeEvent(self, event: QCloseEvent) -> None:
        self.close_requested.emit()
        event.ignore()