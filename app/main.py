import logging
import sys
from fastapi import FastAPI, Request, Depends, HTTPException, Form, Body
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, Column, Integer, String, Float, Text, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base, Session
import os
import urllib.parse
import uuid
import secrets
import hashlib
import base64
import httpx
from datetime import datetime
import json
import smtplib
import random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import hmac # <--- ДОБАВЛЕНО ДЛЯ TELEGRAM

# === ЮKassa ===
from yookassa import Configuration, Payment as YooPayment

# --- НАСТРОЙКА ЛОГИРОВАНИЯ ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

app = FastAPI()

# --- ПУТИ ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

if os.path.exists(STATIC_DIR):
    logger.info(f"Папка static найдена: {STATIC_DIR}")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
else:
    logger.error(f"CRITICAL: Папка static НЕ найдена по пути: {STATIC_DIR}")

templates = Jinja2Templates(directory=TEMPLATES_DIR)

# --- ПЕРЕХВАТ ОШИБОК 500 ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Глобальная ошибка при обработке {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"message": "Internal Server Error", "detail": str(exc)},
    )

# --- НАСТРОЙКИ ---
SITE_URL = os.getenv("SITE_URL", "http://localhost:8081")
AUTH_URL = os.getenv("AUTH_URL", "http://localhost:8000")

logger.info(f"Запуск с настройками: SITE_URL={SITE_URL}, AUTH_URL={AUTH_URL}")

VK_CLIENT_ID = os.getenv("VK_CLIENT_ID")
VK_CLIENT_SECRET = os.getenv("VK_CLIENT_SECRET")
VK_REDIRECT_URI = f"{SITE_URL}/callback/vk"

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = f"{SITE_URL}/callback/google-direct"

YANDEX_CLIENT_ID = os.getenv("YANDEX_CLIENT_ID")
YANDEX_CLIENT_SECRET = os.getenv("YANDEX_CLIENT_SECRET")
YANDEX_REDIRECT_URI = f"{SITE_URL}/callback/yandex-direct"

# <--- TELEGRAM TOKEN --->
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

CASDOOR_CLIENT_ID = os.getenv("CASDOOR_CLIENT_ID")
CASDOOR_CLIENT_SECRET = os.getenv("CASDOOR_CLIENT_SECRET")

# === НАСТРОЙКИ ЮKASSA ===
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")

if YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY:
    Configuration.account_id = YOOKASSA_SHOP_ID
    Configuration.secret_key = YOOKASSA_SECRET_KEY
    logger.info("ЮKassa успешно настроена")
else:
    logger.warning("Нет ключей ЮKassa! Платежи работать не будут.")

# === НАСТРОЙКИ ПОЧТЫ (SMTP) ===
SMTP_HOST = os.getenv("SMTP_HOST")
# Важно: преобразуем порт в int, иначе будет ошибка
try:
    SMTP_PORT = int(os.getenv("SMTP_PORT", 465))
except ValueError:
    SMTP_PORT = 465
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

# --- БАЗА ДАННЫХ ---
DB_URL = os.getenv("DB_URL", "sqlite:///./test.db")
logger.info(f"Подключение к БД: {DB_URL}")

try:
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

    class Payment(Base):
        __tablename__ = "payments"
        id = Column(Integer, primary_key=True, index=True)
        yookassa_payment_id = Column(String, unique=True, index=True)
        user_id = Column(String, index=True)
        amount = Column(Float)
        status = Column(String, default="pending")
        description = Column(String, nullable=True)
        created_at = Column(DateTime, default=datetime.utcnow)
        
    # Таблица для кодов почты
    class EmailCode(Base):
        __tablename__ = "email_codes"
        id = Column(Integer, primary_key=True, index=True)
        email = Column(String, index=True)
        code = Column(String)
        created_at = Column(DateTime, default=datetime.utcnow)

    Base.metadata.create_all(bind=engine)
    logger.info("Таблицы в БД успешно созданы/проверены")
except Exception as e:
    logger.critical(f"Ошибка подключения к БД: {e}", exc_info=True)

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

# <--- TELEGRAM CHECK FUNCTION --->
def check_telegram_authorization(data: dict, bot_token: str) -> bool:
    if not bot_token:
        return False
    
    check_hash = data.get('hash')
    if not check_hash:
        return False
    
    # Сортируем параметры по алфавиту и собираем строку
    data_check_arr = []
    for key, value in data.items():
        if key != 'hash':
            data_check_arr.append(f'{key}={value}')
    data_check_arr.sort()
    data_check_string = '\n'.join(data_check_arr)
    
    # Вычисляем HMAC
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    hash_calc = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    
    return hash_calc == check_hash

