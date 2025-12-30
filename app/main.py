import logging
import sys
import os

from fastapi import FastAPI, Request, Depends, HTTPException, UploadFile, File
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
# ВАЖНО: Добавлен импорт для обработки HTTP ошибок (404)
from starlette.exceptions import HTTPException as StarletteHTTPException

# === ИМПОРТ РОУТЕРОВ ===
from app.routers import chats, auth, payments

# === ИМПОРТ ЗАВИСИМОСТЕЙ ===
from app.dependencies import get_current_user
from app.services.s3 import upload_file_to_s3

# === ИМПОРТЫ БАЗЫ ===
from app.database import engine, get_db, Base
# ДОБАВЛЕНО: Chat (нужен для поиска чата по токену)
from app.models import UserWallet, UserSession, Chat

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

# === ОБРАБОТЧИК ОШИБОК 404 (НОВОЕe) ===
@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        # Если запрос идет к API (например, фронтенд стучится), отдаем JSON
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        # Если это обычный пользователь в браузере — показываем красивую страницу
        return templates.TemplateResponse("404.html", {"request": request}, status_code=404)
    # Остальные ошибки (401, 403 и т.д.) отдаем как есть
    return JSONResponse({"detail": str(exc.detail)}, status_code=exc.status_code)

# GLOBAL ERROR HANDLER (500)
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global Error: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"message": "Internal Server Error", "detail": str(exc)})

# === ПОДКЛЮЧАЕМ РОУТЕРЫ ===
app.include_router(chats.router)
app.include_router(auth.router)
app.include_router(payments.router)

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

# === НОВЫЙ МАРШРУТ: Публичный доступ к чату ===
@app.get("/share/{token}")
def shared_chat_page(token: str, request: Request, db: Session = Depends(get_db)):
    """Страница просмотра расшаренного чата (публичная)"""
    chat = db.query(Chat).filter_by(share_token=token).first()
    
    if not chat:
        # Используем стандартный обработчик 404
        raise StarletteHTTPException(status_code=404, detail="Chat not found")
        
    # Сериализуем сообщения для шаблона
    messages = []
    for m in chat.messages:
        messages.append({
            "role": m.role,
            "content": m.content,
            "image_url": m.image_url,
            "attachment_url": m.attachment_url
        })

    return templates.TemplateResponse("shared_chat.html", {
        "request": request,
        "title": chat.title,
        "date": chat.created_at.strftime("%d.%m.%Y"),
        "messages": messages,
        "model_name": chat.model
    })

@app.post("/api/upload")
async def upload_file(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user: raise HTTPException(401)
    
    content = await file.read()
    url = await upload_file_to_s3(content, file.filename, file.content_type)
    
    if not url: raise HTTPException(500, "S3 Upload Failed")
    return {"url": url, "filename": file.filename}