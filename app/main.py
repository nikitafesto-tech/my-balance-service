from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, Column, Integer, String, Float, Text
from sqlalchemy.orm import sessionmaker, declarative_base, Session
import os
import urllib.parse
import uuid
import secrets
import hashlib
import base64
import httpx

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- НАСТРОЙКИ ---
SITE_URL = os.getenv("SITE_URL", "http://localhost:8081")
AUTH_URL = os.getenv("AUTH_URL", "http://localhost:8000")

# Ключи провайдеров (Добавь их в .env)
VK_CLIENT_ID = os.getenv("VK_CLIENT_ID")
VK_CLIENT_SECRET = os.getenv("VK_CLIENT_SECRET")
VK_REDIRECT_URI = f"{SITE_URL}/callback/vk"

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = f"{SITE_URL}/callback/google-direct"

YANDEX_CLIENT_ID = os.getenv("YANDEX_CLIENT_ID") # Client ID из Яндекса
YANDEX_CLIENT_SECRET = os.getenv("YANDEX_CLIENT_SECRET") # Client Secret из Яндекса
YANDEX_REDIRECT_URI = f"{SITE_URL}/callback/yandex-direct"

# Ключи Casdoor для API (нужны для синхронизации)
CASDOOR_CLIENT_ID = os.getenv("CASDOOR_CLIENT_ID")
CASDOOR_CLIENT_SECRET = os.getenv("CASDOOR_CLIENT_SECRET")

DB_URL = os.getenv("DB_URL", "sqlite:///./test.db")
engine = create_engine(DB_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class UserWallet(Base):
    __tablename__ = "wallets"
    id = Column(Integer, primary_key=True, index=True)
    casdoor_id = Column(String, unique=True, index=True)
    email = Column(String)
    name = Column(String, nullable=True)
    avatar = Column(String, nullable=True)
    phone = Column(String, nullable=True)
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

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def generate_pkce():
    verifier = secrets.token_urlsafe(32)
    m = hashlib.sha256()
    m.update(verifier.encode('ascii'))
    challenge = base64.urlsafe_b64encode(m.digest()).decode('ascii').rstrip('=')
    return verifier, challenge

async def sync_user_to_casdoor(user_data, provider_prefix):
    """
    Универсальная функция синхронизации.
    user_data: словарь {id, name, avatar, email}
    provider_prefix: 'vk', 'google', 'yandex'
    """
    user_id = str(user_data.get("id"))
    full_name = user_data.get("name", "")
    
    # Создаем уникальный ID для Casdoor (например, google_12345)
    casdoor_username = f"{provider_prefix}_{user_id}"
    
    casdoor_user = {
        "owner": "users",
        "name": casdoor_username,
        "displayName": full_name,
        "avatar": user_data.get("avatar", ""),
        "email": user_data.get("email", ""),
        "phone": user_data.get("phone", ""),
        "id": user_id,
        "type": "normal",
        "properties": {}
    }

    # Стучимся в Casdoor API
    api_url_add = "http://casdoor:8000/api/add-user"
    api_url_update = "http://casdoor:8000/api/update-user"
    
    async with httpx.AsyncClient() as client:
        try:
            auth = (CASDOOR_CLIENT_ID, CASDOOR_CLIENT_SECRET)
            # Пробуем создать
            resp = await client.post(api_url_add, json=casdoor_user, auth=auth)
            # Если такой уже есть (status != ok), обновляем данные
            if resp.json().get('status') != 'ok':
                await client.post(api_url_update, json=casdoor_user, auth=auth)
        except Exception as e:
            print(f"Ошибка синхронизации с Casdoor: {e}")
    
    return casdoor_username # Возвращаем ID, который запишем в базу

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
        return RedirectResponse("/login")
    
    # Теперь token - это всегда ID в нашей базе (vk_..., google_..., yandex_...)
    # Логика едина для всех
    wallet = db.query(UserWallet).filter(UserWallet.casdoor_id == token).first()
    
    if not wallet:
        return RedirectResponse("/logout")

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "name": wallet.name,
        "email": wallet.email,
        "avatar": wallet.avatar,
        "balance": wallet.balance
    })

@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse("signin.html", {"request": request})

# ----------------------------------------------------
# 1. ВКОНТАКТЕ (Direct Bridge)
# ----------------------------------------------------
@app.get("/login/vk-direct")
def login_vk_direct():
    verifier, challenge = generate_pkce()
    params = {
        "client_id": VK_CLIENT_ID,
        "redirect_uri": VK_REDIRECT_URI,
        "response_type": "code",
        "scope": "vkid.personal_info email phone",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": "vk_login"
    }
    auth_url = f"https://id.vk.com/authorize?{urllib.parse.urlencode(params)}"
    response = RedirectResponse(auth_url)
    response.set_cookie("vk_verifier", verifier, httponly=True, samesite="lax")
    return response

