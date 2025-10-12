from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


db = SQLAlchemy()


class News(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    image = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Schedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # day_of_week: 0=Mon ... 6=Sun
    day_of_week = db.Column(db.Integer, nullable=False)
    time = db.Column(db.String(50), nullable=False)
    activity = db.Column(db.String(120), nullable=False)
    coach = db.Column(db.String(120))


class Trainer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    bio = db.Column(db.Text, nullable=False)
    photo = db.Column(db.String(255))


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)

    # New required fields
    email = db.Column(db.String(255), unique=True, index=True, nullable=False)
    username = db.Column(db.String(80), unique=True)  # optional for compatibility
    password_hash = db.Column(db.String(255), nullable=False)

    # Public profile fields (optional for this project, can be extended)
    full_name = db.Column(db.String(255))
    level = db.Column(db.String(120))
    group_name = db.Column(db.String(120))

    # Roles: 'user' | 'admin' (default 'user')
    role = db.Column(db.String(10), index=True, nullable=False, default='user')

    # Account flags and metadata
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Legacy compatibility (kept so existing code using current_user.is_admin keeps working)
    # NOTE: In new code prefer checking self.role == 'admin'. Keep this column in sync where needed.
    is_admin = db.Column(db.Boolean, default=False)

    # Relationships
    subscriptions = db.relationship('Subscription', backref='user', lazy='dynamic', cascade="all, delete-orphan")
    payments = db.relationship('Payment', backref='user', lazy='dynamic', cascade="all, delete-orphan")
    documents = db.relationship('Document', backref='user', lazy='dynamic', cascade="all, delete-orphan")

    # Password helpers
    def set_password(self, plain: str) -> None:
        self.password_hash = generate_password_hash(plain)

    def check_password(self, plain: str) -> bool:
        return check_password_hash(self.password_hash or '', plain)

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} role={self.role!r}>"


class Subscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True, nullable=False)
    stripe_customer_id = db.Column(db.String(120), index=True)
    stripe_subscription_id = db.Column(db.String(120), index=True)
    stripe_price_id = db.Column(db.String(120), index=True)
    status = db.Column(db.String(50), index=True)  # active | past_due | canceled | incomplete | trialing
    current_period_end = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True, nullable=False)
    stripe_invoice_id = db.Column(db.String(120), index=True)
    amount = db.Column(db.Integer)  # amount in cents
    currency = db.Column(db.String(10))
    status = db.Column(db.String(50), index=True)
    paid_at = db.Column(db.DateTime)
    raw = db.Column(db.JSON)  # store raw event/invoice data

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True, nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    stored_path = db.Column(db.String(512), nullable=False)
    mime = db.Column(db.String(120))
    size_bytes = db.Column(db.Integer)
    note = db.Column(db.String(500))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Signup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(50))
    activity = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
