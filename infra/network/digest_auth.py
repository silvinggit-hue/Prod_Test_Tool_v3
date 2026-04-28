from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from urllib.parse import urlsplit


_DIGEST_ITEM_RE = re.compile(r'(\w+)\s*=\s*("(?:[^"\\]|\\.)*"|[^,]+)')


@dataclass(frozen=True)
class DigestChallenge:
    realm: str
    nonce: str
    qop: str = ""
    opaque: str | None = None
    algorithm: str = "MD5"


def _strip_quotes(value: str) -> str:
    s = (value or "").strip()
    if len(s) >= 2 and s[0] == s[-1] == '"':
        return s[1:-1]
    return s


def parse_www_authenticate_digest(header_value: str) -> DigestChallenge:
    raw = (header_value or "").strip()
    if not raw:
        raise ValueError("empty WWW-Authenticate header")

    if raw.lower().startswith("digest "):
        raw = raw[7:].strip()

    items: dict[str, str] = {}
    for key, value in _DIGEST_ITEM_RE.findall(raw):
        items[key.lower()] = _strip_quotes(value)

    realm = items.get("realm", "")
    nonce = items.get("nonce", "")
    if not realm or not nonce:
        raise ValueError("invalid digest challenge")

    return DigestChallenge(
        realm=realm,
        nonce=nonce,
        qop=items.get("qop", ""),
        opaque=items.get("opaque"),
        algorithm=items.get("algorithm", "MD5"),
    )


def _pick_qop(qop_raw: str) -> str:
    if not qop_raw:
        return "auth"
    items = [x.strip().lower() for x in qop_raw.split(",") if x.strip()]
    return "auth" if "auth" in items else (items[0] if items else "auth")


def _uri_from_full_url(url: str) -> str:
    sp = urlsplit(url)
    path = sp.path or "/"
    if not path.startswith("/"):
        path = "/" + path
    if sp.query:
        return path + "?" + sp.query
    return path


def build_digest_authorization(
    *,
    method: str,
    url: str,
    username: str,
    password: str,
    challenge: DigestChallenge,
    nc: int,
    cnonce: str | None = None,
) -> str:
    algo = (challenge.algorithm or "MD5").upper()
    qop = _pick_qop(challenge.qop)
    nonce_count = f"{int(nc):08x}"
    client_nonce = cnonce or os.urandom(8).hex()

    hfunc = hashlib.sha256 if "SHA-256" in algo else hashlib.md5

    def hhex(value: str) -> str:
        return hfunc(value.encode("utf-8")).hexdigest()

    uri = _uri_from_full_url(url)
    ha1 = hhex(f"{username}:{challenge.realm}:{password}")
    ha2 = hhex(f"{method}:{uri}")
    response = hhex(
        f"{ha1}:{challenge.nonce}:{nonce_count}:{client_nonce}:{qop}:{ha2}"
    )

    parts = [
        'Digest username="%s"' % username,
        'realm="%s"' % challenge.realm,
        'nonce="%s"' % challenge.nonce,
        'uri="%s"' % uri,
        "algorithm=%s" % algo,
        'response="%s"' % response,
        "qop=%s" % qop,
        "nc=%s" % nonce_count,
        'cnonce="%s"' % client_nonce,
    ]
    if challenge.opaque is not None:
        parts.append('opaque="%s"' % challenge.opaque)
    return ", ".join(parts)