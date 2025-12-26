from fastapi import APIRouter, Request, Depends, HTTPException, Body
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime
import json

from app.database import get_db
from app.models import UserWallet, UserSession, Chat, Message
# Импортируем генераторы из ai_generation (функции обновим следующим шагом)
from app.services.ai_generation import generate_ai_response_stream, generate_ai_response_media

# Вспомогательная функция для получения юзера (копия из main, чтобы избежать циклических импортов)
def get_current_user_local(request: Request, db: Session):
    session_id = request.cookies.get("session_id")
    if not session_id: return None
    sess = db.query(UserSession).filter_by(session_id=session_id).first()
    if not sess: return None
    return db.query(UserWallet).filter_by(casdoor_id=sess.token).first()

router = APIRouter(prefix="/api/chats", tags=["chats"])

@router.get("")
def get_chats(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_local(request, db)
    if not user: raise HTTPException(401)
    chats = db.query(Chat).filter_by(user_casdoor_id=user.casdoor_id).order_by(desc(Chat.updated_at)).all()
    return [{"id": c.id, "title": c.title, "date": c.updated_at.isoformat()} for c in chats]

@router.get("/{chat_id}")
def get_chat_history(chat_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user_local(request, db)
    if not user: raise HTTPException(401)
    chat = db.query(Chat).filter_by(id=chat_id, user_casdoor_id=user.casdoor_id).first()
    if not chat: raise HTTPException(404, "Chat not found")
    
    messages = []
    for m in chat.messages:
        messages.append({
            "id": m.id, "role": m.role, "content": m.content,
            "image_url": m.image_url, "attachment_url": m.attachment_url
        })
    return messages

@router.post("/new")
async def create_new_chat(request: Request, data: dict = Body(...), db: Session = Depends(get_db)):
    return await handle_chat_request(request, data, db, is_new=True)

@router.post("/{chat_id}/message")
async def chat_reply(chat_id: int, request: Request, data: dict = Body(...), db: Session = Depends(get_db)):
    return await handle_chat_request(request, data, db, chat_id=chat_id)

async def handle_chat_request(request: Request, data: dict, db: Session, is_new=False, chat_id=None):
    user = get_current_user_local(request, db)
    if not user: raise HTTPException(401)

    user_text = data.get("message", "")
    model = data.get("model", "gpt-4o")
    temp = data.get("temperature", 0.7)
    web = data.get("web_search", False)
    attach = data.get("attachment_url")

    # 1. Создаем/Ищем чат
    if is_new:
        title = user_text[:30] + "..." if len(user_text) > 30 else user_text
        chat = Chat(user_casdoor_id=user.casdoor_id, title=title, model=model)
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
    
    # Список моделей, которые НЕ поддерживают стриминг (генерация фото/видео)
    # Я добавил сюда основные из твоего списка, если добавишь новые медиа-модели - добавь их ID сюда
    media_models_keywords = ["recraft", "flux", "midjourney", "veo", "sora", "luma", "video", "image"]
    is_media = any(kw in model.lower() for kw in media_models_keywords) or \
               (model in ["fal-ai/recraft-v3", "fal-ai/flux-pro/v1.1-ultra"])

    if is_media:
        # Обычный запрос (ждем полного ответа)
        reply_text, cost = await generate_ai_response_media(model, messages_payload, user.balance, attach)
        
        if cost > 0:
            user.balance = max(0, user.balance - cost)
            db.add(user)
            # await update_casdoor_balance(user.casdoor_id, user.balance) # Если нужно

        bot_msg = Message(chat_id=chat.id, role="assistant", content=reply_text)
        if "[Generated]" in reply_text:
            try: bot_msg.image_url = reply_text.split("(")[1].split(")")[0]
            except: pass
        
        db.add(bot_msg)
        db.commit()

        # Возвращаем обычный JSON
        return {
            "chat_id": chat.id,
            "messages": [
                {"role": "user", "content": user_text, "attachment_url": attach},
                {"role": "assistant", "content": reply_text, "image_url": bot_msg.image_url}
            ]
        }

    else:
        # Текстовый запрос (Стриминг)
        async def response_generator():
            full_text = ""
            total_cost = 0.0
            
            # 1. Отправляем мету (ID чата)
            yield json.dumps({"type": "meta", "chat_id": chat.id}) + "\n"

            try:
                # 2. Стримим текст
                async for chunk_text, chunk_cost in generate_ai_response_stream(
                    model, messages_payload, user.balance, temp, web, attach
                ):
                    full_text += chunk_text
                    total_cost = chunk_cost
                    yield json.dumps({"type": "content", "text": chunk_text}) + "\n"
                
                # 3. Финализация (Сохранение в БД)
                bot_msg = Message(chat_id=chat.id, role="assistant", content=full_text)
                if total_cost > 0:
                    user.balance = max(0, user.balance - total_cost)
                    db.add(user)
                    # await update_casdoor_balance...
                
                db.add(bot_msg)
                db.commit()
                
            except Exception as e:
                yield json.dumps({"type": "error", "text": str(e)}) + "\n"

        return StreamingResponse(response_generator(), media_type="application/x-ndjson")