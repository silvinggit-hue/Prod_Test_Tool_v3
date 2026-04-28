from __future__ import annotations

from enum import Enum


class CommandKind(str, Enum):
    CONNECT = "connect"
    INFO_LOAD = "info_load"
    STATUS_POLL = "status_poll"
    CONTROL = "control"
    DISCOVERY = "discovery"
    SETIP = "setip"
    RESET = "reset"
    VIDEO_REFRESH = "video_refresh"
    FIRMWARE_BATCH = "firmware_batch"


class TaskLane(str, Enum):
    EMERGENCY = "emergency"
    CONTROL = "control"
    CONNECT = "connect"
    INFO = "info"
    POLL_HOT = "poll_hot"
    POLL_WARM = "poll_warm"
    FIRMWARE = "firmware"
    UDP_ADMIN = "udp_admin"


class ControlKind(str, Enum):
    PT = "pt"
    ZOOM = "zoom"
    FOCUS = "focus"
    TDN = "tdn"
    ICR = "icr"
    SYSTEM = "system"
    MODEL = "model"
    RTC = "rtc"
    EXTRA_ID = "extra_id"
    AUDIO = "audio"
    VIDEO_INPUT = "video_input"