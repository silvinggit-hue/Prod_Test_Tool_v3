from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote, urlencode

from domain.errors.app_error import AppError
from domain.models.phase1 import Phase1Response
from infra.network.camera_http_client import CameraHttpClient

PT_DIR_MAP = {
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "leftup": "leftup",
    "rightup": "rightup",
    "leftdown": "leftdown",
    "rightdown": "rightdown",
    "stop": "stop",
}

ZOOM_MAP = {
    "in": "zoomin,-1",
    "out": "zoomout,-1",
    "stop": "stop",
    "1x": None,
}

FOCUS_MAP = {
    "near": "focusnear,-1",
    "far": "focusfar,-1",
    "stop": "stop",
    "auto": None,
}

TDN_MAP = {
    "auto": "0",
    "day": "2",
    "night": "3",
}

ICR_MAP = {
    "auto": "0",
    "on": "1",
    "off": "2",
}


@dataclass(frozen=True)
class ControlResult:
    ok: bool
    action: str
    response_text: str
    detail: str = ""


def parse_pt_speed(value: str | int | None) -> int:
    try:
        speed = int(str(value).strip())
    except Exception:
        speed = 5
    return max(1, min(8, speed))


class ControlRepository:
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
            raise AppError(kind="param", message="invalid phase1 response for control repository")
        return self.build_client(
            base_url=phase1.base_url,
            root_path=phase1.root_path,
            username=phase1.effective_username or "",
            password=phase1.effective_password or "",
            auth_scheme=phase1.auth_scheme,
            timeout_sec=timeout_sec,
            verify_tls=verify_tls,
        )

    def request_raw(self, client: CameraHttpClient, tail: str) -> str:
        resp = client.request_tail(tail)
        body = (resp.body or "").strip()

        if resp.status == 200:
            if body.lower() and any(x in body.lower() for x in ("ng", "error", "fail", "invalid")):
                raise AppError(
                    kind="compat",
                    message="request rejected",
                    status_code=200,
                    detail=body[:200],
                )
            return body

        if resp.status in (401, 403):
            raise AppError(
                kind="auth",
                message="authentication failed",
                status_code=resp.status,
                detail=body[:200],
            )

        raise AppError(
            kind="http",
            message="request failed",
            status_code=resp.status,
            detail=body[:200],
        )

    def read_value(self, client: CameraHttpClient, key: str) -> str:
        return client.read_param_value(key)

    def write_param(self, client: CameraHttpClient, key: str, value: str) -> str:
        kq = quote(str(key), safe="")
        vq = quote(str(value or ""), safe="")
        return self.request_raw(client, f"WriteParam?action=writeparam&{kq}={vq}")

    def set_state(self, client: CameraHttpClient, key: str, value: str) -> str:
        kq = quote(str(key), safe="")
        vq = quote(str(value or ""), safe="")
        return self.request_raw(client, f"SetState?action=setstate&{kq}={vq}")

    def send_ptz_move(
        self,
        client: CameraHttpClient,
        *,
        channel: int,
        move: str,
        timeout_ms: int | None = 5000,
    ) -> str:
        params: list[str] = [
            "action=sendptz",
            f"PTZ_CHANNEL={int(channel)}",
            f"PTZ_MOVE={quote(move or '', safe=',')}",
        ]
        if timeout_ms is not None and (move or "").lower() != "stop":
            params.append(f"PTZ_TIMEOUT={int(timeout_ms)}")
        return self.request_raw(client, "SendPTZ?" + "&".join(params))

    def send_ptz_direction(
        self,
        client: CameraHttpClient,
        *,
        channel: int,
        direction: str,
        speed: int,
        timeout_ms: int | None = 5000,
        mode: int = 1,
    ) -> str:
        sp = parse_pt_speed(speed)
        move = f"{direction},{sp},{int(mode)}"
        return self.send_ptz_move(
            client,
            channel=channel,
            move=move,
            timeout_ms=timeout_ms,
        )

    def pt(self, client: CameraHttpClient, action: str, *, speed: int | str | None = 5) -> ControlResult:
        act = (action or "").strip().lower()
        if act not in PT_DIR_MAP:
            raise AppError(kind="param", message=f"unsupported pt action: {act}")

        if act == "stop":
            body = self.send_ptz_move(client, channel=1, move="stop", timeout_ms=None)
            return ControlResult(ok=True, action=act, response_text=body or "PT stop")

        body = self.send_ptz_direction(
            client,
            channel=1,
            direction=PT_DIR_MAP[act],
            speed=parse_pt_speed(speed),
            timeout_ms=5000,
            mode=1,
        )
        return ControlResult(ok=True, action=act, response_text=body or PT_DIR_MAP[act])

    def zoom(self, client: CameraHttpClient, action: str) -> ControlResult:
        act = (action or "").strip().lower()
        if act not in ZOOM_MAP:
            raise AppError(kind="param", message=f"unsupported zoom action: {act}")

        if act == "1x":
            body = self.request_raw(
                client,
                "SendPTZ?action=sendptz&PTZ_CHANNEL=1&PTZ_ABSOLUTEPOSITION=-1,-1,0,-1",
            )
            return ControlResult(ok=True, action=act, response_text=body or "1x")

        move = ZOOM_MAP[act] or "stop"
        body = self.send_ptz_move(
            client,
            channel=1,
            move=move,
            timeout_ms=None if act == "stop" else 5000,
        )
        return ControlResult(ok=True, action=act, response_text=body or move)

    def focus(self, client: CameraHttpClient, action: str) -> ControlResult:
        act = (action or "").strip().lower()
        if act not in FOCUS_MAP:
            raise AppError(kind="param", message=f"unsupported focus action: {act}")

        if act == "auto":
            body = self.request_raw(
                client,
                "SendPTZ?action=sendptz&PTZ_CHANNEL=1&PTZ_FOCUSAUTO=1",
            )
            return ControlResult(ok=True, action=act, response_text=body or "focus auto")

        move = FOCUS_MAP[act] or "stop"
        body = self.send_ptz_move(
            client,
            channel=1,
            move=move,
            timeout_ms=None if act == "stop" else 5000,
        )
        return ControlResult(ok=True, action=act, response_text=body or move)

    def set_tdn(self, client: CameraHttpClient, action: str) -> ControlResult:
        act = (action or "").strip().lower()
        if act not in TDN_MAP:
            raise AppError(kind="param", message=f"unsupported tdn action: {act}")
        body = self.write_param(client, "CAM_HI_TDN_MODE", TDN_MAP[act])
        return ControlResult(ok=True, action=act, response_text=body or f"CAM_HI_TDN_MODE={TDN_MAP[act]}")

    def set_icr(self, client: CameraHttpClient, action: str) -> ControlResult:
        act = (action or "").strip().lower()
        if act not in ICR_MAP:
            raise AppError(kind="param", message=f"unsupported icr action: {act}")
        body = self.write_param(client, "CAM_HI_TDN_FILTER", ICR_MAP[act])
        return ControlResult(ok=True, action=act, response_text=body or f"CAM_HI_TDN_FILTER={ICR_MAP[act]}")

    def reboot(self, client: CameraHttpClient) -> ControlResult:
        body = self.write_param(client, "SYS_REBOOT", "1")
        return ControlResult(ok=True, action="reboot", response_text=body or "SYS_REBOOT=1")

    def factory_reset(self, client: CameraHttpClient) -> ControlResult:
        body = self.write_param(client, "SYS_RESET_V2", "0")
        return ControlResult(ok=True, action="factory_reset", response_text=body or "SYS_RESET_V2=0")

    def set_model_name(self, client: CameraHttpClient, value: str) -> ControlResult:
        v = (value or "").strip()
        if not v:
            raise AppError(kind="param", message="model name is empty")
        body = self.write_param(client, "SYS_MODELNAME2", v)
        return ControlResult(ok=True, action="set_modelname", response_text=body or f"SYS_MODELNAME2={v}")

    def set_rtc(self, client: CameraHttpClient, value: str | None = None) -> ControlResult:
        v = (value or "").strip() or datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        body = self.write_param(client, "SYS_CURRENTTIME", v)
        return ControlResult(ok=True, action="set_rtc", response_text=body or f"SYS_CURRENTTIME={v}")

    def set_extra_id(self, client: CameraHttpClient, value: str) -> ControlResult:
        v = (value or "").strip()
        if not v:
            raise AppError(kind="param", message="extra id is empty")
        body = self.write_param(client, "NET_EXTRA_ID", v)
        return ControlResult(ok=True, action="set_extra_id", response_text=body or f"NET_EXTRA_ID={v}")

    def set_video_input_format(self, client: CameraHttpClient, input_code: str) -> ControlResult:
        code = (input_code or "").strip()
        if not code:
            raise AppError(kind="param", message="video input code is empty")
        body = self.write_param(client, "VID_INPUTFORMAT", code)
        return ControlResult(ok=True, action="video_input", response_text=body or f"VID_INPUTFORMAT={code}")

    def apply_audio_payload(self, client: CameraHttpClient, *, payload: dict[str, str]) -> ControlResult:
        if not payload:
            raise AppError(kind="param", message="audio payload is empty")
        query = urlencode({str(k): str(v) for k, v in payload.items()})
        body = self.request_raw(client, "WriteParam?action=writeparam&" + query)
        return ControlResult(ok=True, action="audio", response_text=body or query)