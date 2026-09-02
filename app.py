"""JSON Table Converter - Flask application factory."""

import gzip
import logging
import os
import sys

from flask import Flask, current_app, jsonify, request
from flask_wtf.csrf import CSRFError
from werkzeug.middleware.proxy_fix import ProxyFix

from config import DEV_SECRET_KEY, Config, is_production
from extensions import csrf, limiter
from helpers import format_size
from security import apply_security_headers

logger = logging.getLogger(__name__)


def _assert_production_secret_key(app):
    """
    Refuse to start a production deployment on the publicly known dev key (F7).

    Without this the app runs happily with a key anyone can read out of the
    repository, which makes CSRF tokens forgeable and the session cookie
    signable. render.yaml generates a key, but the Docker and self-hosted paths
    in the README leave it to the operator.
    """
    if not is_production():
        return
    secret = app.config.get('SECRET_KEY')
    if not secret or secret == DEV_SECRET_KEY:
        raise RuntimeError(
            'SECRET_KEY must be set to a random value when APP_ENV=production; '
            'the built-in development key is public.'
        )


# --- gzip (P1/D1) -----------------------------------------------------------
#
# /process returns the full flattened dataset, so a 10 MB input commonly means a
# 5-20 MB response body. Repetitive JSON compresses 5-10x, which is the single
# largest transfer win available. Implemented in-repo rather than via
# Flask-Compress: ~40 lines against a new pinned dependency (D1).
#
# It does NOT reduce peak server memory or the client's parse cost -- the browser
# still receives, decompresses and stores the whole dataset. Those are P2/P5/P12.

COMPRESSIBLE_MIMETYPES = frozenset(
    {
        'application/json',
        'application/javascript',
        'application/xml',
        'image/svg+xml',
    }
)


def _mark_varies_on_encoding(response):
    """Add Accept-Encoding to Vary without duplicating an existing entry."""
    existing = [value.strip().lower() for value in response.headers.get('Vary', '').split(',')]
    if 'accept-encoding' not in existing:
        response.headers.add('Vary', 'Accept-Encoding')


def _is_compressible(response):
    mimetype = (response.mimetype or '').lower()
    return (
        mimetype.startswith('text/')
        or mimetype.endswith('+json')
        or (mimetype in COMPRESSIBLE_MIMETYPES)
    )


def compress_response(response):
    """Gzip an eligible response body in place."""
    # A streamed or passthrough body must never be materialized here: reading it
    # would consume the generator the export routes rely on.
    if response.direct_passthrough or response.is_streamed:
        return response
    # 204/304 carry no body; HEAD must keep the headers a GET would produce, and
    # rewriting Content-Length for a body we do not send would be wrong.
    if response.status_code in (204, 304) or request.method == 'HEAD':
        return response
    if 'Content-Encoding' in response.headers:
        return response
    if not _is_compressible(response):
        return response

    _mark_varies_on_encoding(response)

    # A substring test on the raw header treats `gzip;q=0` -- an explicit refusal
    # -- as permission, because the token is present either way. Werkzeug's
    # parsed Accept applies the q-values, so a zero quality reads as "not
    # acceptable" and `*` reads as "anything", both per RFC 9110 12.5.3.
    if request.accept_encodings.quality('gzip') <= 0:
        return response

    data = response.get_data()
    if len(data) < current_app.config.get('GZIP_MIN_SIZE', 1024):
        return response

    compressed = gzip.compress(data, compresslevel=6)
    if len(compressed) >= len(data):
        return response

    # set_data recomputes Content-Length, so it always matches what we send.
    response.set_data(compressed)
    response.headers['Content-Encoding'] = 'gzip'
    return response


# --- Rate-limit topology guard (2.10 / F12) ---------------------------------


def worker_count_from_start_command(argv):
    """
    Return the worker count the start command names, or None.

    gunicorn forks its workers, so a worker inherits the master's argv. A bare
    `--workers N` that disagrees with WEB_CONCURRENCY is exactly the drift this
    exists to catch -- the app would validate one number while gunicorn ran
    another.
    """
    if not argv or 'gunicorn' not in os.path.basename(argv[0]):
        return None
    for index, arg in enumerate(argv):
        if arg.startswith('--workers='):
            value = arg.split('=', 1)[1]
        elif arg in ('-w', '--workers') and index + 1 < len(argv):
            value = argv[index + 1]
        else:
            continue
        try:
            return int(value)
        except ValueError:
            return None
    return None


def worker_timeout_from_start_command(argv):
    """
    Return the gunicorn worker timeout the start command names, or None.

    Same inheritance argument as worker_count_from_start_command: the worker
    forked from the master sees the master's argv, so the command line is the
    authoritative value rather than something the app has to be told twice.
    """
    if not argv or 'gunicorn' not in os.path.basename(argv[0]):
        return None
    for index, arg in enumerate(argv):
        if arg.startswith('--timeout='):
            value = arg.split('=', 1)[1]
        elif arg in ('-t', '--timeout') and index + 1 < len(argv):
            value = argv[index + 1]
        else:
            continue
        try:
            return int(value)
        except ValueError:
            return None
    return None


