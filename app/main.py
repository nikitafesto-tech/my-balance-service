import logging
import sys
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
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from fastapi import FastAPI, Request, Depends, HTTPException, Form, Body, UploadFile, File
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import desc

# ЮKassa
from yookassa import Configuration, Payment as YooPayment

# === ИМПОРТЫ ДЛЯ ИИ ===
from app.services.ai_generation import generate_ai_response

# === ИМПОРТЫ ИЗ ВАШИХ МОДУЛЕЙ ===
from app.database import engine, get_db, Base
from app.models import UserWallet, UserSession, Payment, EmailCode, Chat, Message
from app.services.s3 import upload_file_to_s3

# --- ЛОГИРОВАНИЕ ---
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

# --- ИНИЦИАЛИЗАЦИЯ ---
Base.metadata.create_all(bind=engine)
app = FastAPI()

# --- ПУТИ ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

templates = Jinja2Templates(directory=TEMPLATES_DIR)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global Error: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"message": "Internal Server Error", "detail": str(exc)})

# --- CONFIG ---
SITE_URL = os.getenv("SITE_URL", "http://localhost:8081")
AUTH_URL = os.getenv("AUTH_URL", "http://localhost:8000")

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
CASDOOR_CLIENT_ID = os.getenv("CASDOOR_CLIENT_ID")
CASDOOR_CLIENT_SECRET = os.getenv("CASDOOR_CLIENT_SECRET")

# SMTP
SMTP_HOST = os.getenv("SMTP_HOST")
try:
    SMTP_PORT = int(os.getenv("SMTP_PORT", 465))
except:
    SMTP_PORT = 465
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

# ЮKassa
if os.getenv("YOOKASSA_SHOP_ID"):
    Configuration.account_id = os.getenv("YOOKASSA_SHOP_ID")
    Configuration.secret_key = os.getenv("YOOKASSA_SECRET_KEY")

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def get_current_user(request: Request, db: Session):
    session_id = request.cookies.get("session_id")
    if not session_id: return None
    sess = db.query(UserSession).filter_by(session_id=session_id).first()
    if not sess: return None
    return db.query(UserWallet).filter_by(casdoor_id=sess.token).first()

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
    if not SMTP_HOST: return False
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_USER
        msg['To'] = to_email
        msg['Subject'] = f"Код входа: {code}"
        body = f"<h2>Ваш код: {code}</h2>"
        msg.attach(MIMEText(body, 'html'))
        server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT)
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        logger.error(f"SMTP Error: {e}")
        return False

# --- CASDOOR SYNC ---

async def sync_user_to_casdoor(user_data, provider_prefix):
    user_id = str(user_data.get("id"))
    full_name = user_data.get("name") or f"User {user_id}"
    casdoor_username = f"{provider_prefix}_{user_id}"
    
    casdoor_user = {
        "owner": "users", "name": casdoor_username, "displayName": full_name,
        "avatar": user_data.get("avatar", ""), "email": user_data.get("email", ""),
        "phone": user_data.get("phone", ""), "id": user_id, "type": "normal-user",
        "properties": {"oauth_Source": provider_prefix}, "signupApplication": "Myservice"
    }
    
    api_url_add = "http://casdoor:8000/api/add-user"
    api_url_update = "http://casdoor:8000/api/update-user"
    
    async with httpx.AsyncClient() as client:
        try:
            auth = (CASDOOR_CLIENT_ID, CASDOOR_CLIENT_SECRET)
            resp = await client.post(api_url_add, json=casdoor_user, auth=auth)
            if resp.status_code != 200 or resp.json().get('status') != 'ok':
                await client.post(api_url_update, json=casdoor_user, auth=auth)
        except Exception as e:
            logger.error(f"Casdoor Sync Error: {e}")
    return casdoor_username