# Функция отправки письма (ИСПРАВЛЕННАЯ)
def send_email_via_smtp(to_email, code):
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASSWORD:
        logger.error("Настройки SMTP не заполнены в .env!")
        return False
    
    try:
        logger.info(f"Попытка отправки письма на {to_email} через {SMTP_HOST}:{SMTP_PORT}")
        
        msg = MIMEMultipart()
        msg['From'] = SMTP_USER
        msg['To'] = to_email
        msg['Subject'] = f"Код входа: {code}"
        
        body = f"""
        <html>
          <body style="font-family: Arial, sans-serif; background-color: #f4f4f4; padding: 20px;">
            <div style="max-width: 500px; margin: 0 auto; background: #fff; padding: 30px; border-radius: 10px; text-align: center;">
               <h2 style="color: #333;">Вход в MyService</h2>
               <div style="font-size: 32px; font-weight: bold; letter-spacing: 5px; color: #27ae60; margin: 20px 0;">
                  {code}
               </div>
               <p style="font-size: 12px; color: #999;">Никому не сообщайте этот код.</p>
            </div>
          </body>
        </html>
        """
        msg.attach(MIMEText(body, 'html'))
        
        # Используем SMTP_SSL для порта 465 (Mail.ru / Yandex / VK Work)
        server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT)
        # server.set_debuglevel(1) # Раскомментируй для глубокого дебага в консоли
        
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        logger.info(f"✅ Письмо успешно отправлено на {to_email}")
        return True
        
    except smtplib.SMTPAuthenticationError:
        logger.error("❌ Ошибка авторизации SMTP! Проверьте логин (полный email) и Пароль Приложения.")
        return False
    except Exception as e:
        logger.error(f"❌ Общая ошибка отправки письма: {e}", exc_info=True)
        return False

async def sync_user_to_casdoor(user_data, provider_prefix):
    logger.info(f"Начинаем синхронизацию юзера {user_data.get('id')} ({provider_prefix})")
    
    user_id = str(user_data.get("id"))
    full_name = user_data.get("name") or f"User {user_id}"
    casdoor_username = f"{provider_prefix}_{user_id}"
    
    casdoor_user = {
        "owner": "users",
        "name": casdoor_username,
        "displayName": full_name,
        "avatar": user_data.get("avatar", ""),
        "email": user_data.get("email", ""),
        "phone": user_data.get("phone", ""),
        "id": user_id,
        "type": "normal-user",
        "properties": {
            "oauth_Source": provider_prefix
        },
        "signupApplication": "Myservice"
    }

    api_url_add = "http://casdoor:8000/api/add-user"
    api_url_update = "http://casdoor:8000/api/update-user"
    
    async with httpx.AsyncClient() as client:
        try:
            auth = (CASDOOR_CLIENT_ID, CASDOOR_CLIENT_SECRET)
            resp = await client.post(api_url_add, json=casdoor_user, auth=auth)
            
            if resp.status_code != 200 or resp.json().get('status') != 'ok':
                resp = await client.post(api_url_update, json=casdoor_user, auth=auth)
                
        except Exception as e:
            logger.error(f"Ошибка синхронизации с Casdoor: {e}", exc_info=True)
    
    return casdoor_username

async def update_casdoor_balance(user_id, new_balance):
    owner = "users" 
    full_id = f"{owner}/{user_id}"
    api_base = "http://casdoor:8000"
    api_get = f"{api_base}/api/get-user?id={full_id}"
    api_update = f"{api_base}/api/update-user"
    auth = (CASDOOR_CLIENT_ID, CASDOOR_CLIENT_SECRET)

    async with httpx.AsyncClient() as client:
        try:
            resp_get = await client.get(api_get, auth=auth)
            if resp_get.status_code != 200:
                return

            user_data = resp_get.json().get('data')
            if not user_data:
                return

            user_data['balance'] = float(new_balance)
            user_data['balanceCurrency'] = "RUB"

            resp_update = await client.post(f"{api_update}?id={full_id}", json=user_data, auth=auth)
            
            if resp_update.json().get('status') != 'ok':
                user_data['score'] = int(new_balance)
                await client.post(f"{api_update}?id={full_id}", json=user_data, auth=auth)

        except Exception as e:
            logger.error(f"Ошибка связи с Casdoor: {e}")

