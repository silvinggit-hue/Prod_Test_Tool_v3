from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urljoin

import requests
from requests.auth import HTTPBasicAuth, HTTPDigestAuth

from domain.errors.app_error import AppError
from domain.models.firmware_models import FirmwareTarget
from domain.models.phase1 import Phase1Response
from infra.network.camera_http_client import CameraHttpClient
from infra.network.http_client import is_remote_closed, tail_text
from infra.network.session_factory import create_session


def _normalize_root_path(root_path: str) -> str:
    r = (root_path or "").strip()
    if not r.startswith("/"):
        r = "/" + r
    if not r.endswith("/"):
        r += "/"
    return r


def _build_upload_base_candidates(base_url: str, *, try_flipped_scheme: bool = True) -> list[str]:
    raw = (base_url or "").strip().rstrip("/")
    if not raw:
        return []

    out = [raw]
    if try_flipped_scheme:
        if raw.startswith("https://"):
            out.append("http://" + raw[len("https://") :])
        elif raw.startswith("http://"):
            out.append("https://" + raw[len("http://") :])

    uniq: list[str] = []
    for item in out:
        if item not in uniq:
            uniq.append(item)
    return uniq


def _default_headers() -> dict[str, str]:
    return {
        "User-Agent": "Mozilla/5.0 Prod_Test_Tool_v3/Firmware",
        "Accept": "*/*",
        "Connection": "keep-alive",
    }


def _auth_for_requests(*, username: str, password: str, auth_scheme: str):
    scheme = (auth_scheme or "").strip().lower()
    if scheme == "basic":
        return HTTPBasicAuth(username, password)
    if scheme == "digest":
        return HTTPDigestAuth(username, password)
    return None


@dataclass(frozen=True)
class UploadResult:
    status: int
    body_tail: str
    used_url: str


@dataclass(frozen=True)
class ReconnectProbeResult:
    ok: bool
    sys_version: str | None = None
    detail: str | None = None


class FirmwareRepository:
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
            raise AppError(kind="param", message="invalid phase1 response for firmware repository")
        return self.build_client(
            base_url=phase1.base_url,
            root_path=phase1.root_path,
            username=phase1.effective_username or "",
            password=phase1.effective_password or "",
            auth_scheme=phase1.auth_scheme,
            timeout_sec=timeout_sec,
            verify_tls=verify_tls,
        )

    def build_client_from_target(
        self,
        target: FirmwareTarget,
        *,
        timeout_sec: float,
        verify_tls: bool,
    ) -> CameraHttpClient:
        return self.build_client(
            base_url=target.base_url,
            root_path=target.root_path,
            username=target.username,
            password=target.password,
            auth_scheme=target.auth_scheme,
            timeout_sec=timeout_sec,
            verify_tls=verify_tls,
        )

    def read_sys_version(self, client: CameraHttpClient) -> str:
        value = (client.read_param_value("SYS_VERSION") or "").strip()
        if not value:
            raise AppError(kind="parse", message="SYS_VERSION is empty")
        return value

    def write_remote_upgrade_userinfo(self, client: CameraHttpClient, firmware_path: str) -> str:
        path = (firmware_path or "").strip()
        if not path:
            raise AppError(kind="param", message="firmware path is empty")

        if not os.path.isfile(path):
            raise AppError(kind="param", message="firmware file not found", detail=path)

        filename = os.path.basename(path)
        body = client.write_param("SYS_REMOTEUPGRADEUSERINFO", filename)
        return body or f"SYS_REMOTEUPGRADEUSERINFO={filename}"

    def upload_firmware_progress_html(
        self,
        *,
        base_url: str,
        root_path: str,
        username: str,
        password: str,
        auth_scheme: str,
        firmware_path: str,
        verify_tls: bool,
        timeout_sec: float,
        try_flipped_scheme: bool = True,
    ) -> UploadResult:
        path = (firmware_path or "").strip()
        if not path:
            raise AppError(kind="param", message="firmware path is empty")
        if not os.path.isfile(path):
            raise AppError(kind="param", message="firmware file not found", detail=path)

        filename = os.path.basename(path)
        rp = _normalize_root_path(root_path)
        upload_paths = ["progress.html", rp + "progress.html"]

        last_error: AppError | None = None
        auth = _auth_for_requests(
            username=username,
            password=password,
            auth_scheme=auth_scheme,
        )

        for base in _build_upload_base_candidates(base_url, try_flipped_scheme=try_flipped_scheme):
            base_norm = base.rstrip("/")

            for rel in upload_paths:
                url = f"{base_norm}/{rel.lstrip('/')}"
                session = create_session(verify_tls=verify_tls)

                try:
                    headers = _default_headers()

                    with open(path, "rb") as fp:
                        files = {
                            "upgrade": (
                                filename,
                                fp,
                                "application/octet-stream",
                            )
                        }
                        data = {"MAX_FILE_SIZE": "30000000"}

                        r = session.post(
                            url,
                            headers=headers,
                            data=data,
                            files=files,
                            timeout=float(timeout_sec),
                            allow_redirects=False,
                            verify=bool(verify_tls),
                            auth=auth,
                        )

                    status = int(r.status_code)
                    body_tail = tail_text(getattr(r, "text", ""), 300)

                    if status in (200, 204, 302, 303):
                        return UploadResult(
                            status=status,
                            body_tail=body_tail,
                            used_url=url,
                        )

                    if status in (401, 403):
                        raise AppError(
                            kind="auth",
                            message="firmware upload authentication failed",
                            status_code=status,
                            detail=body_tail,
                        )

                    raise AppError(
                        kind="http",
                        message="firmware upload failed",
                        status_code=status,
                        detail=body_tail,
                    )

                except requests.exceptions.SSLError as exc:
                    last_error = AppError(kind="ssl", message="ssl error", detail=str(exc))

                except requests.Timeout as exc:
                    if is_remote_closed(str(exc)):
                        return UploadResult(
                            status=200,
                            body_tail=str(exc),
                            used_url=url,
                        )
                    last_error = AppError(kind="timeout", message="timeout", detail=str(exc))

                except requests.RequestException as exc:
                    if is_remote_closed(str(exc)):
                        return UploadResult(
                            status=200,
                            body_tail=str(exc),
                            used_url=url,
                        )
                    last_error = AppError(kind="network", message="network error", detail=str(exc))

                except AppError as exc:
                    last_error = exc

                finally:
                    try:
                        session.close()
                    except Exception:
                        pass

        raise last_error or AppError(
            kind="http",
            message="firmware upload failed",
            detail="no candidate upload url worked",
        )

    def try_probe_reconnect(
        self,
        *,
        target: FirmwareTarget,
        verify_tls: bool,
        timeout_sec: float,
    ) -> ReconnectProbeResult:
        try:
            client = self.build_client_from_target(
                target,
                timeout_sec=timeout_sec,
                verify_tls=verify_tls,
            )
            version = self.read_sys_version(client)
            return ReconnectProbeResult(ok=True, sys_version=version)
        except AppError as exc:
            return ReconnectProbeResult(ok=False, sys_version=None, detail=str(exc))

    def read_after_reconnect_version(
        self,
        *,
        target: FirmwareTarget,
        verify_tls: bool,
        timeout_sec: float,
    ) -> str:
        client = self.build_client_from_target(
            target,
            timeout_sec=timeout_sec,
            verify_tls=verify_tls,
        )
        return self.read_sys_version(client)