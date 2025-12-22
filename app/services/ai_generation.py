import os
import re
import fal_client
from openai import AsyncOpenAI
from fastapi import HTTPException
from app.services.s3 import upload_url_to_s3

# === НАСТРОЙКИ ===
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
        print(f"⚠️ OpenAI Init Error: {e}")

# === КАТАЛОГ МОДЕЛЕЙ (ПРОВЕРЕННЫЕ ID) ===
MODEL_CONFIG = {
    # --- OPENAI ---
    "gpt-4o":         {"type": "text", "id": "openai/gpt-4o", "price_in": 2.5, "price_out": 10},
    "gpt-4o-mini":    {"type": "text", "id": "openai/gpt-4o-mini", "price_in": 0.15, "price_out": 0.6},
    "o1-preview":     {"type": "text", "id": "openai/o1-preview", "price_in": 15, "price_out": 60},
    "o1-mini":        {"type": "text", "id": "openai/o1-mini", "price_in": 3, "price_out": 12},
    
    # --- ANTHROPIC (CLAUDE) ---
    "claude-3.5-sonnet": {"type": "text", "id": "anthropic/claude-3.5-sonnet", "price_in": 3, "price_out": 15},
    "claude-3-opus":     {"type": "text", "id": "anthropic/claude-3-opus", "price_in": 15, "price_out": 75},
    "claude-3-haiku":    {"type": "text", "id": "anthropic/claude-3-haiku", "price_in": 0.25, "price_out": 1.25},

    # --- GOOGLE ---
    "gemini-pro-1.5":    {"type": "text", "id": "google/gemini-pro-1.5", "price_in": 3.5, "price_out": 10.5},
    "gemini-flash-1.5":  {"type": "text", "id": "google/gemini-flash-1.5", "price_in": 0.075, "price_out": 0.3},

    # --- X.AI (GROK) ---
    "grok-2":            {"type": "text", "id": "x-ai/grok-2-vision-1212", "price_in": 2, "price_out": 10},
    "grok-beta":         {"type": "text", "id": "x-ai/grok-beta", "price_in": 5, "price_out": 15},

    # --- DEEPSEEK & MISTRAL ---
    "deepseek-v3":       {"type": "text", "id": "deepseek/deepseek-chat", "price_in": 0.14, "price_out": 0.28},
    "mistral-large":     {"type": "text", "id": "mistralai/mistral-large", "price_in": 2, "price_out": 6},
    "llama-3.1-405b":    {"type": "text", "id": "meta-llama/llama-3.1-405b-instruct", "price_in": 3, "price_out": 3},

    # --- PERPLEXITY (ПОИСК) ---
    "sonar-online":      {"type": "text", "id": "perplexity/sonar-reasoning", "price_in": 1, "price_out": 5},

    # --- ВИДЕО (FAL.AI) ---
    "kling-1.5":         {"type": "video", "id": "fal-ai/kling-video/v1.5/pro", "price_fixed": 90},
    "luma-ray":          {"type": "video", "id": "fal-ai/luma-dream-machine", "price_fixed": 45},
    "runway-gen3":       {"type": "video", "id": "fal-ai/runway-gen3/turbo/image-to-video", "price_fixed": 40},
    "minimax":           {"type": "video", "id": "fal-ai/minimax/video-01", "price_fixed": 70},
    "hailuo":            {"type": "video", "id": "fal-ai/hailuo/video", "price_fixed": 60},

    # --- ФОТО (FAL.AI) ---
    "flux-pro":          {"type": "image", "id": "fal-ai/flux-pro/v1.1-ultra", "price_fixed": 6},
    "flux-realism":      {"type": "image", "id": "fal-ai/flux-realism", "price_fixed": 5},
    "recraft-v3":        {"type": "image", "id": "fal-ai/recraft-v3", "price_fixed": 8},
    "ideogram":          {"type": "image", "id": "fal-ai/ideogram/v2", "price_fixed": 12},
    "midjourney":        {"type": "image", "id": "fal-ai/midjourney-v6", "price_fixed": 15}, # Через прокси
}