async def finalize_login(data, prefix, db):
    await sync_user_to_casdoor(data, prefix)

def update_session_cookie(response, data, prefix, db):
    full_id = f"{prefix}_{data['id']}"
    logger.info(f"Сохраняем сессию для: {full_id}")
    
    try:
        wallet = db.query(UserWallet).filter(UserWallet.casdoor_id == full_id).first()
        if not wallet:
            logger.info("Создаем новый кошелек")
            wallet = UserWallet(
                casdoor_id=full_id, email=data['email'], name=data['name'], 
                avatar=data['avatar'], phone=data['phone'], balance=0.0
            )
            db.add(wallet)
        else:
            logger.info("Обновляем существующий кошелек")
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
        logger.error(f"Ошибка при сохранении в БД: {e}", exc_info=True)
        raise e

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

# === АВТОРИЗАЦИЯ ПО EMAIL (МАРШРУТЫ) ===
@app.post("/auth/email/request-code")
async def request_email_code(data: dict = Body(...), db: Session = Depends(get_db)):
    email = data.get("email")
    if not email or "@" not in email:
        return JSONResponse({"error": "Некорректный Email"}, status_code=400)
    
    code = str(random.randint(1000, 9999))
    
    db.query(EmailCode).filter(EmailCode.email == email).delete()
    new_code = EmailCode(email=email, code=code)
    db.add(new_code)
    db.commit()
    
    success = send_email_via_smtp(email, code)
    if not success:
        # Важно: клиенту возвращаем 500, чтобы он видел ошибку
        return JSONResponse({"error": "Ошибка отправки письма. Проверьте логи сервера."}, status_code=500)
        
    return JSONResponse({"status": "ok", "message": "Code sent"})

@app.post("/auth/email/verify-code")
async def verify_email_code(data: dict = Body(...), db: Session = Depends(get_db)):
    email = data.get("email")
    code = data.get("code")
    
    if not email or not code:
        return JSONResponse({"error": "Введите email и код"}, status_code=400)
        
    record = db.query(EmailCode).filter(EmailCode.email == email, EmailCode.code == code).first()
    if not record:
        return JSONResponse({"error": "Неверный код"}, status_code=400)
        
    db.delete(record)
    db.commit()
    
    clean_id = email.replace("@", "_").replace(".", "_")
    user_data = {
        "id": clean_id,
        "email": email,
        "name": email.split("@")[0],
        "avatar": "",
        "phone": ""
    }
    await finalize_login(user_data, "email", db)
    return update_session_cookie(JSONResponse({"status": "ok"}), user_data, "email", db)

# --- ПЛАТЕЖИ ---
@app.post("/payment/create")
async def create_payment(request: Request, data: dict = Body(...), db: Session = Depends(get_db)):
    amount = data.get("amount")
    session_id = request.cookies.get("session_id")
    if not session_id: raise HTTPException(status_code=401)
    db_session = db.query(UserSession).filter(UserSession.session_id == session_id).first()
    if not db_session: raise HTTPException(status_code=401)
    user_id = db_session.token 
    try:
        payment = YooPayment.create({
            "amount": {"value": str(amount), "currency": "RUB"},
            "confirmation": {"type": "embedded"},
            "capture": True,
            "description": f"Пополнение для {user_id}",
            "metadata": {"user_id": user_id}
        })
        new_payment = Payment(yookassa_payment_id=payment.id, user_id=user_id, amount=float(amount))
        db.add(new_payment)
        db.commit()
        return JSONResponse({"confirmation_token": payment.confirmation.confirmation_token})
    except Exception as e:
        logger.error(f"Error payment: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/payment/webhook")
async def payment_webhook(request: Request, db: Session = Depends(get_db)):
    try:
        event_json = await request.json()
        if event_json['event'] == 'payment.succeeded':
            payment_data = event_json['object']
            yookassa_id = payment_data['id']
            amount = float(payment_data['amount']['value'])
            user_id = payment_data['metadata'].get('user_id')
            db_payment = db.query(Payment).filter(Payment.yookassa_payment_id == yookassa_id).first()
            if db_payment and db_payment.status == "succeeded": return JSONResponse({"status": "ok"})
            if db_payment: db_payment.status = "succeeded"
            else:
                db_payment = Payment(yookassa_payment_id=yookassa_id, user_id=user_id, amount=amount, status="succeeded")
                db.add(db_payment)
            if user_id:
                wallet = db.query(UserWallet).filter(UserWallet.casdoor_id == user_id).first()
                if wallet:
                    wallet.balance += amount
                    await update_casdoor_balance(user_id, wallet.balance)
            db.commit()
        return JSONResponse({"status": "ok"})
    except Exception:
        return JSONResponse({"status": "error"}, status_code=500)

