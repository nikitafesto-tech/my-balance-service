import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Берем URL базы из .env или используем локальный файл по умолчанию
DB_URL = os.getenv("DB_URL", "sqlite:///./test.db")

# Для SQLite нужна специальная настройка потоков
connect_args = {"check_same_thread": False} if "sqlite" in DB_URL else {}

engine = create_engine(DB_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()