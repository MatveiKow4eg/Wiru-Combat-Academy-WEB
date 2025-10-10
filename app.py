from flask import Flask, render_template, request, redirect, url_for, flash, session, abort
from flask_babel import Babel, gettext as _
from flask_login import LoginManager, current_user, login_user, logout_user, login_required
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash
from urllib.parse import urlparse
from datetime import datetime
from config import Config
from models import db, News, Schedule, Trainer, Signup, User
from forms import LoginForm, RegisterForm, NewsForm, ScheduleForm, SignupForm

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

                # Add columns if missing (NULL allowed initially for safety)
                if "email" not in cols:
                    conn.exec_driver_sql("ALTER TABLE user ADD COLUMN email VARCHAR(255)")
                if "role" not in cols:
                    conn.exec_driver_sql("ALTER TABLE user ADD COLUMN role VARCHAR(10)")
                if "is_active" not in cols:
                    conn.exec_driver_sql("ALTER TABLE user ADD COLUMN is_active BOOLEAN")
                if "created_at" not in cols:
                    conn.exec_driver_sql("ALTER TABLE user ADD COLUMN created_at DATETIME")

                # Backfill defaults
                conn.exec_driver_sql("UPDATE user SET role = COALESCE(role, 'user')")
                conn.exec_driver_sql("UPDATE user SET is_active = COALESCE(is_active, 1)")
                conn.exec_driver_sql("UPDATE user SET created_at = COALESCE(created_at, datetime('now'))")

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

                # Create indexes
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
        return dict(now=datetime.utcnow(), LANGUAGES=app.config["LANGUAGES"])

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
            # already logged in: route by role
            return redirect(url_for("admin_dashboard" if current_user.role == 'admin' else "profile"))
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
                if nxt and is_safe_next(nxt):
                    return redirect(nxt)
                if user.role == 'admin':
                    return redirect(url_for("admin_dashboard"))
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
            return redirect(url_for("admin_dashboard"))
        form = LoginForm()
        if form.validate_on_submit():
            ident = (form.email.data or '').strip()
            user = User.query.filter_by(email=ident.lower()).first()
            if not user:
                user = User.query.filter_by(username=ident).first()
            if user and user.role == 'admin' and user.is_active and user.check_password(form.password.data):
                login_user(user, remember=form.remember.data)
                flash(_("Добро пожаловать в админ-панель!"))
                nxt = request.args.get("next")
                if nxt and is_safe_next(nxt):
                    return redirect(nxt)
                return redirect(url_for("admin_dashboard"))
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
            if len(new_pwd) < 6:
                flash(_("Новый пароль слишком коротк��й."), 'error')
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

        return render_template("profile.html")

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
