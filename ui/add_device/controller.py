from __future__ import annotations

from collections.abc import Callable

from ui.add_device.window import AddDeviceWindow


class AddDeviceController:
    def __init__(
        self,
        *,
        window: AddDeviceWindow,
        on_rows_added: Callable[[list[dict]], None],
    ) -> None:
        self.window = window
        self.on_rows_added = on_rows_added

    def bind(self) -> None:
        self.window.rows_submitted.connect(self._on_rows_submitted)

    def _on_rows_submitted(self, rows: list[dict]) -> None:
        self.on_rows_added(rows)