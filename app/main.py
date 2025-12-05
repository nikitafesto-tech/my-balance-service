from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from casdoor import CasdoorSDK
from sqlalchemy import create_engine, Column, Integer, String, Float, Text
from sqlalchemy.orm import sessionmaker, declarative_base, Session
import os
import urllib.parse
import uuid

app = FastAPI()

# 1. НАСТРОЙКИ
SITE_URL = os.getenv("SITE_URL", "http://localhost:8081")
AUTH_URL = os.getenv("AUTH_URL", "http://localhost:8000")

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
    phone = Column(String, nullable=True)  # <-- НОВОЕ ПОЛЕ
    name = Column(String, nullable=True)
    avatar = Column(String, nullable=True)
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
cert_filename = os.getenv("CASDOOR_CERT_FILE", "cert.pem")
certificate_content = ""
try:
    if os.path.exists(cert_filename):
        with open(cert_filename, "r") as f:
            certificate_content = f.read()
    else:
        print(f"⚠️ Сертификат {cert_filename} не найден")
except Exception:
    pass

sdk = CasdoorSDK(
    endpoint="http://casdoor:8000",
    client_id=os.getenv("CASDOOR_CLIENT_ID"),
    client_secret=os.getenv("CASDOOR_CLIENT_SECRET"),
    certificate=certificate_content,
    org_name="users",
    application_name="MyService",
    front_endpoint=AUTH_URL
)

# --- МАРШРУТЫ ---

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
                    <a href="/login"><button style="padding: 15px 30px; background: #000; color: #fff; border: none; border-radius: 5px; cursor: pointer;">ВОЙТИ</button></a>
                </div>
            </div>
        ''')
    
    try:
        user_info = sdk.parse_jwt_token(token)
        user_id = user_info.get("id")
        
        # Данные из Casdoor
        raw_name = user_info.get("name")
        raw_email = user_info.get("email", "")
        raw_avatar = user_info.get("avatar", "")
        raw_phone = user_info.get("phone", "") # Получаем телефон

        # Умная логика имени
        if not raw_name or raw_name == user_id:
             # Если имя пустое или равно ID, пробуем взять логин из почты
             raw_name = raw_email.split("@")[0] if "@" in raw_email else "Пользователь"

        # Умная логика аватарки
        final_avatar = ""
        if raw_avatar and "http" in raw_avatar:
            final_avatar = raw_avatar
        elif raw_avatar:
             final_avatar = f"https://avatars.yandex.net/get-yapic/{raw_avatar}/islands-200"
        else:
             final_avatar = f"https://ui-avatars.com/api/?name={raw_name}&background=random"

        wallet = db.query(UserWallet).filter(UserWallet.casdoor_id == user_id).first()
        
        if not wallet:
            wallet = UserWallet(
                casdoor_id=user_id, 
                email=raw_email, 
                phone=raw_phone,
                name=raw_name,
                avatar=final_avatar,
                balance=0.0
            )
            db.add(wallet)
        else:
            # Обновляем данные
            wallet.name = raw_name
            wallet.avatar = final_avatar
            wallet.phone = raw_phone
            # Email обновляем, только если он не пустой и не ID
            if raw_email and raw_email != user_id:
                wallet.email = raw_email
        
        db.commit()
        db.refresh(wallet)
            
        # --- НОВЫЙ ДИЗАЙН С ШАПКОЙ ---
        return HTMLResponse(f'''
            <body style="margin: 0; font-family: sans-serif; background: #f5f5f5;">
                <header style="background: #fff; padding: 10px 20px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                    <div style="font-weight: bold; font-size: 18px;">MyService</div>
                    
                    <div style="display: flex; align-items: center; gap: 10px; cursor: pointer;" onclick="alert('Переход в настройки профиля (пока тут)')">
                        <div style="text-align: right;">
                            <div style="font-weight: bold; font-size: 14px;">{wallet.name}</div>
                            <div style="font-size: 12px; color: #888;">{wallet.email}</div>
                        </div>
                        <img src="{wallet.avatar}" style="width: 40px; height: 40px; border-radius: 50%; object-fit: cover;">
                    </div>
                </header>

                <div style="max-width: 800px; margin: 40px auto; padding: 20px;">
                    <div style="background: #fff; padding: 40px; border-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); text-align: center;">
                        <div style="color: #888; font-size: 14px; text-transform: uppercase; letter-spacing: 1px;">Ваш баланс</div>
                        <div style="font-size: 64px; font-weight: bold; color: #333; margin: 10px 0;">{wallet.balance} ₽</div>
                        
                        <div style="margin-top: 30px;">
                             <a href="/logout" style="color: #e74c3c; text-decoration: none; border-bottom: 1px dashed #e74c3c;">Выйти из аккаунта</a>
                        </div>
                    </div>
                </div>
            </body>
        ''')
    except Exception as e:
        return HTMLResponse(f"Ошибка авторизации: {e} <br><a href='/logout'>Сброс</a>")

@app.get("/login")
def login(provider: str = None):
    params = {
        "client_id": sdk.client_id,
        "response_type": "code",
        "redirect_uri": f"{SITE_URL}/callback",
        "scope": "read",
        "state": sdk.application_name
    }
    auth_link = f"{AUTH_URL}/login/oauth/authorize?{urllib.parse.urlencode(params)}"
    if provider:
        auth_link += f"&provider={provider}"
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