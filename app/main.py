from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from casdoor import CasdoorSDK
from sqlalchemy import create_engine, Column, Integer, String, Float, Text
from sqlalchemy.orm import sessionmaker, declarative_base, Session
import os
import urllib.parse
import uuid

app = FastAPI()

# === ГИБКИЕ НАСТРОЙКИ (Берем из .env с дефолтом для локалки) ===
# Если переменных нет - используем localhost. Если есть (на сервере) - используем их.
SITE_URL = os.getenv("SITE_URL", "http://localhost:8081") 
AUTH_URL = os.getenv("AUTH_URL", "http://localhost:8000") # Локально Casdoor на 8000
# ==============================================================

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

# Сертификат
certificate_content = ""
try:
    with open("cert.pem", "r") as f:
        certificate_content = f.read()
except Exception:
    pass

# --- 2. SDK ---
sdk = CasdoorSDK(
    endpoint="http://casdoor:8000", # Внутренний всегда неизменен
    client_id=os.getenv("CASDOOR_CLIENT_ID"),
    client_secret=os.getenv("CASDOOR_CLIENT_SECRET"),
    certificate=certificate_content,
    org_name="users",
    application_name="MyService",
    front_endpoint=AUTH_URL # Используем переменную!
)

# --- 3. МАРШРУТЫ ---

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
            <div style="text-align:center; margin-top:50px; font-family:sans-serif;">
                <h1>Сервис Баланса</h1>
                <a href="/login"><button style="padding:15px; background:#000; color:#fff;">ВОЙТИ</button></a>
            </div>
        ''')
    
    try:
        user_info = sdk.parse_jwt_token(token)
        user_id = user_info.get("id")
        wallet = db.query(UserWallet).filter(UserWallet.casdoor_id == user_id).first()
        if not wallet:
            wallet = UserWallet(casdoor_id=user_id, email=user_info.get("email"), name=user_info.get("name"), balance=0.0)
            db.add(wallet)
            db.commit()
            
        return HTMLResponse(f'''
            <div style="text-align:center; font-family:sans-serif; padding:50px;">
                <h1>Личный кабинет</h1>
                <p>Привет, {user_info.get("name")}!</p>
                <h2>Баланс: {wallet.balance} ₽</h2>
                <a href="/logout" style="color:red;">Выйти</a>
            </div>
        ''')
    except Exception as e:
        return HTMLResponse(f"Ошибка: {e} <a href='/logout'>Сброс</a>")

@app.get("/login")
def login():
    params = {
        "client_id": sdk.client_id,
        "response_type": "code",
        "redirect_uri": f"{SITE_URL}/callback", # Используем переменную!
        "scope": "read",
        "state": sdk.application_name
    }
    auth_link = f"{AUTH_URL}/login/oauth/authorize?{urllib.parse.urlencode(params)}"
    return RedirectResponse(auth_link)

@app.get("/callback")
def callback(code: str, state: str, db: Session = Depends(get_db)):
    try:
        token_response = sdk.get_oauth_token(code)
        token = token_response.get("access_token")
    except Exception as e:
        return HTMLResponse(f"Ошибка: {e}")
    new_session_id = str(uuid.uuid4())
    db_session = UserSession(session_id=new_session_id, token=token)
    db.add(db_session)
    db.commit()
    
    response = RedirectResponse("/")
    # Убираем domain=..., чтобы работало и на localhost, и на домене
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