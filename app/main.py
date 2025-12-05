from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from casdoor import CasdoorSDK
from sqlalchemy import create_engine, Column, Integer, String, Float, Text
from sqlalchemy.orm import sessionmaker, declarative_base, Session
import os
import urllib.parse
import uuid

app = FastAPI()

# ==========================================
# 1. НАСТРОЙКИ
# ==========================================
SITE_URL = os.getenv("SITE_URL", "http://localhost:8081")
AUTH_URL = os.getenv("AUTH_URL", "http://localhost:8000")

DB_URL = os.getenv("DB_URL")
if not DB_URL:
    DB_URL = "sqlite:///./test.db"

engine = create_engine(DB_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Модель кошелька
class UserWallet(Base):
    __tablename__ = "wallets"
    id = Column(Integer, primary_key=True, index=True)
    casdoor_id = Column(String, unique=True, index=True)
    email = Column(String)
    name = Column(String, nullable=True)
    avatar = Column(String, nullable=True) # Добавили поле для аватарки
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

# Загрузка сертификата
cert_filename = os.getenv("CASDOOR_CERT_FILE", "cert.pem")
certificate_content = ""
try:
    if os.path.exists(cert_filename):
        with open(cert_filename, "r") as f:
            certificate_content = f.read()
            print(f"✅ Сертификат загружен из {cert_filename}")
    else:
        print(f"⚠️ Файл сертификата не найден: {cert_filename}")
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

# ==========================================
# 3. МАРШРУТЫ
# ==========================================

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
        
        # Обработка данных пользователя
        raw_name = user_info.get("name", "Пользователь")
        raw_email = user_info.get("email", "")
        raw_avatar = user_info.get("avatar", "")

        # Хак для Яндекс.Аватарки: если пришел ID, превращаем в ссылку
        # Яндекс ID обычно короткие и без точек/слэшей, а URL длинный
        if raw_avatar and "http" not in raw_avatar:
             raw_avatar = f"https://avatars.yandex.net/get-yapic/{raw_avatar}/islands-200"

        # Ищем кошелек
        wallet = db.query(UserWallet).filter(UserWallet.casdoor_id == user_id).first()
        
        if not wallet:
            # Создаем новый
            wallet = UserWallet(
                casdoor_id=user_id, 
                email=raw_email, 
                name=raw_name,
                avatar=raw_avatar,
                balance=0.0
            )
            db.add(wallet)
        else:
            # ОБНОВЛЯЕМ данные (если в Casdoor исправили имя/аватар)
            wallet.name = raw_name
            wallet.email = raw_email
            wallet.avatar = raw_avatar
        
        db.commit()
        db.refresh(wallet)
            
        return HTMLResponse(f'''
            <div style="font-family: sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; border: 1px solid #ddd; border-radius: 10px;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <h2 style="margin: 0;">Личный кабинет</h2>
                    <a href="/logout" style="color: #e74c3c; text-decoration: none;">Выйти</a>
                </div>
                <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
                
                <div style="display: flex; align-items: center; gap: 15px; margin-bottom: 20px;">
                    <img src="{wallet.avatar}" style="width: 60px; height: 60px; border-radius: 50%; object-fit: cover; background: #eee;" onerror="this.style.display='none'">
                    <div>
                        <div style="font-size: 20px; font-weight: bold;">{wallet.name}</div>
                        <div style="color: #777;">{wallet.email}</div>
                    </div>
                </div>
                
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
        "redirect_uri": f"{SITE_URL}/callback",
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