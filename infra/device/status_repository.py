from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from domain.errors.app_error import AppError
from domain.models.phase1 import Phase1Response
from infra.network.camera_http_client import CameraHttpClient, parse_kv_lines

GETSTATE_TAIL = "GetState?action=getstate"
GETSTATE_RATE_TAIL_PREFIX = "GetState?action=getrate"
GETSTATE_INPUT_TAIL_PREFIX = "GetState?action=getinput"
GETSTATE_ETHTOOL_TAIL = "GetState?action=ethtool&ETHTOOL=0"

READPARAM_STATUS_KEYS: tuple[str, ...] = (
    "SYS_CURRENTTIME",
    "GIS_RTC",
    "RTC_TIME",
    "SYS_BOARDTEMP",
    "SYS_BOARD_TEMP",
    "ETC_BOARDTEMP",
    "SYS_FTCAMERA_CDS",
    "GIS_CDS",
    "GIS_CDS_CUR",
    "GIS_CDS_CURRENT",
    "CAM_HI_CURRENT_Y",
    "CAM_NXP_CURRENT_Y",
    "CAM_AMBA_CURRENT_Y",
    "SYS_FANSTATUS",
    "SYS_FAN_STATUS",
    "FAN_STATUS",
    "NET_LINKSTATE",
    "NET_LINK_STATE",
    "NET_LINKSPEED",
    "NET_LINK_SPEED",
    "SYS_ETHERNET",
)

RATE_KEYS: tuple[str, ...] = (
    "GRS_VENCFRAME1",
    "GRS_VENCBITRATE1",
    "GRS_VENCFRAME2",
    "GRS_VENCBITRATE2",
    "GRS_VENCFRAME3",
    "GRS_VENCBITRATE3",
    "GRS_VENCFRAME4",
    "GRS_VENCBITRATE4",
    "GRS_AENCBITRATE1",
    "GRS_ADECBITRATE1",
    "GRS_ADECALGORITHM1",
    "GRS_ADECSAMPLERATE1",
)

INPUT_KEYS: tuple[str, ...] = (
    "GIS_SENSOR1",
    "GIS_SENSOR2",
    "GIS_SENSOR3",
    "GIS_SENSOR4",
    "GIS_SENSOR5",
    "GIS_MOTION1",
    "GIS_MOTION2",
    "GIS_MOTION3",
    "GIS_MOTION4",
    "GIS_VIDEOLOSS1",
    "GIS_VIDEOLOSS2",
    "GIS_VIDEOLOSS3",
    "GIS_VIDEOLOSS4",
    "GIS_ALARM1",
    "GIS_ALARM2",
    "GIS_ALARM3",
    "GIS_ALARM4",
    "GIS_RECORD1",
    "GIS_AIRWIPER",
)

ETHTOOL_KEYS: tuple[str, ...] = ("ETHTOOL",)


@dataclass(frozen=True)
class StatusReadResult:
    getstate_kv: dict[str, str]
    readparam_kv: dict[str, str]
    merged_kv: dict[str, str]
    missing_keys: tuple[str, ...]


