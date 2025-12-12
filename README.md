Техническая документация проекта MyService
Версия документа: 1.1 Дата обновления: 12.12.2025 Статус: Production (MVP)

1. Общее описание проекта
MyService — это веб-сервис, предоставляющий пользователям личный кабинет с возможностью авторизации через социальные сети и пополнения внутреннего баланса.

Ключевая особенность архитектуры: Сервис использует Casdoor в качестве централизованного провайдера идентификации (Identity Provider), но реализует кастомный фронтенд авторизации. Приложение на FastAPI выступает "мостом": оно самостоятельно обрабатывает OAuth-коллбэки от соцсетей, создает локальную сессию и синхронизирует пользователя с базой данных Casdoor в фоновом режиме.

2. Технологический стек
Бэкенд и Приложение
Язык: Python 3.11 (Slim образ).

Фреймворк: FastAPI.

Сервер приложений: Uvicorn.

Шаблонизатор: Jinja2 (Server-side rendering).

HTTP Клиент: httpx (асинхронные запросы к API).

База данных и Хранение
СУБД: PostgreSQL 15.

Драйвер: psycopg2-binary.

Архитектура БД: Единая база данных casdoor_db. В ней сосуществуют системные таблицы Casdoor и кастомные таблицы приложения (wallets, payments, sessions).

Инфраструктура
Контейнеризация: Docker & Docker Compose.

