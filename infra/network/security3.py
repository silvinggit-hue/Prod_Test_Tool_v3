from __future__ import annotations

import base64
import re
import socket
import time
from typing import Iterable
from urllib.parse import quote

from domain.errors.app_error import AppError
from infra.network.camera_http_client import CameraHttpClient

SEC3_PUBLIC_KEY = "SYS_PUBLIC_KEY"
ESSENTIAL_KEYS = ("SYS_VERSION", "SYS_MODELNAME", "SYS_BOARDID")

_PEM_RE = re.compile(
    r"-----BEGIN PUBLIC KEY-----\s*(.*?)\s*-----END PUBLIC KEY-----",
    re.DOTALL,
)


def detect_local_ip(target_host: str) -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect((target_host, 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except Exception:
        return "127.0.0.1"


def normalize_public_key_pem(readparam_text: str) -> str:
    if not readparam_text:
        return ""

    s = readparam_text.replace("\r", "").strip()
    if "SYS_PUBLIC_KEY=" in s:
        s = s.split("SYS_PUBLIC_KEY=", 1)[1].strip()

    m = _PEM_RE.search(s)
    if m:
        b64 = re.sub(r"\s+", "", m.group(1))
    else:
        b64 = re.sub(r"\s+", "", s)

    if not b64 or len(b64) < 80:
        return ""

    lines = [b64[i : i + 64] for i in range(0, len(b64), 64)]
    return "-----BEGIN PUBLIC KEY-----\n" + "\n".join(lines) + "\n-----END PUBLIC KEY-----\n"


def rsa_encrypt_with_pem(public_key_pem: str, msg: str) -> str:
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import padding
    except Exception as exc:
        raise AppError(
            kind="compat",
            message="cryptography package is required for security3 bootstrap",
            detail=str(exc),
        ) from exc

    try:
        key = serialization.load_pem_public_key(public_key_pem.encode())
        encrypted = key.encrypt(msg.encode(), padding.PKCS1v15())
        return base64.b64encode(encrypted).decode()
    except Exception as exc:
        raise AppError(
            kind="compat",
            message="rsa encrypt failed",
            detail=str(exc),
        ) from exc


def read_essentials_best_effort(
    client: CameraHttpClient,
    keys: Iterable[str] = ESSENTIAL_KEYS,
) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in keys:
        try:
            out[str(key)] = client.read_param_value(str(key))
        except Exception:
            out[str(key)] = ""
    return out


def sec3_usr_add_noauth(
    *,
    base_url: str,
    root_path: str,
    new_user: str,
    new_pass: str,
    verify_tls: bool,
    timeout_sec: float,
) -> CameraHttpClient:
    cli_none = CameraHttpClient(
        base_url=base_url,
        root_path=root_path,
        username="",
        password="",
        auth_scheme="none",
        timeout_sec=timeout_sec,
        verify_tls=verify_tls,
    )

    txt = cli_none.read_param_text(SEC3_PUBLIC_KEY)
    pem = normalize_public_key_pem(txt)

    if not pem:
        raise AppError(kind="compat", message="security3 public key missing/invalid")

    cipher_b64 = rsa_encrypt_with_pem(pem, new_pass)
    enc_cipher = quote(cipher_b64, safe="")

    tail = (
        "WriteParam?action=writeparam&USR_ADD="
        f"{quote(new_user, safe='')}:{enc_cipher}:0"
    )
    resp = cli_none.request_tail(tail)
    body = (resp.body or "").strip()

    if resp.status == 200 and body.lower().startswith("ok"):
        return cli_none

    raise AppError(
        kind="http",
        message="USR_ADD failed",
        status_code=resp.status,
        detail=body[:300],
    )


def sec3_write_remoteaccess_first(
    *,
    base_url: str,
    root_path: str,
    shared_session_client: CameraHttpClient,
    username: str,
    password: str,
    allowed_ip: str,
    verify_tls: bool,
    timeout_sec: float,
) -> CameraHttpClient:
    cli = CameraHttpClient(
        base_url=base_url,
        root_path=root_path,
        username=username,
        password=password,
        auth_scheme="digest",
        timeout_sec=timeout_sec,
        verify_tls=verify_tls,
    ).with_shared_session(shared_session_client.get_session())

    home_ok = False
    last_exc: Exception | None = None

    for _ in range(10):
        try:
            r_home = cli.get_abs("/")
            if r_home.status == 200:
                home_ok = True
                break
        except Exception as exc:
            last_exc = exc
        time.sleep(0.5)

    if not home_ok:
        raise AppError(
            kind="auth",
            message="digest home failed after security3 bootstrap",
            detail=str(last_exc) if last_exc else None,
        )

    ip0 = (allowed_ip or "").strip() or "192.168.10.2"
    kv: dict[str, str] = {}
    for i in range(20):
        kv[f"ETC_REMOTEACCESS_IP{i:02d}"] = ip0 if i == 0 else "0.0.0.0"
        kv[f"ETC_REMOTEACCESS_USE{i:02d}"] = "1" if i == 0 else "0"

    resp = cli.write_param_raw(kv)
    body = (resp.body or "").strip()

    if resp.status != 200 or (body and not body.lower().startswith("ok")):
        raise AppError(
            kind="http",
            message="remoteaccess write failed",
            status_code=resp.status,
            detail=body[:300],
        )

    return cli


def security3_bootstrap(
    *,
    target_ip: str,
    base_url: str,
    root_path: str,
    sec3_username: str,
    sec3_password: str,
    allowed_ip: str | None,
    verify_tls: bool,
    timeout_sec: float,
) -> tuple[CameraHttpClient, dict[str, str]]:
    cli_none = sec3_usr_add_noauth(
        base_url=base_url,
        root_path=root_path,
        new_user=sec3_username,
        new_pass=sec3_password,
        verify_tls=verify_tls,
        timeout_sec=timeout_sec,
    )

    local_ip = (allowed_ip or "").strip() or detect_local_ip(target_ip)

    cli_digest = sec3_write_remoteaccess_first(
        base_url=base_url,
        root_path=root_path,
        shared_session_client=cli_none,
        username=sec3_username,
        password=sec3_password,
        allowed_ip=local_ip,
        verify_tls=verify_tls,
        timeout_sec=timeout_sec,
    )

    essentials: dict[str, str] = {}
    last_exc: Exception | None = None

    for _ in range(3):
        try:
            essentials = read_essentials_best_effort(cli_digest, ESSENTIAL_KEYS)
            if any((essentials.get(k) or "").strip() for k in ESSENTIAL_KEYS):
                break
        except Exception as exc:
            last_exc = exc
        time.sleep(0.3)

    if not (essentials.get("SYS_VERSION") or "").strip():
        raise AppError(
            kind="auth",
            message="security3 bootstrap completed but SYS_VERSION is still unavailable",
            detail=str(last_exc) if last_exc else None,
        )

    return cli_digest, essentials