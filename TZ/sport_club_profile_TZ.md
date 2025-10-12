ТЫ — старший разработчик. Реализуй модуль “Личный профиль участника” для проекта на Flask + SQLAlchemy + Jinja2 с поддержкой Stripe Billing. Сделай аккуратный тёмный UI а-ля современная админ-панель (как на прикреплённом референсе), но с фирменной палитрой Wiru Combat Academy.

========================
ТЕХНИЧЕСКИЙ КОНТЕКСТ
========================
Стек: Flask, SQLAlchemy, Flask-Login, Flask-WTF, Flask-Migrate, Jinja2, Stripe Billing (Checkout + Billing Portal + Webhooks).
БД: SQLAlchemy (SQLite/Postgres). Язык UI: RU. Роли: user, admin.
Файловая структура (добавь недостающие):
- app.py
- config.py
- /blueprints/{profile,billing,documents,admin}/__init__.py + routes.py + forms.py
- /models.py
- /templates/base.html
- /templates/profile/{overview.html,billing.html,documents.html}
- /templates/admin/{users_list.html,user_detail.html,subs.html,payments.html,schedule.html}
- /static/css/profile.css
- /migrations/ (Flask-Migrate)
- /tests/ (pytest)
- /uploads/ (создай при первом запуске)

ENV-переменные (используй os.environ):
STRIPE_SECRET_KEY=...
STRIPE_WEBHOOK_SECRET=...
APP_BASE_URL=http://localhost:5000
UPLOAD_DIR=./uploads
MAX_UPLOAD_MB=15

Палитра (через CSS-переменные):
:root{
  --bg:#0d0d0d;
  --panel:#1a1a1a;
  --text:#f5f5f5;
  --head:#ffffff;
  --accent:#e02525;
  --accent-hover:#ff3333;
  --muted:#bdbdbd;
  --border:#222;
  --radius:14px;
  --shadow:0 6px 18px rgba(0,0,0,.35);
}

UI-требования:
- Левый сайдбар (аватар + имя, пункты навигации). Центральная колонка — карточки/формы.
- Карточки с радиусом var(--radius), тенью var(--shadow), отступами 16–24px.
- Сетка форм: 2 колонки ≥1024px, 1 колонка на мобиле.
- Кнопки/ссылки — акцентные (var(--accent)), hover — var(--accent-hover).
- Адаптивность, фокус-стили (доступность), aria-лейблы.

========================
ФУНКЦИОНАЛ И РОУТЫ
========================
1) ПРОФИЛЬ — вкладка “Главная”
- GET /profile → templates/profile/overview.html
- Показать: фото (заглушка + Upload), ФИО, уровень/категория/группа, статус подписки (active/past_due/canceled), дата current_period_end.
- Быстрые кнопки: “Продлить” (ведёт на /billing/checkout/session c price_id), “Посмотреть расписание” (линк на общую страницу сайта), “Связаться с тренером” (mailto: или ссылка на /contact).
- Секция смены пароля (старый/новый/повтор), POST /profile/password – CSRF + валидация.
- Если до окончания < 7 дней — жёлтый баннер “Подписка истекает …”.

2) АБОНЕМЕНТЫ И ОПЛАТА — вкладка
- GET /billing → templates/profile/billing.html
- Таб “Активный абонемент”: тип (monthly|yearly), статус, current_period_end.
- Таблица “История оплат”: дата, сумма, валюта, статус, invoice_id (линк на квитанцию, если есть).
- Кнопки:
  - “Продлить абонемент” → POST /billing/checkout/session {price_id: price_monthly}
  - “Перейти на годовой тариф” → POST /billing/checkout/session {price_id: price_yearly}
  - “Управлять подпиской” → POST /billing/portal {customer_id}
- Stripe:
  - POST /billing/checkout/session — создаёт Checkout Session (mode=subscription, automatic_tax.enabled=true, allow_promotion_codes=true). Ответ: JSON {url}.
  - POST /billing/portal — создаёт Billing Portal Session. Ответ: JSON {url}.
  - POST /billing/webhook — обрабатывает: checkout.session.completed, invoice.paid, invoice.payment_failed, customer.subscription.updated/deleted. Синхронизация в БД.
- После успешной оплаты — редирект на /billing с флеш-уведомлением.

3) ДОКУМЕНТЫ / СОГЛАСИЯ — вкладка
- GET /documents → templates/profile/documents.html
- Пользователь может загрузить файл + текстовую заметку “что за документ”.
- Допустимые типы: pdf, jpg, jpeg, png. Лимит размера: MAX_UPLOAD_MB. Сохранение в UPLOAD_DIR/{user_id}/{uuid.ext}
- POST /documents/upload — приём multipart/form-data, валидация, запись в БД.
- Пользователь видит только свои документы. Admin видит все и может скачать:
  - GET /admin/documents?user_id=...
  - GET /admin/documents/<doc_id>/download

4) АДМИН — только role=admin
- GET /admin/users — список пользователей (поиск: email/ФИО), колонки: ФИО, email, группа, статус подписки, кол-во документов, кнопка “Открыть”.
- GET /admin/users/<id> — карточка пользователя c вкладками: Профиль, Подписка, Платежи, Документы (ссылки на скачку).
- GET /admin/billing/subscriptions — список подписок (user, plan, статус, period_end, customer_id).
- GET /admin/billing/payments — список платежей (дата, сумма, статус, invoice_id).
- GET /admin/schedule — простая форма добавления тренировок (CRUD минималка) и распределение по группам (user.group_name).

