from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class UiSettings:
    device_page_size: int = 10
    ui_flush_ms: int = 100
    focused_flush_ms: int = 50
    log_flush_ms: int = 100

    default_visible_columns: tuple[str, ...] = field(
        default_factory=lambda: (
            "ip",
            "connected",
            "state",
            "model",
            "firmware",
            "mac",
            "board_id",
            "ptz_type",
            "temp",
            "eth",
            "rate1",
            "sensor",
            "alarm",
        )
    )

    @classmethod
    def load(cls) -> "UiSettings":
        return cls()