from flask import Flask, render_template, request, redirect, url_for, flash, session, abort
from flask_babel import Babel, gettext as _
from flask_login import LoginManager, current_user
from flask_wtf.csrf import CSRFProtect
from datetime import datetime
from config import Config
from models import db, News, Schedule, Trainer, Signup, User
from forms import LoginForm, NewsForm, ScheduleForm, SignupForm

import os
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


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Compile translations on startup
    compile_translations(app)

    # DB
    db.init_app(app)
    with app.app_context():
        db.create_all()
        seed_if_empty()

    # Auth and CSRF
    login_manager = LoginManager(app)
    login_manager.login_view = "admin_login"

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    csrf = CSRFProtect(app)

    # Admin-required decorator (403 on failure)
    def admin_required(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(403)
            if not getattr(current_user, "is_admin", False):
                abort(403)
            return view(*args, **kwargs)
        return wrapper

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

    # Routes
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

    # Admin auth
    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        form = LoginForm()
        return render_template("admin/login.html", form=form)

    @app.route("/admin/logout")
    def admin_logout():
        session.clear()
        flash(_("Вы вышли из админ-панели."))
        return redirect(url_for("home"))

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

    return app


def seed_if_empty():
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
    db.session.commit()


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
