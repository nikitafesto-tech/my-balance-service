from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from casdoor import CasdoorSDK
from sqlalchemy import create_engine, Column, Integer, String, Float, Text
from sqlalchemy.orm import sessionmaker, declarative_base, Session
import os
import urllib.parse
import uuid

app = FastAPI()

# --- 1. БАЗА ДАННЫХ ---
DB_URL = os.getenv("DB_URL")
if not DB_URL:
    DB_URL = "sqlite:///./test.db"

engine = create_engine(DB_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class UserWallet(Base):
    __tablename__ = "wallets"
    id = Column(Integer, primary_key=True, index=True)
    casdoor_id = Column(String, unique=True, index=True)
    email = Column(String)
    name = Column(String, nullable=True)
    balance = Column(Float, default=0.0)

class UserSession(Base):
    __tablename__ = "sessions"
    session_id = Column(String, primary_key=True)
    token = Column(Text)

try:
    Base.metadata.create_all(bind=engine)
except Exception as e:
    print(f"Ошибка БД: {e}")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- 2. ЗАГРУЗКА СЕРТИФИКАТА ИЗ ФАЙЛА (DevOps Way) ---
certificate_content = ""
try:
    # Мы ищем файл прямо рядом с кодом
    with open("cert.pem", "r") as f:
        certificate_content = f.read()
    print("✅ Сертификат успешно загружен из файла")
except Exception as e:
    print(f"⚠️ ВНИМАНИЕ: Не удалось прочитать cert.pem: {e}")
    # Если файла нет, оставляем пустым (для локального теста может прокатить, но лучше иметь файл)

# --- 3. НАСТРОЙКА SDK ---
sdk = CasdoorSDK(
    endpoint="http://casdoor:8000",
    client_id=os.getenv("CASDOOR_CLIENT_ID"),
    client_secret=os.getenv("CASDOOR_CLIENT_SECRET"),
    certificate=certificate_content, # <-- Передаем прочитанный текст
    org_name="users",
    application_name="MyService",
    front_endpoint="http://localhost"
)

# --- 4. МАРШРУТЫ ---

@app.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    session_id = request.cookies.get("session_id")
    token = None
    
    if session_id:
        db_session = db.query(UserSession).filter(UserSession.session_id == session_id).first()
        if db_session:
            token = db_session.token

    if not token:
        return HTMLResponse('''
            <div style="display: flex; justify-content: center; align-items: center; height: 100vh; font-family: sans-serif;">
                <div style="text-align: center;">
                    <h1>Сервис Баланса</h1>
                    <p>Доступ закрыт. Пожалуйста, войдите.</p>
                    <a href="/login">
                        <button style="padding: 15px 30px; font-size: 18px; cursor: pointer; background: #000; color: #fff; border: none; border-radius: 5px;">
                            ВОЙТИ В КАБИНЕТ
                        </button>
                    </a>
                </div>
            </div>
        ''')
    
    try:
        user_info = sdk.parse_jwt_token(token)
        user_id = user_info.get("id")
        
        wallet = db.query(UserWallet).filter(UserWallet.casdoor_id == user_id).first()
        if not wallet:
            wallet = UserWallet(
                casdoor_id=user_id, 
                email=user_info.get("email"), 
                name=user_info.get("name"),
                balance=0.0
            )
            db.add(wallet)
            db.commit()
            db.refresh(wallet)
            
        return HTMLResponse(f'''
            <div style="font-family: sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; border: 1px solid #ddd; border-radius: 10px;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <h2 style="margin: 0;">Личный кабинет</h2>
                    <a href="/logout" style="color: #e74c3c; text-decoration: none;">Выйти</a>
                </div>
                <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
                
                <p>Привет, <strong>{user_info.get("name")}</strong>!</p>
                
                <div style="background: #f8f9fa; padding: 30px; border-radius: 10px; text-align: center;">
                    <div style="font-size: 14px; color: #555; margin-bottom: 5px;">ВАШ БАЛАНС</div>
                    <div style="font-size: 48px; color: #27ae60; font-weight: bold;">{wallet.balance} ₽</div>
                </div>
            </div>
        ''')
    except Exception as e:
        return HTMLResponse(f"Ошибка авторизации: {e} <br><a href='/logout'>Сбросить вход</a>")

@app.get("/login")
def login():
    params = {
        "client_id": sdk.client_id,
        "response_type": "code",
        "redirect_uri": "http://localhost:8081/callback",
        "scope": "read",
        "state": sdk.application_name
    }
    auth_link = f"{sdk.front_endpoint}/login/oauth/authorize?{urllib.parse.urlencode(params)}"
    return RedirectResponse(auth_link)

@app.get("/callback")
def callback(code: str, state: str, db: Session = Depends(get_db)):
    try:
        token_response = sdk.get_oauth_token(code)
        token = token_response.get("access_token")
    except Exception as e:
        return HTMLResponse(f"Ошибка получения токена: {e}")
        
    new_session_id = str(uuid.uuid4())
    db_session = UserSession(session_id=new_session_id, token=token)
    db.add(db_session)
    db.commit()
    
    response = RedirectResponse("/")
    response.set_cookie(key="session_id", value=new_session_id, httponly=True, samesite="lax")
    return response

@app.get("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    session_id = request.cookies.get("session_id")
    if session_id:
        db.query(UserSession).filter(UserSession.session_id == session_id).delete()
        db.commit()
        
    response = RedirectResponse("/")
    response.delete_cookie("session_id")
    return response