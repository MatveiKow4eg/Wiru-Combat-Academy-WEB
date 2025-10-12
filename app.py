from flask import Flask, render_template, request, redirect, url_for, flash, session, abort, jsonify, send_file
from flask_babel import Babel, gettext as _
from flask_login import LoginManager, current_user, login_user, logout_user, login_required
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash
from urllib.parse import urlparse
from datetime import datetime, timezone
from config import Config
from models import db, News, Schedule, Trainer, Signup, User, Subscription, Payment, Document
import models as models
from forms import LoginForm, RegisterForm, NewsForm, ScheduleForm, SignupForm, DocumentUploadForm, UserSearchForm

import os
import secrets
import sqlite3
from functools import wraps
from babel.messages.pofile import read_po
from babel.messages.mofile import write_mo


def compile_translations(app):
    trans_dir = os.path.join(app.root_path, "translations")
    if not os.path.isdir(trans_dir):
        return
    for lang in os.listdir(trans_dir):
        po_path = os.path.join(trans_dir, lang, "LC_MESSAGES", "messages.po")
        mo_path = os.path.join(trans_dir, lang, "LC_MESSAGES", "messages.mo")
        if os.path.isfile(po_path):
            try:
                with open(po_path, "r", encoding="utf-8") as f:
                    catalog = read_po(f)
                os.makedirs(os.path.dirname(mo_path), exist_ok=True)
                with open(mo_path, "wb") as f:
                    write_mo(f, catalog)
            except Exception:
                # Skip locale if it fails to compile
                pass


