from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QAction,
    QHeaderView,
    QMainWindow,
    QScrollArea,
    QSplitter,
    QTableView,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from config.constants import APP_DISPLAY_NAME
from ui.delegates.led_delegate import LedBarDelegate
from ui.main.status_bar import MainStatusBarWidget
from ui.main.table_model import DeviceTableModel
from ui.panels.connect_panel import ConnectPanel
from ui.panels.control_panel import ControlPanel
from ui.panels.info_panel import InfoPanel
from ui.panels.log_panel import LogPanel
from ui.panels.result_panel import ResultPanel
from ui.panels.status_panel import StatusPanel


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_DISPLAY_NAME)
        self.resize(1600, 950)

        self._build_toolbar()
        self._build_table()
        self._build_panels()
        self._build_layout()

    def _build_toolbar(self) -> None:
        self.toolbar = QToolBar("Main", self)
        self.toolbar.setMovable(False)
        self.addToolBar(self.toolbar)

        self.add_device_action = QAction("Add Device", self)
        self.discovery_action = QAction("IP Discovery", self)
        self.clear_selection_action = QAction("Clear Selection", self)

        self.toolbar.addAction(self.add_device_action)
        self.toolbar.addAction(self.discovery_action)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.clear_selection_action)

    def _build_table(self) -> None:
        self.device_table_model = DeviceTableModel()
        self.device_table = QTableView()
        self.device_table.setModel(self.device_table_model)
        self.device_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.device_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.device_table.setAlternatingRowColors(True)
        self.device_table.setSortingEnabled(False)
        self.device_table.verticalHeader().setVisible(False)
        self.device_table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.device_table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.device_table.setWordWrap(False)

        header = self.device_table.horizontalHeader()
        header.setSectionsClickable(True)
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeToContents)

        result_col = self.device_table_model.column_index("result")
        if result_col >= 0:
            header.setSectionResizeMode(result_col, QHeaderView.Stretch)

        sel_col = self.device_table_model.column_index("selected")
        conn_col = self.device_table_model.column_index("connected")
        if sel_col >= 0:
            self.device_table.setColumnWidth(sel_col, 48)
        if conn_col >= 0:
            self.device_table.setColumnWidth(conn_col, 55)

        sensor_col = self.device_table_model.column_index("sensor")
        alarm_col = self.device_table_model.column_index("alarm")
        if sensor_col >= 0:
            self.device_table.setItemDelegateForColumn(sensor_col, LedBarDelegate(self.device_table))
        if alarm_col >= 0:
            self.device_table.setItemDelegateForColumn(alarm_col, LedBarDelegate(self.device_table))

    def _build_panels(self) -> None:
        self.connect_panel = ConnectPanel()
        self.info_panel = InfoPanel()
        self.status_panel = StatusPanel()
        self.control_panel = ControlPanel()
        self.log_panel = LogPanel("System Log")
        self.result_panel = ResultPanel()

        self.right_scroll_content = QWidget()
        right_layout = QVBoxLayout(self.right_scroll_content)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)
        right_layout.addWidget(self.connect_panel)
        right_layout.addWidget(self.info_panel)
        right_layout.addWidget(self.status_panel)
        right_layout.addWidget(self.control_panel)
        right_layout.addStretch(1)

        self.right_scroll_area = QScrollArea()
        self.right_scroll_area.setWidgetResizable(True)
        self.right_scroll_area.setWidget(self.right_scroll_content)

        self.main_status_bar = MainStatusBarWidget()
        self.statusBar().addPermanentWidget(self.main_status_bar, 1)

    def _build_layout(self) -> None:
        top_splitter = QSplitter(Qt.Horizontal)
        top_splitter.addWidget(self.device_table)
        top_splitter.addWidget(self.right_scroll_area)
        top_splitter.setStretchFactor(0, 4)
        top_splitter.setStretchFactor(1, 2)

        bottom_splitter = QSplitter(Qt.Horizontal)
        bottom_splitter.addWidget(self.log_panel)
        bottom_splitter.addWidget(self.result_panel)
        bottom_splitter.setStretchFactor(0, 2)
        bottom_splitter.setStretchFactor(1, 1)

        main_splitter = QSplitter(Qt.Vertical)
        main_splitter.addWidget(top_splitter)
        main_splitter.addWidget(bottom_splitter)
        main_splitter.setStretchFactor(0, 4)
        main_splitter.setStretchFactor(1, 1)

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(6, 6, 6, 6)
        central_layout.addWidget(main_splitter)
        self.setCentralWidget(central)

    def resize_columns_to_contents(self) -> None:
        self.device_table.resizeColumnsToContents()
        header = self.device_table.horizontalHeader()
        result_col = self.device_table_model.column_index("result")
        if result_col >= 0:
            header.setSectionResizeMode(result_col, QHeaderView.Stretch)