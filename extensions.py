"""Flask extensions (initialized without app, bound later via init_app)."""

from flask import request
from flask_limiter import Limiter
from flask_wtf.csrf import CSRFProtect


def client_ip_key():
    """
    Rate-limit bucket key: the client's IP.

    Deliberately reads request.remote_addr rather than the X-Forwarded-For
    header. remote_addr is only rewritten from that header when ProxyFix is
    installed, which create_app does exclusively under TRUST_PROXY=1 (F12/D3).
    Reading the raw header here would let any client forge its own bucket.
    """
    return request.remote_addr or 'unknown'


csrf = CSRFProtect()
limiter = Limiter(key_func=client_ip_key)
