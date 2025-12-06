# Sports Club (Flask)

Полностью рабочий сайт спортивного клуба на Flask (Jinja2, SQLAlchemy, Flask-Babel, WTForms) с адаптивным дизайном.

## Запуск локально

```bash
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
export FLASK_APP=app.py  # Windows: set FLASK_APP=app.py
flask run
```

По умолчанию база SQLite создастся как `sports_club.db`. Админ-логин/пароль: `admin` / `admin123` (перенастройте через переменные окружения).

## Структура
- `app.py` — маршруты, i18n, админ.
- `models.py` — модели: News, Schedule, Trainer, User, Signup.
- `forms.py` — формы (вход, новости, расписание, заявка).
- `templates/` — Jinja2 шаблоны (включая `templates/admin/`).
- `static/` — стили, js, изображения (тёмная тема).
- `translations/` — каталоги для RU/EN/ET.
- `TZ/` — исходные файлы ТЗ, которые соблюдены в проекте.

## Переводы (Flask-Babel)

В шаблонах и коде строки обёрнуты в `_()`. Чтобы активировать переводы:

```bash
# создать/обновить pot
pybabel extract -F babel.cfg -o messages.pot .
# инициализировать каталоги (однократно)
pybabel init -i messages.pot -d translations -l ru
pybabel init -i messages.pot -d translations -l en
pybabel init -i messages.pot -d translations -l et
# затем отредактируйте translations/<lang>/LC_MESSAGES/messages.po
# и соберите
pybabel compile -d translations
```

Примерные `messages.po` уже добавлены. Вы можете отредактировать их и выполнить `pybabel compile`.

## Письма (Mailgun)

Проект использует Mailgun для отправки писем.

Переменные окружения:
- MAILGUN_API_KEY
- MAILGUN_DOMAIN (например, sandbox0c5bd5b6f554e3d8e8ae28b80b55224.mailgun.org)
- MAIL_FROM (от кого отправлять)
- MAIL_TO (куда отправлять сообщения с формы и для /test-mail)

Локально можно задать в .env:
```
MAILGUN_API_KEY=... 
MAILGUN_DOMAIN=sandbox0c5bd5b6f554e3d8e8ae28b80b55224.mailgun.org
MAIL_FROM="Club <noreply@example.com>"
MAIL_TO=you@example.com
```

Тестовый маршрут:
- GET /test-mail — отправляет тестовое письмо на MAIL_TO и возвращает JSON. Если Mailgun отвечает не 200 — возвращается 500.

Форма контактов отправляет POST /send-message, который использует mailgun_service.send_email.

## Деплой

Пример Gunicorn:
```bash
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

Подходит для деплоя на Render/Railway/PythonAnywhere/VPS с Nginx. Не забудьте настроить окружение:
- `SECRET_KEY`
- `DATABASE_URL` (например, PostgreSQL)
- `ADMIN_USERNAME`, `ADMIN_PASSWORD`
- `BABEL_DEFAULT_LOCALE` (ru/en/et)

## Соответствие ТЗ
- Структура проекта, страницы (Главная, Новости, Расписание, Тренеры, Контакты, Запись) — реализованы.
- Админ-панель (dashboard, добавление новостей, редактирование расписания) — реализована.
- Локализация RU/EN/ET — подключена через Flask-Babel, добавлены примерные переводы.
- Адаптив и стили — тёмная палитра, hover-эффекты, бургер-меню, минимализм, акценты.
