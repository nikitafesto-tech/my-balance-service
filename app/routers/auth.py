import os
import urllib.parse
import uuid
import secrets
import hashlib
import base64
import httpx
import random
import hmac
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from fastapi import APIRouter, Request, Depends, Body, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import UserWallet, UserSession, EmailCode
from app.services.casdoor import sync_user_to_casdoor

logger = logging.getLogger(__name__)

router = APIRouter()

# --- КОНФИГУРАЦИЯ ---
SITE_URL = os.getenv("SITE_URL", "http://localhost:8081")

VK_CLIENT_ID = os.getenv("VK_CLIENT_ID")
VK_CLIENT_SECRET = os.getenv("VK_CLIENT_SECRET")
VK_REDIRECT_URI = f"{SITE_URL}/callback/vk"

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = f"{SITE_URL}/callback/google-direct"

YANDEX_CLIENT_ID = os.getenv("YANDEX_CLIENT_ID")
YANDEX_CLIENT_SECRET = os.getenv("YANDEX_CLIENT_SECRET")
YANDEX_REDIRECT_URI = f"{SITE_URL}/callback/yandex-direct"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# SMTP Config
SMTP_HOST = os.getenv("SMTP_HOST")
try:
    SMTP_PORT = int(os.getenv("SMTP_PORT", 465))
except:
    SMTP_PORT = 465
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def generate_pkce():
    verifier = secrets.token_urlsafe(32)
    m = hashlib.sha256()
    m.update(verifier.encode('ascii'))
    challenge = base64.urlsafe_b64encode(m.digest()).decode('ascii').rstrip('=')
    return verifier, challenge

def check_telegram_authorization(data: dict, bot_token: str) -> bool:
    if not bot_token: return False
    check_hash = data.get('hash')
    if not check_hash: return False
    data_check_arr = []
    for key, value in data.items():
        if key != 'hash': data_check_arr.append(f'{key}={value}')
    data_check_arr.sort()
    data_check_string = '\n'.join(data_check_arr)
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    hash_calc = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return hash_calc == check_hash

def send_email_via_smtp(to_email, code):
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASSWORD:
        logger.error("SMTP credentials not configured in .env")
        return False
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_USER
        msg['To'] = to_email
        msg['Subject'] = f"Код входа: {code}"
        body = f"<h2>Ваш код для входа: {code}</h2><p>Если вы не запрашивали код, проигнорируйте это письмо.</p>"
        msg.attach(MIMEText(body, 'html'))
        
        if SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT)
        else:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
            server.starttls()
            
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        logger.info(f"Email sent to {to_email}")
        return True
    except Exception as e:
        logger.error(f"SMTP Error: {e}")
        return False

async def finalize_login(data, prefix, db):
    await sync_user_to_casdoor(data, prefix)

def update_session_cookie(response, data, prefix, db):
    full_id = f"{prefix}_{data['id']}"
    try:
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

        new_session_id = str(uuid.uuid4())
        db_session = UserSession(session_id=new_session_id, token=full_id)
        db.add(db_session)
        db.commit()
        
        response.set_cookie(key="session_id", value=new_session_id, httponly=True, samesite="lax")
        return response
    except Exception as e:
        logger.error(f"Login DB error: {e}")
        raise e


# --- МАРШРУТЫ (EMAIL) ---

@router.post("/auth/email/request-code")
async def request_email_code(data: dict = Body(...), db: Session = Depends(get_db)):
    email = data.get("email")
    if not email: return JSONResponse({"error": "No email"}, 400)
    code = str(random.randint(1000,9999))
    db.query(EmailCode).filter_by(email=email).delete()
    db.add(EmailCode(email=email, code=code))
    db.commit()
    if send_email_via_smtp(email, code): return {"status": "ok"}
    return JSONResponse({"error": "SMTP Error. Check logs."}, 500)

@router.post("/auth/email/verify-code")
async def verify_email_code(data: dict = Body(...), db: Session = Depends(get_db)):
    email, code = data.get("email"), data.get("code")
    record = db.query(EmailCode).filter_by(email=email, code=code).first()
    if not record: return JSONResponse({"error": "Bad code"}, 400)
    db.delete(record)
    user_data = {"id": email.replace("@","_"), "email": email, "name": email.split("@")[0], "avatar": "", "phone": ""}
    await finalize_login(user_data, "email", db)
    return update_session_cookie(JSONResponse({"status": "ok"}), user_data, "email", db)


# --- МАРШРУТЫ (OAUTH) ---

@router.get("/login/vk-direct")
def login_vk_direct():
    verifier, challenge = generate_pkce()
    params = {"client_id": VK_CLIENT_ID, "redirect_uri": VK_REDIRECT_URI, "response_type": "code", "scope": "vkid.personal_info email phone", "code_challenge": challenge, "code_challenge_method": "S256", "state": "vk_login"}
    resp = RedirectResponse(f"https://id.vk.com/authorize?{urllib.parse.urlencode(params)}")
    resp.set_cookie("vk_verifier", verifier, httponly=True, samesite="lax")
    return resp

