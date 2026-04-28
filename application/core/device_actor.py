from __future__ import annotations

import time
import re
from dataclasses import replace
from typing import Any, Callable

from application.core.device_session import DeviceSession
from application.core.device_registry import DeviceRegistry
from application.core.ui_update_bus import UiUpdateBus
from application.services.connect_service import CameraConnectService
from common.display.enum_formatters import format_display_value
from domain.enums.command import CommandKind
from domain.enums.device import DeviceState
from domain.errors.app_error import AppError
from domain.models.phase1 import Phase1Request, Phase1Response
from domain.models.tasks import TaskSpec
from infra.device.control_repository import ControlRepository
from infra.device.info_repository import InfoRepository, build_disk_text
from infra.device.status_repository import StatusRepository


class DeviceActor:
    def __init__(
        self,
        *,
        ip: str,
        registry: DeviceRegistry,
        ui_update_bus: UiUpdateBus,
        connect_service: CameraConnectService,
        info_repository: InfoRepository,
        status_repository: StatusRepository,
        control_repository: ControlRepository,
        verify_tls: bool = False,
        default_timeout_sec: float = 6.0,
    ) -> None:
        self.ip = ip
        self.registry = registry
        self.ui_update_bus = ui_update_bus

        self.connect_service = connect_service
        self.info_repository = info_repository
        self.status_repository = status_repository
        self.control_repository = control_repository

        self.verify_tls = bool(verify_tls)
        self.default_timeout_sec = float(default_timeout_sec)

        self.session: DeviceSession | None = None
        self.current_task_id: str | None = None
        self.current_task_kind: str | None = None
        self.pending_count: int = 0

    def is_busy(self) -> bool:
        return self.current_task_id is not None

    def can_accept_task(self, task: TaskSpec) -> bool:
        return not self.is_busy()

    def begin_task(self, task: TaskSpec) -> None:
        if self.is_busy():
            raise AppError(kind="busy", message="device actor already busy", detail=self.ip)

        self.current_task_id = task.task_id
        self.current_task_kind = task.command.value

        snapshot = self.registry.require_snapshot(self.ip)
        updated = replace(
            snapshot,
            command=replace(
                snapshot.command,
                current_task_id=task.task_id,
                current_task_kind=task.command.value,
                inflight=True,
                queued_count=max(0, self.pending_count),
                progress_text=task.command.value,
            ),
        )
        self.registry.upsert_snapshot(updated)
        self.ui_update_bus.mark_device_dirty(self.ip)

    def finish_task(
        self,
        *,
        message: str = "",
        error: AppError | None = None,
    ) -> None:
        snapshot = self.registry.require_snapshot(self.ip)

        # Step 4 최종 수정 반영:
        # generic message가 control-specific message를 덮어쓰지 않도록 기존 last_message 유지
        keep_message = snapshot.command.last_message
        final_message = keep_message or message

        updated = replace(
            snapshot,
            command=replace(
                snapshot.command,
                current_task_id=None,
                current_task_kind=None,
                inflight=False,
                queued_count=max(0, self.pending_count),
                last_result="ok" if error is None else "error",
                last_message=final_message if error is None else keep_message,
                last_error_kind=(error.kind if error else ""),
                last_error_detail=(error.detail or error.message if error else ""),
                progress_text="",
            ),
        )
        self.registry.upsert_snapshot(updated)
        self.current_task_id = None
        self.current_task_kind = None
        self.ui_update_bus.mark_device_dirty(self.ip)

    def execute_task(self, task: TaskSpec) -> None:
        self.begin_task(task)
        try:
            if task.command == CommandKind.CONNECT:
                self._handle_connect(task)
                self.finish_task(message="connect completed")
            elif task.command == CommandKind.INFO_LOAD:
                self._handle_info_load(task)
                self.finish_task(message="info_load completed")
            elif task.command == CommandKind.STATUS_POLL:
                self._handle_status_poll(task)
                self.finish_task(message="status_poll completed")
            elif task.command == CommandKind.CONTROL:
                self._handle_control(task)
                self.finish_task(message="")
            else:
                raise AppError(kind="param", message="unsupported task command", detail=task.command.value)

        except AppError as exc:
            self._apply_error_state(exc)
            self.finish_task(message="", error=exc)
            raise
        except Exception as exc:
            wrapped = AppError(kind="runtime", message="device task failed", detail=str(exc))
            self._apply_error_state(wrapped)
            self.finish_task(message="", error=wrapped)
            raise wrapped from exc

    def _apply_error_state(self, error: AppError) -> None:
        snapshot = self.registry.require_snapshot(self.ip)
        new_state = snapshot.state

        if error.kind == "auth":
            new_state = DeviceState.AUTH_FAILED
        elif error.kind in ("timeout", "network", "http"):
            new_state = DeviceState.DISCONNECTED

        updated = replace(snapshot, state=new_state, connected=(new_state == DeviceState.READY))
        self.registry.upsert_snapshot(updated)
        self.ui_update_bus.mark_device_dirty(self.ip)

    def _handle_connect(self, task: TaskSpec) -> None:
        payload = dict(task.payload or {})
        request = payload.get("request")
        if not isinstance(request, Phase1Request):
            raise AppError(kind="param", message="connect task missing Phase1Request")

        response = self.connect_service.connect(request)
        if not response.ok:
            raise response.error or AppError(kind="auth", message="connect failed")

        self.session = DeviceSession.from_phase1(response)

        snapshot = self.registry.require_snapshot(self.ip)
        updated = replace(
            snapshot,
            port=request.port,
            state=DeviceState.READY,
            connected=True,
            info_loaded=False,
            base_url=response.base_url or "",
            root_path=response.root_path or "",
            auth_scheme=response.auth_scheme or "",
            flavor=self.session.flavor,
            username=response.effective_username or "",
            effective_password=response.effective_password or "",
            default_password_state=response.default_password_state,
            password_changed=response.password_changed,
            sys_version=response.sys_version or snapshot.sys_version,
            firmware=response.sys_version or snapshot.firmware,
            last_success_at=time.time(),
        )
        self.registry.upsert_snapshot(updated)
        self.ui_update_bus.mark_device_dirty(self.ip)

    def _require_session(self) -> DeviceSession:
        if self.session is None:
            snapshot = self.registry.require_snapshot(self.ip)
            if snapshot.base_url and snapshot.root_path and snapshot.auth_scheme:
                response = Phase1Response(
                    ok=True,
                    base_url=snapshot.base_url,
                    root_path=snapshot.root_path,
                    auth_scheme=snapshot.auth_scheme,
                    flavor=snapshot.flavor.value,
                    effective_username=snapshot.username,
                    effective_password=snapshot.effective_password,
                    sys_version=snapshot.sys_version,
                )
                self.session = DeviceSession.from_phase1(response)
            else:
                raise AppError(kind="state", message="device session is not established", detail=self.ip)
        return self.session

    def _handle_info_load(self, task: TaskSpec) -> None:
        session = self._require_session()
        client = self.info_repository.build_client(
            **session.as_client_kwargs(
                timeout_sec=self.default_timeout_sec,
                verify_tls=self.verify_tls,
            )
        )
        result = self.info_repository.read_info_kv(client)
        kv = result.merged_kv

        snapshot = self.registry.require_snapshot(self.ip)

        updated = replace(
            snapshot,
            state=DeviceState.READY,
            connected=True,
            info_loaded=True,
            mac=(kv.get("NET_MAC") or snapshot.mac).strip(),
            model=(kv.get("SYS_MODELNAME_ID") or kv.get("SYS_MODELNAME") or snapshot.model).strip(),
            firmware=(kv.get("SYS_VERSION") or snapshot.firmware).strip(),
            sys_version=(kv.get("SYS_VERSION") or snapshot.sys_version).strip(),
            board_id=(kv.get("SYS_BOARDID") or snapshot.board_id).strip(),
            module_type=(kv.get("SYS_MODULE_TYPE") or snapshot.module_type).strip(),
            module_detail=(kv.get("SYS_MODULE_DETAIL") or snapshot.module_detail).strip(),
            ptz_type=(kv.get("SYS_PTZ_TYPE") or snapshot.ptz_type).strip(),
            zoom_module=(kv.get("SYS_ZOOMMODULE") or snapshot.zoom_module).strip(),

            sys_mode_text=format_display_value("SYS_MODE", kv.get("SYS_MODE")),
            module_version=(kv.get("CAM_READMODULEVERSION") or snapshot.module_version).strip() or "-",
            ptz_fw=(kv.get("CAM_READMECAVERSION") or snapshot.ptz_fw).strip() or "-",

            # 기존 extra_id 대신 LD
            linkdown_num=(kv.get("SYS_LINKDOWN_NUM") or snapshot.linkdown_num).strip() or "-",

            local_ip_mode=format_display_value("NET_LOCALIPMODE", kv.get("NET_LOCALIPMODE")),
            power_type=(kv.get("TEST_Power_CheckString") or snapshot.power_type).strip() or "-",
            startup_time=(kv.get("SYS_STARTTIME") or snapshot.startup_time).strip() or "-",
            disk_text=build_disk_text(kv),
            ai_version=(kv.get("SYS_AI_VERSION") or snapshot.ai_version).strip() or "-",
            rcv_version=(kv.get("SYS_RCV_VERSION") or snapshot.rcv_version).strip() or "-",

            last_success_at=time.time(),
        )
        self.registry.upsert_snapshot(updated)
        self.ui_update_bus.mark_device_dirty(self.ip)

    def _handle_status_poll(self, task: TaskSpec) -> None:
        session = self._require_session()
        client = self.status_repository.build_client(
            **session.as_client_kwargs(
                timeout_sec=self.default_timeout_sec,
                verify_tls=self.verify_tls,
            )
        )
        result = self.status_repository.read_status_kv(client)
        kv = result.merged_kv

        def first(*keys: str) -> str:
            for key in keys:
                value = (kv.get(key) or "").strip()
                if value:
                    return value
            return "-"

        snapshot = self.registry.require_snapshot(self.ip)

        metrics = replace(
            snapshot.metrics,
            rtc_text=first("SYS_CURRENTTIME"),
            temp_text=first("SYS_BOARDTEMP", "SYS_BOARD_TEMP", "ETC_BOARDTEMP"),

            # Ethernet: raw ETHTOOL 말고 사람이 읽는 값
            eth_text=self._format_ethernet_text(kv),

            rate1_text=self._build_rate_text(kv, 1),
            rate2_text=self._build_rate_text(kv, 2),
            rate3_text=self._build_rate_text(kv, 3),
            rate4_text=self._build_rate_text(kv, 4),
            audio_enc_bitrate=first("GRS_AENCBITRATE1"),
            audio_dec_bitrate=first("GRS_ADECBITRATE1"),
            audio_dec_algorithm=first("GRS_ADECALGORITHM1"),
            audio_dec_samplerate=first("GRS_ADECSAMPLERATE1"),

            # CDS 보정
            cds_text=self._pick_cds_text(kv),

            # Current Y는 "Current Value 81 CDS Value 0" 같은 raw에서 숫자만 추출
            current_y_text=self._parse_current_y_value(
                first("CAM_HI_CURRENT_Y", "CAM_NXP_CURRENT_Y", "CAM_AMBA_CURRENT_Y")
            ),

            fan_text=first("SYS_FANSTATUS", "SYS_FAN_STATUS", "FAN_STATUS"),
            sensor_leds=self._tuple_leds(kv, "GIS_SENSOR"),
            alarm_leds=self._tuple_leds(kv, "GIS_ALARM"),
            updated_at=time.time(),
        )

        updated = replace(
            snapshot,
            state=DeviceState.READY,
            connected=True,
            metrics=metrics,
            air_wiper=(kv.get("GIS_AIRWIPER") or snapshot.air_wiper).strip() or "-",

            # Ethernet Speed Rate는 속도만 보관
            ethernet_speed_rate=self._format_link_speed_from_ethtool(kv.get("ETHTOOL")),

            last_success_at=time.time(),
        )
        self.registry.upsert_snapshot(updated)
        self.ui_update_bus.mark_device_dirty(self.ip)

    def _handle_control(self, task: TaskSpec) -> None:
        session = self._require_session()
        client = self.control_repository.build_client(
            **session.as_client_kwargs(
                timeout_sec=self.default_timeout_sec,
                verify_tls=self.verify_tls,
            )
        )
        payload = dict(task.payload or {})
        handler_name = str(payload.get("handler") or "").strip()
        kwargs = dict(payload.get("kwargs") or {})

        if not handler_name:
            raise AppError(kind="param", message="control task missing handler")

        handler: Callable[..., Any] | None = getattr(self.control_repository, handler_name, None)
        if handler is None:
            raise AppError(kind="param", message="unknown control handler", detail=handler_name)

        result = handler(client, **kwargs)

        snapshot = self.registry.require_snapshot(self.ip)

        # Step 4 최종 수정 반영:
        # 실제 control 종류별 완료 메시지를 유지
        completed_message = f"{handler_name} completed"

        updated = replace(
            snapshot,
            command=replace(
                snapshot.command,
                last_result="ok",
                last_message=completed_message,
                last_error_kind="",
                last_error_detail="",
            ),
            last_success_at=time.time(),
        )
        self.registry.upsert_snapshot(updated)
        self.ui_update_bus.mark_device_dirty(self.ip)

    def has_session(self) -> bool:
        return self.session is not None

    @staticmethod
    def _tuple_leds(kv: dict[str, str], prefix: str) -> tuple[bool, bool, bool, bool]:
        values: list[bool] = []
        for idx in range(1, 5):
            raw = (kv.get(f"{prefix}{idx}") or "").strip().lower()
            values.append(raw in ("1", "on", "true", "yes"))
        return tuple(values)  # type: ignore[return-value]

    @staticmethod
    def _build_rate_text(kv: dict[str, str], idx: int) -> str:
        bitrate = (kv.get(f"GRS_VENCBITRATE{idx}") or "").strip()
        fps = (kv.get(f"GRS_VENCFRAME{idx}") or "").strip()
        if not bitrate and not fps:
            return "-"
        return f"{bitrate or '-'}kbps / {fps or '-'}fps"

    @staticmethod
    def _parse_current_y_value(text: str | None) -> str:
        if not text:
            return "-"

        s = " ".join(str(text).split()).strip()
        low = s.lower()

        if low in {"unknown", "n/a", "na", "--", "-", "not support", "not supported", "unsupported"}:
            return "-"

        m = re.search(r"current\s+value\s+(-?\d+)", s, flags=re.IGNORECASE)
        if m:
            return m.group(1)

        ints = re.findall(r"(-?\d+)", s)
        if ints:
            return ints[0]

        return s or "-"

    @staticmethod
    def _format_link_speed_from_ethtool(code: str | None) -> str:
        if code is None:
            return "-"

        v = str(code).strip()
        if not v:
            return "-"

        if v == "24":
            return "1G"
        if v == "22":
            return "100M"

        return f"ETHTOOL({v})"

    @classmethod
    def _format_ethernet_text(cls, kv: dict[str, str]) -> str:
        link_state = (
                (kv.get("NET_LINKSTATE") or "")
                or (kv.get("NET_LINK_STATE") or "")
        ).strip().lower()

        state_text = "link"
        if link_state in {"0", "down", "off", "nolink"}:
            state_text = "unlink"
        elif link_state in {"1", "up", "on", "link"}:
            state_text = "link"

        speed_text = cls._format_link_speed_from_ethtool(kv.get("ETHTOOL"))
        if speed_text == "-":
            speed_text = (
                                 (kv.get("NET_LINKSPEED") or "")
                                 or (kv.get("NET_LINK_SPEED") or "")
                                 or "-"
                         ).strip() or "-"

        if speed_text == "-":
            return state_text

        return f"{state_text} / {speed_text}"

    @staticmethod
    def _pick_cds_text(kv: dict[str, str]) -> str:
        # as_test_tool 계열 우선순위: SYS_FTCAMERA_CDS -> GIS_CDS 계열
        for key in ("SYS_FTCAMERA_CDS", "GIS_CDS", "GIS_CDS_CUR", "GIS_CDS_CURRENT"):
            value = (kv.get(key) or "").strip()
            if value:
                return value
        return "-"