# app/__init__.py
from flask import Flask
from app.extensions import db, migrate, csrf, mail, limiter
from app.config import get_config

def create_app(config_name="prod"):
    app = Flask(__name__)
    app.config.from_object(get_config(config_name))

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    mail.init_app(app)
    limiter.init_app(app)

    from app.blueprints.public.views import bp as public_bp
    from app.blueprints.admin.views import bp as admin_bp
    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")

    from .cli import register_cli
    register_cli(app)
    return app
