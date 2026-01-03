from fastapi import APIRouter, Request, Depends, HTTPException, Body, BackgroundTasks
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
from app.services.ai_generation import generate_ai_response_stream, get_models_config
from app.services.casdoor import update_casdoor_balance

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chats"])


# === ФОНОВАЯ ЗАДАЧА: Очистка просроченных чатов ===
def cleanup_expired_chats(db: Session):
    try:
        now = datetime.utcnow()
        expired_chats = db.query(Chat).filter(Chat.expires_at.isnot(None), Chat.expires_at <= now).all()
        if expired_chats:
            for chat in expired_chats:
                db.delete(chat)
            db.commit()
    except Exception as e:
        logger.error(f"Cleanup error: {e}")


# === ХЕЛПЕР ДЛЯ SSE ===
async def sse_wrapper(chat_id: int, model_id: str, messages: list, user_balance: float, user_casdoor_id: str, attachment_url: str = None):
    """
    Стримит ответ клиенту и сохраняет в БД после завершения.
    
    Args:
        chat_id: ID чата для сохранения сообщения
        model_id: ID модели AI
        messages: История сообщений для контекста
        user_balance: Баланс пользователя
        user_casdoor_id: ID пользователя для списания баланса
        attachment_url: URL прикреплённого файла
    """
    generator = generate_ai_response_stream(
        model_id=model_id,
        messages=messages,
        user_balance=float(user_balance),
        temperature=0.7,
        web_search=False,
        attachment_url=attachment_url
    )
    
    full_response = ""  # Накапливаем полный ответ
    total_cost = 0.0
    
    async for content, cost in generator:
        if content:
            full_response += content
            data = json.dumps({"content": content}, ensure_ascii=False)
            yield f"data: {data}\n\n"
        if cost > 0:
            total_cost = cost
    
    # === СОХРАНЯЕМ ОТВЕТ АССИСТЕНТА В БД ===
    if full_response:
        db = SessionLocal()
        try:
            # 1. Сохраняем сообщение ассистента
            assistant_msg = Message(
                chat_id=chat_id,
                role="assistant",
                content=full_response
            )
            db.add(assistant_msg)
            
            # 2. Списываем баланс если есть стоимость
            if total_cost > 0:
                wallet = db.query(UserWallet).filter(
                    UserWallet.casdoor_id == user_casdoor_id
                ).first()
                if wallet:
                    wallet.balance = max(0, wallet.balance - total_cost)
                    logger.info(f"Balance updated: user={user_casdoor_id}, -{total_cost:.4f}₽, new={wallet.balance:.2f}₽")
            
            db.commit()
            logger.info(f"Saved assistant message to chat {chat_id}, length={len(full_response)}")
            
        except Exception as e:
            logger.error(f"Failed to save assistant message: {e}")
            db.rollback()
        finally:
            db.close()


# === 1. Список моделей ===
@router.get("/models")
def get_available_models():
    return get_models_config()


