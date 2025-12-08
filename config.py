import os

class Config:
    # Core Flask/DB
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")

    # Берём DATABASE_URL (если есть)
    _db_url = os.environ.get("DATABASE_URL")

    # Чиним старый формат postgres:// -> postgresql:// (SQLAlchemy этого требует)
    if _db_url and _db_url.startswith("postgres://"):
        _db_url = _db_url.replace("postgres://", "postgresql://", 1)

    # Если DATABASE_URL нет – падаем обратно на локальный SQLite
    SQLALCHEMY_DATABASE_URI = _db_url or "sqlite:///sports_club.db"

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
        "pool_size": int(os.environ.get("DB_POOL_SIZE", "5")),
        "max_overflow": int(os.environ.get("DB_MAX_OVERFLOW", "10")),
        "pool_timeout": int(os.environ.get("DB_POOL_TIMEOUT", "30")),
    }

    # i18n
    LANGUAGES = ["ru", "en", "et"]
    BABEL_DEFAULT_LOCALE = os.environ.get("BABEL_DEFAULT_LOCALE", "ru")
    BABEL_DEFAULT_TIMEZONE = os.environ.get("BABEL_DEFAULT_TIMEZONE", "Europe/Tallinn")

    # Admin demo creds (legacy/demo)
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

    # App URLs
    APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:5000")

    # Uploads
    UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "./uploads")
    MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "15"))
    ALLOWED_UPLOAD_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}

    # Mail settings
    MAIL_FROM = os.environ.get("MAIL_FROM")
    MAIL_TO = os.environ.get("MAIL_TO")
    MAILGUN_API_KEY = os.environ.get("MAILGUN_API_KEY")
    MAILGUN_DOMAIN = os.environ.get("MAILGUN_DOMAIN")
    MAILGUN_BASE_URL = os.environ.get("MAILGUN_BASE_URL", "https://api.mailgun.net/v3")
    WTF_CSRF_TIME_LIMIT = None