from fastapi import FastAPI, Request, Depends, HTTPException, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from casdoor import CasdoorSDK
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

# --- 1. НАСТРОЙКИ ---
SITE_URL = os.getenv("SITE_URL", "http://localhost:8081")
AUTH_URL = os.getenv("AUTH_URL", "http://localhost:8000")

# ВСТАВЬ СВОИ ДАННЫЕ
VK_CLIENT_ID = os.getenv("VK_CLIENT_ID")
VK_CLIENT_SECRET = os.getenv("VK_CLIENT_SECRET")
VK_REDIRECT_URI = f"{SITE_URL}/callback/vk"

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

# Сертификат
cert_filename = os.getenv("CASDOOR_CERT_FILE", "cert.pem")
certificate_content = ""
try:
    if os.path.exists(cert_filename):
        with open(cert_filename, "r") as f:
            certificate_content = f.read()
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

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def generate_pkce():
    verifier = secrets.token_urlsafe(32)
    m = hashlib.sha256()
    m.update(verifier.encode('ascii'))
    challenge = base64.urlsafe_b64encode(m.digest()).decode('ascii').rstrip('=')
    return verifier, challenge

async def sync_user_to_casdoor(vk_user):
    """Синхронизирует пользователя VK в базу Casdoor"""
    user_id = str(vk_user.get("user_id"))
    full_name = f"{vk_user.get('first_name', '')} {vk_user.get('last_name', '')}".strip()
    
    casdoor_user = {
        "owner": "users",
        "name": f"vk_{user_id}", # Уникальное имя
        "displayName": full_name,
        "avatar": vk_user.get("avatar", ""),
        "email": vk_user.get("email", ""),
        "phone": vk_user.get("phone", ""),
        "id": user_id,
        "type": "normal",
        "properties": {}
    }

    api_url = "http://casdoor:8000/api/add-user"
    async with httpx.AsyncClient() as client:
        try:
            auth = (os.getenv("CASDOOR_CLIENT_ID"), os.getenv("CASDOOR_CLIENT_SECRET"))
            resp = await client.post(api_url, json=casdoor_user, auth=auth)
            
            if resp.json().get('status') != 'ok':
                await client.post("http://casdoor:8000/api/update-user", json=casdoor_user, auth=auth)
        except Exception as e:
            print(f"Ошибка синхронизации с Casdoor: {e}")

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
        return templates.TemplateResponse("index.html", {"request": request})
    
    # ЛОГИКА ОПРЕДЕЛЕНИЯ ПОЛЬЗОВАТЕЛЯ
    user_id = None
    name = "Пользователь"
    email = ""
    avatar = ""
    
    try:
        # ВАРИАНТ А: Это наш токен от VK (начинается с vk_)
        if token.startswith("vk_"):
            user_id = token 
            wallet = db.query(UserWallet).filter(UserWallet.casdoor_id == user_id).first()
            if wallet:
                name = wallet.name
                email = wallet.email
                avatar = wallet.avatar
            else:
                return RedirectResponse("/logout")

        # ВАРИАНТ Б: Это токен от Casdoor (JWT)
        else:
            user_info = sdk.parse_jwt_token(token)
            user_id = user_info.get("id")
            
            raw_name = user_info.get("name")
            raw_email = user_info.get("email", "")
            raw_avatar = user_info.get("avatar", "")
            raw_phone = user_info.get("phone", "")

            if not raw_name or raw_name == user_id:
                 raw_name = raw_email.split("@")[0] if "@" in raw_email else "Пользователь"
            
            final_avatar = ""
            if raw_avatar and "http" in raw_avatar: final_avatar = raw_avatar
            elif raw_avatar: final_avatar = f"https://avatars.yandex.net/get-yapic/{raw_avatar}/islands-200"
            else: final_avatar = f"https://ui-avatars.com/api/?name={raw_name}&background=random"

            wallet = db.query(UserWallet).filter(UserWallet.casdoor_id == user_id).first()
            if not wallet:
                wallet = UserWallet(
                    casdoor_id=user_id, email=raw_email, phone=raw_phone,
                    name=raw_name, avatar=final_avatar, balance=0.0
                )
                db.add(wallet)
            else:
                wallet.name = raw_name
                wallet.avatar = final_avatar
                wallet.phone = raw_phone
                if raw_email and raw_email != user_id: wallet.email = raw_email
            
            db.commit()
            db.refresh(wallet)
            
            name = wallet.name
            email = wallet.email
            avatar = wallet.avatar

    except Exception:
        return RedirectResponse("/logout")

    if not user_id or not wallet:
        return RedirectResponse("/logout")

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "name": name,
        "email": email,
        "avatar": avatar,
        "balance": wallet.balance
    })

