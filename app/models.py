from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

# === ПОЛЬЗОВАТЕЛИ ===
class UserWallet(Base):
    __tablename__ = "wallets"
    id = Column(Integer, primary_key=True, index=True)
    casdoor_id = Column(String, unique=True, index=True)
    email = Column(String)
    name = Column(String, nullable=True)
    avatar = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    balance = Column(Float, default=0.0)
    
    # Связь с чатами: у одного юзера много чатов
    chats = relationship("Chat", back_populates="user")

class UserSession(Base):
    __tablename__ = "sessions"
    session_id = Column(String, primary_key=True)
    token = Column(Text)

# === ПЛАТЕЖИ ===
class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True, index=True)
    yookassa_payment_id = Column(String, unique=True, index=True)
    user_id = Column(String, index=True)
    amount = Column(Float)
    status = Column(String, default="pending")
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class EmailCode(Base):
    __tablename__ = "email_codes"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, index=True)
    code = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

# === ЧАТЫ И СООБЩЕНИЯ (НОВОЕ) ===
class Chat(Base):
    __tablename__ = "chats"
    
    id = Column(Integer, primary_key=True, index=True)
    user_casdoor_id = Column(String, ForeignKey("wallets.casdoor_id"))
    title = Column(String, default="Новый чат")
    model = Column(String, default="gpt-4o") # Какая модель используется
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow) # Для сортировки списка
    
    user = relationship("UserWallet", back_populates="chats")
    # cascade="all, delete" означает: удалили чат -> удалились все сообщения
    messages = relationship("Message", back_populates="chat", cascade="all, delete")

class Message(Base):
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey("chats.id"))
    role = Column(String) # 'user' или 'assistant'
    content = Column(Text) # Текст сообщения
    
    # Ссылки на файлы в S3 (Selectel)
    image_url = Column(String, nullable=True)     # Сгенерированная картинка
    attachment_url = Column(String, nullable=True) # Загруженный пользователем файл
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    chat = relationship("Chat", back_populates="messages")