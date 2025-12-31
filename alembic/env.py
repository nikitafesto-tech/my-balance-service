from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context
import sys
import os

# Добавляем корневую папку в путь, чтобы видеть app
sys.path.append(os.getcwd())

# === ИМПОРТ ВАШИХ МОДЕЛЕЙ ===
from app.database import Base
# Обязательно импортируем модели, чтобы Alembic их увидел
from app.models import UserWallet, Chat, Message, Payment, UserSession, EmailCode

config = context.config

# === ЛОГИКА ВЫБОРА БАЗЫ ===
# Если мы внутри Docker (есть переменная DB_URL), используем её.
# Если нет - используем локальный sqlite (test.db)
db_url = os.getenv("DB_URL", "sqlite:///./test.db")
config.set_main_option("sqlalchemy.url", db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # render_as_batch нужен для корректной работы с SQLite локально
        render_as_batch=("sqlite" in url) 
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, 
            target_metadata=target_metadata,
            # render_as_batch нужен для корректной работы с SQLite локально
            render_as_batch=("sqlite" in db_url)
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()