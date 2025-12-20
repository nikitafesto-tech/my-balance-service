import os
import fal_client
from openai import AsyncOpenAI
from fastapi import HTTPException
# Используем ваш стиль импортов
from app.services.s3 import upload_url_to_s3

# === 1. НАСТРОЙКИ (БЕЗОПАСНАЯ ЗАГРУЗКА) ===
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
FAL_KEY = os.getenv("FAL_KEY")

# Инициализируем клиента ТОЛЬКО если есть ключ
text_client = None
if OPENROUTER_KEY:
    try:
        text_client = AsyncOpenAI(
            api_key=OPENROUTER_KEY,
            base_url="https://openrouter.ai/api/v1",
        )
    except Exception as e:
        print(f"⚠️ Ошибка инициализации OpenAI: {e}")
else:
    print("⚠️ WARNING: OpenRouter API Key не найден. Текстовый ИИ работать не будет.")

# === 2. КОНФИГУРАЦИЯ МОДЕЛЕЙ ===
MODEL_CONFIG = {
    "deepseek/deepseek-chat":      {"type": "text", "tier": "free"},
    "openai/gpt-4o":               {"type": "text", "tier": "paid"},
    "anthropic/claude-3.5-sonnet": {"type": "text", "tier": "paid"},
    "fal-ai/recraft-v3":           {"type": "image", "tier": "paid"},
    "fal-ai/flux-pro/v1.1-ultra":  {"type": "image", "tier": "paid"},
    
    # Алиасы (короткие имена с фронтенда)
    "gpt-4o":     "openai/gpt-4o",
    "claude-3.5": "anthropic/claude-3.5-sonnet",
    "recraft":    "fal-ai/recraft-v3",
    "flux":       "fal-ai/flux-pro/v1.1-ultra",
    "suno":       "deepseek/deepseek-chat",
}

async def generate_ai_response(model_alias: str, messages: list, user_balance: float) -> str:
    # 1. Определяем ID модели
    model_id = MODEL_CONFIG.get(model_alias, model_alias)
    if isinstance(model_id, dict): model_id = model_alias
    
    # 2. Получаем настройки
    config = MODEL_CONFIG.get(model_id, {"type": "text", "tier": "paid"})

    # 3. Проверка баланса
    if config["tier"] == "paid" and user_balance < 10:
        raise HTTPException(status_code=402, detail="Недостаточно средств. Пополните баланс.")

    try:
        # === ВЕТКА КАРТИНОК (Fal.ai) ===
        if config["type"] == "image":
            if not FAL_KEY: return "Ошибка сервера: Нет ключа FAL_KEY."
            
            last_prompt = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "Art")
            print(f"🎨 Fal.ai: {model_id} | {last_prompt[:30]}...")
            
            handler = await fal_client.submit_async(
                model_id,
                arguments={"prompt": last_prompt, "image_size": "landscape_16_9"}
            )
            result = await handler.get()
            image_url = result['images'][0]['url']
            
            # Сохраняем к себе
            saved_url = await upload_url_to_s3(image_url)
            return f"![Generated Image]({saved_url or image_url})"

        # === ВЕТКА ТЕКСТА (OpenRouter) ===
        else:
            if not text_client: return "Ошибка сервера: API ключ OpenRouter не настроен."
            
            # Чистим историю от картинок для текста
            clean_messages = [m for m in messages if not (m.get("content","").startswith("![") and "](" in m.get("content",""))]
            
            print(f"📝 OpenRouter: {model_id}")
            response = await text_client.chat.completions.create(
                model=model_id,
                messages=clean_messages,
                headers={"HTTP-Referer": "https://neirosetim.ru"}
            )
            return response.choices[0].message.content

    except Exception as e:
        print(f"❌ AI Error: {e}")
        return f"Ошибка генерации: {str(e)}"