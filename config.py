"""Application configuration from environment variables."""

import os


class Config:
    """Flask configuration with env var overrides."""

    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

    # Upload and payload limits
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_UPLOAD_SIZE', 10 * 1024 * 1024))

    # Preview and processing
    PREVIEW_ROW_LIMIT = int(os.environ.get('PREVIEW_ROW_LIMIT', 25))
    API_FETCH_TIMEOUT = int(os.environ.get('API_FETCH_TIMEOUT', 30))
    API_FETCH_MAX_RESPONSE = int(os.environ.get('API_FETCH_MAX_RESPONSE', 10 * 1024 * 1024))
    FLATTEN_MAX_DEPTH = int(os.environ.get('FLATTEN_MAX_DEPTH', 10))

    # Rate limiting (Flask-Limiter reads RATELIMIT_* keys automatically)
    RATELIMIT_STORAGE_URI = 'memory://'
    RATELIMIT_DEFAULT = os.environ.get('RATE_LIMIT_DEFAULT', '120/minute')
    RATE_LIMIT_PROCESS = os.environ.get('RATE_LIMIT_PROCESS', '30/minute')
    RATE_LIMIT_EXPORT = os.environ.get('RATE_LIMIT_EXPORT', '60/minute')

    # Application metadata
    APP_VERSION = '1.1.0'

    # Debug mode
    DEBUG = os.environ.get('FLASK_DEBUG', '0').lower() in ('1', 'true', 'yes')