def run_simple_migrations(app):
    """Lightweight, idempotent runtime migrations for the User table.
    Adds missing columns and indexes required by the new auth model without Alembic.
    Uses the same SQLAlchemy engine/connection to avoid path mismatches.
    """
    with app.app_context():
        engine = db.engine
        if engine.dialect.name != "sqlite":
            return
        try:
            with engine.begin() as conn:
                # Inspect existing columns
                cols_rows = conn.exec_driver_sql("PRAGMA table_info('user')").fetchall()
                cols = {row[1] for row in cols_rows}

                # Add columns if missing (NULL allowed initially for safety).
                # Include all columns defined on models.User to prevent SELECT errors.
                add_cols_sql = []
                if "email" not in cols:
                    add_cols_sql.append("ALTER TABLE user ADD COLUMN email VARCHAR(255)")
                if "username" not in cols:
                    add_cols_sql.append("ALTER TABLE user ADD COLUMN username VARCHAR(80)")
                if "password_hash" not in cols:
                    add_cols_sql.append("ALTER TABLE user ADD COLUMN password_hash VARCHAR(255)")
                if "full_name" not in cols:
                    add_cols_sql.append("ALTER TABLE user ADD COLUMN full_name VARCHAR(255)")
                if "level" not in cols:
                    add_cols_sql.append("ALTER TABLE user ADD COLUMN level VARCHAR(120)")
                if "group_name" not in cols:
                    add_cols_sql.append("ALTER TABLE user ADD COLUMN group_name VARCHAR(120)")
                if "role" not in cols:
                    add_cols_sql.append("ALTER TABLE user ADD COLUMN role VARCHAR(10)")
                if "is_active" not in cols:
                    add_cols_sql.append("ALTER TABLE user ADD COLUMN is_active BOOLEAN")
                if "created_at" not in cols:
                    add_cols_sql.append("ALTER TABLE user ADD COLUMN created_at DATETIME")
                if "is_admin" not in cols:
                    add_cols_sql.append("ALTER TABLE user ADD COLUMN is_admin BOOLEAN")
                for stmt in add_cols_sql:
                    conn.exec_driver_sql(stmt)

                # Backfill safe defaults for new columns
                conn.exec_driver_sql("UPDATE user SET role = COALESCE(role, 'user')")
                conn.exec_driver_sql("UPDATE user SET is_active = COALESCE(is_active, 1)")
                conn.exec_driver_sql("UPDATE user SET created_at = COALESCE(created_at, datetime('now'))")
                conn.exec_driver_sql("UPDATE user SET is_admin = COALESCE(is_admin, 0)")

                # If there is an admin with no email, assign a default email if free
                row = conn.exec_driver_sql(
                    "SELECT id FROM user WHERE (COALESCE(is_admin,0) = 1 OR role = 'admin') AND (email IS NULL OR email = '') LIMIT 1"
                ).fetchone()
                if row:
                    admin_id = row[0]
                    default_email = "admin@site.local"
                    exists = conn.exec_driver_sql("SELECT 1 FROM user WHERE email = ?", (default_email,)).fetchone()
                    if exists:
                        default_email = f"admin+{admin_id}@site.local"
                    conn.exec_driver_sql("UPDATE user SET email = ? WHERE id = ?", (default_email, admin_id))

                # Create indexes (avoid creating a unique index on username to prevent failures on duplicates)
                conn.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS ux_user_email ON user(email)")
                conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_user_role ON user(role)")
        except Exception:
            app.logger.warning("User table migration skipped or failed. Consider using Alembic.")


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Compile translations on startup
    compile_translations(app)

    # DB
    db.init_app(app)
    with app.app_context():
        db.create_all()
        run_simple_migrations(app)
        seed_if_empty()
        # Ensure upload directory exists
        try:
            os.makedirs(app.config.get("UPLOAD_DIR", "./uploads"), exist_ok=True)
        except Exception:
            app.logger.warning("Unable to create upload directory")

    # Auth and CSRF
    login_manager = LoginManager(app)
    login_manager.login_view = "login"

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    csrf = CSRFProtect(app)

    # Role-based decorator
    def role_required(*roles):
        def decorator(view):
            @wraps(view)
            def wrapper(*args, **kwargs):
                if not current_user.is_authenticated:
                    next_rel = request.full_path if request.query_string else request.path
                    return redirect(url_for("login", next=next_rel))
                if roles and (getattr(current_user, "role", None) not in roles):
                    flash(_("Доступ запрещён"))
                    return abort(403)
                return view(*args, **kwargs)
            return wrapper
        return decorator

    # Backward alias for existing admin protection
    def admin_required(view):
        return role_required('admin')(view)

    @login_manager.unauthorized_handler
    def unauthorized():
        flash(_("Требуется вход для доступа."))
        next_rel = request.full_path if request.query_string else request.path
        return redirect(url_for("login", next=next_rel))

    # Babel
    def select_locale():
        # 1) explicit ?lang=xx
        lang = request.args.get("lang")
        if lang and lang in app.config["LANGUAGES"]:
            session["lang"] = lang
        # 2) session
        if "lang" in session:
            return session["lang"]
        # 3) best match from headers
        return request.accept_languages.best_match(app.config["LANGUAGES"])

    babel = Babel(app, locale_selector=select_locale)

    # Template globals
    @app.context_processor
    def inject_now_and_langs():
        return dict(now=datetime.utcnow(), LANGUAGES=app.config["LANGUAGES"], models=models, config=app.config)

    # Utilities
    def is_safe_next(target: str) -> bool:
        if not target:
            return False
        # Only allow relative URLs (no netloc)
        return urlparse(target).netloc == ""

    # Public routes
    @app.route("/")
    def home():
        news = News.query.order_by(News.created_at.desc()).limit(6).all()
        schedule = Schedule.query.order_by(
            Schedule.day_of_week.asc(), Schedule.time.asc()
        ).all()
        trainers = Trainer.query.all()
        return render_template(
            "home.html", news=news, schedule=schedule, trainers=trainers
        )

    @app.route("/news")
    def news_list():
        news = News.query.order_by(News.created_at.desc()).all()
        return render_template("news.html", news=news)

    @app.route("/news/<int:news_id>")
    def news_detail(news_id):
        item = News.query.get_or_404(news_id)
        return render_template("news_detail.html", item=item)

    @app.route("/schedule")
    def schedule_page():
        schedule = Schedule.query.order_by(
            Schedule.day_of_week.asc(), Schedule.time.asc()
        ).all()
        return render_template(
            "schedule.html", schedule=schedule, today=datetime.utcnow().weekday()
        )

    @app.route("/trainers")
    def trainers_page():
        trainers = Trainer.query.all()
        return render_template("trainers.html", trainers=trainers)

    @app.route("/contact")
    def contact():
        return render_template("contact.html")

    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        form = SignupForm()
        if form.validate_on_submit():
            s = Signup(
                name=form.name.data,
                email=form.email.data,
                phone=form.phone.data,
                activity=form.activity.data,
            )
            db.session.add(s)
            db.session.commit()
            flash(_("Спасибо! Мы свяжемся с вами скоро."))
            return redirect(url_for("home"))
        return render_template("signup.html", form=form)

    # Authentication routes (public)
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            # already logged in: go to profile
            return redirect(url_for("profile"))
        form = LoginForm()
        if form.validate_on_submit():
            ident = (form.email.data or '').strip()
            user = User.query.filter_by(email=ident.lower()).first()
            if not user:
                user = User.query.filter_by(username=ident).first()
            if user and user.is_active and user.check_password(form.password.data):
                login_user(user, remember=form.remember.data)
                flash(_("Добро пожаловать!"))
                nxt = request.args.get("next")
                if nxt and is_safe_next(nxt) and not nxt.startswith('/admin'):
                    return redirect(nxt)
                return redirect(url_for("profile"))
            flash(_("Неверный email/имя пользователя или пароль"))
        return render_template("auth/login.html", form=form)

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if current_user.is_authenticated:
            return redirect(url_for("profile"))
        form = RegisterForm()
        if form.validate_on_submit():
            email = form.email.data.lower().strip()
            if User.query.filter_by(email=email).first():
                flash(_("Пользователь с таким email уже существует"))
                return render_template("auth/register.html", form=form)
            username = (form.username.data or '').strip() or None
            user = User(email=email, username=username, role='user', is_active=True)
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash(_("Регистрация успешна"))
            nxt = request.args.get("next")
            if nxt and is_safe_next(nxt):
                return redirect(nxt)
            return redirect(url_for("profile"))
        return render_template("auth/register.html", form=form)

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        flash(_("Вы вышли из аккаунта."))
        return redirect(url_for("home"))

    # Admin-specific login (only admins can enter)
    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        if current_user.is_authenticated and current_user.role == 'admin':
            return redirect(url_for("profile"))
        form = LoginForm()
        if form.validate_on_submit():
            ident = (form.email.data or '').strip()
            user = User.query.filter_by(email=ident.lower()).first()
            if not user:
                user = User.query.filter_by(username=ident).first()
            if user and user.role == 'admin' and user.is_active and user.check_password(form.password.data):
                login_user(user, remember=form.remember.data)
                flash(_("Добро пожаловать в админ-панель!"))
                # Always redirect to profile after admin login
                return redirect(url_for("profile"))
            flash(_("Неверный email/имя пользователя или пароль"))
        return render_template("admin/login.html", form=form)

    # Admin area
    @app.route("/admin")
    @admin_required
    def admin_dashboard():
        return render_template(
            "admin/dashboard.html",
            news_count=News.query.count(),
            signup_count=Signup.query.count(),
        )

    @app.route("/admin/news/add", methods=["GET", "POST"])
    @admin_required
    def admin_add_news():
        form = NewsForm()
        if form.validate_on_submit():
            n = News(
                title=form.title.data,
                body=form.body.data,
                image=form.image.data.strip() or None,
            )
            db.session.add(n)
            db.session.commit()
            flash(_("Новость добавлена."))
            return redirect(url_for("admin_news_list"))
        return render_template("admin/news_form.html", form=form, page_title=_("Добавить новость"))

    @app.route("/admin/news")
    @admin_required
    def admin_news_list():
        items = News.query.order_by(News.created_at.desc()).all()
        return render_template("admin/news_list.html", items=items)

    @app.route("/admin/news/edit/<int:news_id>", methods=["GET", "POST"])
    @admin_required
    def admin_edit_news(news_id):
        item = News.query.get_or_404(news_id)
        form = NewsForm(obj=item)
        if form.validate_on_submit():
            item.title = form.title.data
            item.body = form.body.data
            item.image = (form.image.data or "").strip() or None
            db.session.commit()
            flash(_("Новость обновлена."))
            return redirect(url_for("admin_news_list"))
        return render_template("admin/news_form.html", form=form, page_title=_("Редактировать новость"), item=item)

    @app.route("/admin/news/delete/<int:news_id>", methods=["POST"])
    @admin_required
    def admin_delete_news(news_id):
        item = News.query.get_or_404(news_id)
        db.session.delete(item)
        db.session.commit()
        flash(_("Новость удалена."))
        return redirect(url_for("admin_news_list"))

    @app.route("/admin/schedule", methods=["GET", "POST"])
    @admin_required
    def admin_edit_schedule():
        form = ScheduleForm()
        if form.validate_on_submit():
            item = Schedule(
                day_of_week=form.day_of_week.data,
                time=form.time.data,
                activity=form.activity.data,
                coach=form.coach.data,
            )
            db.session.add(item)
            db.session.commit()
            flash(_("Тренировка добавлена в расписание."))
            return redirect(url_for("schedule_page"))
        schedule = Schedule.query.order_by(
            Schedule.day_of_week.asc(), Schedule.time.asc()
        ).all()
        return render_template(
            "admin/edit_schedule.html", form=form, schedule=schedule
        )

    # Admin: Users list and detail
    @app.route("/admin/users")
    @admin_required
    def admin_users():
        form = UserSearchForm(request.args)
        q = (form.q.data or '').strip() if form else ''
        query = User.query
        if q:
            like = f"%{q}%"
            query = query.filter(
                (User.email.ilike(like)) |
                (User.username.ilike(like)) |
                (User.full_name.ilike(like))
            )
        users = query.order_by(User.created_at.desc()).limit(200).all()
        return render_template("admin/users_list.html", users=users, form=form, q=q)

    @app.route("/admin/users/<int:user_id>")
    @admin_required
    def admin_user_detail(user_id):
        u = User.query.get_or_404(user_id)
        subs = u.subscriptions.order_by(Subscription.created_at.desc()).all()
        pays = u.payments.order_by(Payment.created_at.desc()).all()
        docs = u.documents.order_by(Document.uploaded_at.desc()).all()
        return render_template("admin/user_detail.html", user=u, subs=subs, payments=pays, docs=docs)

    # Admin: billing lists
    @app.route("/admin/billing/subscriptions")
    @admin_required
    def admin_billing_subscriptions():
        subs = Subscription.query.order_by(Subscription.created_at.desc()).limit(500).all()
        return render_template("admin/subs.html", subs=subs)

    @app.route("/admin/billing/payments")
    @admin_required
    def admin_billing_payments():
        pays = Payment.query.order_by(Payment.created_at.desc()).limit(500).all()
        return render_template("admin/payments.html", payments=pays)

    # Billing routes
    @app.route("/billing")
    @login_required
    def billing_home():
        return redirect(url_for("profile", tab="billing"))

    @app.route("/billing/checkout/session", methods=["POST"]) 
    @login_required
    def billing_checkout_session():
        data = request.get_json(silent=True) or {}
        price_id = (data.get("price_id") or '').strip()
        if not price_id:
            return jsonify({"error": "price_id required"}), 400
        secret = app.config.get("STRIPE_SECRET_KEY")
        if not secret:
            return jsonify({"error": "Stripe not configured"}), 400
        try:
            import stripe
            stripe.api_key = secret
            success_url = f"{app.config.get('APP_BASE_URL').rstrip('/')}/billing?success=1"
            cancel_url = f"{app.config.get('APP_BASE_URL').rstrip('/')}/billing?canceled=1"
            # try reuse customer if exists
            existing = None
            try:
                existing = current_user.subscriptions.order_by(Subscription.created_at.desc()).first()
            except Exception:
                existing = None
            kwargs = {}
            if existing and existing.stripe_customer_id:
                kwargs["customer"] = existing.stripe_customer_id
            checkout = stripe.checkout.Session.create(
                mode="subscription",
                success_url=success_url,
                cancel_url=cancel_url,
                line_items=[{"price": price_id, "quantity": 1}],
                allow_promotion_codes=True,
                automatic_tax={"enabled": True},
                metadata={"user_id": str(current_user.id), "price_id": price_id},
                **kwargs
            )
            return jsonify({"url": checkout.url})
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/billing/portal", methods=["POST"]) 
    @login_required
    def billing_portal():
        secret = app.config.get("STRIPE_SECRET_KEY")
        if not secret:
            return jsonify({"error": "Stripe not configured"}), 400
        try:
            active_sub = current_user.subscriptions.order_by(Subscription.created_at.desc()).first()
        except Exception:
            active_sub = None
        if not active_sub or not active_sub.stripe_customer_id:
            return jsonify({"error": "No Stripe customer"}), 400
        try:
            import stripe
            stripe.api_key = secret
            portal = stripe.billing_portal.Session.create(
                customer=active_sub.stripe_customer_id,
                return_url=f"{app.config.get('APP_BASE_URL').rstrip('/')}/billing"
            )
            return jsonify({"url": portal.url})
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/billing/webhook", methods=["POST"]) 
    def billing_webhook():
        import json
        endpoint_secret = app.config.get("STRIPE_WEBHOOK_SECRET")
        payload = request.data
        sig_header = request.headers.get("Stripe-Signature")
        try:
            import stripe
            event = None
            if endpoint_secret:
                event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
            else:
                event = json.loads(payload)
        except Exception as e:
            return ("", 400)

        def find_user_by_customer(customer_id: str):
            if not customer_id:
                return None
            sub = Subscription.query.filter_by(stripe_customer_id=customer_id).order_by(Subscription.created_at.desc()).first()
            return sub.user if sub else None

        etype = event.get("type") if isinstance(event, dict) else event.type
        data_obj = event.get("data", {}).get("object") if isinstance(event, dict) else event.data.object

        try:
            if etype == "checkout.session.completed":
                customer_id = data_obj.get("customer")
                subscription_id = data_obj.get("subscription")
                metadata = data_obj.get("metadata") or {}
                user_id = metadata.get("user_id")
                price_id = metadata.get("price_id")
                user = None
                if user_id:
                    user = User.query.get(int(user_id))
                if not user:
                    user = find_user_by_customer(customer_id)
                if user:
                    # retrieve subscription details from Stripe to get status & period end
                    status = "active"
                    current_period_end = None
                    try:
                        import stripe
                        stripe.api_key = app.config.get("STRIPE_SECRET_KEY")
                        if subscription_id:
                            s = stripe.Subscription.retrieve(subscription_id)
                            status = s.get("status") or status
                            cpe = s.get("current_period_end")
                            if cpe:
                                current_period_end = datetime.fromtimestamp(int(cpe), tz=timezone.utc)
                            if not price_id:
                                items = (s.get("items") or {}).get("data") or []
                                if items:
                                    price_id = items[0].get("price", {}).get("id")
                    except Exception:
                        pass
                    sub = Subscription.query.filter_by(stripe_subscription_id=subscription_id).first()
                    if not sub:
                        sub = Subscription(user_id=user.id)
                    sub.stripe_customer_id = customer_id
                    sub.stripe_subscription_id = subscription_id
                    sub.stripe_price_id = price_id
                    sub.status = status
                    sub.current_period_end = current_period_end
                    db.session.add(sub)
                    db.session.commit()

            elif etype == "invoice.paid":
                invoice = data_obj
                customer_id = invoice.get("customer")
                user = find_user_by_customer(customer_id)
                if user:
                    p = Payment(
                        user_id=user.id,
                        stripe_invoice_id=invoice.get("id"),
                        amount=invoice.get("amount_paid"),
                        currency=(invoice.get("currency") or "").upper(),
                        status="paid",
                        paid_at=datetime.fromtimestamp(int(invoice.get("status_transitions", {}).get("paid_at") or invoice.get("created") or 0), tz=timezone.utc),
                        raw=invoice,
                    )
                    db.session.add(p)
                    # ensure subscription status stays active
                    sub = user.subscriptions.order_by(Subscription.created_at.desc()).first()
                    if sub:
                        sub.status = "active"
                    db.session.commit()

            elif etype == "invoice.payment_failed":
                invoice = data_obj
                customer_id = invoice.get("customer")
                user = find_user_by_customer(customer_id)
                if user:
                    sub = user.subscriptions.order_by(Subscription.created_at.desc()).first()
                    if sub:
                        sub.status = "past_due"
                        db.session.commit()

            elif etype in ("customer.subscription.updated", "customer.subscription.deleted"):
                s = data_obj
                subscription_id = s.get("id")
                sub = Subscription.query.filter_by(stripe_subscription_id=subscription_id).first()
                if sub:
                    sub.status = s.get("status") or sub.status
                    cpe = s.get("current_period_end")
                    if cpe:
                        sub.current_period_end = datetime.fromtimestamp(int(cpe), tz=timezone.utc)
                    db.session.commit()
        except Exception:
            # swallow exceptions to let Stripe retry
            pass

        return ("", 200)

    # Simple profile page for authenticated users
    @app.route("/profile", methods=["GET", "POST"])
    @login_required
    def profile():
        # Determine which form/tab was submitted
        action = request.form.get('action') if request.method == 'POST' else None

        # Update account (username/email)
        if action == 'update_account':
            new_username = (request.form.get('username') or '').strip() or None
            new_email = (request.form.get('email') or '').strip().lower()
            # Email can be read-only if blank in form
            if new_email and new_email != current_user.email:
                # Ensure uniqueness
                if User.query.filter(User.email == new_email, User.id != current_user.id).first():
                    flash(_("Этот email уже занят."), 'error')
                else:
                    current_user.email = new_email
            # Update username with uniqueness check
            if new_username != current_user.username:
                if new_username and User.query.filter(User.username == new_username, User.id != current_user.id).first():
                    flash(_("Это имя пользователя уже занято."), 'error')
                else:
                    current_user.username = new_username
            db.session.commit()
            flash(_("Профиль обновлён."), 'success')
            return redirect(url_for('profile'))

        # Change password
        if action == 'change_password':
            current_pwd = request.form.get('current_password') or ''
            new_pwd = request.form.get('new_password') or ''
            confirm_pwd = request.form.get('confirm_password') or ''
            # Validate
            if not current_user.check_password(current_pwd):
                flash(_("Текущий пароль неверен."), 'error')
                return redirect(url_for('profile'))
            if len(new_pwd) < 8:
                flash(_("Новый пароль слишком короткий."), 'error')
                return redirect(url_for('profile'))
            if new_pwd != confirm_pwd:
                flash(_("Пароли не совпадают."), 'error')
                return redirect(url_for('profile'))
            current_user.set_password(new_pwd)
            db.session.commit()
            flash(_("Пароль успешно изменён."), 'success')
            return redirect(url_for('profile'))

        # Preferences: language
        if action == 'update_prefs':
            lang = request.form.get('lang')
            if lang in app.config.get('LANGUAGES', ['ru','en','et']):
                session['lang'] = lang
                flash(_("Язык интерфейса обновлён."), 'success')
            else:
                flash(_("Недопустимый язык."), 'error')
            # remember-me preference is handled at login; here we could store preference if needed
            return redirect(url_for('profile'))

        # Compute latest subscription for UI (Overview)
        last_sub = None
        try:
            last_sub = current_user.subscriptions.order_by(Subscription.created_at.desc()).first()
        except Exception:
            last_sub = None

        # Data for Billing tab
        try:
            active_sub = current_user.subscriptions.order_by(Subscription.created_at.desc()).first()
        except Exception:
            active_sub = None
        try:
            payments = current_user.payments.order_by(Payment.created_at.desc()).limit(50).all()
        except Exception:
            payments = []
        customer_id = active_sub.stripe_customer_id if active_sub and active_sub.stripe_customer_id else None

        # Data for Documents tab
        form = DocumentUploadForm()
        try:
            docs = current_user.documents.order_by(Document.uploaded_at.desc()).all()
        except Exception:
            docs = []

        return render_template("profile/overview.html", last_sub=last_sub, active_sub=active_sub, payments=payments, customer_id=customer_id, form=form, docs=docs)

    # Documents routes
    @app.route("/documents", methods=["GET"]) 
    @login_required
    def documents():
        return redirect(url_for("profile", tab="documents"))

    @app.route("/documents/upload", methods=["POST"]) 
    @login_required
    def documents_upload():
        form = DocumentUploadForm()
        if not form.validate_on_submit():
            flash(_("Ошибка загрузки файла"), 'error')
            return redirect(url_for("documents"))
        f = form.file.data
        filename = f.filename or ''
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        allowed = set(app.config.get("ALLOWED_UPLOAD_EXTENSIONS", {"pdf","jpg","jpeg","png"}))
        if ext not in allowed:
            flash(_("Недопустимый тип файла"), 'error')
            return redirect(url_for("documents"))
        max_bytes = int(app.config.get("MAX_UPLOAD_MB", 15)) * 1024 * 1024
        content_len = request.content_length or 0
        if content_len and content_len > max_bytes + 8192:
            flash(_("Файл слишком большой"), 'error')
            return redirect(url_for("documents"))
        import uuid
        user_dir = os.path.join(app.config.get("UPLOAD_DIR", "./uploads"), str(current_user.id))
        os.makedirs(user_dir, exist_ok=True)
        stored_name = f"{uuid.uuid4().hex}.{ext}"
        stored_path = os.path.join(user_dir, stored_name)
        try:
            f.save(stored_path)
            size_bytes = os.path.getsize(stored_path)
            if size_bytes > max_bytes:
                os.remove(stored_path)
                flash(_("Файл слишком большой"), 'error')
                return redirect(url_for("documents"))
        except Exception:
            try:
                if os.path.exists(stored_path): os.remove(stored_path)
            except Exception:
                pass
            flash(_("Ошибка сохранения файла"), 'error')
            return redirect(url_for("documents"))
        doc = Document(
            user_id=current_user.id,
            filename=filename,
            stored_path=stored_path,
            mime=getattr(f, 'mimetype', None),
            size_bytes=size_bytes,
            note=(form.note.data or '').strip() or None,
        )
        db.session.add(doc)
        db.session.commit()
        flash(_("Документ загружен"), 'success')
        return redirect(url_for("profile", tab="documents"))

    @app.route("/admin/documents")
    @admin_required
    def admin_documents():
        user_id = request.args.get("user_id", type=int)
        q = (request.args.get("q") or "").strip()
        query = Document.query
        if user_id:
            query = query.filter(Document.user_id == user_id)
        if q:
            like = f"%{q}%"
            query = query.filter((Document.filename.ilike(like)) | (Document.note.ilike(like)))
        docs = query.order_by(Document.uploaded_at.desc()).limit(200).all()
        return render_template("admin/documents_list.html", docs=docs, user_id=user_id, q=q)

    @app.route("/admin/documents/<int:doc_id>/download")
    @admin_required
    def admin_document_download(doc_id):
        doc = Document.query.get_or_404(doc_id)
        base = os.path.realpath(app.config.get("UPLOAD_DIR", "./uploads"))
        path = os.path.realpath(doc.stored_path or "")
        if not path.startswith(base + os.sep) and path != base:
            abort(403)
        try:
            return send_file(path, as_attachment=True, download_name=doc.filename or os.path.basename(path))
        except Exception:
            abort(404)

    @app.errorhandler(403)
    def forbidden(_e):
        return render_template("errors/403.html"), 403

    # CLI command to create or reset admin user
    @app.cli.command("create-admin")
    def create_admin_cmd():
        """Create superuser admin@site.local with password from ADMIN_PASSWORD or generated."""
        with app.app_context():
            email = "admin@site.local"
            user = User.query.filter_by(email=email).first()
            pwd = os.environ.get("ADMIN_PASSWORD") or secrets.token_urlsafe(12)
            if not user:
                user = User(email=email, username="admin", role='admin', is_active=True, is_admin=True)
                user.set_password(pwd)
                db.session.add(user)
            else:
                user.role = 'admin'
                user.is_active = True
                user.is_admin = True
                user.set_password(pwd)
            db.session.commit()
            print(f"Admin email: {email}\nAdmin password: {pwd}")

    return app


