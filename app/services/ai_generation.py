import os
import fal_client
from openai import AsyncOpenAI
from fastapi import HTTPException
from app.services.s3 import upload_url_to_s3

# === 1. НАСТРОЙКИ ===
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
FAL_KEY = os.getenv("FAL_KEY")

text_client = None
if OPENROUTER_KEY:
    try:
        text_client = AsyncOpenAI(
            api_key=OPENROUTER_KEY,
            base_url="https://openrouter.ai/api/v1",
        )
    except Exception as e:
        print(f"⚠️ Ошибка OpenAI: {e}")

# === 2. АКТУАЛЬНЫЕ МОДЕЛИ (2025) ===
MODEL_CONFIG = {
    # Текст
    "openai/gpt-5.2":              {"type": "text", "tier": "paid"},
    "openai/gpt-4o":               {"type": "text", "tier": "paid"},
    "google/gemini-3-flash-preview":{"type": "text", "tier": "free"},
    "deepseek/deepseek-chat":      {"type": "text", "tier": "free"},
    "anthropic/claude-3.5-sonnet": {"type": "text", "tier": "paid"},

    # Картинки
    "fal-ai/recraft-v3":           {"type": "image", "tier": "paid"},
    "fal-ai/flux-pro/v1.1-ultra":  {"type": "image", "tier": "paid"},

    # Видео (Luma Ray 2 и Hailuo)
    "fal-ai/luma-dream-machine/ray-2": {"type": "video", "tier": "paid"},
    "fal-ai/minimax/video-01":         {"type": "video", "tier": "paid"},

    # Алиасы (короткие имена с фронтенда)
    "gpt-5.2":    "openai/gpt-5.2",
    "gpt-4o":     "openai/gpt-4o",
    "gemini":     "google/gemini-3-flash-preview",
    "claude-3.5": "anthropic/claude-3.5-sonnet",
    "recraft":    "fal-ai/recraft-v3",
    "flux":       "fal-ai/flux-pro/v1.1-ultra",
    "luma":       "fal-ai/luma-dream-machine/ray-2",
    "hailuo":     "fal-ai/minimax/video-01",
}

async def generate_ai_response(model_alias: str, messages: list, user_balance: float) -> str:
    # 1. Определяем ID
    model_id = MODEL_CONFIG.get(model_alias, model_alias)
    if isinstance(model_id, dict): model_id = model_alias
    
    config = MODEL_CONFIG.get(model_id, {"type": "text", "tier": "paid"})

    # 2. Проверка баланса (видео дороже)
    min_price = 25 if config["type"] == "video" else 10
    if config["tier"] == "paid" and user_balance < min_price:
        raise HTTPException(status_code=402, detail=f"Недостаточно средств. Минимум {min_price}₽.")

    try:
        prompt = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "Art")

        # === ВИДЕО (Fal.ai) ===
        if config["type"] == "video":
            if not FAL_KEY: return "Ошибка: Нет ключа FAL_KEY."
            print(f"🎬 Генерирую видео ({model_id}): {prompt[:30]}...")
            
            handler = await fal_client.submit_async(
                model_id,
                arguments={"prompt": prompt}
            )
            result = await handler.get()
            # Fal может возвращать видео в разных полях, ищем url
            video_url = result.get('video', {}).get('url') or result.get('file', {}).get('url')
            
            saved_url = await upload_url_to_s3(video_url)
            return f"![Video]({saved_url or video_url})"

        # === КАРТИНКИ (Fal.ai) ===
        elif config["type"] == "image":
            if not FAL_KEY: return "Ошибка: Нет ключа FAL_KEY."
            print(f"🎨 Генерирую фото ({model_id}): {prompt[:30]}...")
            
            handler = await fal_client.submit_async(
                model_id,
                arguments={"prompt": prompt, "image_size": "landscape_16_9"}
            )
            result = await handler.get()
            image_url = result['images'][0]['url']
            
            saved_url = await upload_url_to_s3(image_url)
            return f"![Image]({saved_url or image_url})"

        # === ТЕКСТ (OpenRouter) ===
        else:
            if not text_client: return "Ошибка: OpenRouter Key не настроен."
            clean_msgs = [m for m in messages if not str(m.get("content","")).endswith((".mp4", ".png", ".jpg"))]
            
            print(f"📝 Текст ({model_id})")
            response = await text_client.chat.completions.create(
                model=model_id,
                messages=clean_msgs,
                # ВАЖНО: extra_headers вместо headers (фикс ошибки)
                extra_headers={
                    "HTTP-Referer": "https://neirosetim.ru",
                    "X-Title": "Neirosetim"
                },
            )
            return response.choices[0].message.content

    except Exception as e:
        print(f"❌ AI Error: {e}")
        return f"Ошибка генерации: {str(e)}"