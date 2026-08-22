"""Application configuration from environment variables."""

import os

# Publicly known, and therefore only ever acceptable outside production.
DEV_SECRET_KEY = 'dev-secret-key-change-in-production'

# See MAX_EXPORT_CELLS below and docs/export-budget-v1.2.md for how this number
# was measured.
DEFAULT_MAX_EXPORT_CELLS = 250_000


def is_production():
    """
    True when this process is running as a production deployment.

    `APP_ENV=production` is the single canonical signal, checked through this one
    helper by the SECRET_KEY fail-fast (F7), the Secure cookie flag (F16) and the
    rate-limit topology guard (2.10).

    Two things it deliberately is not:

    - It is never inferred from `not DEBUG`. The documented local run
      `python app.py` has DEBUG False by default, so that would block ordinary
      development startup.
    - No second spelling (`PRODUCTION=true`, `ENV=prod`, ...) is accepted. Two
      accepted names let a deployment satisfy one gate and silently miss another
      -- e.g. passing the SECRET_KEY check while SESSION_COOKIE_SECURE stays off.
    """
    return os.environ.get('APP_ENV', '').strip().lower() == 'production'


def env_int(name, default):
    """
    Read an integer setting, failing with a message that names the variable.

    Plain int(os.environ.get(...)) raises a bare ValueError from deep inside the
    import, which tells an operator nothing about which variable they mistyped
    (F7).
    """
    raw = os.environ.get(name)
    if raw is None or raw.strip() == '':
        return default
    try:
        return int(raw.strip())
    except ValueError:
        raise RuntimeError(f'Environment variable {name} must be an integer, got {raw!r}') from None


def env_int_set(name, default):
    """
    Read a comma-separated integer list (e.g. an allowlist of ports).

    Only an UNSET variable selects the default. An explicitly empty value yields
    an empty set, which is how an operator disables a list-based check -- folding
    the two together silently restored the default and made the documented
    escape hatch a no-op.
    """
    raw = os.environ.get(name)
    if raw is None:
        raw = default
    try:
        return frozenset(int(part.strip()) for part in raw.split(',') if part.strip())
    except ValueError:
        raise RuntimeError(
            f'Environment variable {name} must be a comma-separated list of integers, got {raw!r}'
        ) from None


def env_positive_int(name, default):
    """
    Read an integer setting that must be >= 1.

    ThreadPoolExecutor rejects max_workers <= 0, so without this an
    API_DNS_MAX_WORKERS of 0 sailed through import and blew up as a 500 inside
    the first API fetch instead of failing fast like every other misconfiguration.
    """
    value = env_int(name, default)
    if value < 1:
        raise RuntimeError(f'Environment variable {name} must be >= 1, got {value}')
    return value


