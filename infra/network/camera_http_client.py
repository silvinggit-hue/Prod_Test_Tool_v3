from __future__ import annotations

import base64
import logging
import time
from typing import Iterable
from urllib.parse import quote, urljoin, urlparse, urlsplit

import requests

from domain.errors.app_error import AppError
from infra.network.digest_auth import (
    DigestChallenge,
    build_digest_authorization,
    parse_www_authenticate_digest,
)
from infra.network.http_client import (
    HttpResponse,
    http_get,
    is_remote_closed,
    looks_like_auth_error_body,
    tail_text,
)
from infra.network.session_factory import create_session

log = logging.getLogger(__name__)


def parse_kv_lines(text: str | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (text or "").splitlines():
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _normalize_root_path(root_path: str) -> str:
    rp = (root_path or "").strip()
    if not rp:
        return "/"
    if not rp.startswith("/"):
        rp = "/" + rp
    if not rp.endswith("/"):
        rp += "/"
    return rp


def _pick_digest_header(www_list: list[str]) -> str | None:
    for h in (www_list or []):
        if h and "digest" in h.lower():
            return h
    return www_list[0] if www_list else None


def _uri_from_full_url(url: str) -> str:
    sp = urlsplit(url)
    path = sp.path or "/"
    if not path.startswith("/"):
        path = "/" + path
    if sp.query:
        return path + "?" + sp.query
    return path


def _contains_basic(www_list: list[str]) -> bool:
    return any(h and "basic" in h.lower() for h in (www_list or []))


def _contains_digest(www_list: list[str]) -> bool:
    return any(h and "digest" in h.lower() for h in (www_list or []))


class CameraHttpClient:
    def __init__(
        self,
        *,
        base_url: str,
        root_path: str,
        username: str,
        password: str,
        auth_scheme: str,
        timeout_sec: float = 6.0,
        verify_tls: bool = False,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.root_path = _normalize_root_path(root_path)
        self.username = username or ""
        self.password = password or ""
        self.auth_scheme = (auth_scheme or "digest").strip().lower()
        self.timeout_sec = float(timeout_sec or 6.0)
        self.verify_tls = bool(verify_tls)

        self._session: requests.Session | None = session
        self._digest_challenge: DigestChallenge | None = None
        self._digest_nc: int = 0
        self._digest_cnonce: str = ""

    def get_session(self) -> requests.Session:
        if self._session is None:
            self._session = create_session(verify_tls=self.verify_tls)
        return self._session

    def with_shared_session(self, session: requests.Session) -> "CameraHttpClient":
        self._session = session
        return self

    def _make_url(self, tail: str) -> str:
        root = self.root_path
        if tail.startswith("/"):
            tail = tail[1:]
        return urljoin(self.base_url.rstrip("/") + "/", root.lstrip("/") + tail)

    def _make_abs_url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return self.base_url + path

    def _default_headers_for_url(self, url: str) -> dict[str, str]:
        p = urlparse(url)
        path = p.path or "/"

        if path == "/" or path == "":
            return {
                "User-Agent": "Mozilla/5.0 Prod_Test_Tool_v3",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Upgrade-Insecure-Requests": "1",
                "Connection": "keep-alive",
            }

        if (
            ("/ReadParam" in path)
            or ("/WriteParam" in path)
            or ("/GetState" in path)
            or ("/SendPTZ" in path)
            or ("/SetState" in path)
        ):
            return {
                "User-Agent": "Mozilla/5.0 Prod_Test_Tool_v3",
                "Accept": "text/plain, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": self.base_url.rstrip("/") + "/",
                "Connection": "keep-alive",
            }

        return {
            "User-Agent": "Mozilla/5.0 Prod_Test_Tool_v3",
            "Accept": "*/*",
            "Connection": "keep-alive",
        }

    def _merge_headers(self, url: str, extra: dict[str, str] | None) -> dict[str, str]:
        headers = dict(self._default_headers_for_url(url))
        if extra:
            headers.update(extra)
        return headers

    def _request_raw(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        read_body: bool = True,
    ) -> HttpResponse:
        last_err: AppError | None = None

        for attempt in range(1, 3):
            try:
                return http_get(
                    url=url,
                    headers=headers,
                    timeout_sec=self.timeout_sec,
                    verify_tls=self.verify_tls,
                    session=self.get_session(),
                    read_body=read_body,
                    allow_redirects=False,
                )
            except AppError as exc:
                last_err = exc
                if exc.kind == "network" and is_remote_closed(exc.detail) and attempt < 2:
                    time.sleep(0.25)
                    continue
                raise

        raise last_err or AppError(kind="network", message="request failed")

    def _ensure_digest_challenge(self) -> DigestChallenge:
        if self._digest_challenge is not None:
            return self._digest_challenge

        candidates = [
            self._make_url("ReadParam?action=readparam&ETC_MIN_PASSWORD_LEN=0"),
            self._make_url("ReadParam?action=readparam&SYS_VERSION=0"),
            self._make_abs_url("/"),
        ]

        last_status: int | None = None
        last_detail: str | None = None

        for url in candidates:
            try:
                response = self._request_raw(url, headers={"User-Agent": "Prod_Test_Tool_v3/probe"}, read_body=False)
                last_status = response.status

                if response.status == 401:
                    header = _pick_digest_header(response.header_all("WWW-Authenticate"))
                    if not header:
                        last_detail = "401 but no digest header"
                        continue

                    challenge = parse_www_authenticate_digest(header)
                    self._digest_challenge = challenge
                    self._digest_nc = 0
                    self._digest_cnonce = ""
                    return challenge
            except AppError as exc:
                last_detail = str(exc)
                continue

        raise AppError(
            kind="auth",
            message="cannot obtain digest challenge",
            status_code=last_status,
            detail=last_detail,
        )

    def _digest_authz(self, method: str, url: str) -> str:
        challenge = self._ensure_digest_challenge()
        self._digest_nc += 1
        if not self._digest_cnonce:
            import os

            self._digest_cnonce = os.urandom(8).hex()

        return build_digest_authorization(
            method=method,
            url=url,
            username=self.username,
            password=self.password,
            challenge=challenge,
            nc=self._digest_nc,
            cnonce=self._digest_cnonce,
        )

    def _auth_headers(self, method: str, url: str) -> dict[str, str]:
        scheme = self.auth_scheme
        if scheme == "none":
            return {}

        if scheme == "basic":
            token = base64.b64encode(f"{self.username}:{self.password}".encode("utf-8")).decode("ascii")
            return {"Authorization": f"Basic {token}"}

        if scheme == "digest":
            return {"Authorization": self._digest_authz(method, url)}

        raise AppError(kind="param", message="invalid auth_scheme", detail=scheme)

    def _maybe_refresh_digest(self, response: HttpResponse) -> bool:
        www = response.header_all("WWW-Authenticate")
        header = _pick_digest_header(www)
        if not header or "digest" not in header.lower():
            return False

        try:
            challenge = parse_www_authenticate_digest(header)
        except Exception:
            return False

        self._digest_challenge = challenge
        self._digest_nc = 0
        self._digest_cnonce = ""
        return True

    def _request_with_auth(self, url: str) -> HttpResponse:
        scheme = self.auth_scheme
        auth_headers = self._auth_headers("GET", url) if scheme != "none" else {}
        headers = self._merge_headers(url, auth_headers)

        response = self._request_raw(url, headers=headers, read_body=True)

        if scheme == "digest" and response.status == 401:
            if self._maybe_refresh_digest(response):
                auth_headers = self._auth_headers("GET", url)
                headers = self._merge_headers(url, auth_headers)
                response = self._request_raw(url, headers=headers, read_body=True)

        if response.status == 200 and scheme != "none" and looks_like_auth_error_body(response.body):
            raise AppError(
                kind="auth",
                message="authentication failed",
                status_code=200,
                detail=tail_text(response.body),
            )

        return response

    def request_tail(self, tail: str) -> HttpResponse:
        url = self._make_url(tail)
        return self._request_with_auth(url)

    def get_abs(self, path: str) -> HttpResponse:
        url = self._make_abs_url(path)
        return self._request_with_auth(url)

    def read_param_text(self, keys: str | Iterable[str]) -> str:
        if isinstance(keys, str):
            key_list = [keys]
        else:
            key_list = [str(x).strip() for x in keys if str(x).strip()]

        if not key_list:
            raise AppError(kind="param", message="empty readparam keys")

        query = "&".join([f"{quote(k, safe='')}=0" for k in key_list])
        tail = f"ReadParam?action=readparam&{query}"
        response = self.request_tail(tail)

        if response.status == 200:
            return response.body or ""

        if response.status in (401, 403):
            raise AppError(
                kind="auth",
                message="authentication failed",
                status_code=response.status,
                detail=tail_text(response.body),
            )

        if response.status == 404:
            raise AppError(
                kind="http",
                message="not found",
                status_code=response.status,
                detail=tail_text(response.body),
            )

        raise AppError(
            kind="http",
            message="read_param failed",
            status_code=response.status,
            detail=tail_text(response.body),
        )

    def read_param_value(self, key: str) -> str:
        text = self.read_param_text(key)
        return parse_kv_lines(text).get(key, "")

    def read_param_values(self, keys: Iterable[str]) -> dict[str, str]:
        text = self.read_param_text(list(keys))
        kv = parse_kv_lines(text)
        out: dict[str, str] = {}
        for key in keys:
            out[str(key)] = kv.get(str(key), "")
        return out

    def write_param_raw(self, kv: dict[str, str]) -> HttpResponse:
        if not kv:
            raise AppError(kind="param", message="empty write params")

        parts = []
        for key, value in kv.items():
            parts.append(f"{quote(str(key), safe='')}={quote(str(value), safe='')}")
        tail = "WriteParam?action=writeparam&" + "&".join(parts)
        response = self.request_tail(tail)

        if response.status == 200 and self.auth_scheme != "none" and looks_like_auth_error_body(response.body):
            raise AppError(
                kind="auth",
                message="authentication failed",
                status_code=200,
                detail=tail_text(response.body),
            )
        return response

    def write_param(self, key: str, value: str) -> str:
        response = self.write_param_raw({key: value})
        body = (response.body or "").strip()

        if response.status == 200:
            if body and not body.lower().startswith("ok"):
                raise AppError(kind="http", message="write_param rejected", detail=tail_text(body))
            return body

        if response.status in (401, 403):
            raise AppError(
                kind="auth",
                message="authentication failed",
                status_code=response.status,
                detail=tail_text(body),
            )

        raise AppError(
            kind="http",
            message="write_param failed",
            status_code=response.status,
            detail=tail_text(body),
        )