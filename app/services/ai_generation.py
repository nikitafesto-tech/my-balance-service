import os
import re
import fal_client
import httpx
from openai import AsyncOpenAI
from fastapi import HTTPException
from app.services.s3 import upload_url_to_s3

# === НАСТРОЙКИ И ПРОКСИ ===
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
FAL_KEY = os.getenv("FAL_KEY")
PROXY_URL = os.getenv("AI_PROXY_URL")

# Настраиваем прокси для Fal.ai (через переменные окружения)
if PROXY_URL:
    os.environ["HTTP_PROXY"] = PROXY_URL
    os.environ["HTTPS_PROXY"] = PROXY_URL
    print(f"🌍 AI Proxy activated: {PROXY_URL}")

# Настраиваем клиент OpenAI с прокси
text_client = None
if OPENROUTER_KEY:
    try:
        # Создаем HTTP клиент с прокси
        http_client = httpx.AsyncClient(proxies=PROXY_URL) if PROXY_URL else None
        
        text_client = AsyncOpenAI(
            api_key=OPENROUTER_KEY,
            base_url="https://openrouter.ai/api/v1",
            http_client=http_client, # Подключаем прокси
        )
    except Exception as e:
        print(f"⚠️ OpenAI Init Error: {e}")

# === КАТАЛОГ МОДЕЛЕЙ ===
MODEL_CONFIG = {
    # --- OPENAI ---
    "gpt-5.2":            {"type": "text", "id": "openai/gpt-5.2", "price_in": 2.5, "price_out": 10},
    "gpt-5.2-chat":       {"type": "text", "id": "openai/gpt-5.2-chat", "price_in": 2.5, "price_out": 10},
    "gpt-5.2-pro":        {"type": "text", "id": "openai/gpt-5.2-pro", "price_in": 2.5, "price_out": 10},
    "gpt-5.1":            {"type": "text", "id": "openai/gpt-5.1", "price_in": 0.15, "price_out": 0.6},
    "gpt-5.1-codex":      {"type": "text", "id": "openai/gpt-5.1-codex", "price_in": 0.15, "price_out": 0.6},
    "gpt-5.1-chat":       {"type": "text", "id": "openai/gpt-5.1-chat", "price_in": 2.5, "price_out": 10},
    "gpt-5":              {"type": "text", "id": "openai/gpt-5", "price_in": 2.5, "price_out": 10},
    "o1-preview":         {"type": "text", "id": "openai/o1-preview", "price_in": 15, "price_out": 60},
    "o1-mini":            {"type": "text", "id": "openai/o1-mini", "price_in": 3, "price_out": 12},
    "gpt-4o":             {"type": "text", "id": "openai/gpt-4o", "price_in": 2.5, "price_out": 10},
    "gpt-4o-mini":        {"type": "text", "id": "openai/gpt-4o-mini", "price_in": 0.15, "price_out": 0.6},

    # --- ANTHROPIC ---
    "claude-4.5-sonnet":  {"type": "text", "id": "anthropic/claude-sonnet-4.5", "price_in": 3, "price_out": 15},
    "claude-opus-4.5":    {"type": "text", "id": "anthropic/claude-opus-4.5", "price_in": 3, "price_out": 15},
    "claude-3.7-sonnet":  {"type": "text", "id": "anthropic/claude-3.7-sonnet", "price_in": 3, "price_out": 15},
    "claude-3.5-sonnet":  {"type": "text", "id": "anthropic/claude-3.5-sonnet", "price_in": 3, "price_out": 15},
    "claude-3-opus":      {"type": "text", "id": "anthropic/claude-3-opus", "price_in": 15, "price_out": 75},

    # --- GOOGLE ---
    "gemini-3-pro":       {"type": "text", "id": "google/gemini-3-pro-preview", "price_in": 3.5, "price_out": 10.5},
    "gemini-3-flash":     {"type": "text", "id": "google/gemini-3-flash-preview", "price_in": 3.5, "price_out": 10.5},
    "gemini-2.5-flash":   {"type": "text", "id": "google/gemini-2.5-flash", "price_in": 3.5, "price_out": 10.5},
    "gemini-free":        {"type": "text", "id": "google/gemini-2.0-flash-exp:free", "price_in": 0, "price_out": 0},

    # --- OTHERS ---
    "grok-2":             {"type": "text", "id": "x-ai/grok-2-vision-1212", "price_in": 2, "price_out": 10},
    "deepseek-v3":        {"type": "text", "id": "deepseek/deepseek-chat", "price_in": 0.14, "price_out": 0.28},
    "deepseek-r1":        {"type": "text", "id": "deepseek/deepseek-r1", "price_in": 0.5, "price_out": 2},
    "mistral-large":      {"type": "text", "id": "mistralai/mistral-large", "price_in": 2, "price_out": 6},
    "llama-3.3-70b":      {"type": "text", "id": "meta-llama/llama-3.3-70b-instruct", "price_in": 0.7, "price_out": 0.9},
    "sonar-deep":         {"type": "text", "id": "perplexity/sonar-deep-research", "price_in": 1, "price_out": 5},

    # --- MEDIA ---
    "recraft-v3":         {"type": "image", "id": "fal-ai/recraft-v3", "price_fixed": 10},
    "flux-1.1-ultra":     {"type": "image", "id": "fal-ai/flux-pro/v1.1-ultra", "price_fixed": 12},
    "luma-ray-2":         {"type": "video", "id": "fal-ai/luma-dream-machine/ray-2", "price_fixed": 50},
    "veo-3.1":            {"type": "video", "id": "fal-ai/veo-3.1", "price_fixed": 249},
}

