# app/__init__.py
from flask import Flask
from .extensions import db, migrate, csrf, mail, limiter
from .config import get_config

from flask import Blueprint

public_bp = Blueprint("public", __name__)
admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def create_app(config_name="prod"):
    app = Flask(__name__)
    app.config.from_object(get_config(config_name))

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    mail.init_app(app)
    limiter.init_app(app)

    from .blueprints.public import bp as public_bp
    from .blueprints.admin import bp as admin_bp
    from .blueprints.api import bp as api_bp
    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")

    from .cli import register_cli
    register_cli(app)
    return app