def check_fetch_timeout_headroom(app, argv=None):
    """
    Refuse a deployment whose API fetch can outlive the worker that serves it.

    gunicorn kills a sync worker that has been silent for --timeout seconds. An
    API_FETCH_TIMEOUT at or above that budget means requests.get() is still
    waiting when the axe falls, so a slow upstream shows the user a 502 instead
    of the timeout message the fetch path raises (P9). render.yaml's comment
    already states the invariant; nothing enforced it.

    Raises under APP_ENV=production and warns otherwise, matching
    check_rate_limit_topology: a local dev server has no gunicorn argv to read
    and must not be blocked by a topology it does not have.
    """
    argv = sys.argv if argv is None else argv
    worker_timeout = worker_timeout_from_start_command(argv)
    if worker_timeout is None:
        return

    fetch_timeout = app.config.get('API_FETCH_TIMEOUT', 30)
    if fetch_timeout < worker_timeout:
        return

    message = (
        f'API_FETCH_TIMEOUT is {fetch_timeout}s but gunicorn runs '
        f'--timeout {worker_timeout}s, so a slow upstream fetch is killed with the '
        f'worker and the client sees a 502 rather than the fetch timeout; raise '
        f'--timeout above API_FETCH_TIMEOUT, or lower API_FETCH_TIMEOUT below it'
    )
    if is_production():
        raise RuntimeError(message)
    logger.warning(message)


def check_rate_limit_topology(app, argv=None):
    """
    Refuse a production deployment whose rate limiting cannot be trusted.

    Raises under APP_ENV=production and warns otherwise, so local development is
    never blocked by a topology it does not have.
    """
    argv = sys.argv if argv is None else argv
    production = is_production()

    workers = app.config.get('WEB_CONCURRENCY', 1)
    replicas = app.config.get('APP_REPLICAS', 1)
    storage = app.config.get('RATELIMIT_STORAGE_URI', 'memory://')
    storage_is_shared = not storage.startswith('memory:')

    problems = []
    unverified = False

    if production:
        if not app.config.get('WEB_CONCURRENCY_DECLARED'):
            problems.append(
                'WEB_CONCURRENCY is not declared; under APP_ENV=production the worker '
                'count must be explicit, because a default of 1 makes an undeclared '
                'multi-worker deployment look single-worker'
            )
            unverified = True
        if not app.config.get('APP_REPLICAS_DECLARED'):
            problems.append(
                'APP_REPLICAS is not declared; it must mirror the deployment layer '
                "(render.yaml's numInstances)"
            )
            unverified = True

    commanded_workers = worker_count_from_start_command(argv)
    if commanded_workers is not None and commanded_workers != workers:
        problems.append(
            f'the start command runs --workers {commanded_workers} but WEB_CONCURRENCY '
            f'is {workers}; derive the command from the variable '
            f'(gunicorn ... --workers "$WEB_CONCURRENCY") so the two cannot disagree'
        )

    if not storage_is_shared and (workers > 1 or replicas > 1 or unverified):
        problems.append(
            f'RATELIMIT_STORAGE_URI is {storage!r}, whose counters are process-local, '
            f'so the effective limit is multiplied by workers x replicas '
            f'({workers} x {replicas}); set a shared backend '
            '(RATELIMIT_STORAGE_URI=redis://...) or run one worker and one instance'
        )

    if not problems:
        return

    message = 'Rate-limit topology is inconsistent: ' + '; '.join(problems)
    if production:
        raise RuntimeError(message)
    logger.warning(message)


def _register_error_handlers(app):
    """
    Keep every error response JSON (F10).

    Flask's built-in 413 and 500 pages are HTML, so app.js's response.json()
    threw a SyntaxError on the body and surfaced a parse error instead of the
    real problem. Every other error path in this app returns {"error": ...}.
    """

    @app.errorhandler(CSRFError)
    def _csrf_error(_error):
        # Flask-WTF's own 400 is an HTML page, and app.js calls response.json()
        # on every /process reply -- so a missing token surfaced as a JSON parse
        # error rather than "CSRF token missing" (F10).
        return jsonify({'error': 'CSRF token missing or invalid'}), 400

    @app.errorhandler(413)
    def _request_entity_too_large(_error):
        limit = app.config.get('MAX_CONTENT_LENGTH') or 0
        return jsonify({'error': f'Request too large (max {format_size(limit)})'}), 413

    @app.errorhandler(500)
    def _internal_server_error(_error):
        return jsonify({'error': 'An internal error occurred'}), 500

    @app.errorhandler(404)
    def _not_found(_error):
        return jsonify({'error': 'Not found'}), 404


def create_app(config_class=Config):
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    _assert_production_secret_key(app)
    check_rate_limit_topology(app)
    check_fetch_timeout_headroom(app)

    if app.config.get('TRUST_PROXY'):
        # Exactly one trusted hop. Behind Render's load balancer or an Nginx
        # reverse proxy every request otherwise appears to come from the proxy
        # IP, so all users share one rate-limit bucket and one client can exhaust
        # the site's quota (F12). x_proto also makes request.is_secure correct,
        # which the HSTS header (1.5) and the Secure cookie flag (1.14) rely on.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # Initialize extensions
    csrf.init_app(app)
    limiter.init_app(app)

    # Security headers on every response
    app.after_request(apply_security_headers)
    app.after_request(compress_response)

    _register_error_handlers(app)

    # Register routes
    from routes import bp

    app.register_blueprint(bp)

    return app


app = create_app()

if __name__ == '__main__':
    app.run(debug=app.config.get('DEBUG', False), host='0.0.0.0', port=5000)
