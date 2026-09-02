"""Security utilities: SSRF protection and response headers."""

import concurrent.futures
import ipaddress
import os
import socket
import threading
from typing import Any
from urllib.parse import urlparse

from flask import current_app, has_app_context, request

# Built as a list of directives so appending can never fuse two tokens into one
# malformed directive (F5). Google Fonts is the only third-party origin the page
# uses; scripts stay self-only, so no inline JS is possible anywhere.
CSP_DIRECTIVES = (
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data:",
    "connect-src 'self'",
    # Shrink the XSS blast radius: no plugins, no <base> hijacking, no framing,
    # no cross-origin form exfiltration.
    "object-src 'none'",
    "base-uri 'self'",
    "frame-ancestors 'none'",
    "form-action 'self'",
    # Inert on a plain-http deployment, mandatory on an https one (F5/F14).
    'upgrade-insecure-requests',
)

CONTENT_SECURITY_POLICY = '; '.join(CSP_DIRECTIVES)

# Responses that carry payload data (or ops state) must not be retained by a
# shared cache, a proxy or the browser's bfcache (F11). The index page and the
# static assets are deliberately absent -- they are cacheable (P6).
NO_STORE_ENDPOINTS = frozenset(
    {
        'main.process_json',
        'main.export_csv',
        'main.export_xlsx',
        'main.health',
        'main.health_live',
        'main.health_ready',
    }
)


# --- Bounded DNS admission (F6.1 / P7) --------------------------------------
#
# socket.getaddrinfo takes no timeout and cannot be cancelled, so a hostname
# served by a slow or unresponsive nameserver pins the gunicorn worker that
# called it for as long as the platform resolver takes. The lookup therefore runs
# on a shared, fixed-size pool and the caller waits with a timeout.
#
# What this bounds and what it does not:
#
#   * Bounded: how long a REQUEST waits (Future.result timeout), and how many
#     lookups may be in flight at once (the admission permits). Concurrency is
#     the actual worker-starvation fix.
#   * NOT bounded: the lookup itself, and therefore worker teardown. cancel_futures
#     only drops queued work, a running getaddrinfo cannot be cancelled, and
#     concurrent.futures joins its non-daemon threads at interpreter exit whatever
#     `wait` says. The wait is whatever the platform resolver takes -- glibc
#     defaults to ~5s per nameserver x 2 attempts x every nameserver in
#     resolv.conf, so tens of seconds is the realistic worst case, and it is
#     bounded at all only where `options timeout:N attempts:M` is configured.
#     Pinning `options timeout:2 attempts:1` in the container's resolv.conf is a
#     best-effort narrowing, not a guarantee. A killable subprocess resolver is
#     the only real bound and is deliberately out of v1.2 scope.
#
# Do not describe teardown as bounded anywhere.

DEFAULT_ALLOWED_PORTS = frozenset({80, 443, 8443})
DEFAULT_SCHEME_PORTS = {'http': 80, 'https': 443}

DEFAULT_DNS_TIMEOUT = 3
DEFAULT_DNS_MAX_WORKERS = 4
DEFAULT_DNS_ADMISSION_TIMEOUT = 1


class ResolverBusyError(Exception):
    """No admission permit was free within the admission wait."""


class _ResolverPool:
    """A fixed-size resolver pool with an admission permit per in-flight lookup."""

    def __init__(self, max_workers: int) -> None:
        self.pid = os.getpid()
        self.max_workers = max_workers
        # Pool size plus an equal backlog: a bounded submission queue. Beyond this
        # callers are rejected rather than queued without limit.
        self.capacity = max_workers * 2
        self.executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix='dns-resolver'
        )
        self._permits = threading.Semaphore(self.capacity)
        self._counter_lock = threading.Lock()
        self.in_flight = 0

    def submit(self, hostname: str, admission_timeout: float) -> concurrent.futures.Future:
        """
        Admit and start one lookup, or raise ResolverBusyError.

        The permit is taken BEFORE submit and released from the future's
        done-callback -- never from the caller's finally. Releasing on caller
        timeout would re-admit work while the blocked getaddrinfo thread still
        occupies the pool, which is precisely how the pool saturates under
        repeated slow-DNS requests.
        """
        if not self._permits.acquire(timeout=admission_timeout):
            raise ResolverBusyError
        with self._counter_lock:
            self.in_flight += 1
        try:
            future = self.executor.submit(socket.getaddrinfo, hostname, None)
        except BaseException:
            self._release()
            raise
        future.add_done_callback(self._on_done)
        return future

    def _on_done(self, _future: concurrent.futures.Future) -> None:
        self._release()

    def _release(self) -> None:
        with self._counter_lock:
            self.in_flight -= 1
        self._permits.release()


_pool_lock = threading.Lock()
_pool = None