========================
МОДЕЛИ (SQLAlchemy)
========================
User(id, email unique, password_hash, full_name, level, group_name, role, created_at)
Subscription(id, user_id FK, stripe_customer_id, stripe_subscription_id, stripe_price_id, status, current_period_end)
Payment(id, user_id FK, stripe_invoice_id, amount, currency, status, paid_at, raw JSON)
Document(id, user_id FK, filename, stored_path, mime, size_bytes, note, uploaded_at)
Связи: User has many Subscriptions, Payments, Documents.
Индексы: stripe_*_id, user_id.

========================
БЕЗОПАСНОСТЬ
========================
- Flask-Login, декораторы login_required, role_required('admin').
- CSRF на всех POST-формах.
- Валидация загрузок: расширение, MIME, размер; uuid-имена; запрет прямой раздачи из /uploads; выдавать через send_file после проверки прав.
- Политика паролей (мин. 8 символов). Смена пароля требует текущий пароль.

========================
Шаблоны (Jinja2)
========================
1) base.html:
- Тёмный фон var(--bg), левый сайдбар с аватаром и навигацией:
  - Главная, Абонемент, Документы, Настройки
  - Блок “Админ” (если role=admin): Участники, Подписки, Расписание
- Контент-область: контейнер max-width 1200px, паддинги 24px.

2) profile/overview.html:
- Карточка “Account Management”: аватар + Upload (fake action, подключи форму), форма смены пароля.
- Карточка “Profile Information”: ФИО, уровень, категория/группа (grid 2x).
- Карточка “Subscription Status”: цветной чип статуса, дата истечения, быстрые кнопки (Продлить / Расписание / Связаться).
- Баннер об истечении при <7 дней.

3) profile/billing.html:
- Блок текущего плана и статуса.
- Кнопки: Продлить (monthly), Перейти на годовой (yearly), Управлять подпиской (Portal).
- Таблица Payment History (пагинация).

4) profile/documents.html:
- Форма загрузки файла + textarea note.
- Список документов (имя, дата, размер). Иконки типов.
- Удаления пока нет.

5) admin/*:
- users_list.html — таблица с поиском и пагинацией.
- user_detail.html — табы: обзор профиля, подписка, платежи, документы.
- subs.html / payments.html — списки с фильтрами.
- schedule.html — примитивный CRUD.

========================
СТИЛИ (static/css/profile.css)
========================
- Базовый reset; html,body {background:var(--bg); color:var(--text);}
- .sidebar, .card, .btn, .input, .table… в тёмной теме; hover/focus стили; радиусы/тени из переменных.
- Сетка карточек: .grid {display:grid; gap:16px;} @media(min-width:1024px){grid-template-columns:1fr 1fr;}

========================
FORMS (Flask-WTF)
========================
- PasswordChangeForm(old_password, new_password, confirm)
- DocumentUploadForm(file, note)
- (Админ) UserSearchForm(q), ScheduleForm(title, date, time, group)

========================
STRIPE И ЛОГИКА
========================
- /billing/checkout/session принимает JSON {price_id, quantity?} → создаёт Checkout Session (mode=subscription, automatic_tax.enabled=true) и возвращает {url}.
- /billing/portal {customer_id} → возвращает {url}.
- Webhook:
  - checkout.session.completed: связать customer/subscription с User; создать/обновить Subscription; current_period_end.
  - invoice.paid: создать Payment; продлить доступ.
  - invoice.payment_failed: пометить Subscription.status=past_due.
  - customer.subscription.updated/deleted: синк статуса и дат.
- Price IDs: price_monthly, price_yearly (вынеси в config).

========================
ТЕСТЫ (pytest)
========================
- Логин и доступ к /profile (гость → редирект).
- POST /billing/checkout/session (моки Stripe) → 200 и url.
- POST /billing/webhook (фиктивные payload’ы) → корректные апдейты БД.
- Upload документа: валид/невалид (тип, размер).

========================
СИДЫ/ДЕПЛОЙ
========================
- seed скрипт: admin (email+пароль), 2 тест-пользователя, по 1 подписке/платежу/документу.
- README_DEPLOY.md: команды (pip install -r reqs; flask db init/migrate/upgrade; запуск; настройка webhook URL).
- Создай UPLOAD_DIR на сервере и права.

========================
КРИТЕРИИ ПРИЁМКИ
========================
- Пользователь видит /profile, /billing, /documents; меняет пароль; загружает документы.
- Подписка оформляется через Stripe Checkout, статусы синхронизируются вебхуком; Payments и Subscriptions видны в UI.
- Админ видит списки пользователей/подписок/платежей/документов; может открыть карточку пользователя.
- Весь UI тёмный, в палитре WCA; адаптив ≥360px; фокус-стили присутствуют.
- Базовые тесты проходят.

СОЗДАЙ КОД СРАЗУ: модели+миграции, блюпринты, роуты, формы, шаблоны, CSS, тесты, seed и README. Выводи файлы блоками с путями, кратким описанием и минимальными сниппетами для мгновенной вставки.