@router.get("/callback/vk")
async def callback_vk(code: str, request: Request, db: Session = Depends(get_db)):
    verifier = request.cookies.get("vk_verifier")
    device_id = request.query_params.get("device_id") or str(uuid.uuid4())
    if not verifier: return RedirectResponse("/login")
    async with httpx.AsyncClient() as client:
        token_resp = await client.post("https://id.vk.com/oauth2/auth", data={"grant_type": "authorization_code", "code": code, "client_id": VK_CLIENT_ID, "client_secret": VK_CLIENT_SECRET, "code_verifier": verifier, "redirect_uri": VK_REDIRECT_URI, "device_id": device_id})
        access_token = token_resp.json().get("access_token")
        if not access_token: return HTMLResponse(f"Error VK: {token_resp.text}")
        user_resp = await client.post("https://id.vk.com/oauth2/user_info", data={"access_token": access_token, "client_id": VK_CLIENT_ID})
        user_info = user_resp.json().get("user", {})
    clean_data = {"id": user_info.get("user_id"), "name": f"{user_info.get('first_name','')}".strip(), "avatar": user_info.get("avatar", ""), "email": user_info.get("email", ""), "phone": user_info.get("phone", "")}
    await finalize_login(clean_data, "vk", db)
    return update_session_cookie(RedirectResponse("/"), clean_data, "vk", db)

@router.get("/callback/telegram")
async def callback_telegram(request: Request, db: Session = Depends(get_db)):
    data = dict(request.query_params)
    if not check_telegram_authorization(data, TELEGRAM_BOT_TOKEN): return JSONResponse({"error": "Auth failed"}, 400)
    clean_data = {"id": data.get("id"), "name": f"{data.get('first_name','')} {data.get('last_name','')}".strip(), "avatar": data.get("photo_url",""), "email": f"tg_{data.get('id')}@no.mail", "phone": ""}
    await finalize_login(clean_data, "telegram", db)
    return update_session_cookie(RedirectResponse("/"), clean_data, "telegram", db)

@router.get("/login/google-direct")
def login_google_direct():
    params = {"client_id": GOOGLE_CLIENT_ID, "redirect_uri": GOOGLE_REDIRECT_URI, "response_type": "code", "scope": "openid email profile", "access_type": "online", "prompt": "select_account"}
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}")

@router.get("/callback/google-direct")
async def callback_google_direct(code: str, db: Session = Depends(get_db)):
    async with httpx.AsyncClient() as client:
        token_resp = await client.post("https://oauth2.googleapis.com/token", data={"client_id": GOOGLE_CLIENT_ID, "client_secret": GOOGLE_CLIENT_SECRET, "code": code, "grant_type": "authorization_code", "redirect_uri": GOOGLE_REDIRECT_URI})
        access_token = token_resp.json().get("access_token")
        user_resp = await client.get("https://www.googleapis.com/oauth2/v3/userinfo", params={"access_token": access_token})
        g_user = user_resp.json()
    unique_login = f"google_{g_user.get('sub')}"
    clean_data = {"id": g_user.get("sub"), "name": g_user.get("name") or unique_login, "avatar": g_user.get("picture"), "email": g_user.get("email"), "phone": ""}
    await finalize_login(clean_data, "google", db)
    return update_session_cookie(RedirectResponse("/"), clean_data, "google", db)

@router.get("/login/yandex-direct")
def login_yandex_direct():
    params = {"client_id": YANDEX_CLIENT_ID, "redirect_uri": YANDEX_REDIRECT_URI, "response_type": "code"}
    return RedirectResponse(f"https://oauth.yandex.ru/authorize?{urllib.parse.urlencode(params)}")

@router.get("/callback/yandex-direct")
async def callback_yandex_direct(code: str, db: Session = Depends(get_db)):
    async with httpx.AsyncClient() as client:
        token_resp = await client.post("https://oauth.yandex.ru/token", data={"grant_type": "authorization_code", "code": code, "client_id": YANDEX_CLIENT_ID, "client_secret": YANDEX_CLIENT_SECRET})
        access_token = token_resp.json().get("access_token")
        user_resp = await client.get("https://login.yandex.ru/info?format=json", headers={"Authorization": f"OAuth {access_token}"})
        y_user = user_resp.json()
    avatar_id = y_user.get("default_avatar_id")
    clean_data = {"id": y_user.get("id"), "name": y_user.get("display_name") or y_user.get("real_name"), "avatar": f"https://avatars.yandex.net/get-yapic/{avatar_id}/islands-200" if avatar_id else "", "email": y_user.get("default_email"), "phone": ""}
    await finalize_login(clean_data, "yandex", db)
    return update_session_cookie(RedirectResponse("/"), clean_data, "yandex", db)

@router.get("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    session_id = request.cookies.get("session_id")
    if session_id:
        db.query(UserSession).filter_by(session_id=session_id).delete()
        db.commit()
    resp = RedirectResponse("/login")
    resp.delete_cookie("session_id")
    resp.delete_cookie("vk_verifier")
    return resp