# === 2. Список чатов ===
@router.get("/")
def get_chats(request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(401)
    
    background_tasks.add_task(cleanup_expired_chats, db)
    
    chats = db.query(Chat).filter(Chat.user_casdoor_id == user.casdoor_id)\
        .order_by(Chat.is_pinned.desc(), Chat.updated_at.desc()).all()
    
    return [{
        "id": c.id, 
        "title": c.title, 
        "date": c.updated_at.isoformat(), 
        "model": c.model, 
        "is_pinned": c.is_pinned,
        "expires_at": c.expires_at.isoformat() if c.expires_at else None
    } for c in chats]


# === 3. История чата ===
@router.get("/{chat_id}")
def get_chat_history(chat_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(401)

    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_casdoor_id == user.casdoor_id).first()
    if not chat:
        raise HTTPException(404, "Chat not found")
    
    return {
        "id": chat.id,
        "title": chat.title,
        "model": chat.model,
        "is_pinned": chat.is_pinned,
        "share_token": chat.share_token,
        "expires_at": chat.expires_at.isoformat() if chat.expires_at else None,
        "messages": [{"role": m.role, "content": m.content, "image_url": m.image_url} for m in chat.messages]
    }


# === 4. Новый чат ===
@router.post("/new")
async def create_new_chat(request: Request, payload: dict = Body(...), db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(401)
    
    user_msg = payload.get("message", "")
    model_id = payload.get("model", "openai/gpt-4o")
    attachment_url = payload.get("attachment_url")
    is_temporary = payload.get("is_temporary", False)

    expires_at = None
    if is_temporary:
        expires_at = datetime.utcnow() + timedelta(hours=24)

    # Создаём чат
    chat = Chat(
        user_casdoor_id=user.casdoor_id,
        title=user_msg[:40] if user_msg else "Новый чат",
        model=model_id,
        expires_at=expires_at
    )
    db.add(chat)
    db.commit()
    db.refresh(chat)
    
    # Сохраняем сообщение пользователя
    msg = Message(chat_id=chat.id, role="user", content=user_msg, image_url=attachment_url)
    db.add(msg)
    db.commit()
    
    # Формируем историю для AI (пока только одно сообщение)
    messages = [{"role": "user", "content": user_msg}]
    
    return StreamingResponse(
        sse_wrapper(chat.id, model_id, messages, user.balance, user.casdoor_id, attachment_url),
        media_type="text/event-stream",
        headers={"X-Chat-Id": str(chat.id)}
    )


# === 5. Продолжить чат ===
@router.post("/{chat_id}/message")
async def continue_chat(chat_id: int, request: Request, payload: dict = Body(...), db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(401)
    
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_casdoor_id == user.casdoor_id).first()
    if not chat:
        raise HTTPException(404, "Chat not found")
    
    user_msg = payload.get("message", "")
    attachment_url = payload.get("attachment_url")
    
    # Сохраняем сообщение пользователя
    msg = Message(chat_id=chat.id, role="user", content=user_msg, image_url=attachment_url)
    db.add(msg)
    
    # Обновляем модель если передана
    if "model" in payload:
        chat.model = payload["model"]
    chat.updated_at = datetime.utcnow()
    db.commit()
    
    # === КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ: Собираем ВСЮ историю чата для контекста AI ===
    messages = [{"role": m.role, "content": m.content} for m in chat.messages]
    
    return StreamingResponse(
        sse_wrapper(chat.id, chat.model, messages, user.balance, user.casdoor_id, attachment_url),
        media_type="text/event-stream"
    )


# === 6. Удалить чат ===
@router.delete("/{chat_id}")
def delete_chat(chat_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(401)
    
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_casdoor_id == user.casdoor_id).first()
    if not chat:
        raise HTTPException(404)
    
    db.delete(chat)
    db.commit()
    return {"status": "ok"}


# === 7. Очистить историю ===
@router.delete("/history/clear")
def clear_history(range: str, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(401)
    
    query = db.query(Chat).filter(Chat.user_casdoor_id == user.casdoor_id)
    now = datetime.utcnow()
    
    if range == 'last_hour':
        query = query.filter(Chat.created_at >= now - timedelta(hours=1))
    elif range == 'last_24h':
        query = query.filter(Chat.created_at >= now - timedelta(hours=24))
    
    chats_to_delete = query.all()
    chat_ids = [chat.id for chat in chats_to_delete]
    
    if chat_ids:
        # Сначала удаляем сообщения (зависимые данные)
        db.query(Message).filter(Message.chat_id.in_(chat_ids)).delete(synchronize_session=False)
        # Потом удаляем чаты
        db.query(Chat).filter(Chat.id.in_(chat_ids)).delete(synchronize_session=False)
        db.commit()
    
    return {"status": "cleared", "count": len(chat_ids)}


# === 8. Переименовать чат ===
@router.patch("/{chat_id}")
def rename_chat(chat_id: int, request: Request, payload: dict = Body(...), db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(401)
    
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_casdoor_id == user.casdoor_id).first()
    if not chat:
        raise HTTPException(404)
    
    if "title" in payload:
        chat.title = payload["title"]
    db.commit()
    return {"status": "ok"}


# === 9. Закрепить/открепить чат ===
@router.patch("/{chat_id}/pin")
def pin_chat(chat_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(401)
    
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_casdoor_id == user.casdoor_id).first()
    if not chat:
        raise HTTPException(404)
    
    chat.is_pinned = not chat.is_pinned
    db.commit()
    return {"status": "ok", "is_pinned": chat.is_pinned}


# === 10. Поделиться чатом ===
@router.post("/{chat_id}/share")
def share_chat(chat_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(401)
    
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_casdoor_id == user.casdoor_id).first()
    if not chat:
        raise HTTPException(404)
    
    if not chat.share_token:
        chat.share_token = str(uuid.uuid4())
        db.commit()
    
    return {"link": f"https://lk.neirosetim.ru/share/{chat.share_token}"}
