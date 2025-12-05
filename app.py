from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    abort,
    jsonify,
    send_file,
    send_from_directory,
    current_app,
)
from flask_babel import Babel, gettext as _
from flask_login import (
    LoginManager,
    current_user,
    login_user,
    logout_user,
    login_required,
)
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash
from urllib.parse import urlparse
from datetime import datetime, timezone
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from config import Config
from models import db, News, Schedule, Trainer, Signup, User, Document, RoleChangeLog
import models as models
from forms import (
    LoginForm,
    RegisterForm,
    NewsForm,
    ScheduleForm,
    SignupForm,
    DocumentUploadForm,
    UserSearchForm,
    ProfileEditForm,
)

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
    """Lightweight, idempotent runtime migrations for the User table."""
    with app.app_context():
        engine = db.engine
        if engine.dialect.name != "sqlite":
            return
        try:
            with engine.begin() as conn:
                # user table
                cols_rows = conn.exec_driver_sql("PRAGMA table_info('user')").fetchall()
                cols = {row[1] for row in cols_rows}

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
                if "avatar_path" not in cols:
                    add_cols_sql.append("ALTER TABLE user ADD COLUMN avatar_path VARCHAR(512)")
                if "is_superadmin" not in cols:
                    add_cols_sql.append("ALTER TABLE user ADD COLUMN is_superadmin BOOLEAN")
                for stmt in add_cols_sql:
                    conn.exec_driver_sql(stmt)

                # defaults
                conn.exec_driver_sql("UPDATE user SET role = COALESCE(role, 'user')")
                conn.exec_driver_sql("UPDATE user SET is_active = COALESCE(is_active, 1)")
                conn.exec_driver_sql("UPDATE user SET created_at = COALESCE(created_at, datetime('now'))")
                conn.exec_driver_sql("UPDATE user SET is_admin = COALESCE(is_admin, 0)")
                conn.exec_driver_sql("UPDATE user SET is_superadmin = COALESCE(is_superadmin, 0)")

                # ensure admin email
                row = conn.exec_driver_sql(
                    "SELECT id FROM user "
                    "WHERE (COALESCE(is_admin,0) = 1 OR role = 'admin') "
                    "AND (email IS NULL OR email = '') LIMIT 1"
                ).fetchone()
                if row:
                    admin_id = row[0]
                    default_email = "admin@site.local"
                    exists = conn.exec_driver_sql(
                        "SELECT 1 FROM user WHERE email = ?", (default_email,)
                    ).fetchone()
                    if exists:
                        default_email = f"admin+{admin_id}@site.local"
                    conn.exec_driver_sql(
                        "UPDATE user SET email = ? WHERE id = ?",
                        (default_email, admin_id),
                    )

                # indexes
                conn.exec_driver_sql(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ux_user_email ON user(email)"
                )
                conn.exec_driver_sql(
                    "CREATE INDEX IF NOT EXISTS ix_user_role ON user(role)"
                )

                # schedule table
                try:
                    sched_cols = conn.exec_driver_sql(
                        "PRAGMA table_info('schedule')"
                    ).fetchall()
                    s_cols = {row[1] for row in sched_cols}
                    if "discipline" not in s_cols:
                        conn.exec_driver_sql(
                            "ALTER TABLE schedule ADD COLUMN discipline VARCHAR(50)"
                        )
                    if "age" not in s_cols:
                        conn.exec_driver_sql(
                            "ALTER TABLE schedule ADD COLUMN age VARCHAR(50)"
                        )
                except Exception:
                    pass
        except Exception:
            app.logger.warning("User table migration skipped or failed. Consider using Alembic.")


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Стабильный SECRET_KEY
    app.config["SECRET_KEY"] = os.environ.get(
        "SECRET_KEY",
        app.config.get("SECRET_KEY") or "wiru-dev-secret-change-me",
    )

    # Compile translations on startup
    compile_translations(app)

    # DB
    db.init_app(app)
    with app.app_context():
        db.create_all()
        run_simple_migrations(app)
        seed_if_empty()
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

    # Role-based decorators
    def role_required(*roles):
        def decorator(view):
            @wraps(view)
            def wrapper(*args, **kwargs):
                if not current_user.is_authenticated:
                    next_rel = (
                        request.full_path if request.query_string else request.path
                    )
                    return redirect(url_for("login", next=next_rel))
                # keep generic role check for other uses
                if roles and (getattr(current_user, "role", None) not in roles):
                    flash(_("Доступ запрещён"))
                    return abort(403)
                return view(*args, **kwargs)

            return wrapper

        return decorator

    def admin_required(view):
        # allow both admin and superadmin using model properties
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                next_rel = request.full_path if request.query_string else request.path
                return redirect(url_for("login", next=next_rel))
            if not getattr(current_user, "is_admin", False):
                flash(_("Доступ запрещён"))
                return abort(403)
            return view(*args, **kwargs)
        return wrapped

    def superadmin_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                next_rel = request.full_path if request.query_string else request.path
                return redirect(url_for("login", next=next_rel))
            if not bool(getattr(current_user, "is_superadmin", False)):
                flash(_("Доступ только для супер-админа"))
                return abort(403)
            return view(*args, **kwargs)
        return wrapped

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
        # 't' is a safe gettext helper to avoid Jinja i18n extension's percent-formatting.
        return dict(
            now=datetime.utcnow(),
            LANGUAGES=app.config["LANGUAGES"],
            models=models,
            config=app.config,
            t=_,
        )

    # Utilities
    def is_safe_next(target: str) -> bool:
        if not target:
            return False
        return urlparse(target).netloc == ""

    def valid_time(s: str) -> bool:
        try:
            parts = (s or "").split(":")
            if len(parts) != 2:
                return False
            h, m = int(parts[0]), int(parts[1])
            return 0 <= h <= 23 and 0 <= m <= 59
        except Exception:
            return False

    # ----------------- PUBLIC PAGES -----------------

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

    @app.route('/robots.txt')
    def robots():
        return send_from_directory('static', 'robots.txt', mimetype='text/plain')

    @app.route("/news")
    def news_list():
        news = News.query.order_by(News.created_at.desc()).all()
        return render_template(
            "news.html",
            news=news,
            title="Новости — Wiru Combat Academy, Кохтла-Ярве",
            description="Новости и события Wiru Combat Academy в Кохтла-Ярве: турниры, мероприятия, результаты.",
            og_title="Новости Wiru Combat Academy, Кохтла-Ярве",
            og_desc="Будьте в курсе спортивных событий и мероприятий академии единоборств."
        )

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
        return render_template(
            "trainers.html",
            trainers=trainers,
            title="Тренеры — Wiru Combat Academy, Кохтла-Ярве",
            description="Профессиональные тренеры по боксу и ММА в Кохтла-Ярве. Опытные наставники, инд��видуальный подход.",
            og_title="Тренерский состав Wiru Combat Academy, Кохтла-Ярве",
            og_desc="Познакомьтесь с нашими тренерами и их опытом в единоборствах."
        )

    @app.route("/contact")
    def contact():
        return render_template(
            "contact.html",
            title="Контакты — Wiru Combat Academy, Кохтла-Ярве",
            description="Контакты Wiru Combat Academy в Кохтла-Ярве: адрес зала, телефон, электронная почта и форма обратной связи.",
            og_title="Контакты Wiru Combat Academy, Кохтла-Ярве",
            og_desc="Свяжитесь с нами, чтобы записаться на тренировку или задать вопрос."
        )

    @app.route("/send-message", methods=["POST"])
    def send_message():
        name = request.form.get("name")
        email = request.form.get("email")
        message = request.form.get("message")

        if not (name and email and message):
            flash(_("Пожалуйста, заполните все поля."), "error")
            return redirect(url_for("home"))

        body = f"""Новое сообщение с сайта Wiru Combat Academy

    Имя: {name}
    Email: {email}

    Сообщение:
{message}
"""

        api_key = current_app.config.get("SENDGRID_API_KEY")
        mail_from = current_app.config.get("MAIL_FROM")
        mail_to = current_app.config.get("MAIL_TO")

        if not (api_key and mail_from and mail_to):
            flash(_("Ошибка: почта не настроена на сервере."), "error")
            return redirect(url_for("home"))

        try:
            msg = Mail(
                from_email=mail_from,
                to_emails=mail_to,
                subject="Сообщение с сайта Wiru Combat Academy",
                plain_text_content=body,
            )

            sg = SendGridAPIClient(api_key)
            response = sg.send(msg)

            if 200 <= response.status_code < 300:
                flash(_("Спасибо! Ваше сообщение отправлено."), "success")
            else:
                print("SendGrid error:", response.status_code, response.body)
                flash(_("Произошла ошибка при отправке сообщения."), "error")

        except Exception as e:
            print("Mail error:", e)
            flash(_("Произошла ошибка при отправке сообщения."), "error")

        return redirect(url_for("home"))

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

    # ----------------- AUTH -----------------

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("profile"))

        form = LoginForm()

        if form.validate_on_submit():
            print("LOGIN: form.validate_on_submit() = True", flush=True)
            print("LOGIN: ident =", repr(form.email.data), flush=True)

            ident = (form.email.data or "").strip()
            user = User.query.filter_by(email=ident.lower()).first()
            if not user:
                user = User.query.filter_by(username=ident).first()

            print(
                "LOGIN: user found =",
                bool(user),
                "id=",
                getattr(user, "id", None),
                flush=True,
            )

            if user and user.is_active and user.check_password(form.password.data):
                print("LOGIN: password OK, logging in", flush=True)
                login_user(user, remember=form.remember.data)
                flash(_("Добро пожаловать!"))
                nxt = request.args.get("next")
                print("LOGIN: next =", repr(nxt), flush=True)
                if nxt and is_safe_next(nxt) and not nxt.startswith("/admin"):
                    return redirect(nxt)
                return redirect(url_for("profile"))

            print("LOGIN: invalid credentials or inactive", flush=True)
            flash(_("Неверный email/имя пользователя или пароль"))
        else:
            if request.method == "POST":
                print(
                    "LOGIN: validate_on_submit() = False, errors:",
                    form.errors,
                    flush=True,
                )

        return render_template("auth/login.html", form=form)

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if current_user.is_authenticated:
            return redirect(url_for("profile"))

        form = RegisterForm()

        if form.validate_on_submit():
            email = (form.email.data or "").lower().strip()
            if User.query.filter_by(email=email).first():
                flash(_("Пользователь с таким email уже существует"))
                return render_template("auth/register.html", form=form)

            username = (form.username.data or "").strip() or None
            user = User(email=email, username=username, role="user", is_active=True)
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

    # ----------------- ADMIN LOGIN & DASHBOARD -----------------

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        if current_user.is_authenticated and getattr(current_user, "is_admin", False):
            return redirect(url_for("profile"))
        form = LoginForm()
        if form.validate_on_submit():
            ident = (form.email.data or "").strip()
            user = User.query.filter_by(email=ident.lower()).first()
            if not user:
                user = User.query.filter_by(username=ident).first()
            if (
                user
                and getattr(user, "is_admin", False)
                and user.is_active
                and user.check_password(form.password.data)
            ):
                login_user(user, remember=form.remember.data)
                flash(_("Добро пожаловать в админ-панель!"))
                return redirect(url_for("profile"))
            flash(_("Неверный email/имя пользователя или пароль"))
        return render_template("admin/login.html", form=form)

    @app.route("/admin")
    @admin_required
    def admin_dashboard():
        return render_template(
            "admin/dashboard.html",
            news_count=News.query.count(),
            signup_count=Signup.query.count(),
        )

    # ----------------- ADMIN: NEWS -----------------

    @app.route("/admin/news/add", methods=["GET", "POST"])
    @admin_required
    def admin_add_news():
        form = NewsForm()
        if form.validate_on_submit():
            n = News(
                title=form.title.data,
                body=form.body.data,
                image=(form.image.data or "").strip() or None,
            )
            db.session.add(n)
            db.session.commit()
            flash(_("Новость добавлена."))
            return redirect(url_for("admin_news_list"))
        return render_template(
            "admin/news_form.html", form=form, page_title=_("Добавить новость")
        )

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
        return render_template(
            "admin/news_form.html",
            form=form,
            page_title=_("Редактировать новость"),
            item=item,
        )

    @app.route("/admin/news/delete/<int:news_id>", methods=["POST"])
    @admin_required
    def admin_delete_news(news_id):
        item = News.query.get_or_404(news_id)
        db.session.delete(item)
        db.session.commit()
        flash(_("Новость удалена."))
        return redirect(url_for("admin_news_list"))

    # ----------------- ADMIN: SCHEDULE -----------------

    @app.route("/admin/schedule", methods=["GET", "POST"])
    @admin_required
    def admin_edit_schedule():
        form = ScheduleForm()
        if form.validate_on_submit():
            disc = form.discipline.data if hasattr(form, "discipline") else None
            labels = {"boxing": "Boxing", "wrestling": "Wrestling", "mma": "MMA"}
            item = Schedule(
                day_of_week=form.day_of_week.data,
                time=form.time.data,
                activity=labels.get(disc),
                discipline=disc,
                coach=form.coach.data,
            )
            db.session.add(item)
            db.session.commit()
            flash(_("Тренировка добавлена в расписание."))
            return redirect(url_for("schedule_page"))
        schedule = Schedule.query.order_by(
            Schedule.day_of_week.asc(), Schedule.time.asc()
        ).all()
        return render_template("admin/edit_schedule.html", form=form, schedule=schedule)

    @app.route("/admin/schedule/data")
    @admin_required
    def admin_schedule_data():
        items = Schedule.query.order_by(
            Schedule.day_of_week.asc(), Schedule.time.asc()
        ).all()
        return jsonify(
            [
                {
                    "id": i.id,
                    "day_of_week": i.day_of_week,
                    "time": i.time,
                    "activity": i.activity,
                    "discipline": i.discipline,
                    "coach": i.coach,
                    "age": i.age,
                }
                for i in items
            ]
        )

    @app.route("/admin/schedule/item", methods=["POST"])
    @admin_required
    def admin_schedule_create():
        try:
            data = request.get_json(silent=True) or {}
        except Exception:
            data = {}
        day = data.get("day_of_week")
        time = (data.get("time") or "").strip()
        activity = (data.get("activity") or "").strip()
        coach = (data.get("coach") or "").strip() or None
        discipline = (data.get("discipline") or "").strip().lower() or None
        age = (data.get("age") or "").strip() or None

        app.logger.info(
            f"Schedule create request: day={day}, time={time}, discipline={discipline}, activity={activity}, age={age}"
        )

        if not isinstance(day, int) or day < 0 or day > 6:
            app.logger.error(f"Invalid day_of_week: {day}")
            return jsonify({"error": "invalid day_of_week"}), 400
        if not time or not valid_time(time):
            app.logger.error(f"Invalid time: {time}")
            return jsonify({"error": "invalid time"}), 400
        if not discipline or discipline not in {"boxing", "wrestling", "mma", "other"}:
            app.logger.error(f"Invalid discipline: {discipline}")
            return jsonify({"error": "invalid discipline"}), 400

        labels = {
            "boxing": "Boxing",
            "wrestling": "Wrestling",
            "mma": "MMA",
            "other": "Other",
        }
        if discipline == "other":
            if not activity:
                app.logger.error(
                    f"Activity required for 'other' discipline but got: {activity}"
                )
                return (
                    jsonify({"error": "activity required for 'other' discipline"}),
                    400,
                )
            base = activity
        else:
            base = labels.get(discipline)
        activity = (base or "Other") + ((" " + age) if age else "")

        existing = Schedule.query.filter_by(day_of_week=day, time=time).first()
        if existing:
            return (
                jsonify(
                    {"error": "schedule for this day and time already exists"}
                ),
                400,
            )

        item = Schedule(
            day_of_week=day,
            time=time,
            activity=activity,
            coach=coach,
            discipline=discipline,
            age=age,
        )
        db.session.add(item)
        db.session.commit()
        return jsonify(
            {
                "ok": True,
                "item": {
                    "id": item.id,
                    "day_of_week": item.day_of_week,
                    "time": item.time,
                    "activity": item.activity,
                    "discipline": item.discipline,
                    "coach": item.coach,
                },
            }
        )

    @app.route("/admin/schedule/item/<int:item_id>", methods=["PUT", "PATCH"])
    @admin_required
    def admin_schedule_update(item_id):
        item = Schedule.query.get_or_404(item_id)
        try:
            data = request.get_json(silent=True) or {}
        except Exception:
            data = {}
        prev_age = item.age
        prev_activity = item.activity

        if "day_of_week" in data:
            day = data.get("day_of_week")
            if not isinstance(day, int) or day < 0 or day > 6:
                return jsonify({"error": "invalid day_of_week"}), 400
            item.day_of_week = day
        if "time" in data:
            time = (data.get("time") or "").strip()
            if not time or not valid_time(time):
                return jsonify({"error": "invalid time"}), 400
            item.time = time
        if "activity" in data:
            activity = (data.get("activity") or "").strip()
            if not activity:
                return jsonify({"error": "activity required"}), 400
            item.activity = activity
        if "coach" in data:
            coach = (data.get("coach") or "").strip() or None
            item.coach = coach
        if "discipline" in data:
            disc = (data.get("discipline") or "").strip().lower() or None
            if not disc or disc not in {"boxing", "wrestling", "mma", "other"}:
                return jsonify({"error": "invalid discipline"}), 400
            item.discipline = disc
        if "age" in data:
            item.age = (data.get("age") or "").strip() or None

        if "discipline" in data or "age" in data:
            labels = {"boxing": "Boxing", "wrestling": "Wrestling", "mma": "MMA"}
            if item.discipline == "other":
                custom_base = (data.get("activity") or "").strip()
                if not custom_base:
                    txt = prev_activity or item.activity or ""
                    if (
                        prev_age
                        and isinstance(prev_age, str)
                        and txt.endswith(" " + prev_age)
                    ):
                        custom_base = txt[: -(len(prev_age) + 1)]
                    else:
                        parts = txt.rsplit(" ", 1)
                        custom_base = parts[0] if len(parts) == 2 else txt
                base = custom_base or "Other"
            else:
                base = labels.get(item.discipline) or (
                    item.activity.split(" ")[0] if item.activity else "Training"
                )
            item.activity = base + ((" " + item.age) if item.age else "")

        db.session.commit()
        return jsonify({"ok": True})

    @app.route("/admin/schedule/item/<int:item_id>", methods=["DELETE"])
    @admin_required
    def admin_schedule_delete(item_id):
        item = Schedule.query.get_or_404(item_id)
        db.session.delete(item)
        db.session.commit()
        return jsonify({"ok": True})

    @app.route("/admin/schedule/copy_day", methods=["POST"])
    @admin_required
    def admin_schedule_copy_day():
        try:
            data = request.get_json(silent=True) or {}
        except Exception:
            data = {}
        src = data.get("source_day")
        dst = data.get("target_day")
        replace = bool(data.get("replace"))
        if not all(
            isinstance(x, int) and 0 <= x <= 6 for x in [src, dst]
        ):
            return jsonify({"error": "invalid day values"}), 400
        if replace:
            Schedule.query.filter_by(day_of_week=dst).delete()
        src_items = Schedule.query.filter_by(day_of_week=src).all()
        created = 0
        for it in src_items:
            if not replace:
                existing = Schedule.query.filter_by(
                    day_of_week=dst, time=it.time
                ).first()
                if existing:
                    continue
            db.session.add(
                Schedule(
                    day_of_week=dst,
                    time=it.time,
                    activity=it.activity,
                    discipline=it.discipline,
                    coach=it.coach,
                    age=it.age,
                )
            )
            created += 1
        db.session.commit()
        return jsonify({"ok": True, "created": created})

    # ----------------- ADMIN: USERS -----------------

    @app.route("/admin/users")
    @admin_required
    def admin_users():
        form = UserSearchForm(request.args)
        q = (form.q.data or "").strip() if form else ""
        query = User.query
        if q:
            like = f"%{q}%"
            query = query.filter(
                (User.email.ilike(like))
                | (User.username.ilike(like))
                | (User.full_name.ilike(like))
            )
        users = query.order_by(User.created_at.desc()).limit(200).all()
        return render_template("admin/users_list.html", users=users, form=form, q=q)

    @app.route("/admin/users/<int:user_id>")
    @admin_required
    def admin_user_detail(user_id):
        u = User.query.get_or_404(user_id)
        subs = []
        pays = []
        docs = u.documents.order_by(Document.uploaded_at.desc()).all()
        role_logs = (
            RoleChangeLog.query.filter_by(target_id=u.id)
            .order_by(RoleChangeLog.created_at.desc())
            .limit(10)
            .all()
        )
        return render_template(
            "admin/user_detail.html", user=u, subs=subs, payments=pays, docs=docs, role_logs=role_logs
        )

    @app.route("/admin/users/<int:user_id>/make-admin", methods=["POST"])
    @superadmin_required
    def admin_make_admin(user_id):
        u = User.query.get_or_404(user_id)
        if getattr(u, "is_superadmin", False):
            flash(_("Нельзя менять роль супер-админа."), "error")
            return redirect(url_for("admin_user_detail", user_id=user_id))
        old_role = u.role
        u.role = "admin"
        # keep legacy flag in sync
        try:
            u.is_admin = True
        except Exception:
            pass
        # audit log
        try:
            db.session.add(
                RoleChangeLog(
                    actor_id=current_user.id,
                    target_id=u.id,
                    old_role=old_role,
                    new_role=u.role,
                )
            )
        except Exception:
            pass
        db.session.commit()
        flash(_("Пользователь назначен администратором."), "success")
        return redirect(url_for("admin_user_detail", user_id=user_id))

    @app.route("/admin/users/<int:user_id>/remove-admin", methods=["POST"])
    @superadmin_required
    def admin_remove_admin(user_id):
        u = User.query.get_or_404(user_id)
        # явный запрет самопонижения супер-админа с собственным сообщением
        if current_user.is_superadmin and current_user.id == u.id:
            flash(_("Супер-админ не может снять роль с себя."), "error")
            return redirect(url_for("admin_user_detail", user_id=user_id))
        if getattr(u, "is_superadmin", False):
            flash(_("Нельзя менять роль супер-админа."), "error")
            return redirect(url_for("admin_user_detail", user_id=user_id))
        old_role = u.role
        u.role = "user"
        try:
            u.is_admin = False
        except Exception:
            pass
        # audit log
        try:
            db.session.add(
                RoleChangeLog(
                    actor_id=current_user.id,
                    target_id=u.id,
                    old_role=old_role,
                    new_role=u.role,
                )
            )
        except Exception:
            pass
        db.session.commit()
        flash(_("Роль администратора снята."), "success")
        return redirect(url_for("admin_user_detail", user_id=user_id))

    # ----------------- PROFILE -----------------

    @app.route("/profile", methods=["GET", "POST"])
    @login_required
    def profile():
        # Сейчас просто редиректим на overview
        return redirect(url_for("profile_overview"))

    @app.route("/profile/overview")
    @login_required
    def profile_overview():
        last_sub = None
        try:
            docs = (
                current_user.documents.order_by(
                    Document.uploaded_at.desc()
                )
                .limit(5)
                .all()
            )
        except Exception:
            docs = []
        return render_template(
            "profile/profile_overview.html",
            last_sub=last_sub,
            docs=docs,
        )

    @app.route("/profile/edit", methods=["GET", "POST"])
    @login_required
    def profile_edit():
        form = ProfileEditForm(obj=current_user)
        action = request.form.get("action") if request.method == "POST" else None

        # Change password
        if action == "change_password":
            current_pwd = request.form.get("current_password") or ""
            new_pwd = request.form.get("new_password") or ""
            confirm_pwd = request.form.get("confirm_password") or ""
            if not current_user.check_password(current_pwd):
                flash(_("Текущий пароль неверен."), "error")
                return redirect(url_for("profile_edit"))
            if len(new_pwd) < 8:
                flash(_("Новый пароль слишком короткий."), "error")
                return redirect(url_for("profile_edit"))
            if new_pwd != confirm_pwd:
                flash(_("Пароли не совпадают."), "error")
                return redirect(url_for("profile_edit"))
            current_user.set_password(new_pwd)
            db.session.commit()
            flash(_("Пароль успешно изменён."), "success")
            return redirect(url_for("profile_edit"))

        # Main profile form
        if form.validate_on_submit():
            new_username = (form.username.data or "").strip() or None
            if new_username != current_user.username:
                if new_username and User.query.filter(
                    User.username == new_username, User.id != current_user.id
                ).first():
                    flash(_("Это имя пользователя уже занято."), "error")
                    return redirect(url_for("profile_edit"))
                current_user.username = new_username

            current_user.full_name = (form.full_name.data or "").strip() or None

            if getattr(current_user, "role", "user") == "admin":
                current_user.level = (form.level.data or "").strip() or None
                current_user.group_name = (
                    form.group_name.data or ""
                ).strip() or None

            # Avatar upload
            try:
                f = form.avatar.data
            except Exception:
                f = None

            if f and getattr(f, "filename", None):
                filename = f.filename or ""
                ext = (
                    filename.rsplit(".", 1)[-1].lower()
                    if "." in filename
                    else ""
                )
                allowed = set(
                    app.config.get(
                        "ALLOWED_UPLOAD_EXTENSIONS",
                        {"jpg", "jpeg", "png"},
                    )
                )
                if ext not in allowed:
                    flash(_("Недопустимый тип файла"), "error")
                    return redirect(url_for("profile_edit"))
                max_bytes = int(app.config.get("MAX_UPLOAD_MB", 15)) * 1024 * 1024
                content_len = request.content_length or 0
                if content_len and content_len > max_bytes + 8192:
                    flash(_("Файл слишком большой"), "error")
                    return redirect(url_for("profile_edit"))
                import uuid

                user_dir = os.path.join(
                    app.config.get("UPLOAD_DIR", "./uploads"),
                    str(current_user.id),
                )
                os.makedirs(user_dir, exist_ok=True)
                stored_name = f"avatar_{uuid.uuid4().hex}.{ext}"
                stored_path = os.path.join(user_dir, stored_name)
                try:
                    f.save(stored_path)
                    size_bytes = os.path.getsize(stored_path)
                    if size_bytes > max_bytes:
                        os.remove(stored_path)
                        flash(_("Файл слишком большой"), "error")
                        return redirect(url_for("profile_edit"))
                    current_user.avatar_path = stored_path
                except Exception:
                    try:
                        if os.path.exists(stored_path):
                            os.remove(stored_path)
                    except Exception:
                        pass
                    flash(_("Ошибка сохранения файла"), "error")
                    return redirect(url_for("profile_edit"))

            db.session.commit()
            flash(_("Профиль обновлён."), "success")
            return redirect(url_for("profile_edit", cleared=1))
        elif request.method == "POST":
            flash(_("Ошибка валидации формы."), "error")

        return render_template("profile/profile_edit.html", form=form)

    @app.route("/profile/avatar")
    @login_required
    def profile_avatar():
        path = current_user.avatar_path or ""
        if not path:
            abort(404)
        base = os.path.realpath(app.config.get("UPLOAD_DIR", "./uploads"))
        real = os.path.realpath(path)
        if not real.startswith(base + os.sep) and real != base:
            abort(403)
        try:
            return send_file(real)
        except Exception:
            abort(404)

    # ----------------- DOCUMENTS (USER & ADMIN) -----------------

    @app.route("/documents/<int:doc_id>/download")
    @login_required
    def document_download(doc_id):
        doc = Document.query.get_or_404(doc_id)
        if doc.user_id != current_user.id and getattr(
            current_user, "role", "user"
        ) != "admin":
            abort(403)
        base = os.path.realpath(app.config.get("UPLOAD_DIR", "./uploads"))
        path = os.path.realpath(doc.stored_path or "")
        if not path.startswith(base + os.sep) and path != base:
            abort(403)
        try:
            return send_file(
                path,
                as_attachment=True,
                download_name=doc.filename or os.path.basename(path),
            )
        except Exception:
            abort(404)

    @app.route("/documents/<int:doc_id>/view")
    @login_required
    def document_view(doc_id):
        doc = Document.query.get_or_404(doc_id)
        if doc.user_id != current_user.id and getattr(
            current_user, "role", "user"
        ) != "admin":
            abort(403)
        base = os.path.realpath(app.config.get("UPLOAD_DIR", "./uploads"))
        path = os.path.realpath(doc.stored_path or "")
        if not path.startswith(base + os.sep) and path != base:
            abort(403)
        try:
            return send_file(
                path,
                as_attachment=False,
                download_name=doc.filename or os.path.basename(path),
                mimetype=doc.mime or None,
            )
        except Exception:
            abort(404)

    @app.route("/documents", methods=["GET"])
    @login_required
    def documents():
        form = DocumentUploadForm()
        try:
            docs = current_user.documents.order_by(
                Document.uploaded_at.desc()
            ).all()
        except Exception:
            docs = []
        return render_template("profile/documents.html", form=form, docs=docs)

    @app.route("/documents/upload", methods=["POST"])
    @login_required
    def documents_upload():
        form = DocumentUploadForm()
        if not form.validate_on_submit():
            flash(_("Ошибка загрузки файла"), "error")
            return redirect(url_for("documents"))
        f = form.file.data
        filename = f.filename or ""
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        allowed = set(
            app.config.get(
                "ALLOWED_UPLOAD_EXTENSIONS",
                {"pdf", "jpg", "jpeg", "png"},
            )
        )
        if ext not in allowed:
            flash(_("Недопустимый тип файла"), "error")
            return redirect(url_for("documents"))
        max_bytes = int(app.config.get("MAX_UPLOAD_MB", 15)) * 1024 * 1024
        content_len = request.content_length or 0
        if content_len and content_len > max_bytes + 8192:
            flash(_("Файл слишком большой"), "error")
            return redirect(url_for("documents"))
        import uuid

        user_dir = os.path.join(
            app.config.get("UPLOAD_DIR", "./uploads"), str(current_user.id)
        )
        os.makedirs(user_dir, exist_ok=True)
        stored_name = f"{uuid.uuid4().hex}.{ext}"
        stored_path = os.path.join(user_dir, stored_name)
        try:
            f.save(stored_path)
            size_bytes = os.path.getsize(stored_path)
            if size_bytes > max_bytes:
                os.remove(stored_path)
                flash(_("Файл слишком большой"), "error")
                return redirect(url_for("documents"))
        except Exception:
            try:
                if os.path.exists(stored_path):
                    os.remove(stored_path)
            except Exception:
                pass
            flash(_("Ошибка сохранения файла"), "error")
            return redirect(url_for("documents"))
        doc = Document(
            user_id=current_user.id,
            filename=filename,
            stored_path=stored_path,
            mime=getattr(f, "mimetype", None),
            size_bytes=size_bytes,
            note=(form.note.data or "").strip() or None,
        )
        db.session.add(doc)
        db.session.commit()
        flash(_("Документ загружен"), "success")
        return redirect(url_for("documents"))

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
            query = query.filter(
                (Document.filename.ilike(like))
                | (Document.note.ilike(like))
            )
        docs = query.order_by(Document.uploaded_at.desc()).limit(200).all()
        return render_template(
            "admin/documents_list.html", docs=docs, user_id=user_id, q=q
        )

    @app.route("/admin/documents/<int:doc_id>/download")
    @admin_required
    def admin_document_download(doc_id):
        doc = Document.query.get_or_404(doc_id)
        base = os.path.realpath(app.config.get("UPLOAD_DIR", "./uploads"))
        path = os.path.realpath(doc.stored_path or "")
        if not path.startswith(base + os.sep) and path != base:
            abort(403)
        try:
            return send_file(
                path,
                as_attachment=True,
                download_name=doc.filename or os.path.basename(path),
            )
        except Exception:
            abort(404)

    # ----------------- ERRORS & CLI -----------------

    @app.errorhandler(403)
    def forbidden(_e):
        return render_template("errors/403.html"), 403

    @app.cli.command("create-admin")
    def create_admin_cmd():
        """Create superuser admin@site.local with password from ADMIN_PASSWORD or generated."""
        with app.app_context():
            email = "admin@site.local"
            user = User.query.filter_by(email=email).first()
            pwd = os.environ.get("ADMIN_PASSWORD") or secrets.token_urlsafe(12)
            if not user:
                user = User(
                    email=email,
                    username="admin",
                    role="admin",
                    is_active=True,
                    is_admin=True,
                )
                user.set_password(pwd)
                db.session.add(user)
            else:
                user.role = "admin"
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
        # Понедельник
        db.session.add(
            Schedule(
                day_of_week=0,
                time="16:00",
                activity="Борьба 6–12 лет",
                discipline="wrestling",
                age="6–12a.",
            )
        )
        db.session.add(
            Schedule(
                day_of_week=0,
                time="17:00",
                activity="Бокс 8–12 лет",
                discipline="boxing",
                age="8–12a.",
            )
        )
        db.session.add(
            Schedule(
                day_of_week=0,
                time="17:00",
                activity="Борьба 13+ лет",
                discipline="wrestling",
                age="13+ a.",
            )
        )
        db.session.add(
            Schedule(
                day_of_week=0,
                time="18:00",
                activity="ММА",
                discipline="mma",
            )
        )
        db.session.add(
            Schedule(
                day_of_week=0,
                time="18:30",
                activity="Бокс Молодежь и взрослые",
                discipline="boxing",
                age="Noored & täiskasvanud",
            )
        )
        db.session.add(
            Schedule(
                day_of_week=0,
                time="19:00",
                activity="Общая физическая/Круговая тренировка (Женщины)",
                discipline="other",
                age="(Naised)",
            )
        )

        # Вторник
        db.session.add(
            Schedule(
                day_of_week=1,
                time="17:15",
                activity="Бокс 5–7 лет",
                discipline="boxing",
                age="5–7a",
            )
        )
        db.session.add(
            Schedule(
                day_of_week=1,
                time="18:00",
                activity="ММА",
                discipline="mma",
            )
        )
        db.session.add(
            Schedule(
                day_of_week=1,
                time="18:30",
                activity="Бокс Молодежь и взрослые",
                discipline="boxing",
                age="Noored & täiskasvanud",
            )
        )

        # Среда
        db.session.add(
            Schedule(
                day_of_week=2,
                time="16:00",
                activity="Борьба 6–12 лет",
                discipline="wrestling",
                age="6–12a",
            )
        )
        db.session.add(
            Schedule(
                day_of_week=2,
                time="17:00",
                activity="Бокс 8–12 лет",
                discipline="boxing",
                age="8–12a.",
            )
        )
        db.session.add(
            Schedule(
                day_of_week=2,
                time="17:00",
                activity="Борьба 13+ лет",
                discipline="wrestling",
                age="13-99a",
            )
        )
        db.session.add(
            Schedule(
                day_of_week=2,
                time="18:00",
                activity="ММА",
                discipline="mma",
            )
        )
        db.session.add(
            Schedule(
                day_of_week=2,
                time="18:30",
                activity="Бокс Молодежь и взрослые",
                discipline="boxing",
                age="Noored & täiskasvanud",
            )
        )
        db.session.add(
            Schedule(
                day_of_week=2,
                time="19:00",
                activity="Общая физическая/Круговая тренировка (Женщины)",
                discipline="other",
                age="(Naised)",
            )
        )

        # Четверг
        db.session.add(
            Schedule(
                day_of_week=3,
                time="17:15",
                activity="Бокс 5–7 лет",
                discipline="boxing",
                age="5–7a",
            )
        )
        db.session.add(
            Schedule(
                day_of_week=3,
                time="18:00",
                activity="ММА",
                discipline="mma",
            )
        )
        db.session.add(
            Schedule(
                day_of_week=3,
                time="18:30",
                activity="Бокс Молодежь и взрослые",
                discipline="boxing",
                age="Noored & täiskasvanud",
            )
        )

        # Пятница
        db.session.add(
            Schedule(
                day_of_week=4,
                time="17:00",
                activity="Борьба 13+ лет",
                discipline="wrestling",
                age="13+ a.",
            )
        )
        db.session.add(
            Schedule(
                day_of_week=4,
                time="18:00",
                activity="ММА",
                discipline="mma",
            )
        )
        db.session.add(
            Schedule(
                day_of_week=4,
                time="18:30",
                activity="Бокс Молодежь и взрослые",
                discipline="boxing",
                age="Noored & täiskasvanud",
            )
        )
        db.session.add(
            Schedule(
                day_of_week=4,
                time="19:00",
                activity="Общая физическая/Круговая тренировка (Женщины)",
                discipline="other",
                age="(Naised)",
            )
        )

        # Суббота
        db.session.add(
            Schedule(
                day_of_week=5,
                time="12:00",
                activity="ММА",
                discipline="mma",
            )
        )

        # Доп. блоки (как у тебя были)
        db.session.add(
            Schedule(
                day_of_week=1,
                time="17:15",
                activity="Бокс 5-7 лет",
                discipline="boxing",
                age="5-7 лет",
            )
        )
        db.session.add(
            Schedule(
                day_of_week=3,
                time="17:15",
                activity="Бокс 5-7 лет",
                discipline="boxing",
                age="5-7 лет",
            )
        )
        db.session.add(
            Schedule(
                day_of_week=0,
                time="17:00",
                activity="Бокс 8-12 лет",
                discipline="boxing",
                age="8-12 лет",
            )
        )
        db.session.add(
            Schedule(
                day_of_week=2,
                time="17:00",
                activity="Бокс 8-12 лет",
                discipline="boxing",
                age="8-12 лет",
            )
        )
        for d in range(0, 5):
            db.session.add(
                Schedule(
                    day_of_week=d,
                    time="18:30",
                    activity="Бокс ��олодежь и взрослые",
                    discipline="boxing",
                    age="Молодежь и взрослые",
                )
            )

        db.session.add(
            Schedule(
                day_of_week=0,
                time="16:00",
                activity="Борьба 6-12 лет",
                discipline="wrestling",
                age="6-12 лет",
            )
        )
        db.session.add(
            Schedule(
                day_of_week=2,
                time="16:00",
                activity="Борьба 6-12 лет",
                discipline="wrestling",
                age="6-12 лет",
            )
        )
        for d in [0, 2, 4]:
            db.session.add(
                Schedule(
                    day_of_week=d,
                    time="17:00",
                    activity="Борьба 13+",
                    discipline="wrestling",
                    age="13+",
                )
            )

        for d in range(0, 5):
            db.session.add(
                Schedule(
                    day_of_week=d,
                    time="18:00",
                    activity="ММА",
                    discipline="mma",
                )
            )
        db.session.add(
            Schedule(
                day_of_week=5,
                time="12:00",
                activity="ММА",
                discipline="mma",
            )
        )

        for d in [0, 2, 4]:
            db.session.add(
                Schedule(
                    day_of_week=d,
                    time="19:00",
                    activity="Общая физическая/Круговая тренировка (Женщины)",
                    discipline="other",
                )
            )

    if Trainer.query.count() == 0:
        trainers = [
            ("Alex Strong", "Мастер спорта по боксу.", "/static/images/boxing.svg"),
            ("Marta Grip", "Тренер по борьбе с 10-летним стажем.", "/static/images/wrestling.svg"),
            ("Ivan Iron", "Профессиональный боец ММА.", "/static/images/mma.svg"),
        ]
        for name, bio, photo in trainers:
            db.session.add(Trainer(name=name, bio=bio, photo=photo))

    # Superadmin seeding
    superadmin = User.query.filter(User.is_superadmin == True).first()
    if superadmin is None:
        superadmin_email = os.environ.get("SUPERADMIN_EMAIL")
        pwd = os.environ.get("ADMIN_PASSWORD")
        if superadmin_email and pwd:
            su = User(
                email=superadmin_email.strip().lower(),
                username="superadmin",
                role="superadmin",
                is_superadmin=True,
                is_active=True,
            )
            su.set_password(pwd)
            db.session.add(su)
            db.session.commit()
            print("Created superadmin user. Credentials:")
            print(f"  email: {superadmin_email}")
            print("  password: [from ADMIN_PASSWORD env]")
        else:
            print("Superadmin not created: set SUPERADMIN_EMAIL and ADMIN_PASSWORD environment variables.")
            db.session.commit()
    else:
        db.session.commit()


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