@app.get("/callback/vk")
async def callback_vk(code: str, request: Request, db: Session = Depends(get_db)):
    verifier = request.cookies.get("vk_verifier")
    device_id = request.query_params.get("device_id") or str(uuid.uuid4())
    if not verifier: return RedirectResponse("/login")

    async with httpx.AsyncClient() as client:
        token_resp = await client.post("https://id.vk.com/oauth2/auth", data={
            "grant_type": "authorization_code", "code": code,
            "client_id": VK_CLIENT_ID, "client_secret": VK_CLIENT_SECRET,
            "code_verifier": verifier, "redirect_uri": VK_REDIRECT_URI, "device_id": device_id
        })
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token: return HTMLResponse(f"Ошибка VK: {token_data}")

        user_resp = await client.post("https://id.vk.com/oauth2/user_info", data={"access_token": access_token, "client_id": VK_CLIENT_ID})
        user_info = user_resp.json().get("user", {})

    # Формируем данные
    full_name = f"{user_info.get('first_name', '')} {user_info.get('last_name', '')}".strip()
    clean_data = {
        "id": user_info.get("user_id"),
        "name": full_name,
        "avatar": user_info.get("avatar", ""),
        "email": user_info.get("email", ""),
        "phone": user_info.get("phone", "")
    }
    
    # Синхронизация и вход
    await finalize_login(clean_data, "vk", db)
    response = RedirectResponse("/")
    response.set_cookie(key="session_id", value=str(uuid.uuid4()), httponly=True, samesite="lax")
    return update_session_cookie(response, clean_data, "vk", db)

# ----------------------------------------------------
# 2. GOOGLE (Direct Bridge)
# ----------------------------------------------------
@app.get("/login/google-direct")
def login_google_direct():
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online",
        "prompt": "select_account"
    }
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
    return RedirectResponse(auth_url)

@app.get("/callback/google-direct")
async def callback_google_direct(code: str, db: Session = Depends(get_db)):
    async with httpx.AsyncClient() as client:
        token_resp = await client.post("https://oauth2.googleapis.com/token", data={
            "client_id": GOOGLE_CLIENT_ID, "client_secret": GOOGLE_CLIENT_SECRET,
            "code": code, "grant_type": "authorization_code", "redirect_uri": GOOGLE_REDIRECT_URI
        })
        access_token = token_resp.json().get("access_token")
        
        user_resp = await client.get("https://www.googleapis.com/oauth2/v3/userinfo", params={"access_token": access_token})
        g_user = user_resp.json()

    clean_data = {
        "id": g_user.get("sub"),
        "name": g_user.get("name"),
        "avatar": g_user.get("picture"),
        "email": g_user.get("email"),
        "phone": ""
    }
    return update_session_cookie(RedirectResponse("/"), clean_data, "google", db)

# ----------------------------------------------------
# 3. YANDEX (Direct Bridge)
# ----------------------------------------------------
@app.get("/login/yandex-direct")
def login_yandex_direct():
    params = {
        "client_id": YANDEX_CLIENT_ID,
        "redirect_uri": YANDEX_REDIRECT_URI,
        "response_type": "code"
    }
    auth_url = f"https://oauth.yandex.ru/authorize?{urllib.parse.urlencode(params)}"
    return RedirectResponse(auth_url)

@app.get("/callback/yandex-direct")
async def callback_yandex_direct(code: str, db: Session = Depends(get_db)):
    async with httpx.AsyncClient() as client:
        token_resp = await client.post("https://oauth.yandex.ru/token", data={
            "grant_type": "authorization_code", "code": code,
            "client_id": YANDEX_CLIENT_ID, "client_secret": YANDEX_CLIENT_SECRET
        })
        access_token = token_resp.json().get("access_token")
        
        user_resp = await client.get("https://login.yandex.ru/info?format=json", headers={"Authorization": f"OAuth {access_token}"})
        y_user = user_resp.json()

    # Яндекс отдает аватарки специфично, берем дефолтную если нет
    avatar_id = y_user.get("default_avatar_id")
    avatar_url = f"https://avatars.yandex.net/get-yapic/{avatar_id}/islands-200" if avatar_id else ""

    clean_data = {
        "id": y_user.get("id"),
        "name": y_user.get("display_name") or y_user.get("real_name"),
        "avatar": avatar_url,
        "email": y_user.get("default_email"),
        "phone": y_user.get("default_phone", {}).get("number", "")
    }
    return update_session_cookie(RedirectResponse("/"), clean_data, "yandex", db)

# --- ОБЩАЯ ЛОГИКА СОХРАНЕНИЯ ---

async def finalize_login(data, prefix, db):
    # 1. Синхронизация с Casdoor (для админки)
    # Запускаем в фоне, чтобы не ждать, или await (быстро)
    casdoor_id = await sync_user_to_casdoor(data, prefix)
    return casdoor_id

def update_session_cookie(response, data, prefix, db):
    # Эта функция: сохраняет в БД, создает сессию, ставит куку
    import asyncio
    # Синхронизация с Casdoor (хак для синхронного вызова в асинхронном контексте если надо, но лучше так)
    # Для простоты вызовем sync внутри (он быстрый)
    
    # 1. Генерируем ID
    full_id = f"{prefix}_{data['id']}"
    
    # 2. Сохраняем в нашу базу
    wallet = db.query(UserWallet).filter(UserWallet.casdoor_id == full_id).first()
    if not wallet:
        wallet = UserWallet(
            casdoor_id=full_id, email=data['email'], name=data['name'], 
            avatar=data['avatar'], phone=data['phone'], balance=0.0
        )
        db.add(wallet)
    else:
        wallet.name = data['name']
        wallet.avatar = data['avatar']
        if data['email']: wallet.email = data['email']
    db.commit()

    # 3. Сессия
    new_session_id = str(uuid.uuid4())
    db_session = UserSession(session_id=new_session_id, token=full_id)
    db.add(db_session)
    db.commit()

    response.set_cookie(key="session_id", value=new_session_id, httponly=True, samesite="lax")
    return response

@app.get("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    session_id = request.cookies.get("session_id")
    if session_id:
        db.query(UserSession).filter(UserSession.session_id == session_id).delete()
        db.commit()
    response = RedirectResponse("/login")
    response.delete_cookie("session_id")
    response.delete_cookie("vk_verifier")
    return response