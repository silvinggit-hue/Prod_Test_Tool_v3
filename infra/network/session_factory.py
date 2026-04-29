from __future__ import annotations

import ssl
import warnings

import requests
from requests.adapters import HTTPAdapter
from urllib3.exceptions import InsecureRequestWarning


class LegacyTlsAdapter(HTTPAdapter):
    def __init__(self, verify_tls: bool) -> None:
        self._verify_tls = bool(verify_tls)
        super().__init__()

    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        ctx = ssl.create_default_context()

        if not self._verify_tls:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

        try:
            ctx.set_ciphers("DEFAULT@SECLEVEL=1")
        except Exception:
            pass

        if hasattr(ssl, "OP_LEGACY_SERVER_CONNECT"):
            try:
                ctx.options |= ssl.OP_LEGACY_SERVER_CONNECT
            except Exception:
                pass

        pool_kwargs["ssl_context"] = ctx
        return super().init_poolmanager(connections, maxsize, block=block, **pool_kwargs)

    def proxy_manager_for(self, *args, **kwargs):
        if "ssl_context" not in kwargs:
            ctx = ssl.create_default_context()
            if not self._verify_tls:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            try:
                ctx.set_ciphers("DEFAULT@SECLEVEL=1")
            except Exception:
                pass
            kwargs["ssl_context"] = ctx
        return super().proxy_manager_for(*args, **kwargs)


def create_session(*, verify_tls: bool) -> requests.Session:
    session = requests.Session()
    session.verify = bool(verify_tls)

    adapter = LegacyTlsAdapter(verify_tls=verify_tls)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    if not verify_tls:
        warnings.simplefilter("ignore", InsecureRequestWarning)
        try:
            requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
        except Exception:
            pass

    return session