from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_babel import Babel, gettext as _
from datetime import datetime
from config import Config
from models import db, News, Schedule, Trainer, Signup
from forms import LoginForm, NewsForm, ScheduleForm, SignupForm

import os
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
    def is_admin():
        return session.get("is_admin", False)

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        if is_admin():
            return redirect(url_for("admin_dashboard"))
        form = LoginForm()
        if form.validate_on_submit():
            if (
                form.username.data == app.config["ADMIN_USERNAME"]
                and form.password.data == app.config["ADMIN_PASSWORD"]
            ):
                session["is_admin"] = True
                flash(_("Добро пожаловать в админ-панель!"))
                return redirect(url_for("admin_dashboard"))
            flash(_("Неверный логин или пароль."))
        return render_template("admin/login.html", form=form)

    @app.route("/admin/logout")
    def admin_logout():
        session.clear()
        flash(_("Вы вышли из админ-панели."))
        return redirect(url_for("home"))

    def admin_required():
        if not is_admin():
            flash(_("Требуется авторизация администратора."))
            return False
        return True

    @app.route("/admin")
    def admin_dashboard():
        if not admin_required():
            return redirect(url_for("admin_login"))
        return render_template(
            "admin/dashboard.html",
            news_count=News.query.count(),
            signup_count=Signup.query.count(),
        )

    @app.route("/admin/news/add", methods=["GET", "POST"])
    def admin_add_news():
        if not admin_required():
            return redirect(url_for("admin_login"))
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
            return redirect(url_for("news_list"))
        return render_template("admin/add_news.html", form=form)

    @app.route("/admin/schedule", methods=["GET", "POST"])
    def admin_edit_schedule():
        if not admin_required():
            return redirect(url_for("admin_login"))
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
