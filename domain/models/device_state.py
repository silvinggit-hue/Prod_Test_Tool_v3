from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceCommandState:
    current_task_id: str | None = None
    current_task_kind: str | None = None
    queued_count: int = 0
    inflight: bool = False
    last_result: str = ""
    last_message: str = ""
    last_error_kind: str = ""
    last_error_detail: str = ""
    progress_percent: int = 0
    progress_text: str = ""
    next_retry_at: float | None = None


@dataclass(frozen=True)
class DeviceLiveMetrics:
    rtc_text: str = "-"
    temp_text: str = "-"
    eth_text: str = "-"
    rate1_text: str = "-"
    rate2_text: str = "-"
    rate3_text: str = "-"
    rate4_text: str = "-"

    audio_enc_bitrate: str = "-"
    audio_dec_bitrate: str = "-"
    audio_dec_algorithm: str = "-"
    audio_dec_samplerate: str = "-"

    cds_text: str = "-"
    current_y_text: str = "-"
    fan_text: str = "-"

    sensor_leds: tuple[bool, bool, bool, bool] = (False, False, False, False)
    alarm_leds: tuple[bool, bool, bool, bool] = (False, False, False, False)

    updated_at: float | None = None