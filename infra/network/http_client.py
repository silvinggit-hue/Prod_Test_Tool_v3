from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import requests

from domain.errors.app_error import AppError
from infra.network.session_factory import create_session


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: str
    headers: dict[str, str] = field(default_factory=dict)
    raw_headers: dict[str, list[str]] = field(default_factory=dict)

    def header_all(self, name: str) -> list[str]:
        key = (name or "").strip().lower()
        return list(self.raw_headers.get(key, []))


def _collect_raw_headers(response: requests.Response) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    try:
        if hasattr(response.raw, "headers") and hasattr(response.raw.headers, "getlist"):
            for k in response.raw.headers.keys():
                out[str(k).lower()] = [str(x) for x in response.raw.headers.getlist(k)]
            return out
    except Exception:
        pass

    for k, v in response.headers.items():
        out.setdefault(str(k).lower(), []).append(str(v))
    return out


def tail_text(text: str | None, limit: int = 300) -> str:
    body = (text or "").replace("\r", " ").replace("\n", " ").strip()
    if len(body) <= limit:
        return body
    return body[-limit:]


def looks_like_auth_error_body(body: str | None) -> bool:
    if not body:
        return False

    t = body.lower()
    needles = (
        "authentication error",
        "access denied",
        "denied",
        "auth error",
        "unauthorized",
        "<h2>authentication error",
        "login fail",
        "forbidden",
        "policy block",
    )
    return any(n in t for n in needles)


def is_remote_closed(detail: str | None) -> bool:
    d = (detail or "").lower()
    return (
        "remote end closed connection without response" in d
        or "remote disconnected" in d
        or "remotedisconnected" in d
        or "connection was closed" in d
        or "connection reset by peer" in d
        or "broken pipe" in d
        or "eof occurred in violation of protocol" in d
        or "read timed out" in d
    )


def _map_request_exception(exc: Exception) -> AppError:
    if isinstance(exc, requests.exceptions.SSLError):
        return AppError(kind="ssl", message="ssl handshake error", detail=str(exc))
    if isinstance(exc, requests.exceptions.Timeout):
        return AppError(kind="timeout", message="timeout", detail=str(exc))
    if isinstance(exc, requests.exceptions.ConnectionError):
        return AppError(kind="network", message="request failed", detail=str(exc))
    if isinstance(exc, requests.exceptions.RequestException):
        return AppError(kind="network", message="request failed", detail=str(exc))
    return AppError(kind="network", message="unexpected request failure", detail=str(exc))


def http_get(
    *,
    url: str,
    headers: dict[str, str] | None = None,
    timeout_sec: float,
    verify_tls: bool,
    session: requests.Session | None = None,
    read_body: bool = True,
    allow_redirects: bool = False,
) -> HttpResponse:
    sess = session or create_session(verify_tls=verify_tls)

    try:
        r = sess.get(
            url,
            headers=headers or {},
            timeout=float(timeout_sec),
            allow_redirects=bool(allow_redirects),
        )
    except Exception as exc:
        raise _map_request_exception(exc) from exc

    try:
        body = r.text if read_body else ""
    except Exception:
        body = ""

    return HttpResponse(
        status=int(r.status_code),
        body=body,
        headers={str(k): str(v) for k, v in r.headers.items()},
        raw_headers=_collect_raw_headers(r),
    )


def join_query_pairs(pairs: Iterable[tuple[str, str]]) -> str:
    from urllib.parse import quote

    out: list[str] = []
    for k, v in pairs:
        out.append(f"{quote(str(k), safe='')}={quote(str(v), safe='')}")
    return "&".join(out)