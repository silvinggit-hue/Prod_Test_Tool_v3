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

    def set_air_wiper(self, client: CameraHttpClient, action: str) -> ControlResult:
        act = (action or "").strip().lower()
        if act not in {"on", "off"}:
            raise AppError(kind="param", message=f"unsupported air wiper action: {act}")

        body = self.request_raw(
            client,
            f"SendPTZ?action=sendptz&PTZ_CHANNEL=1&PTZ_WIPER={'1' if act == 'on' else '0'}",
        )
        return ControlResult(ok=True, action=act, response_text=body or f"PTZ_WIPER={1 if act == 'on' else 0}")

    def apply_secondary_video(self, client: CameraHttpClient) -> ControlResult:
        cap_res = (self.read_value(client, "VID_CAPDUALRESOLUTION") or "").strip()
        cap_bw_max_raw = (self.read_value(client, "VID_CAPDUALBANDWIDTHMAX") or "").strip()
        cap_bw_min_raw = (self.read_value(client, "VID_CAPDUALBANDWIDTHMIN") or "").strip()

        try:
            cap_mask = int(cap_res or "0", 0)
        except Exception:
            cap_mask = 0

        try:
            cap_bw_max = int(cap_bw_max_raw or "0")
        except Exception:
            cap_bw_max = 0

        try:
            cap_bw_min = int(cap_bw_min_raw or "0")
        except Exception:
            cap_bw_min = 0

        dual_res_1080p = 131072
        if cap_mask and not (cap_mask & dual_res_1080p):
            raise AppError(
                kind="param",
                message=f"secondary 1920x1080 unsupported: VID_CAPDUALRESOLUTION={cap_res}",
            )

        target_bw = 4000
        if cap_bw_max > 0:
            target_bw = min(target_bw, cap_bw_max)

        if cap_bw_min > 0 and target_bw < cap_bw_min:
            raise AppError(
                kind="param",
                message=f"secondary bitrate unsupported: requested=4000 supported={cap_bw_min}~{cap_bw_max}",
            )

        tail = (
            "WriteParam?action=writeparam"
            "&VID_PREVIEWENABLE=0"
            "&VID_DUALRESOLUTION=17"
            f"&VID_DUALBANDWIDTH={target_bw}"
            "&VID_DUALALGORITHM=0"
            "&VID_DUALPREFERENCE=1"
            "&VID_USEDUAL=1"
        )
        body = self.request_raw(client, tail)
        return ControlResult(ok=True, action="apply", response_text=body or tail)

    def set_min_focus_length(self, client: CameraHttpClient, value: str) -> ControlResult:
        v = (value or "").strip()
        if not v:
            raise AppError(kind="param", message="minimum focus length is empty")
        try:
            int(v)
        except ValueError:
            raise AppError(kind="param", message=f"minimum focus length must be numeric: {v}")

        body = self.request_raw(client, f"WriteParam?action=writeparam&CAM_HI_FOCUS_LIMIT={quote(v, safe='')}")
        return ControlResult(ok=True, action="apply", response_text=body or f"CAM_HI_FOCUS_LIMIT={v}")

    def set_sensor_485(self, client: CameraHttpClient, action: str) -> ControlResult:
        act = (action or "").strip().lower()
        if act not in {"on", "off"}:
            raise AppError(kind="param", message=f"unsupported 485 sensor action: {act}")

        termination = "1" if act == "on" else "0"
        tail = (
            "WriteParam?action=writeparam"
            "&SER_PROTOCOL_1=0"
            "&SER_BITRATE_1=0"
            "&SER_DATABIT_1=3"
            "&SER_PARITY_1=0"
            "&SER_STOPBIT_1=0"
            "&SER_TCPLISTENPORT_1=0"
            "&SER_PROTOCOL_2=2"
            "&SER_BITRATE_2=0"
            "&SER_DATABIT_2=3"
            "&SER_PARITY_2=0"
            "&SER_STOPBIT_2=0"
            "&SER_TCPLISTENPORT_2=0"
            f"&SER_485TERMINATION={termination}"
        )
        body = self.request_raw(client, tail)
        return ControlResult(ok=True, action=act, response_text=body or tail)

    def set_shock_sensor(self, client: CameraHttpClient, action: str) -> ControlResult:
        act = (action or "").strip().lower()
        if act not in {"on", "off"}:
            raise AppError(kind="param", message=f"unsupported shock sensor action: {act}")

        if act == "on":
            body1 = self.request_raw(
                client,
                "WriteParam?action=writeparam"
                "&EVT_SHOCKENABLE=1"
                "&EVT_SHOCKSENSITIVITY=1"
                "&EVT_LOCALSHOCK=134"
                "&EVT_OSDLOCALSHOCK=1",
            )
            body2 = self.request_raw(
                client,
                "WriteParam?action=writeparam"
                "&ETC_EVENTOSDDISPLAYNAME0=1"
                "&ETC_EVENTOSDFONTSIZE0=84",
            )
            body = "\n".join(x for x in [body1, body2] if x)
        else:
            body = self.request_raw(
                client,
                "WriteParam?action=writeparam"
                "&EVT_SHOCKENABLE=0"
                "&EVT_OSDLOCALSHOCK=0"
                "&ETC_EVENTOSDDISPLAYNAME0=0",
            )

        return ControlResult(ok=True, action=act, response_text=body or act)

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
        explicit = (value or "").strip()

        # RTC write 전에 순차 실행
        pre_commands = [
            "GetState?action=command&Command=i2cset%20-fy%200%200x51%200x02%200x00",
            "GetState?action=command&Command=i2cset%20-fy%200%200x51%200x00%200x00",
        ]

        pre_results: list[str] = []
        for tail in pre_commands:
            try:
                body = self.request_raw(client, tail)
                pre_results.append(body or tail)
            except Exception as exc:
                pre_results.append(f"{tail} -> ignored error: {exc}")

        if explicit:
            body = self.write_param(client, "SYS_CURRENTTIME", explicit)
            result_text = "\n".join(pre_results + [body or f"SYS_CURRENTTIME={explicit}"])
            return ControlResult(
                ok=True,
                action="set_rtc",
                response_text=result_text,
            )

        now = datetime.now()
        candidates = [
            now.strftime("%Y/%m/%d %H:%M:%S"),
            now.strftime("%Y-%m-%d %H:%M:%S"),
            now.strftime("%Y%m%d%H%M%S"),
        ]

        try:
            before_value = (client.read_param_value("SYS_CURRENTTIME") or "").strip()
        except Exception:
            before_value = ""

        last_error: AppError | None = None
        last_body: str = ""
        last_candidate: str = ""

        for candidate in candidates:
            try:
                body = self.write_param(client, "SYS_CURRENTTIME", candidate)
                last_body = body
                last_candidate = candidate

                try:
                    after_value = (client.read_param_value("SYS_CURRENTTIME") or "").strip()
                except Exception:
                    after_value = ""

                if after_value and after_value != before_value:
                    result_text = "\n".join(pre_results + [body or f"SYS_CURRENTTIME={candidate}"])
                    return ControlResult(
                        ok=True,
                        action="set_rtc",
                        response_text=result_text,
                    )

                if after_value and now.strftime("%H:%M") in after_value:
                    result_text = "\n".join(pre_results + [body or f"SYS_CURRENTTIME={candidate}"])
                    return ControlResult(
                        ok=True,
                        action="set_rtc",
                        response_text=result_text,
                    )

            except AppError as exc:
                last_error = exc
                continue

        if last_body:
            result_text = "\n".join(pre_results + [last_body or f"SYS_CURRENTTIME={last_candidate}"])
            return ControlResult(
                ok=True,
                action="set_rtc",
                response_text=result_text,
            )

        raise last_error or AppError(kind="compat", message="rtc write failed")

    def set_extra_id(self, client: CameraHttpClient, value: str) -> ControlResult:
        v = (value or "").strip()
        if not v:
            raise AppError(kind="param", message="extra id is empty")
        body = self.write_param(client, "NET_EXTRA_ID", v)
        return ControlResult(ok=True, action="set_extra_id", response_text=body or f"NET_EXTRA_ID={v}")

    def set_video_input_format(
            self,
            client: CameraHttpClient,
            input_code: str,
            resolution_code: str | None = None,
    ) -> ControlResult:
        code = (input_code or "").strip()
        res = (resolution_code or "").strip()

        if not code:
            raise AppError(kind="param", message="video input code is empty")

        if res:
            tail = (
                "WriteParam?action=writeparam"
                f"&VID_INPUTFORMAT={quote(code, safe='')}"
                f"&VID_RESOLUTION={quote(res, safe='')}"
            )
            body = self.request_raw(client, tail)
            return ControlResult(
                ok=True,
                action="video_input",
                response_text=body or f"VID_INPUTFORMAT={code}&VID_RESOLUTION={res}",
            )

        body = self.write_param(client, "VID_INPUTFORMAT", code)
        return ControlResult(ok=True, action="video_input", response_text=body or f"VID_INPUTFORMAT={code}")

    def apply_audio_payload(self, client: CameraHttpClient, *, payload: dict[str, str]) -> ControlResult:
        if not payload:
            raise AppError(kind="param", message="audio payload is empty")
        query = urlencode({str(k): str(v) for k, v in payload.items()})
        body = self.request_raw(client, "WriteParam?action=writeparam&" + query)
        return ControlResult(ok=True, action="audio", response_text=body or query)

    def apply_audio_profile(
        self,
        client: CameraHttpClient,
        *,
        algorithm: str,
        source: str,
        output: str,
        mode: str = "3",
        set_max_volume: bool = False,
    ) -> ControlResult:
        algo = (algorithm or "").strip().lower()
        src = (source or "").strip().lower()
        out = (output or "").strip().lower()
        audio_mode = (mode or "").strip() or "3"

        if algo not in {"aac", "g711"}:
            raise AppError(kind="param", message=f"unsupported audio algorithm: {algo}")
        if src not in {"analog", "embedded"}:
            raise AppError(kind="param", message=f"unsupported audio source: {src}")
        if out not in {"decoded", "loopback"}:
            raise AppError(kind="param", message=f"unsupported audio output: {out}")
        if audio_mode not in {"0", "1", "2", "3"}:
            raise AppError(kind="param", message=f"unsupported audio mode: {audio_mode}")

        if set_max_volume:
            self.request_raw(client, "WriteParam?action=writeparam&AUD_GAIN=31")

        params: list[tuple[str, str]] = []
        if algo == "g711":
            params.append(("AUD_ALGORITHM", "0"))
        else:
            params.append(("AUD_ALGORITHM", "1"))
            params.append(("AUD_BITRATE", "1"))
            params.append(("AUD_SAMPLERATE", "1"))

        params.append(("AUD_AUDIOMODE", audio_mode))
        params.append(("AUD_NOT_EMBEDDED", "1" if src == "analog" else "0"))
        params.append(("AUD_LOOPBACK", "1" if out == "loopback" else "0"))

        tail = "WriteParam?action=writeparam&" + "&".join(f"{k}={v}" for k, v in params)
        body = self.request_raw(client, tail)
        return ControlResult(ok=True, action="audio", response_text=body or tail)