def get_resolver_pool(max_workers: int | None = None) -> '_ResolverPool':
    """
    Return this process's resolver pool, creating it on first use.

    Creation is lazy so the pool belongs to the gunicorn WORKER, not the master:
    an executor built at import time in the master leaves its threads behind in
    the parent and is not usefully inherited. The recorded pid also makes a pool
    inherited across a fork be replaced rather than reused.
    """
    global _pool
    if max_workers is None:
        max_workers = _setting('API_DNS_MAX_WORKERS', DEFAULT_DNS_MAX_WORKERS)
    pool = _pool
    if pool is not None and pool.pid == os.getpid():
        return pool
    with _pool_lock:
        if _pool is None or _pool.pid != os.getpid():
            _pool = _ResolverPool(max_workers)
        return _pool


def reset_resolver_pool() -> '_ResolverPool | None':
    """
    Drop the current pool so the next lookup builds a fresh one.

    shutdown(wait=False, cancel_futures=True) returns immediately but does NOT
    make teardown bounded: it can only drop queued work, and any thread already
    inside getaddrinfo keeps running until the platform resolver returns.
    """
    global _pool
    with _pool_lock:
        pool = _pool
        _pool = None
    if pool is not None:
        pool.executor.shutdown(wait=False, cancel_futures=True)
    return pool


def _setting(name: str, default: Any) -> Any:
    """Read a config value, falling back to the module default outside a request."""
    if has_app_context():
        return current_app.config.get(name, default)
    return default


def resolve_hostname(hostname: str) -> list[Any]:
    """
    Resolve a hostname under admission control.

    Returns getaddrinfo's result, or raises ResolverBusyError (no permit),
    TimeoutError (the caller's wait elapsed; the lookup itself keeps running) or
    socket.gaierror.
    """
    pool = get_resolver_pool()
    admission_timeout = _setting('API_DNS_ADMISSION_TIMEOUT', DEFAULT_DNS_ADMISSION_TIMEOUT)
    timeout = _setting('API_DNS_TIMEOUT', DEFAULT_DNS_TIMEOUT)
    future = pool.submit(hostname, admission_timeout)
    return future.result(timeout=timeout)


def validate_url(url: str) -> tuple[bool, str | None]:
    """
    Validate a URL for SSRF protection.
    Resolves DNS and rejects non-global IPs.
    Returns (is_valid, error_message_or_none).
    """
    parsed = urlparse(url)

    if parsed.scheme not in ('http', 'https'):
        return False, 'Only HTTP and HTTPS URLs are allowed'

    hostname = parsed.hostname
    if not hostname:
        return False, 'Invalid URL: no hostname'

    # Port check first: it is free, and a rejected URL should not cost a lookup.
    try:
        port = parsed.port
    except ValueError:
        return False, 'Invalid URL: malformed port'
    if port is None:
        port = DEFAULT_SCHEME_PORTS[parsed.scheme]
    allowed_ports = _setting('API_ALLOWED_PORTS', DEFAULT_ALLOWED_PORTS)
    if allowed_ports and port not in allowed_ports:
        return False, (
            f'Port {port} is not allowed. Allowed ports: '
            + ', '.join(str(p) for p in sorted(allowed_ports))
        )

    try:
        addr_infos = resolve_hostname(hostname)
    except ResolverBusyError:
        return False, 'DNS resolver is busy; please retry'
    except socket.gaierror:
        return False, f'Could not resolve hostname: {hostname}'
    except TimeoutError:
        # The caller's wait elapsed. The lookup is still running on the pool and
        # still holds its permit until it finishes -- that is deliberate.
        return False, f'Could not resolve hostname: {hostname}'

    found_valid = False
    for addr_info in addr_infos:
        ip_str = addr_info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if not ip.is_global or ip.is_multicast:
            return False, 'URLs pointing to private or internal networks are not allowed'
        found_valid = True

    if not found_valid:
        return False, 'Could not resolve any valid IP addresses'

    return True, None


def apply_security_headers(response):
    """Add security headers to every response."""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    # Legacy fallback for browsers predating CSP frame-ancestors.
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    response.headers['Cross-Origin-Opener-Policy'] = 'same-origin'
    response.headers['Cross-Origin-Resource-Policy'] = 'same-origin'
    response.headers['Content-Security-Policy'] = CONTENT_SECURITY_POLICY

    if request.endpoint in NO_STORE_ENDPOINTS:
        response.headers['Cache-Control'] = 'no-store'

    # HSTS only makes sense once the connection is already TLS; sending it over
    # plain http would pin a local dev server to https. request.is_secure reads
    # X-Forwarded-Proto only when ProxyFix is enabled (TRUST_PROXY=1), which is
    # exactly the deployment where the proxy terminates TLS.
    if request.is_secure:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'

    return response