async def update_casdoor_balance(user_id, new_balance):
    full_id = f"users/{user_id}"
    api_base = "http://casdoor:8000"
    auth = (CASDOOR_CLIENT_ID, CASDOOR_CLIENT_SECRET)
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{api_base}/api/get-user?id={full_id}", auth=auth)
            if resp.status_code != 200: return
            
            user_data = resp.json().get('data')
            if not user_data: return
            
            user_data['balance'] = float(new_balance)
            user_data['balanceCurrency'] = "RUB"
            
            await client.post(f"{api_base}/api/update-user?id={full_id}", json=user_data, auth=auth)
        except Exception as e:
            logger.error(f"Casdoor Balance Update Error: {e}")

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

# ==================== МАРШРУТЫ (PAGES) ====================

@app.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login")
    
    return templates.TemplateResponse("chat.html", {
        "request": request,
        "name": user.name,
        "email": user.email,
        "balance": int(user.balance),
        "avatar": user.avatar,
        "user_id": user.casdoor_id
    })

@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse("signin.html", {"request": request})

@app.get("/profile")
def profile(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user: return RedirectResponse("/login")
    return templates.TemplateResponse("profile.html", {
        "request": request,
        "name": user.name, 
        "balance": int(user.balance), 
        "email": user.email,
        "avatar": user.avatar
    })

@app.get("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    session_id = request.cookies.get("session_id")
    if session_id:
        db.query(UserSession).filter_by(session_id=session_id).delete()
        db.commit()
    resp = RedirectResponse("/login")
    resp.delete_cookie("session_id")
    resp.delete_cookie("vk_verifier")
    return resp

# ==================== API ЧАТОВ (UPDATED) ====================

@app.get("/api/chats")
def get_chats(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user: raise HTTPException(401)
    
    chats = db.query(Chat).filter_by(user_casdoor_id=user.casdoor_id)\
        .order_by(desc(Chat.updated_at)).all()
    
    return [{"id": c.id, "title": c.title, "date": c.updated_at.isoformat()} for c in chats]

@app.get("/api/chats/{chat_id}")
def get_chat_history(chat_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user: raise HTTPException(401)
    
    chat = db.query(Chat).filter_by(id=chat_id, user_casdoor_id=user.casdoor_id).first()
    if not chat: raise HTTPException(404, "Chat not found")
    
    messages = []
    for m in chat.messages:
        messages.append({
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "image_url": m.image_url,
            "attachment_url": m.attachment_url
        })
    return messages

@app.post("/api/chats/new")
async def create_new_chat(request: Request, data: dict = Body(...), db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user: raise HTTPException(401)
    
    first_msg = data.get("message", "New Chat")
    selected_model = data.get("model", "gpt-4o")
    # Новые параметры от фронтенда
    temperature = data.get("temperature", 0.7)
    web_search = data.get("web_search", False)
    attachment_url = data.get("attachment_url") # <--- ФОТО
    
    title = first_msg[:30] + "..." if len(first_msg) > 30 else first_msg
    
    new_chat = Chat(user_casdoor_id=user.casdoor_id, title=title, model=selected_model)
    db.add(new_chat)
    db.commit()
    db.refresh(new_chat)
    
    msg = Message(chat_id=new_chat.id, role="user", content=first_msg)
    if attachment_url:
        msg.attachment_url = attachment_url
    db.add(msg)
    db.commit()
    
    cost = 0.0
    try:
        # Вызываем ИИ, передаем все параметры (включая attachment_url)
        ai_reply, cost = await generate_ai_response(
            selected_model, 
            [{"role": "user", "content": first_msg}], 
            user.balance,
            temperature=temperature,
            web_search=web_search,
            attachment_url=attachment_url
        )
    except HTTPException as e:
        ai_reply = f"⚠️ {e.detail}"
    except Exception as e:
        ai_reply = f"Ошибка: {str(e)}"

    # Списание денег
    if cost > 0:
        user.balance -= cost
        if user.balance < 0: user.balance = 0
        db.add(user)
        db.commit()
        await update_casdoor_balance(user.casdoor_id, user.balance)

    bot_msg = Message(chat_id=new_chat.id, role="assistant", content=ai_reply)
    # Если это сгенерированная картинка/видео, ссылка придет в тексте Markdown
    if ai_reply.startswith("![") and "[Generated]" in ai_reply:
        try:
            bot_msg.image_url = ai_reply.split("(")[1].split(")")[0]
        except: pass

    db.add(bot_msg)
    db.commit()
    
    return {"chat_id": new_chat.id, "title": title, "messages": [
        {"role": "user", "content": first_msg, "attachment_url": attachment_url},
        {"role": "assistant", "content": ai_reply, "image_url": bot_msg.image_url}
    ]}

@app.post("/api/chats/{chat_id}/message")
async def chat_reply(chat_id: int, request: Request, data: dict = Body(...), db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user: raise HTTPException(401)

    chat = db.query(Chat).filter_by(id=chat_id, user_casdoor_id=user.casdoor_id).first()
    if not chat: raise HTTPException(404, "Chat not found")

    user_text = data.get("message")
    temperature = data.get("temperature", 0.7)
    web_search = data.get("web_search", False)
    attachment_url = data.get("attachment_url")
    
    user_msg = Message(chat_id=chat.id, role="user", content=user_text)
    if attachment_url:
        user_msg.attachment_url = attachment_url
    db.add(user_msg)
    chat.updated_at = datetime.utcnow()
    db.commit()

    last_messages = db.query(Message).filter_by(chat_id=chat.id).order_by(Message.id.desc()).limit(10).all()
    last_messages.reverse()
    
    messages_payload = [{"role": "system", "content": "You are a helpful assistant."}]
    for m in last_messages:
        messages_payload.append({"role": m.role, "content": m.content or ""})

    cost = 0.0
    try:
        ai_reply, cost = await generate_ai_response(
            chat.model, 
            messages_payload, 
            user.balance, 
            temperature=temperature,
            web_search=web_search,
            attachment_url=attachment_url
        )
    except HTTPException as e:
        ai_reply = f"⚠️ {e.detail}"
    except Exception as e:
        ai_reply = f"Ошибка: {str(e)}"
    
    if cost > 0:
        user.balance -= cost
        if user.balance < 0: user.balance = 0
        db.add(user)
        db.commit()
        await update_casdoor_balance(user.casdoor_id, user.balance)

    bot_msg = Message(chat_id=chat.id, role="assistant", content=ai_reply)
    if ai_reply.startswith("![") and "[Generated]" in ai_reply:
        try:
            bot_msg.image_url = ai_reply.split("(")[1].split(")")[0]
        except: pass
        
    db.add(bot_msg)
    db.commit()

    return {
        "chat_id": chat.id,
        "messages": [
            {"role": "user", "content": user_text, "attachment_url": attachment_url},
            {"role": "assistant", "content": ai_reply, "image_url": bot_msg.image_url}
        ]
    }

@app.post("/api/upload")
async def upload_file(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Загрузка в S3"""
    user = get_current_user(request, db)
    if not user: raise HTTPException(401)
    
    content = await file.read()
    # Эта функция теперь возвращает безопасное имя файла
    url = await upload_file_to_s3(content, file.filename, file.content_type)
    
    if not url: raise HTTPException(500, "S3 Upload Failed")
    return {"url": url, "filename": file.filename}

# ==================== ОПЛАТА И AUTH (БЕЗ ИЗМЕНЕНИЙ) ====================

@app.post("/auth/email/request-code")
async def request_email_code(data: dict = Body(...), db: Session = Depends(get_db)):
    email = data.get("email")
    if not email: return JSONResponse({"error": "No email"}, 400)
    code = str(random.randint(1000,9999))
    db.query(EmailCode).filter_by(email=email).delete()
    db.add(EmailCode(email=email, code=code))
    db.commit()
    if send_email_via_smtp(email, code): return {"status": "ok"}
    return JSONResponse({"error": "SMTP Error"}, 500)

@app.post("/auth/email/verify-code")
async def verify_email_code(data: dict = Body(...), db: Session = Depends(get_db)):
    email, code = data.get("email"), data.get("code")
    record = db.query(EmailCode).filter_by(email=email, code=code).first()
    if not record: return JSONResponse({"error": "Bad code"}, 400)
    db.delete(record)
    user_data = {"id": email.replace("@","_"), "email": email, "name": email.split("@")[0], "avatar": "", "phone": ""}
    await finalize_login(user_data, "email", db)
    return update_session_cookie(JSONResponse({"status": "ok"}), user_data, "email", db)

@app.post("/payment/create")
async def create_payment(request: Request, data: dict = Body(...), db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user: raise HTTPException(401)
    amount = data.get("amount")
    try:
        payment = YooPayment.create({
            "amount": {"value": str(amount), "currency": "RUB"},
            "confirmation": {"type": "embedded"},
            "capture": True,
            "description": f"Пополнение {user.email}",
            "metadata": {"user_id": user.casdoor_id}
        })
        db.add(Payment(yookassa_payment_id=payment.id, user_id=user.casdoor_id, amount=float(amount)))
        db.commit()
        return {"confirmation_token": payment.confirmation.confirmation_token}
    except Exception as e:
        return JSONResponse({"error": str(e)}, 500)

@app.post("/api/payment/webhook")
async def payment_webhook(request: Request, db: Session = Depends(get_db)):
    try:
        event = await request.json()
        if event['event'] == 'payment.succeeded':
            obj = event['object']
            db_pay = db.query(Payment).filter_by(yookassa_payment_id=obj['id']).first()
            if db_pay and db_pay.status != "succeeded":
                db_pay.status = "succeeded"
                wallet = db.query(UserWallet).filter_by(casdoor_id=db_pay.user_id).first()
                if wallet:
                    wallet.balance += db_pay.amount
                    await update_casdoor_balance(db_pay.user_id, wallet.balance)
                db.commit()
        return {"status": "ok"}
    except:
        return JSONResponse({"status": "error"}, 500)

# === CALLBACKS (VK, GOOGLE, YANDEX, TG) ===

@app.get("/login/vk-direct")
def login_vk_direct():
    verifier, challenge = generate_pkce()
    params = {"client_id": VK_CLIENT_ID, "redirect_uri": VK_REDIRECT_URI, "response_type": "code", "scope": "vkid.personal_info email phone", "code_challenge": challenge, "code_challenge_method": "S256", "state": "vk_login"}
    resp = RedirectResponse(f"https://id.vk.com/authorize?{urllib.parse.urlencode(params)}")
    resp.set_cookie("vk_verifier", verifier, httponly=True, samesite="lax")
    return resp

@app.get("/callback/vk")
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

@app.get("/callback/telegram")
async def callback_telegram(request: Request, db: Session = Depends(get_db)):
    data = dict(request.query_params)
    if not check_telegram_authorization(data, TELEGRAM_BOT_TOKEN): return JSONResponse({"error": "Auth failed"}, 400)
    clean_data = {"id": data.get("id"), "name": f"{data.get('first_name','')} {data.get('last_name','')}".strip(), "avatar": data.get("photo_url",""), "email": f"tg_{data.get('id')}@no.mail", "phone": ""}
    await finalize_login(clean_data, "telegram", db)
    return update_session_cookie(RedirectResponse("/"), clean_data, "telegram", db)

@app.get("/login/google-direct")
def login_google_direct():
    params = {"client_id": GOOGLE_CLIENT_ID, "redirect_uri": GOOGLE_REDIRECT_URI, "response_type": "code", "scope": "openid email profile", "access_type": "online", "prompt": "select_account"}
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}")

@app.get("/callback/google-direct")
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

@app.get("/login/yandex-direct")
def login_yandex_direct():
    params = {"client_id": YANDEX_CLIENT_ID, "redirect_uri": YANDEX_REDIRECT_URI, "response_type": "code"}
    return RedirectResponse(f"https://oauth.yandex.ru/authorize?{urllib.parse.urlencode(params)}")

@app.get("/callback/yandex-direct")
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