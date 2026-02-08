"""JSON Table Converter - Flask application factory."""

from flask import Flask
from config import Config
from extensions import csrf, limiter
from security import apply_security_headers


def create_app(config_class=Config):
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config.from_object(config_class)

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