class Config:
    """Flask configuration with env var overrides."""

    SECRET_KEY = os.environ.get('SECRET_KEY', DEV_SECRET_KEY)

    # Upload and payload limits
    MAX_CONTENT_LENGTH = env_int('MAX_UPLOAD_SIZE', 10 * 1024 * 1024)

    # Preview and processing
    PREVIEW_ROW_LIMIT = env_int('PREVIEW_ROW_LIMIT', 25)
    API_FETCH_TIMEOUT = env_int('API_FETCH_TIMEOUT', 30)
    API_FETCH_MAX_RESPONSE = env_int('API_FETCH_MAX_RESPONSE', 10 * 1024 * 1024)
    FLATTEN_MAX_DEPTH = env_int('FLATTEN_MAX_DEPTH', 10)

    # DNS admission control for API fetch (F6.1/P7). API_DNS_TIMEOUT bounds how
    # long a REQUEST waits, not how long the lookup runs -- getaddrinfo exposes no
    # timeout and cannot be cancelled. API_DNS_MAX_WORKERS bounds concurrency,
    # which is the actual worker-starvation fix.
    API_DNS_TIMEOUT = env_int('API_DNS_TIMEOUT', 3)
    API_DNS_MAX_WORKERS = env_positive_int('API_DNS_MAX_WORKERS', 4)
    API_DNS_ADMISSION_TIMEOUT = env_int('API_DNS_ADMISSION_TIMEOUT', 1)

    # Ports the API-fetch feature may connect to (F6.2/D5). Only the IP was
    # checked before, so http://public.example.com:22 or :6379 passed. An empty
    # value disables the check.
    API_ALLOWED_PORTS = env_int_set('API_ALLOWED_PORTS', '80,443,8443')

    # Trust X-Forwarded-* from exactly one proxy hop (F12/D3). Off by default:
    # with it unset, behavior is identical to v1.1 and forged headers are ignored.
    TRUST_PROXY = os.environ.get('TRUST_PROXY', '0').strip().lower() in ('1', 'true', 'yes')

    # Rate limiting (Flask-Limiter reads RATELIMIT_* keys automatically).
    #
    # memory:// counters are PROCESS-LOCAL, so the effective limit is multiplied
    # by workers x replicas -- not by workers alone. This was hardcoded before
    # v1.2, so no deployment could configure shared storage at all (2.10a/F12).
    RATELIMIT_STORAGE_URI = os.environ.get('RATELIMIT_STORAGE_URI', 'memory://')

    # WEB_CONCURRENCY is the SINGLE source of truth for the worker count: gunicorn
    # reads it natively and every documented start command passes
    # --workers "$WEB_CONCURRENCY", so the number this process validates cannot
    # drift from the number gunicorn actually runs. Replica count is invisible from
    # inside the process, so APP_REPLICAS is a deployment-layer declaration that
    # must mirror render.yaml's numInstances.
    #
    # Defaults of 1 fail OPEN -- an undeclared 4-worker deployment reads as
    # single-worker -- so under APP_ENV=production both must be declared
    # explicitly; see check_rate_limit_topology in app.py.
    WEB_CONCURRENCY = env_int('WEB_CONCURRENCY', 1)
    APP_REPLICAS = env_int('APP_REPLICAS', 1)
    WEB_CONCURRENCY_DECLARED = (os.environ.get('WEB_CONCURRENCY') or '').strip() != ''
    APP_REPLICAS_DECLARED = (os.environ.get('APP_REPLICAS') or '').strip() != ''
    RATELIMIT_DEFAULT = os.environ.get('RATE_LIMIT_DEFAULT', '120/minute')
    RATE_LIMIT_PROCESS = os.environ.get('RATE_LIMIT_PROCESS', '30/minute')
    RATE_LIMIT_EXPORT = os.environ.get('RATE_LIMIT_EXPORT', '60/minute')

    # Cookie hardening (F16). Flask's defaults are HttpOnly=True but emit no
    # SameSite attribute and never set Secure. Secure is tied to the explicit
    # production signal: a plain local run has DEBUG False, so gating on
    # `not DEBUG` would send Secure cookies over http and break CSRF-protected
    # POSTs during development.
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = is_production()

    # XLSX-only export budget (P3/D6), in CELLS (rows x columns) because that is
    # what drives openpyxl's memory -- a 10 MiB body with 3 columns and one with
    # 500 columns have wildly different footprints at the same row count.
    #
    # Enabled by default: an unlimited default would leave P3 (High) unmitigated.
    # The value is derived from the Performance Review section 4 measurement (see
    # docs/export-budget-v1.2.md), not chosen by feel -- re-derive it whenever that
    # measurement is re-run. 0 disables the guard for operators who knowingly opt
    # out. CSV/TSV stay uncapped and streamed, so every dataset /process accepts
    # remains exportable by some route.
    MAX_EXPORT_CELLS = env_int('MAX_EXPORT_CELLS', DEFAULT_MAX_EXPORT_CELLS)

    # Static assets are revalidated on every navigation without this, costing a
    # round trip per page load -- worst on a Render free-tier cold start (P6).
    # Safe to cache for a day because the asset URLs carry ?v=APP_VERSION.
    SEND_FILE_MAX_AGE_DEFAULT = env_int('STATIC_MAX_AGE', 86400)

    # Responses smaller than this are not worth a gzip round trip (P1).
    GZIP_MIN_SIZE = env_int('GZIP_MIN_SIZE', 1024)

    # Application metadata
    APP_VERSION = '1.2.0'

    # F15: /health returns `version` by default (the existing contract). Operators
    # who would rather not advertise it can set HEALTH_REVEAL_VERSION=0.
    HEALTH_REVEAL_VERSION = os.environ.get('HEALTH_REVEAL_VERSION', '1').strip().lower() not in (
        '0',
        'false',
        'no',
    )

    # Debug mode
    DEBUG = os.environ.get('FLASK_DEBUG', '0').lower() in ('1', 'true', 'yes')