Reverse Proxy: Caddy (автоматическое управление SSL-сертификатами Let's Encrypt).

CI/CD: GitHub Actions (автоматический деплой при пуше в main).

Внешние интеграции
Auth: Casdoor (хранение пользователей), OAuth провайдеры (VK, Google, Yandex).

Payments: ЮKassa (YooKassa API + JS Widget).

3. Архитектура модулей
3.1. Модуль Авторизации ("Мост")
Мы не используем стандартный UI входа Casdoor. Логика реализована в app/main.py:

Вход: Пользователь нажимает кнопку (например, VK) на signin.html.

OAuth: FastAPI перенаправляет пользователя в соцсеть.

Callback: Получив code, приложение обменивает его на токен и получает профиль пользователя (email, name, avatar).

Синхронизация: Функция sync_user_to_casdoor:

Проверяет наличие пользователя в Casdoor через API.

Если нет — создает (POST /api/add-user).

Если есть — обновляет данные.

Важно: При создании проставляется поле signupApplication: "Myservice", чтобы пользователь был виден в админке.

Сессия: Создается запись в локальной таблице sessions. Клиенту отдается кука session_id.

3.2. Модуль Платежей (ЮKassa Widget)
Реализован сценарий оплаты без ухода с сайта (Pop-up окно).

Инициализация: Клиент вводит сумму. Бэкенд создает платеж в ЮKassa с параметром confirmation: { type: "embedded" }.

Нюанс: Мы не передаем метод оплаты жестко (карты/сбп), чтобы виджет сам предложил выбор. Это предотвращает ошибку invalid_request.

Фронтенд: JS-скрипт получает confirmation_token и отрисовывает виджет внутри кастомного модального окна (dashboard.html).

Webhook: ЮKassa отправляет уведомление на /api/payment/webhook.

Обработка: Сервер проверяет статус succeeded, обновляет баланс в таблице wallets и запускает синхронизацию с Casdoor.

3.3. Синхронизация Баланса
Баланс дублируется для отображения в админке:

Primary Source: Таблица wallets (поле balance).

Secondary Source: Casdoor. Функция update_casdoor_balance пытается записать баланс:

Приоритет 1: Поле balance (и balanceCurrency: "RUB").

Приоритет 2: Поле score (если balance недоступен для записи).

4. Структура Базы Данных (SQLAlchemy Models)
Все модели описаны в main.py:

Таблица	Описание	Ключевые поля
wallets	Профиль пользователя и баланс.	id, casdoor_id (связь с Casdoor), balance, email.
payments	История транзакций.	yookassa_payment_id (для идемпотентности), user_id, amount, status.
sessions	Активные сессии.	session_id (UUID), token (хранит casdoor_id).

Экспортировать в Таблицы

5. Конфигурация и Переменные окружения (.env)
Файл .env должен находиться в корне /opt/my-balance-service/.

Ini, TOML

# --- Основные настройки ---
SITE_URL=https://lk.neirosetim.ru
AUTH_URL=https://auth.neirosetim.ru
CASDOOR_CERT_FILE=/app/cert.pem 

# --- База Данных ---
DB_URL=postgresql://postgres:secret_password@db:5432/casdoor_db

# --- Casdoor API (для синхронизации) ---
CASDOOR_CLIENT_ID=<ID приложения Myservice>
CASDOOR_CLIENT_SECRET=<Secret приложения Myservice>

# --- Социальные сети (Client ID / Secret) ---
VK_CLIENT_ID=...
VK_CLIENT_SECRET=...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
YANDEX_CLIENT_ID=...
YANDEX_CLIENT_SECRET=...

# --- Платежи (ЮKassa) ---
YOOKASSA_SHOP_ID=<ID магазина>
YOOKASSA_SECRET_KEY=<API Secret Key>
6. Рабочие среды и Workflow разработки
Проект спроектирован для работы в двух изолированных средах. Обе среды работают на Docker, что гарантирует идентичность окружения.

6.1. Локальная среда (Localhost)
Используется для разработки, тестов и отладки.

Адрес приложения: http://localhost:8081 (FastAPI напрямую).

Адрес Casdoor: http://localhost:8000

Особенности:

В docker-compose.yml проброшены порты 8081:8081, что позволяет стучаться в бэкенд напрямую, минуя HTTPS/Caddy.

Переменные окружения берутся из локального файла .env, который нужно создать вручную.

Внимание: Вебхуки ЮKassa локально работать не будут (нужен туннель ngrok), но создание ссылки на оплату тестировать можно.

Как запустить локально (для нового разработчика):

Установите Docker Desktop.

Склонируйте репозиторий.

Создайте файл .env на основе примера.

Запустите:

Bash

docker compose up -d --build
Откройте в браузере http://localhost:8081.

6.2. Продакшен среда (Production)
Развернута на удаленном VPS (Ubuntu/Selectel).

Адрес: https://lk.neirosetim.ru (защищено SSL).

Управление: Через Docker Compose.

Деплой: Автоматический через GitHub Actions (при пуше в ветку main).

Особенности:

Вход трафика только через Caddy (порты 80/443). Порт 8081 закрыт фаерволом сервера для внешнего мира.

Файл .env генерируется автоматически из GitHub Secrets во время деплоя.

7. Процесс Деплоя (CI/CD)
Деплой автоматизирован через GitHub Actions. Файл: .github/workflows/deploy.yml.

Этапы пайплайна:

Checkout: Получение кода.

Create .env: Создание файла .env на сервере из секрета ENV_FILE.

SCP Copy: Копирование файлов на сервер в /opt/my-balance-service.

Remote Docker Commands:

docker compose down (остановка).

docker compose up -d --build (сборка и запуск).

docker image prune -f (очистка).

8. Нюансы и "Подводные камни"
Ошибка invalid_request в ЮKassa:

При использовании confirmation: embedded (виджет) нельзя передавать payment_method_data. Выбор способа (Карта/СБП) должен происходить строго внутри JS-виджета.

Админка Casdoor (Белый экран):

Для работы админки за HTTPS в docker-compose.yml (сервис casdoor) обязательно должны быть переменные origin и staticBaseUrl, указывающие на https://auth.neirosetim.ru.

Отображение пользователей:

Чтобы пользователи, созданные через API, были видны в списке Users в админке, при создании обязательно передавать поле "signupApplication": "Myservice".

9. Полезные команды (Cheat Sheet)
Посмотреть логи приложения:

Bash

docker compose logs -f --tail=100 app
Зайти в базу данных:

Bash

docker compose exec db psql -U postgres casdoor_db
Принудительная пересборка:

Bash

docker compose up -d --build app
10. План развития (Roadmap)
Telegram Auth: Реализовать вход через Telegram Widget (требует регистрации бота у @BotFather).

Email Auth: Реализовать классический вход (Email + Пароль или Код) через SMTP.

История платежей: Вывести таблицу payments в интерфейс пользователя (dashboard.html).