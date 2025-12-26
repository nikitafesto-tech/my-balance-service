from fastapi import APIRouter, Request, Depends, HTTPException, Body
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime
import json
import logging

from app.database import get_db
from app.models import UserWallet, Chat, Message
from app.dependencies import get_current_user
from app.services.ai_generation import generate_ai_response_stream, generate_ai_response_media
from app.services.casdoor import update_casdoor_balance

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chats", tags=["chats"])

@router.get("")
def get_chats(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user: raise HTTPException(401)
    chats = db.query(Chat).filter_by(user_casdoor_id=user.casdoor_id).order_by(desc(Chat.updated_at)).all()
    return [{"id": c.id, "title": c.title, "date": c.updated_at.isoformat()} for c in chats]

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
    
    # === ИЗМЕНЕНИЕ: Возвращаем не просто список, а объект с моделью ===
    return {
        "id": chat.id,
        "title": chat.title,
        "model": chat.model,  # <-- Важно: возвращаем модель чата
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
        # Если чат старый, можно обновить модель на последнюю использованную (опционально)
        # chat.model = model 

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
            reply_text, cost = await generate_ai_response_media(model, messages_payload, user.balance, attach)
        except Exception as e:
            raise HTTPException(500, f"Generation Error: {e}")
        
        if cost > 0:
            user.balance = max(0, user.balance - cost)
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
        async def response_generator():
            full_text = ""
            total_cost = 0.0
            
            yield json.dumps({"type": "meta", "chat_id": chat.id}) + "\n"

            try:
                async for chunk_text, chunk_cost in generate_ai_response_stream(
                    model, messages_payload, user.balance, temp, web, attach
                ):
                    full_text += chunk_text
                    total_cost = chunk_cost
                    yield json.dumps({"type": "content", "text": chunk_text}) + "\n"
                
                if total_cost > 0:
                    user.balance = max(0, user.balance - total_cost)
                    db.add(user)
                    db.commit()
                    try:
                        await update_casdoor_balance(user.casdoor_id, user.balance)
                    except Exception as e:
                        logger.error(f"Failed to sync balance: {e}")

                bot_msg = Message(chat_id=chat.id, role="assistant", content=full_text)
                db.add(bot_msg)
                db.commit()

                yield json.dumps({"type": "balance", "balance": float(user.balance)}) + "\n"
                
            except Exception as e:
                yield json.dumps({"type": "error", "text": str(e)}) + "\n"

        return StreamingResponse(response_generator(), media_type="application/x-ndjson")