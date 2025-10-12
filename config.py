import os

class Config:
    # Core Flask/DB
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///sports_club.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

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

    # Stripe Billing
    STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
    STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    STRIPE_PRICE_MONTHLY = os.environ.get("STRIPE_PRICE_MONTHLY", os.environ.get("PRICE_MONTHLY", ""))
    STRIPE_PRICE_YEARLY = os.environ.get("STRIPE_PRICE_YEARLY", os.environ.get("PRICE_YEARLY", ""))
    STRIPE_ENABLED = bool(STRIPE_SECRET_KEY)
