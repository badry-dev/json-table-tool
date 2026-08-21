"""Application configuration from environment variables."""

import os

# Publicly known, and therefore only ever acceptable outside production.
DEV_SECRET_KEY = 'dev-secret-key-change-in-production'


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

    # Rate limiting (Flask-Limiter reads RATELIMIT_* keys automatically)
    RATELIMIT_STORAGE_URI = 'memory://'
    RATELIMIT_DEFAULT = os.environ.get('RATE_LIMIT_DEFAULT', '120/minute')
    RATE_LIMIT_PROCESS = os.environ.get('RATE_LIMIT_PROCESS', '30/minute')
    RATE_LIMIT_EXPORT = os.environ.get('RATE_LIMIT_EXPORT', '60/minute')

    # Application metadata
    APP_VERSION = '1.1.0'

    # Debug mode
    DEBUG = os.environ.get('FLASK_DEBUG', '0').lower() in ('1', 'true', 'yes')
