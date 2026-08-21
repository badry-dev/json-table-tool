"""JSON Table Converter - Flask application factory."""

from flask import Flask, jsonify
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

    _register_error_handlers(app)

    # Register routes
    from routes import bp

    app.register_blueprint(bp)

    return app


app = create_app()

if __name__ == '__main__':
    app.run(debug=app.config.get('DEBUG', False), host='0.0.0.0', port=5000)
