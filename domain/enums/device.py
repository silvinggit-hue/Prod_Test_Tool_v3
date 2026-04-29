from __future__ import annotations

from enum import Enum


class DeviceState(str, Enum):
    DISCOVERED = "discovered"
    CONNECTING = "connecting"
    READY = "ready"
    BACKOFF = "backoff"
    AUTH_FAILED = "auth_failed"
    DISCONNECTED = "disconnected"
    FW_LOCKED = "fw_locked"
    REMOVED = "removed"


class AuthScheme(str, Enum):
    NONE = "none"
    BASIC = "basic"
    DIGEST = "digest"


class DeviceFlavor(str, Enum):
    LEGACY = "legacy"
    TTA = "tta"
    SECURITY3 = "security3"
    UNKNOWN = "unknown"