# --- VK (С ДЕБАГОМ) ---
@app.get("/login/vk-direct")
def login_vk_direct():
    verifier, challenge = generate_pkce()
    params = {"client_id": VK_CLIENT_ID, "redirect_uri": VK_REDIRECT_URI, "response_type": "code", "scope": "vkid.personal_info email phone", "code_challenge": challenge, "code_challenge_method": "S256", "state": "vk_login"}
    response = RedirectResponse(f"https://id.vk.com/authorize?{urllib.parse.urlencode(params)}")
    response.set_cookie("vk_verifier", verifier, httponly=True, samesite="lax")
    return response

@app.get("/callback/vk")
async def callback_vk(code: str, request: Request, db: Session = Depends(get_db)):
    logger.info("Получен callback от VK")
    verifier = request.cookies.get("vk_verifier")
    device_id = request.query_params.get("device_id") or str(uuid.uuid4())
    if not verifier: return RedirectResponse("/login")
    
    async with httpx.AsyncClient() as client:
        # Шаг 1: Получение токена
        token_resp = await client.post("https://id.vk.com/oauth2/auth", data={
            "grant_type": "authorization_code", "code": code,
            "client_id": VK_CLIENT_ID, "client_secret": VK_CLIENT_SECRET,
            "code_verifier": verifier, "redirect_uri": VK_REDIRECT_URI, "device_id": device_id
        })
        token_data = token_resp.json()
        logger.info(f"VK Token Response: {token_data}") # <-- Логируем ответ токена
        
        access_token = token_data.get("access_token")
        if not access_token:
            logger.error(f"Ошибка получения токена VK. Тело ответа: {token_data}")
            return HTMLResponse(f"Ошибка VK: {token_data}")

        # Шаг 2: Получение данных пользователя
        user_resp = await client.post("https://id.vk.com/oauth2/user_info", data={"access_token": access_token, "client_id": VK_CLIENT_ID})
        user_json = user_resp.json()
        logger.info(f"VK User Info Response: {user_json}") # <-- Логируем данные юзера
        
        user_info = user_json.get("user", {})
        if not user_info:
             logger.error("VK не вернул объект user. Возможно, scope не тот.")
             # Fallback: иногда VK возвращает данные сразу в корне, если это старый API
             # Но для vkid мы ожидаем ключ 'user'

    clean_data = {
        "id": user_info.get("user_id"), 
        "name": f"{user_info.get('first_name','')}".strip(), # Берем хотя бы имя
        "avatar": user_info.get("avatar", ""),
        "email": user_info.get("email", ""),
        "phone": user_info.get("phone", "")
    }
    
    await finalize_login(clean_data, "vk", db)
    return update_session_cookie(RedirectResponse("/"), clean_data, "vk", db)

# --- TELEGRAM ---
@app.get("/callback/telegram")
async def callback_telegram(request: Request, db: Session = Depends(get_db)):
    # 1. Получаем все параметры, которые прислал Telegram, в виде словаря
    # Это решает проблему с last_name и любыми другими полями
    data = dict(request.query_params)
    
    # 2. Проверяем хеш
    if not check_telegram_authorization(data, TELEGRAM_BOT_TOKEN):
        logger.error(f"Telegram auth failed. Data: {data}")
        return JSONResponse({"error": "Invalid Telegram hash"}, status_code=400)
        
    # 3. Формируем данные пользователя для нашей базы
    # Берем то, что есть, или ставим пустые строки
    tg_id = data.get("id")
    first_name = data.get("first_name", "")
    last_name = data.get("last_name", "")
    username = data.get("username", "")
    photo_url = data.get("photo_url", "")
    
    # Собираем полное имя
    full_name = f"{first_name} {last_name}".strip() or f"user_{tg_id}"
    
    clean_data = {
        "id": tg_id,
        "name": full_name,
        "avatar": photo_url,
        "email": f"telegram_{tg_id}@noemail.com", # Email-заглушка
        "phone": "" 
    }
    
    await finalize_login(clean_data, "telegram", db)
    return update_session_cookie(RedirectResponse("/"), clean_data, "telegram", db)

# --- GOOGLE/YANDEX (Без изменений) ---
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