def extract_image_url(text: str):
    """Ищет ссылку на картинку в формате [Файл: url] или (url)"""
    if not text: return None
    match = re.search(r'(?:\[Файл:|!\[.*?\]\()((https?://\S+?)(?:\.png|\.jpg|\.jpeg|\.webp))(?:\)|\]|\s)', text, re.IGNORECASE)
    if match: return match.group(1)
    return None

async def generate_ai_response(model_alias: str, messages: list, user_balance: float, temperature: float = 0.7, web_search: bool = False) -> tuple[str, float]:
    """Генерирует ответ и возвращает (текст, цена)"""
    
    # 1. Поиск модели
    model_info = MODEL_CONFIG.get(model_alias)
    if not model_info:
        # Если ID нет в списке, пробуем использовать как есть (для гибкости)
        if "/" in model_alias:
             model_info = {"type": "text", "id": model_alias, "price_in": 1, "price_out": 1}
        else:
             model_info = MODEL_CONFIG["gpt-4o"] # Fallback

    model_id = model_info["id"]
    model_type = model_info["type"]

    # 2. Проверка баланса
    min_price = model_info.get("price_fixed", 0.5)
    if user_balance < min_price:
        raise HTTPException(status_code=402, detail=f"Недостаточно средств. Минимум: {min_price}₽")

    prompt = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "Hello")

    # === ВИДЕО / ФОТО ===
    if model_type in ["video", "image"]:
        if not FAL_KEY: raise Exception("Нет ключа FAL_KEY")
        
        cost = model_info.get("price_fixed", 0)
        clean_prompt = re.sub(r'\[Файл:.*?\]', '', prompt).strip()
        print(f"🎨 MEDIA ({model_id}): {clean_prompt[:30]}...")

        args = {"prompt": clean_prompt}
        if model_type == "image": args["image_size"] = "landscape_16_9"
        
        handler = await fal_client.submit_async(model_id, arguments=args)
        result = await handler.get()
        
        # Разбор ответа Fal
        media_url = None
        if 'video' in result and 'url' in result['video']: media_url = result['video']['url']
        elif 'images' in result: media_url = result['images'][0]['url']
        else: media_url = str(result) # Fallback

        saved_url = await upload_url_to_s3(media_url)
        prefix = "!" if model_type in ["image", "video"] else ""
        return f"{prefix}[Generated]({saved_url or media_url})", cost

    # === ТЕКСТ ===
    else:
        if not text_client: raise Exception("OpenRouter Key не настроен")
        
        final_messages = []
        
        # Поиск через системный промпт (самый надежный способ)
        if web_search:
            final_messages.append({"role": "system", "content": "You have access to real-time information via your internal tools. Please search the internet to provide the most accurate and up-to-date answer."})

        # Обработка Vision (картинки)
        input_chars = 0
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            input_chars += len(content)
            
            img_url = extract_image_url(content)
            if img_url and role == "user":
                text_only = content.replace(f"[Файл: {img_url}]", "").strip() or "Describe this image"
                final_messages.append({
                    "role": "user",
                    "content": [
                        {"type": "text", "text": text_only},
                        {"type": "image_url", "image_url": {"url": img_url}}
                    ]
                })
            else:
                final_messages.append({"role": role, "content": content})

        print(f"📝 TEXT ({model_id}) Temp:{temperature}")
        
        # ВАЖНО: Убрал аргумент 'plugins', который вызывал ошибку
        response = await text_client.chat.completions.create(
            model=model_id,
            messages=final_messages,
            temperature=float(temperature),
            extra_headers={
                "HTTP-Referer": "https://neirosetim.ru",
                "X-Title": "Neirosetim"
            }
        )
        
        reply_text = response.choices[0].message.content
        
        # Расчет цены
        input_tokens = input_chars / 4
        output_tokens = len(reply_text) / 4
        cost = (input_tokens / 1000 * model_info.get("price_in", 1)) + \
               (output_tokens / 1000 * model_info.get("price_out", 1))
        
        return reply_text, round(cost, 4)