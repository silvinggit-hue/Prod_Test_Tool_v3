from __future__ import annotations

from infra.network.digest_auth import (
    DigestChallenge,
    build_digest_authorization,
    parse_www_authenticate_digest,
)


def test_parse_www_authenticate_digest() -> None:
    header = (
        'Digest realm="IP Camera", nonce="abc123", qop="auth", '
        'opaque="xyz", algorithm=MD5'
    )

    parsed = parse_www_authenticate_digest(header)

    assert parsed.realm == "IP Camera"
    assert parsed.nonce == "abc123"
    assert parsed.qop == "auth"
    assert parsed.opaque == "xyz"
    assert parsed.algorithm == "MD5"


def test_build_digest_authorization_contains_required_fields() -> None:
    challenge = DigestChallenge(
        realm="IP Camera",
        nonce="abc123",
        qop="auth",
        opaque="xyz",
        algorithm="MD5",
    )

    authz = build_digest_authorization(
        method="GET",
        url="https://192.168.10.100:443/httpapi/ReadParam?action=readparam&SYS_VERSION=0",
        username="admin",
        password="123",
        challenge=challenge,
        nc=1,
        cnonce="deadbeef",
    )

    assert authz.startswith("Digest ")
    assert 'username="admin"' in authz
    assert 'realm="IP Camera"' in authz
    assert 'nonce="abc123"' in authz
    assert 'opaque="xyz"' in authz
    assert "qop=auth" in authz
    assert "nc=00000001" in authz
    assert 'cnonce="deadbeef"' in authz