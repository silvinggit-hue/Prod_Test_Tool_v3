from __future__ import annotations

from urllib.parse import urljoin

from domain.errors.app_error import AppError
from domain.models.phase1 import ProbeResult
from infra.network.http_client import http_get, looks_like_auth_error_body, tail_text


def _normalize_root(root: str) -> str:
    value = (root or "").strip()
    if not value:
        return "/httpapi/"
    if not value.startswith("/"):
        value = "/" + value
    if not value.endswith("/"):
        value += "/"
    return value


def _unique_keep_order(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        if not item:
            continue
        if item not in out:
            out.append(item)
    return out


def build_base_candidates(ip: str, port: int) -> list[str]:
    try:
        p = int(port or 0)
    except Exception:
        p = 0

    if p <= 0:
        ports = [443, 80]
        # TODO: 운영망에서 필요하면 8443 후보를 옵션으로 확장
    else:
        ports = [p]
        if 443 not in ports:
            ports.append(443)
        if 80 not in ports:
            ports.append(80)

    out: list[str] = []
    for pp in ports:
        if pp in (443, 8443):
            out.append(f"https://{ip}:{pp}")
            out.append(f"http://{ip}:{pp}")
        else:
            out.append(f"http://{ip}:{pp}")
            out.append(f"https://{ip}:{pp}")

    return _unique_keep_order(out)


def build_root_candidates(preferred_root: str | None = None) -> list[str]:
    return _unique_keep_order(
        [
            _normalize_root(preferred_root or ""),
            "/httpapi/",
            "/httpapx/",
        ]
    )


def _contains_digest(www: list[str]) -> bool:
    return any(h and "digest" in h.lower() for h in (www or []))


def _contains_basic(www: list[str]) -> bool:
    return any(h and "basic" in h.lower() for h in (www or []))


def _guess_auth_from_home(*, base_url: str, timeout_sec: float, verify_tls: bool) -> str:
    try:
        resp = http_get(
            url=base_url.rstrip("/") + "/",
            headers={"User-Agent": "Prod_Test_Tool_v3/probe-home"},
            timeout_sec=timeout_sec,
            verify_tls=verify_tls,
            read_body=True,
            allow_redirects=False,
        )
    except AppError:
        return "digest"

    www = resp.header_all("WWW-Authenticate")
    if _contains_digest(www):
        return "digest"
    if _contains_basic(www):
        return "basic"
    if resp.status == 200 and not looks_like_auth_error_body(resp.body):
        return "none"
    return "digest"


def _looks_like_public_key_response(body: str | None) -> bool:
    text = (body or "").strip()
    if "SYS_PUBLIC_KEY=" not in text and "BEGIN PUBLIC KEY" not in text:
        return False
    return len(text) >= 64


def _flavor_from_root(root_path: str) -> str:
    root = _normalize_root(root_path)
    if root == "/httpapx/":
        return "tta"
    return "legacy"


def probe_camera(
    *,
    ip: str,
    port: int,
    timeout_sec: float,
    verify_tls: bool,
) -> ProbeResult:
    last_err: AppError | None = None

    for base_url in build_base_candidates(ip, port):
        for root_path in build_root_candidates(None):
            sys_pub_url = urljoin(
                base_url.rstrip("/") + "/",
                root_path.lstrip("/") + "ReadParam?action=readparam&SYS_PUBLIC_KEY=0",
            )

            try:
                sec3_resp = http_get(
                    url=sys_pub_url,
                    headers={"User-Agent": "Prod_Test_Tool_v3/probe-sec3"},
                    timeout_sec=timeout_sec,
                    verify_tls=verify_tls,
                    read_body=True,
                    allow_redirects=False,
                )
                if sec3_resp.status == 200 and _looks_like_public_key_response(sec3_resp.body):
                    return ProbeResult(
                        base_url=base_url,
                        root_path=_normalize_root(root_path),
                        auth_scheme="digest",
                        flavor="security3",
                    )
            except AppError as exc:
                last_err = exc

            test_url = urljoin(
                base_url.rstrip("/") + "/",
                root_path.lstrip("/") + "ReadParam?action=readparam&ETC_MIN_PASSWORD_LEN=0",
            )

            try:
                resp = http_get(
                    url=test_url,
                    headers={"User-Agent": "Prod_Test_Tool_v3/probe"},
                    timeout_sec=timeout_sec,
                    verify_tls=verify_tls,
                    read_body=True,
                    allow_redirects=False,
                )
            except AppError as exc:
                last_err = exc
                continue

            www = resp.header_all("WWW-Authenticate")
            if resp.status in (401, 403):
                if _contains_digest(www):
                    auth = "digest"
                elif _contains_basic(www):
                    auth = "basic"
                else:
                    auth = _guess_auth_from_home(
                        base_url=base_url,
                        timeout_sec=timeout_sec,
                        verify_tls=verify_tls,
                    )

                return ProbeResult(
                    base_url=base_url,
                    root_path=_normalize_root(root_path),
                    auth_scheme=auth,
                    flavor=_flavor_from_root(root_path),
                )

            if resp.status == 404:
                continue

            if resp.status == 200:
                if looks_like_auth_error_body(resp.body):
                    auth = _guess_auth_from_home(
                        base_url=base_url,
                        timeout_sec=timeout_sec,
                        verify_tls=verify_tls,
                    )
                else:
                    auth = "none"

                return ProbeResult(
                    base_url=base_url,
                    root_path=_normalize_root(root_path),
                    auth_scheme=auth,
                    flavor=_flavor_from_root(root_path),
                )

            last_err = AppError(
                kind="probe",
                message="unexpected probe response",
                status_code=resp.status,
                detail=tail_text(resp.body),
            )

    raise last_err or AppError(
        kind="probe",
        message="probe failed",
        detail=f"no candidate base/root worked for {ip}",
    )