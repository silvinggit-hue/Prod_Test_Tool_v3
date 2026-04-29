from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from application.core.video_coordinator import VideoStreamItem
from ui.video.tile_widget import VideoTileWidget


class VideoWindow(QMainWindow):
    prev_page_requested = pyqtSignal()
    next_page_requested = pyqtSignal()
    refresh_requested = pyqtSignal()
    closed = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Video")
        self.resize(1500, 900)

        self._tiles: list[VideoTileWidget] = []
        self._tile_positions: dict[VideoTileWidget, tuple[int, int]] = {}
        self._fullscreen_tile: VideoTileWidget | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        self.mode_label = QLabel("모드: 현재 장비")
        self.count_label = QLabel("대상: 0대")
        self.page_label = QLabel("페이지: 1 / 1")

        self.prev_button = QPushButton("이전 페이지")
        self.next_button = QPushButton("다음 페이지")
        self.refresh_button = QPushButton("새로고침")
        self.close_button = QPushButton("닫기")

        self.prev_button.clicked.connect(self.prev_page_requested.emit)
        self.next_button.clicked.connect(self.next_page_requested.emit)
        self.refresh_button.clicked.connect(self.refresh_requested.emit)
        self.close_button.clicked.connect(self.close)

        top = QHBoxLayout()
        top.addWidget(self.mode_label)
        top.addWidget(self.count_label)
        top.addWidget(self.page_label)
        top.addStretch(1)
        top.addWidget(self.prev_button)
        top.addWidget(self.next_button)
        top.addWidget(self.refresh_button)
        top.addWidget(self.close_button)

        self.grid_page = QWidget()
        self.grid_layout = QGridLayout(self.grid_page)
        self.grid_layout.setContentsMargins(4, 4, 4, 4)
        self.grid_layout.setSpacing(8)

        for idx in range(10):
            tile = VideoTileWidget(self.grid_page)
            tile.double_clicked.connect(self._on_tile_double_clicked)
            row = idx // 5
            col = idx % 5
            self.grid_layout.addWidget(tile, row, col)
            self._tiles.append(tile)
            self._tile_positions[tile] = (row, col)

        self.single_page = QWidget()
        self.single_layout = QVBoxLayout(self.single_page)
        self.single_layout.setContentsMargins(4, 4, 4, 4)

        self.stacked = QStackedWidget()
        self.stacked.addWidget(self.grid_page)
        self.stacked.addWidget(self.single_page)
        self.stacked.setCurrentWidget(self.grid_page)

        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)
        root.addLayout(top)
        root.addWidget(self.stacked, 1)

    def update_header(
        self,
        *,
        mode_label: str,
        target_count: int,
        current_page: int,
        page_count: int,
    ) -> None:
        self.mode_label.setText(f"모드: {mode_label}")
        self.count_label.setText(f"대상: {int(target_count)}대")
        self.page_label.setText(f"페이지: {int(current_page) + 1} / {max(1, int(page_count))}")
        self.prev_button.setEnabled(current_page > 0)
        self.next_button.setEnabled(current_page + 1 < max(1, page_count))

    def set_tiles(self, items: tuple[VideoStreamItem, ...]) -> None:
        self.exit_fullscreen_tile()

        for idx, tile in enumerate(self._tiles):
            tile.set_stream_item(items[idx] if idx < len(items) else None)

    def refresh_tiles(self) -> None:
        for tile in self._tiles:
            tile.refresh_stream()

    def stop_all_tiles(self) -> None:
        for tile in self._tiles:
            tile.stop_stream()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape and self._fullscreen_tile is not None:
            self.exit_fullscreen_tile()
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        self.stop_all_tiles()
        self.closed.emit()
        super().closeEvent(event)

    def _on_tile_double_clicked(self, tile: VideoTileWidget) -> None:
        if self._fullscreen_tile is tile:
            self.exit_fullscreen_tile()
            return
        self.enter_fullscreen_tile(tile)

    def enter_fullscreen_tile(self, tile: VideoTileWidget) -> None:
        if self._fullscreen_tile is tile:
            return

        self.exit_fullscreen_tile()

        self.grid_layout.removeWidget(tile)
        self.single_layout.addWidget(tile)
        self._fullscreen_tile = tile
        self.stacked.setCurrentWidget(self.single_page)
        self.showFullScreen()

    def exit_fullscreen_tile(self) -> None:
        tile = self._fullscreen_tile
        if tile is None:
            return

        self.single_layout.removeWidget(tile)
        row, col = self._tile_positions[tile]
        self.grid_layout.addWidget(tile, row, col)
        self._fullscreen_tile = None
        self.stacked.setCurrentWidget(self.grid_page)
        self.showNormal()