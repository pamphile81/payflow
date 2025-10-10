# config.py
import os
from datetime import timedelta

# ---- Base ----
class Config:
    """Configuration de base pour PayFlow (safe à committer)"""

    # Sécurité
    #SECRET_KEY = os.getenv("SECRET_KEY", "dev-change-me")  # remplacé par .env en local / prod
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key-change-this-v1.2'
    PERMANENT_SESSION_LIFETIME = timedelta(days=int(os.getenv("SESSION_LIFETIME_DAYS", "7")))
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE

    # Base de données
    # En prod, utilise DATABASE_URL ; en dev, DEV_DATABASE_URL peut surcharger.
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL") or \
        os.getenv("DEV_DATABASE_URL") or \
        "postgresql+psycopg2://payflow_db_user:payflow_db_user_pwd@localhost:5432/payflow_db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": int(os.getenv("DB_POOL_RECYCLE_SEC", "300")),
        "connect_args": {
            "connect_timeout": int(os.getenv("DB_CONNECT_TIMEOUT_SEC", "10")),
        },
    }

    # Ajoutez cette nouvelle configuration
    SQLALCHEMY_SESSION_OPTIONS = {
        "expire_on_commit": False
    }

    # Fichiers
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "uploads")
    OUTPUT_FOLDER = os.getenv("OUTPUT_FOLDER", "output")
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", str(50 * 1024 * 1024)))  # 50MB par défaut

    # Liens de téléchargement
    DOWNLOAD_LINK_EXPIRY_DAYS = int(os.getenv("DOWNLOAD_LINK_EXPIRY_DAYS", "30"))
    MAX_DOWNLOAD_ATTEMPTS = int(os.getenv("MAX_DOWNLOAD_ATTEMPTS", "10"))

    # SMTP (remplace email_config.py à terme)
    MAIL_SERVER = os.getenv("SMTP_SERVER", "localhost")
    MAIL_PORT = int(os.getenv("SMTP_PORT", "25"))
    MAIL_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
    MAIL_USERNAME = os.getenv("SMTP_USERNAME")
    MAIL_PASSWORD = os.getenv("SMTP_PASSWORD")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", os.getenv("SMTP_USERNAME"))

class DevelopmentConfig(Config):
    DEBUG = True
    # Si tu veux forcer un DSN spécifique en dev :
    #SQLALCHEMY_DATABASE_URI = os.getenv("DEV_DATABASE_URL") or Config.SQLALCHEMY_DATABASE_URI
    SQLALCHEMY_DATABASE_URI = os.environ.get('DEV_DATABASE_URL') or \
        'postgresql+psycopg2://payflow_db_user:payflow_db_user_pwd@localhost:5432/payflow_db'

class ProductionConfig(Config):
    DEBUG = False

# Utilise un nom qui n’entre pas en conflit avec le nom du module
CONFIG_MAP = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig,
}

# ---- Sélecteur utilisé par app.py (create_app) ----
def get_config(name: str | None = None):
    """Retourne la classe de config en fonction de APP_ENV/FLASK_ENV ou du paramètre."""
    env = (name or os.getenv('APP_ENV') or os.getenv('FLASK_ENV') or 'development').lower()
    return CONFIG_MAP.get(env, DevelopmentConfig)



'''def get_config(name: str | None = None):
    name = (name or os.getenv("APP_ENV", "development")).lower()
    mapping = {
        "development": DevelopmentConfig,
        "prod": ProductionConfig,
        "production": ProductionConfig,
        "default": DevelopmentConfig,
    }
    return mapping.get(name, DevelopmentConfig)'''
class Config:
    PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:5000")
