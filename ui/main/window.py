from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QAction,
    QHeaderView,
    QHBoxLayout,
    QMainWindow,
    QScrollArea,
    QSplitter,
    QTableView,
    QTabWidget,
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
        sensor_col = self.device_table_model.column_index("sensor")
        alarm_col = self.device_table_model.column_index("alarm")

        if sel_col >= 0:
            self.device_table.setColumnWidth(sel_col, 48)
        if conn_col >= 0:
            self.device_table.setColumnWidth(conn_col, 58)
        if sensor_col >= 0:
            self.device_table.setItemDelegateForColumn(sensor_col, LedBarDelegate(self.device_table))
            self.device_table.setColumnWidth(sensor_col, 92)
        if alarm_col >= 0:
            self.device_table.setItemDelegateForColumn(alarm_col, LedBarDelegate(self.device_table))
            self.device_table.setColumnWidth(alarm_col, 92)

    def _build_panels(self) -> None:
        self.connect_panel = ConnectPanel()
        self.info_panel = InfoPanel()
        self.status_panel = StatusPanel()
        self.control_panel = ControlPanel()
        self.log_panel = LogPanel()
        self.result_panel = ResultPanel()
        self.main_status_bar = MainStatusBarWidget()

        self.right_tabs = QTabWidget()
        self.right_tabs.setDocumentMode(True)

        self.system_tab = QWidget()
        self.system_tab_layout = QVBoxLayout(self.system_tab)
        self.system_tab_layout.setContentsMargins(0, 0, 0, 0)
        self.system_tab_layout.setSpacing(4)
        self.system_tab_layout.addWidget(self.info_panel)
        self.system_tab_layout.addWidget(self.status_panel)
        self.system_tab_layout.addStretch(1)

        self.control_tab = QWidget()
        self.control_tab_layout = QVBoxLayout(self.control_tab)
        self.control_tab_layout.setContentsMargins(0, 0, 0, 0)
        self.control_tab_layout.setSpacing(0)
        self.control_tab_layout.addWidget(self.control_panel)

        self.system_scroll = QScrollArea()
        self.system_scroll.setWidgetResizable(True)
        self.system_scroll.setWidget(self.system_tab)

        self.control_scroll = QScrollArea()
        self.control_scroll.setWidgetResizable(True)
        self.control_scroll.setWidget(self.control_tab)

        self.right_tabs.addTab(self.system_scroll, "System")
        self.right_tabs.addTab(self.control_scroll, "Control")

    def _build_layout(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(6)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        left_layout.addWidget(self.device_table, 1)

        right_widget = QWidget()
        right_widget.setMinimumWidth(390)
        right_widget.setMaximumWidth(390)

        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)
        right_layout.addWidget(self.connect_panel, 0)
        right_layout.addWidget(self.right_tabs, 1)

        right_bottom = QWidget()
        right_bottom_layout = QHBoxLayout(right_bottom)
        right_bottom_layout.setContentsMargins(0, 2, 0, 0)
        right_bottom_layout.setSpacing(6)
        right_bottom_layout.addWidget(self.result_panel, 1)
        right_bottom_layout.addWidget(self.log_panel, 1)

        right_layout.addWidget(right_bottom, 0)

        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)

        root.addWidget(splitter, 1)
        root.addWidget(self.main_status_bar, 0)

        splitter.setSizes([1360, 390])

    def resize_columns_to_contents(self) -> None:
        self.device_table.resizeColumnsToContents()
        header = self.device_table.horizontalHeader()
        result_col = self.device_table_model.column_index("result")
        if result_col >= 0:
            header.setSectionResizeMode(result_col, QHeaderView.Stretch)