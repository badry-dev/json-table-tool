"""JSON Table Converter - Flask application factory."""

import gzip

from flask import Flask, current_app, jsonify, request
from werkzeug.middleware.proxy_fix import ProxyFix

from config import DEV_SECRET_KEY, Config, is_production
from extensions import csrf, limiter
from security import apply_security_headers


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

    if 'gzip' not in request.headers.get('Accept-Encoding', '').lower():
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


def _register_error_handlers(app):
    """
    Keep every error response JSON (F10).

    Flask's built-in 413 and 500 pages are HTML, so app.js's response.json()
    threw a SyntaxError on the body and surfaced a parse error instead of the
    real problem. Every other error path in this app returns {"error": ...}.
    """

    @app.errorhandler(413)
    def _request_entity_too_large(_error):
        limit = app.config.get('MAX_CONTENT_LENGTH') or 0
        return jsonify({'error': f'Request too large (max {limit // (1024 * 1024)}MB)'}), 413

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
