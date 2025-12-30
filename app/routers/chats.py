from fastapi import APIRouter, Request, Depends, HTTPException, Body
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_
from datetime import datetime, timedelta
import json
import logging
import uuid

from app.database import get_db, SessionLocal
from app.models import UserWallet, Chat, Message
from app.dependencies import get_current_user
# Импортируем get_models_config из нашего нового единого источника
from app.services.ai_generation import generate_ai_response_stream, generate_ai_response_media, get_models_config
from app.services.casdoor import update_casdoor_balance

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chats", tags=["chats"])

# === НОВЫЙ ЭНДПОИНТ: Отдает список моделей фронтенду ===
@router.get("/models")
def get_available_models():
    """Возвращает список доступных моделей и групп для фронтенда"""
    return get_models_config()

# === ОБНОВЛЕНО: Получение списка чатов (Сортировка + Фильтр временных) ===
@router.get("")
def get_chats(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user: raise HTTPException(401)
    
    now = datetime.utcnow()
    
    # 1. Фильтруем: только чаты юзера И (не временные ИЛИ срок действия не истек)
    # 2. Сортируем: сначала закрепленные, потом по дате обновления
    chats = db.query(Chat).filter(
        Chat.user_casdoor_id == user.casdoor_id,
        or_(Chat.expires_at == None, Chat.expires_at > now)
    ).order_by(
        desc(Chat.is_pinned), 
        desc(Chat.updated_at)
    ).all()
    
    return [
        {
            "id": c.id, 
            "title": c.title, 
            "date": c.updated_at.isoformat(),
            "is_pinned": c.is_pinned,               # Новое поле
            "is_temporary": c.expires_at is not None # Новое поле
        } 
        for c in chats
    ]

# === НОВОЕ: Закрепить / Открепить чат ===
@router.patch("/{chat_id}/pin")
def pin_chat(chat_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user: raise HTTPException(401)
    
    chat = db.query(Chat).filter_by(id=chat_id, user_casdoor_id=user.casdoor_id).first()
    if not chat: raise HTTPException(404, "Chat not found")
    
    chat.is_pinned = not chat.is_pinned
    db.commit()
    
    return {"success": True, "is_pinned": chat.is_pinned}

# === НОВОЕ: Поделиться чатом (Генерация ссылки) ===
@router.post("/{chat_id}/share")
def share_chat(chat_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user: raise HTTPException(401)
    
    chat = db.query(Chat).filter_by(id=chat_id, user_casdoor_id=user.casdoor_id).first()
    if not chat: raise HTTPException(404, "Chat not found")
    
    # Если токена нет - генерируем новый
    if not chat.share_token:
        chat.share_token = str(uuid.uuid4())
        db.commit()
        
    return {"link": f"https://neirosetim.ru/share/{chat.share_token}"}

# === НОВОЕ: Массовая очистка истории ===
@router.delete("/history/clear")
def clear_history(range: str, request: Request, db: Session = Depends(get_db)):
    """range = 'today' | 'week' | 'all'"""
    user = get_current_user(request, db)
    if not user: raise HTTPException(401)
    
    query = db.query(Chat).filter_by(user_casdoor_id=user.casdoor_id)
    now = datetime.utcnow()
    
    if range == 'today':
        start_of_day = datetime(now.year, now.month, now.day)
        query = query.filter(Chat.created_at >= start_of_day)
    elif range == 'week':
        week_ago = now - timedelta(days=7)
        query = query.filter(Chat.created_at >= week_ago)
    elif range == 'all':
        pass
    else:
        raise HTTPException(400, "Invalid range")
    
    chats_to_delete = query.all()
    for chat in chats_to_delete:
        db.delete(chat) # Удалит и сообщения благодаря cascade="all, delete"
        
    db.commit()
    return {"success": True, "deleted_count": len(chats_to_delete)}

@router.delete("/{chat_id}")
def delete_chat(chat_id: int, request: Request, db: Session = Depends(get_db)):
    """Удаление чата и всех его сообщений"""
    user = get_current_user(request, db)
    if not user: raise HTTPException(401)
    chat = db.query(Chat).filter_by(id=chat_id, user_casdoor_id=user.casdoor_id).first()
    if not chat: raise HTTPException(404, "Chat not found")
    
    # Удаляем сам чат (сообщения удалятся каскадно, но можно оставить явное удаление для надежности)
    db.delete(chat)
    db.commit()
    
    return {"success": True, "message": "Chat deleted"}

@router.patch("/{chat_id}")
def rename_chat(chat_id: int, request: Request, data: dict = Body(...), db: Session = Depends(get_db)):
    """Переименование чата"""
    user = get_current_user(request, db)
    if not user: raise HTTPException(401)
    chat = db.query(Chat).filter_by(id=chat_id, user_casdoor_id=user.casdoor_id).first()
    if not chat: raise HTTPException(404, "Chat not found")
    
    new_title = data.get("title", "").strip()
    if not new_title: raise HTTPException(400, "Title cannot be empty")
    
    chat.title = new_title[:50]  # Лимит 50 символов
    db.commit()
    
    return {"success": True, "title": chat.title}

@router.get("/{chat_id}")
def get_chat_history(chat_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user: raise HTTPException(401)
    chat = db.query(Chat).filter_by(id=chat_id, user_casdoor_id=user.casdoor_id).first()
    if not chat: raise HTTPException(404, "Chat not found")
    
    messages = []
    for m in chat.messages:
        messages.append({
            "id": m.id, "role": m.role, "content": m.content,
            "image_url": m.image_url, "attachment_url": m.attachment_url
        })
    
    return {
        "id": chat.id,
        "title": chat.title,
        "model": chat.model,
        "messages": messages
    }

@router.post("/new")
async def create_new_chat(request: Request, data: dict = Body(...), db: Session = Depends(get_db)):
    return await handle_chat_request(request, data, db, is_new=True)

@router.post("/{chat_id}/message")
async def chat_reply(chat_id: int, request: Request, data: dict = Body(...), db: Session = Depends(get_db)):
    return await handle_chat_request(request, data, db, chat_id=chat_id)

async def handle_chat_request(request: Request, data: dict, db: Session, is_new=False, chat_id=None):
    user = get_current_user(request, db)
    if not user: raise HTTPException(401)

    if user.balance <= 0:
        raise HTTPException(status_code=402, detail="Недостаточно средств. Пополните баланс.")

    user_text = data.get("message", "")
    model = data.get("model", "openai/gpt-4o") # Дефолтная модель
    temp = data.get("temperature", 0.5)
    web = data.get("web_search", False)
    attach = data.get("attachment_url")
    
    # Флаг временного чата с фронтенда
    is_temp = data.get("is_temporary", False)

    # 1. Создаем/Ищем чат
    if is_new:
        title = user_text[:30] + "..." if len(user_text) > 30 else user_text
        chat = Chat(user_casdoor_id=user.casdoor_id, title=title, model=model)
        
        # Если чат временный — ставим срок жизни 24 часа
        if is_temp:
            chat.expires_at = datetime.utcnow() + timedelta(hours=24)
            
        db.add(chat)
        db.commit()
        db.refresh(chat)
    else:
        chat = db.query(Chat).filter_by(id=chat_id, user_casdoor_id=user.casdoor_id).first()
        if not chat: raise HTTPException(404, "Chat not found")
        chat.updated_at = datetime.utcnow()

    # 2. Сохраняем сообщение пользователя
    user_msg = Message(chat_id=chat.id, role="user", content=user_text)
    if attach: user_msg.attachment_url = attach
    db.add(user_msg)
    db.commit()

    # 3. Контекст
    last_msgs = db.query(Message).filter_by(chat_id=chat.id).order_by(Message.id.desc()).limit(10).all()
    last_msgs.reverse()
    messages_payload = [{"role": "system", "content": "You are a helpful assistant."}]
    for m in last_msgs:
        messages_payload.append({"role": m.role, "content": m.content or ""})

    # === РАЗДЕЛЕНИЕ НА СТРИМ И МЕДИА ===
    media_models_keywords = ["recraft", "flux", "midjourney", "veo", "sora", "luma", "video", "image"]
    is_media = any(kw in model.lower() for kw in media_models_keywords) or \
               (model in ["fal-ai/recraft-v3", "fal-ai/flux-pro/v1.1-ultra"])

    if is_media:
        try:
            # cost_rub возвращается сразу из функции
            reply_text, cost_rub = await generate_ai_response_media(model, messages_payload, user.balance, attach)
        except Exception as e:
            raise HTTPException(500, f"Generation Error: {e}")
        
        if cost_rub > 0:
            user.balance = max(0, user.balance - cost_rub)
            db.add(user)
            db.commit()
            try:
                await update_casdoor_balance(user.casdoor_id, user.balance)
            except Exception as e:
                logger.error(f"Failed to sync balance: {e}")

        bot_msg = Message(chat_id=chat.id, role="assistant", content=reply_text)
        if "[Generated]" in reply_text:
            try: bot_msg.image_url = reply_text.split("(")[1].split(")")[0]
            except: pass
        
        db.add(bot_msg)
        db.commit()

        return {
            "chat_id": chat.id,
            "balance": float(user.balance),
            "messages": [
                {"role": "user", "content": user_text, "attachment_url": attach},
                {"role": "assistant", "content": reply_text, "image_url": bot_msg.image_url}
            ]
        }

    else:
        # Capture variables to avoid DetachedInstanceError in async generator
        current_balance = user.balance
        current_user_id = user.id
        current_chat_id = chat.id

        async def response_generator():
            full_text = ""
            total_cost_rub = 0.0
            
            yield json.dumps({"type": "meta", "chat_id": current_chat_id}) + "\n"

            try:
                async for chunk_text, chunk_cost in generate_ai_response_stream(
                    model, messages_payload, current_balance, temp, web, attach
                ):
                    full_text += chunk_text
                    total_cost_rub = chunk_cost
                    yield json.dumps({"type": "content", "text": chunk_text}) + "\n"
                
                # Используем отдельную сессию для финального обновления
                final_balance = current_balance
                
                if total_cost_rub > 0:
                    with SessionLocal() as db_new:
                        # Находим пользователя заново в новой сессии
                        user_new = db_new.query(UserWallet).filter_by(id=current_user_id).first()
                        if user_new:
                            user_new.balance = max(0, user_new.balance - total_cost_rub)
                            db_new.commit()
                            final_balance = user_new.balance
                            
                            # Синхронизация с Casdoor
                            try:
                                await update_casdoor_balance(user_new.casdoor_id, user_new.balance)
                            except Exception as e:
                                logger.error(f"Failed to sync balance: {e}")

                        # Сохраняем сообщение бота тоже в новой сессии
                        bot_msg = Message(chat_id=current_chat_id, role="assistant", content=full_text)
                        db_new.add(bot_msg)
                        db_new.commit()

                yield json.dumps({"type": "balance", "balance": float(final_balance)}) + "\n"
                
            except Exception as e:
                logger.error(f"Stream Error: {e}")
                yield json.dumps({"type": "error", "text": str(e)}) + "\n"

        return StreamingResponse(response_generator(), media_type="application/x-ndjson")