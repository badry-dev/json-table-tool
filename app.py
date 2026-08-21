"""JSON Table Converter - Flask application factory."""

from flask import Flask

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


def create_app(config_class=Config):
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    _assert_production_secret_key(app)

    # Initialize extensions
    csrf.init_app(app)
    limiter.init_app(app)

    # Security headers on every response
    app.after_request(apply_security_headers)

    # Register routes
    from routes import bp

    app.register_blueprint(bp)

    return app


app = create_app()

if __name__ == '__main__':
    app.run(debug=app.config.get('DEBUG', False), host='0.0.0.0', port=5000)