def seed_if_empty():
    # Demo content
    if News.query.count() == 0:
        demo = News(
            title="Добро пожаловать в наш клуб!",
            body="Мы открыли двери и ждём вас на тренировках.",
            image="/static/images/hero.svg",
        )
        db.session.add(demo)
    if Schedule.query.count() == 0:
        base = [
            (0, "18:00", "Boxing", "Alex"),
            (2, "19:00", "Wrestling", "Marta"),
            (4, "20:00", "MMA", "Ivan"),
        ]
        for d, t, a, c in base:
            db.session.add(Schedule(day_of_week=d, time=t, activity=a, coach=c))
    if Trainer.query.count() == 0:
        trainers = [
            ("Alex Strong", "Мастер спорта по боксу.", "/static/images/boxing.svg"),
            ("Marta Grip", "Тренер по борьбе с 10-летним стажем.", "/static/images/wrestling.svg"),
            ("Ivan Iron", "Профессиональный боец ММА.", "/static/images/mma.svg"),
        ]
        for name, bio, photo in trainers:
            db.session.add(Trainer(name=name, bio=bio, photo=photo))

    # Seed admin if none exists
    admin = User.query.filter((User.role == 'admin') | (User.is_admin == True)).first()
    if admin is None:
        email = "admin@site.local"
        pwd = os.environ.get("ADMIN_PASSWORD") or secrets.token_urlsafe(12)
        admin_user = User(
            email=email,
            username="admin",
            role='admin',
            is_admin=True,
            is_active=True,
        )
        admin_user.set_password(pwd)
        db.session.add(admin_user)
        db.session.commit()
        print("Created admin user. Credentials:")
        print(f"  email: {email}")
        print(f"  password: {pwd}")
    else:
        db.session.commit()


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