def merge_nonempty_kv(*sources: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for src in sources:
        for key, value in (src or {}).items():
            text = str(value).strip() if value is not None else ""
            if text != "":
                out[str(key)] = text
            elif str(key) not in out:
                out[str(key)] = ""
    return out


def build_rate_text(kv: dict[str, str], idx: int) -> str:
    bitrate = (kv.get(f"GRS_VENCBITRATE{idx}") or "").strip()
    fps = (kv.get(f"GRS_VENCFRAME{idx}") or "").strip()
    if not bitrate and not fps:
        return "-"
    return f"{bitrate or '-'}kbps / {fps or '-'}fps"


def _format_link_speed_from_ethtool(code: str | None) -> str:
    if code is None:
        return "-"
    value = str(code).strip()
    if not value:
        return "-"
    if value == "24":
        return "1G"
    if value == "22":
        return "100M"
    return value


def _format_ethernet_summary_text(kv: dict[str, str]) -> str:
    link_state = (
        (kv.get("NET_LINKSTATE") or "")
        or (kv.get("NET_LINK_STATE") or "")
    ).strip().lower()

    if link_state in {"0", "down", "off", "nolink"}:
        state_text = "unlink"
    else:
        state_text = "link"

    speed_text = _format_link_speed_from_ethtool(kv.get("ETHTOOL"))
    if speed_text == "-":
        speed_text = (
            (kv.get("NET_LINKSPEED") or "")
            or (kv.get("NET_LINK_SPEED") or "")
            or (kv.get("SYS_ETHERNET") or "")
        ).strip() or "-"

    if speed_text == "-":
        return state_text
    return f"{state_text} / {speed_text}"


def build_status_summary_map(kv: dict[str, str]) -> dict[str, str]:
    def first(*keys: str) -> str:
        for key in keys:
            value = (kv.get(key) or "").strip()
            if value:
                return value
        return "-"

    return {
        "cds": first("SYS_FTCAMERA_CDS", "GIS_CDS", "GIS_CDS_CUR", "GIS_CDS_CURRENT"),
        "current_y": first("CAM_HI_CURRENT_Y", "CAM_NXP_CURRENT_Y", "CAM_AMBA_CURRENT_Y"),
        "rate1": build_rate_text(kv, 1),
        "rate2": build_rate_text(kv, 2),
        "rate3": build_rate_text(kv, 3),
        "rate4": build_rate_text(kv, 4),
        "rtc": first("SYS_CURRENTTIME", "GIS_RTC", "RTC_TIME"),
        "temp": first("SYS_BOARDTEMP", "SYS_BOARD_TEMP", "ETC_BOARDTEMP"),
        "fan": first("SYS_FANSTATUS", "SYS_FAN_STATUS", "FAN_STATUS"),
        "eth": _format_ethernet_summary_text(kv),
        "audio_enc_bitrate": first("GRS_AENCBITRATE1"),
        "audio_dec_bitrate": first("GRS_ADECBITRATE1"),
        "audio_dec_algorithm": first("GRS_ADECALGORITHM1"),
        "audio_dec_samplerate": first("GRS_ADECSAMPLERATE1"),
    }


def build_missing_keys(requested_keys: Iterable[str], merged_kv: dict[str, str]) -> tuple[str, ...]:
    return tuple(str(k) for k in requested_keys if not (merged_kv.get(str(k)) or "").strip())


def _split_keys(keys: Sequence[str], chunk_size: int) -> list[list[str]]:
    items = [str(k).strip() for k in keys if str(k).strip()]
    return [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]


def _read_readparam_kv_best_effort(
    client: CameraHttpClient,
    keys: Sequence[str],
    *,
    chunk_size: int = 8,
) -> dict[str, str]:
    items = [str(k).strip() for k in keys if str(k).strip()]
    if not items:
        return {}

    try:
        return client.read_param_values(items)
    except AppError:
        if len(items) == 1:
            return {items[0]: ""}
        out: dict[str, str] = {}
        next_chunk = max(1, min(chunk_size, len(items) // 2 or 1))
        for chunk in _split_keys(items, next_chunk):
            out.update(_read_readparam_kv_best_effort(client, chunk, chunk_size=next_chunk))
        return out


def _request_tail_with_httpapi_fallback(client: CameraHttpClient, tail: str):
    resp = client.request_tail(tail)

    if resp.status == 200:
        return resp

    if resp.status == 404 and client.root_path != "/httpapi/":
        fallback = CameraHttpClient(
            base_url=client.base_url,
            root_path="/httpapi/",
            username=client.username,
            password=client.password,
            auth_scheme=client.auth_scheme,
            timeout_sec=client.timeout_sec,
            verify_tls=client.verify_tls,
        ).with_shared_session(client.get_session())
        return fallback.request_tail(tail)

    return resp


def _read_getstate_kv(client: CameraHttpClient) -> dict[str, str]:
    resp = _request_tail_with_httpapi_fallback(client, GETSTATE_TAIL)

    if resp.status == 200:
        return parse_kv_lines(resp.body or "")

    if resp.status in (401, 403):
        raise AppError(
            kind="auth",
            message="authentication failed",
            status_code=resp.status,
            detail=(resp.body or "")[:200],
        )

    raise AppError(
        kind="http",
        message="getstate failed",
        status_code=resp.status,
        detail=(resp.body or "")[:200],
    )


def _read_getstate_values_optional(
    client: CameraHttpClient,
    *,
    action: str,
    keys: Sequence[str],
    optional: bool,
) -> dict[str, str]:
    if not keys:
        return {}

    parts = "&".join([f"{str(k).strip()}=0" for k in keys if str(k).strip()])
    tail = f"GetState?action={action}&{parts}"

    resp = _request_tail_with_httpapi_fallback(client, tail)

    if resp.status == 200:
        return parse_kv_lines(resp.body or "")

    if optional and resp.status in (400, 404):
        return {}

    if resp.status in (401, 403):
        raise AppError(
            kind="auth",
            message="authentication failed",
            status_code=resp.status,
            detail=(resp.body or "")[:200],
        )

    if optional:
        return {}

    raise AppError(
        kind="http",
        message=f"getstate {action} failed",
        status_code=resp.status,
        detail=(resp.body or "")[:200],
    )


def _read_getstate_rate_kv(client: CameraHttpClient) -> dict[str, str]:
    return _read_getstate_values_optional(
        client,
        action="getrate",
        keys=RATE_KEYS,
        optional=False,
    )


def _read_getstate_input_kv_optional(client: CameraHttpClient) -> dict[str, str]:
    return _read_getstate_values_optional(
        client,
        action="getinput",
        keys=INPUT_KEYS,
        optional=True,
    )


def _read_getstate_ethtool_kv_optional(client: CameraHttpClient) -> dict[str, str]:
    resp = _request_tail_with_httpapi_fallback(client, GETSTATE_ETHTOOL_TAIL)

    if resp.status == 200:
        return parse_kv_lines(resp.body or "")

    if resp.status in (400, 404):
        return {}

    if resp.status in (401, 403):
        raise AppError(
            kind="auth",
            message="authentication failed",
            status_code=resp.status,
            detail=(resp.body or "")[:200],
        )

    return {}


class StatusRepository:
    def build_client(
        self,
        *,
        base_url: str,
        root_path: str,
        username: str,
        password: str,
        auth_scheme: str,
        timeout_sec: float,
        verify_tls: bool,
    ) -> CameraHttpClient:
        return CameraHttpClient(
            base_url=base_url,
            root_path=root_path,
            username=username,
            password=password,
            auth_scheme=auth_scheme,
            timeout_sec=timeout_sec,
            verify_tls=verify_tls,
        )

    def build_client_from_phase1(
        self,
        phase1: Phase1Response,
        *,
        timeout_sec: float,
        verify_tls: bool,
    ) -> CameraHttpClient:
        if not phase1.ok or not phase1.base_url or not phase1.root_path or not phase1.auth_scheme:
            raise AppError(kind="param", message="invalid phase1 response for status repository")
        return self.build_client(
            base_url=phase1.base_url,
            root_path=phase1.root_path,
            username=phase1.effective_username or "",
            password=phase1.effective_password or "",
            auth_scheme=phase1.auth_scheme,
            timeout_sec=timeout_sec,
            verify_tls=verify_tls,
        )

    def read_status_kv(self, client: CameraHttpClient) -> StatusReadResult:
        getstate_kv = _read_getstate_kv(client)
        readparam_kv = _read_readparam_kv_best_effort(client, READPARAM_STATUS_KEYS, chunk_size=8)
        rate_kv = _read_getstate_rate_kv(client)
        input_kv = _read_getstate_input_kv_optional(client)
        ethtool_kv = _read_getstate_ethtool_kv_optional(client)

        merged = merge_nonempty_kv(readparam_kv, getstate_kv, rate_kv, input_kv, ethtool_kv)
        requested_keys = tuple(READPARAM_STATUS_KEYS) + tuple(RATE_KEYS) + tuple(ETHTOOL_KEYS)
        missing = build_missing_keys(requested_keys, merged)

        return StatusReadResult(
            getstate_kv=merge_nonempty_kv(getstate_kv, rate_kv, input_kv, ethtool_kv),
            readparam_kv=readparam_kv,
            merged_kv=merged,
            missing_keys=missing,
        )