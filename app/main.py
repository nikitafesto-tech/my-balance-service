import logging
import sys
import os

from fastapi import FastAPI, Request, Depends, HTTPException, Body, UploadFile, File
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

# ЮKassa
from yookassa import Configuration, Payment as YooPayment

# === ИМПОРТ РОУТЕРОВ ===
from app.routers import chats, auth

# === ИМПОРТ ЗАВИСИМОСТЕЙ ===
from app.dependencies import get_current_user
from app.services.casdoor import update_casdoor_balance
from app.services.s3 import upload_file_to_s3

# === ИМПОРТЫ БАЗЫ ===
from app.database import engine, get_db, Base
from app.models import UserWallet, UserSession, Payment

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

# === ПОДКЛЮЧАЕМ РОУТЕРЫ ===
app.include_router(chats.router)
app.include_router(auth.router)

# ЮKassa Config
if os.getenv("YOOKASSA_SHOP_ID"):
    Configuration.account_id = os.getenv("YOOKASSA_SHOP_ID")
    Configuration.secret_key = os.getenv("YOOKASSA_SECRET_KEY")

# ==================== МАРШРУТЫ СТРАНИЦ (UI) ====================

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

@app.post("/api/upload")
async def upload_file(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user: raise HTTPException(401)
    
    content = await file.read()
    url = await upload_file_to_s3(content, file.filename, file.content_type)
    
    if not url: raise HTTPException(500, "S3 Upload Failed")
    return {"url": url, "filename": file.filename}

# ==================== ПЛАТЕЖИ (Остаются здесь пока) ====================

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