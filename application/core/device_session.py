from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from domain.enums.device import AuthScheme, DeviceFlavor
from domain.errors.app_error import AppError
from domain.models.phase1 import Phase1Response


def _parse_auth_scheme(value: str | None) -> AuthScheme:
    raw = (value or "").strip().lower()
    if raw == AuthScheme.NONE.value:
        return AuthScheme.NONE
    if raw == AuthScheme.BASIC.value:
        return AuthScheme.BASIC
    return AuthScheme.DIGEST


def _parse_device_flavor(value: str | None) -> DeviceFlavor:
    raw = (value or "").strip().lower()
    if raw == DeviceFlavor.LEGACY.value:
        return DeviceFlavor.LEGACY
    if raw == DeviceFlavor.TTA.value:
        return DeviceFlavor.TTA
    if raw == DeviceFlavor.SECURITY3.value:
        return DeviceFlavor.SECURITY3
    return DeviceFlavor.UNKNOWN


@dataclass(frozen=True)
class DeviceSession:
    base_url: str
    root_path: str
    auth_scheme: AuthScheme
    username: str
    effective_password: str
    flavor: DeviceFlavor
    shared_session: requests.Session | None = None

    @classmethod
    def from_phase1(
        cls,
        response: Phase1Response,
        *,
        shared_session: requests.Session | None = None,
    ) -> "DeviceSession":
        if not response.ok:
            raise AppError(kind="param", message="cannot build DeviceSession from failed Phase1Response")

        if not response.base_url or not response.root_path or not response.auth_scheme:
            raise AppError(kind="param", message="Phase1Response missing session fields")

        return cls(
            base_url=response.base_url,
            root_path=response.root_path,
            auth_scheme=_parse_auth_scheme(response.auth_scheme),
            username=response.effective_username or "",
            effective_password=response.effective_password or "",
            flavor=_parse_device_flavor(response.flavor),
            shared_session=shared_session,
        )

    def as_client_kwargs(self, *, timeout_sec: float, verify_tls: bool) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "root_path": self.root_path,
            "username": self.username,
            "password": self.effective_password,
            "auth_scheme": self.auth_scheme.value,
            "timeout_sec": timeout_sec,
            "verify_tls": verify_tls,
        }

    def close(self) -> None:
        session = self.shared_session
        if session is None:
            return
        try:
            session.close()
        except Exception:
            pass