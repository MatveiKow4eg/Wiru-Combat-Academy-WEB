import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///sports_club.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # i18n
    LANGUAGES = ["ru", "en", "et"]
    BABEL_DEFAULT_LOCALE = os.environ.get("BABEL_DEFAULT_LOCALE", "ru")
    BABEL_DEFAULT_TIMEZONE = os.environ.get("BABEL_DEFAULT_TIMEZONE", "Europe/Tallinn")

    # Simple admin auth (demo)
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