def extract_image_url(text: str):
    if not text: return None
    match = re.search(r'(?:\[Файл:|!\[.*?\]\()((https?://\S+?)(?:\.png|\.jpg|\.jpeg|\.webp))(?:\)|\]|\s)', text, re.IGNORECASE)
    if match: return match.group(1)
    return None

async def generate_ai_response(
    model_alias: str, 
    messages: list, 
    user_balance: float, 
    temperature: float = 0.7, 
    web_search: bool = False,
    attachment_url: str = None
) -> tuple[str, float]:
    
    # 1. Поиск модели
    model_info = MODEL_CONFIG.get(model_alias)
    if not model_info:
        # Пытаемся найти по ID, если пришел прямой ID
        for k, v in MODEL_CONFIG.items():
            if v["id"] == model_alias:
                model_info = v
                break
        if not model_info:
            model_info = MODEL_CONFIG["gpt-4o"]

    model_id = model_info["id"]
    model_type = model_info["type"]

    # 2. Проверка баланса
    if user_balance < 0.1:
        raise HTTPException(status_code=402, detail="Недостаточно средств. Пополните баланс.")

    last_msg_obj = next((m for m in reversed(messages) if m["role"] == "user"), None)
    prompt = last_msg_obj["content"] if last_msg_obj else "Hello"

    # === ТЕКСТОВЫЕ МОДЕЛИ (OpenRouter) ===
    if model_type == "text":
        if not text_client: raise Exception("OpenRouter Key is missing")
        
        final_messages = []
        if web_search:
            final_messages.append({
                "role": "system", 
                "content": "You have access to the internet. Please search the web to provide accurate info."
            })

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            # VISION: Если есть картинка в этом сообщении
            if role == "user" and msg == last_msg_obj and attachment_url:
                final_messages.append({
                    "role": "user",
                    "content": [
                        {"type": "text", "text": content},
                        {"type": "image_url", "image_url": {"url": attachment_url}}
                    ]
                })
            else:
                final_messages.append({"role": role, "content": content})

        print(f"📝 REQUEST: {model_id} | Proxy: {bool(PROXY_URL)}")

        try:
            # ВАЖНО: extra_headers вместо headers, убраны plugins
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
            input_chars = sum(len(str(m)) for m in final_messages)
            output_chars = len(reply_text)
            input_tokens = input_chars / 4
            output_tokens = output_chars / 4
            
            price_in = model_info.get("price_in", 1)
            price_out = model_info.get("price_out", 1)
            
            cost = (input_tokens / 1000 * price_in) + (output_tokens / 1000 * price_out)
            return reply_text, round(cost, 4)

        except Exception as e:
            error_msg = str(e)
            print(f"❌ Error: {error_msg}")
            if "403" in error_msg:
                return "⚠️ Ошибка доступа (403). Сервис недоступен в вашем регионе. Обратитесь к администратору для настройки прокси.", 0
            raise e

    # === МЕДИА МОДЕЛИ (Fal.ai) ===
    elif model_type in ["video", "image"]:
        if not FAL_KEY: raise Exception("FAL_KEY missing")
        
        cost = model_info.get("price_fixed", 10)
        clean_prompt = prompt
        
        print(f"🎨 MEDIA: {model_id} | Proxy: {bool(PROXY_URL)}")
        
        args = {"prompt": clean_prompt}
        if model_type == "image": args["image_size"] = "landscape_16_9"
        
        try:
            handler = await fal_client.submit_async(model_id, arguments=args)
            result = await handler.get()
            
            media_url = None
            if 'video' in result and 'url' in result['video']: media_url = result['video']['url']
            elif 'images' in result: media_url = result['images'][0]['url']
            elif 'file' in result: media_url = result['file']['url']
            else: media_url = str(result)

            saved_url = await upload_url_to_s3(media_url)
            prefix = "!" if model_type in ["image", "video"] else ""
            return f"{prefix}[Generated]({saved_url or media_url})", cost
        except Exception as e:
             if "403" in str(e):
                 return "⚠️ Ошибка региона (403). Fal.ai заблокировал запрос.", 0
             raise e

    return "Тип модели не поддерживается", 0