from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from common.display.display_names import display_name
from common.display.enum_formatters import format_display_value
from domain.errors.app_error import AppError
from domain.models.phase1 import Phase1Response
from infra.network.camera_http_client import CameraHttpClient, parse_kv_lines

DEVICE_KEYS: tuple[str, ...] = (
    "SYS_VERSION",
    "SYS_MODELNAME",
    "SYS_MODELNAME_ID",
    "SYS_BOARDID",
    "NET_MAC",
    "NET_LOCALIPMODE",
    "NET_RTSPPORT",
    "SYS_LINKDOWN_NUM",
    "SYS_MODE",
    "SYS_PRODUCT_MODEL",
    "SYS_MODULE_TYPE",
    "SYS_MODULE_DETAIL",
    "SYS_PTZ_TYPE",
    "SYS_ZOOMMODULE",
    "SYS_AI_VERSION",
    "SYS_RCV_VERSION",
    "CAM_READMODULEVERSION",
    "CAM_READMECAVERSION",
    "TEST_Power_CheckString",
    "SYS_STARTTIME",
    "REC_DISKTYPE",
    "REC_DISKSIZE",
    "REC_DISKAVAILABLE",
)

SYSTEM_KEYS: tuple[str, ...] = (
    "SYS_CURRENTTIME",
    "SYS_BOARDTEMP",
    "SYS_BOARD_TEMP",
    "ETC_BOARDTEMP",
    "GIS_CDS",
    "GIS_CDS_CUR",
    "GIS_CDS_CURRENT",
    "SYS_FANSTATUS",
    "SYS_FAN_STATUS",
    "FAN_STATUS",
    "CAM_HI_CURRENT_Y",
    "CAM_NXP_CURRENT_Y",
    "CAM_AMBA_CURRENT_Y",
)

READPAGE_SYSINFO_TAIL = "ReadParam?action=readpage&page=sysinfo"


@dataclass(frozen=True)
class InfoReadResult:
    readparam_kv: dict[str, str]
    sysinfo_kv: dict[str, str]
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


def build_disk_text(kv: dict[str, str]) -> str:
    disk_type = (kv.get("REC_DISKTYPE") or "").strip()
    disk_size = (kv.get("REC_DISKSIZE") or "").strip()
    disk_free = (kv.get("REC_DISKAVAILABLE") or "").strip()

    if not any((disk_type, disk_size, disk_free)):
        return "-"

    parts: list[str] = []
    if disk_type:
        parts.append(disk_type)
    if disk_free or disk_size:
        parts.append(f"{disk_free or '?'} / {disk_size or '?'}")
    return " ".join(parts).strip() or "-"


def build_info_summary_map(kv: dict[str, str]) -> dict[str, str]:
    model_name = (kv.get("SYS_MODELNAME_ID") or kv.get("SYS_MODELNAME") or "").strip() or "-"
    return {
        "mac": (kv.get("NET_MAC") or "-").strip() or "-",
        "sys_modelname": model_name,
        "sys_version": (kv.get("SYS_VERSION") or "-").strip() or "-",
        "sys_mode": format_display_value("SYS_MODE", kv.get("SYS_MODE")),
        "module_version": (kv.get("CAM_READMODULEVERSION") or "-").strip() or "-",
        "meca_version": (kv.get("CAM_READMECAVERSION") or "-").strip() or "-",
        "linkdown_num": (kv.get("SYS_LINKDOWN_NUM") or "-").strip() or "-",
        "local_ip_mode": format_display_value("NET_LOCALIPMODE", kv.get("NET_LOCALIPMODE")),
        "power_type": (kv.get("TEST_Power_CheckString") or "-").strip() or "-",
        "startup_time": (kv.get("SYS_STARTTIME") or "-").strip() or "-",
        "disk": build_disk_text(kv),
        "ai_version": (kv.get("SYS_AI_VERSION") or "-").strip() or "-",
        "rcv_version": (kv.get("SYS_RCV_VERSION") or "-").strip() or "-",
    }


def build_missing_keys(requested_keys: Iterable[str], merged_kv: dict[str, str]) -> tuple[str, ...]:
    missing: list[str] = []
    for key in requested_keys:
        if not (merged_kv.get(key) or "").strip():
            missing.append(str(key))
    return tuple(missing)


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


def _read_readpage_sysinfo(client: CameraHttpClient) -> dict[str, str]:
    resp = client.request_tail(READPAGE_SYSINFO_TAIL)

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
        message="readpage sysinfo failed",
        status_code=resp.status,
        detail=(resp.body or "")[:200],
    )


class InfoRepository:
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
            raise AppError(kind="param", message="invalid phase1 response for info repository")
        return self.build_client(
            base_url=phase1.base_url,
            root_path=phase1.root_path,
            username=phase1.effective_username or "",
            password=phase1.effective_password or "",
            auth_scheme=phase1.auth_scheme,
            timeout_sec=timeout_sec,
            verify_tls=verify_tls,
        )

    def read_info_kv(self, client: CameraHttpClient) -> InfoReadResult:
        rp_kv: dict[str, str] = {}
        rp_kv.update(_read_readparam_kv_best_effort(client, DEVICE_KEYS, chunk_size=8))
        rp_kv.update(_read_readparam_kv_best_effort(client, SYSTEM_KEYS, chunk_size=8))

        try:
            sysinfo_kv = _read_readpage_sysinfo(client)
        except AppError:
            sysinfo_kv = {}

        merged = merge_nonempty_kv(rp_kv, sysinfo_kv)
        missing = build_missing_keys(tuple(DEVICE_KEYS) + tuple(SYSTEM_KEYS), merged)

        return InfoReadResult(
            readparam_kv=rp_kv,
            sysinfo_kv=sysinfo_kv,
            merged_kv=merged,
            missing_keys=missing,
        )

    def build_labeled_map(self, kv: dict[str, str]) -> dict[str, str]:
        return {display_name(k): format_display_value(k, v) for k, v in (kv or {}).items()}