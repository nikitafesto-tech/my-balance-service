from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context
import sys
import os

# Добавляем путь к приложению
sys.path.append(os.getcwd())

# ИМПОРТИРУЕМ ВАШИ МОДЕЛИ
from app.database import Base
from app.models import UserWallet, Chat, Message, Payment, UserSession, EmailCode

config = context.config

# Берем URL базы из переменных окружения (Docker) или локальный
db_url = os.getenv("DB_URL", "sqlite:///./test.db")
config.set_main_option("sqlalchemy.url", db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# === ВАЖНАЯ ФУНКЦИЯ ДЛЯ ЗАЩИТЫ CASDOOR ===
def include_object(object, name, type_, reflected, compare_to):
    # Если это таблица, она есть в базе (reflected), но её нет в наших моделях (compare_to is None)
    # ЗНАЧИТ ЭТО ТАБЛИЦА CASDOOR — ИГНОРИРУЕМ ЕЁ (НЕ УДАЛЯЕМ)
    if type_ == "table" and reflected and compare_to is None:
        return False
    return True

def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=("sqlite" in url),
        include_object=include_object # <--- Подключаем защиту
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
            render_as_batch=("sqlite" in db_url),
            include_object=include_object # <--- Подключаем защиту
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()