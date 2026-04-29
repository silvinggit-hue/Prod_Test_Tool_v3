from __future__ import annotations

from enum import Enum


class AppMode(str, Enum):
    NORMAL = "normal"
    FIRMWARE = "firmware"