# --- ОБЫЧНЫЙ ВХОД (CASDOOR) ---
@app.get("/login")
def login(provider: str = None):
    if provider and provider.lower() in ["vk", "vk_new"]:
        return RedirectResponse("/login/vk-direct")

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
    except Exception:
        return RedirectResponse("/")
        
    new_session_id = str(uuid.uuid4())
    db_session = UserSession(session_id=new_session_id, token=token)
    db.add(db_session)
    db.commit()
    
    response = RedirectResponse("/")
    response.set_cookie(key="session_id", value=new_session_id, httponly=True, samesite="lax")
    return response

# --- СПЕЦ-ВХОД ДЛЯ VK (Исправлено) ---
@app.get("/login/vk-direct")
def login_vk_direct():
    verifier, challenge = generate_pkce()
    state = str(uuid.uuid4())
    
    params = {
        "client_id": VK_CLIENT_ID,
        "redirect_uri": VK_REDIRECT_URI,
        "response_type": "code",
        "scope": "vkid.personal_info email phone",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state
    }
    auth_url = f"https://id.vk.com/authorize?{urllib.parse.urlencode(params)}"
    
    response = RedirectResponse(auth_url)
    # Сохраняем ТОЛЬКО verifier, device_id нам пришлет ВК
    response.set_cookie("vk_verifier", verifier, httponly=True, samesite="lax")
    return response

@app.get("/callback/vk")
async def callback_vk(
    code: str, 
    state: str,
    device_id: str, # <--- Берем device_id из URL от ВКонтакте!
    request: Request, 
    db: Session = Depends(get_db)
):
    verifier = request.cookies.get("vk_verifier")
    
    if not verifier:
        return RedirectResponse("/") 

    async with httpx.AsyncClient() as client:
        token_resp = await client.post("https://id.vk.com/oauth2/auth", data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": VK_CLIENT_ID,
            "client_secret": VK_CLIENT_SECRET,
            "code_verifier": verifier,
            "redirect_uri": VK_REDIRECT_URI,
            "device_id": device_id, # <--- Отправляем правильный ID
            "state": state
        })
        token_data = token_resp.json()
        
        # Обработка ошибки VK
        if "error" in token_data:
             return HTMLResponse(f"Ошибка VK: {token_data}")

        access_token = token_data.get("access_token")
        
        user_resp = await client.post("https://id.vk.com/oauth2/user_info", data={
            "access_token": access_token,
            "client_id": VK_CLIENT_ID
        })
        user_info = user_resp.json().get("user", {})

    # Синхронизация с Casdoor
    await sync_user_to_casdoor(user_info)

    # Сохраняем в локальную базу
    vk_id = str(user_info.get("user_id"))
    full_id = f"vk_{vk_id}"
    
    name = f"{user_info.get('first_name', '')} {user_info.get('last_name', '')}".strip()
    email = user_info.get("email", "")
    avatar = user_info.get("avatar", "")
    phone = user_info.get("phone", "")
    
    wallet = db.query(UserWallet).filter(UserWallet.casdoor_id == full_id).first()
    if not wallet:
        wallet = UserWallet(
            casdoor_id=full_id, email=email, name=name, avatar=avatar, phone=phone, balance=0.0
        )
        db.add(wallet)
    else:
        wallet.name = name
        wallet.avatar = avatar
        if email: wallet.email = email
        if phone: wallet.phone = phone
    
    db.commit()
    
    # Входим
    new_session_id = str(uuid.uuid4())
    db_session = UserSession(session_id=new_session_id, token=full_id)
    db.add(db_session)
    db.commit()
    
    response = RedirectResponse("/")
    response.set_cookie(key="session_id", value=new_session_id, httponly=True, samesite="lax")
    response.delete_cookie("vk_verifier")
    return response

@app.get("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    session_id = request.cookies.get("session_id")
    if session_id:
        db.query(UserSession).filter(UserSession.session_id == session_id).delete()
        db.commit()
    response = RedirectResponse("/")
    response.delete_cookie("session_id")
    response.delete_cookie("vk_verifier")
    return response