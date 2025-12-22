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

# === КАТАЛОГ ВСЕХ МОДЕЛЕЙ (2025) ===
MODEL_CONFIG = {
    # --- OPENAI (Текст) ---
    "gpt-5.2-pro":    {"type": "text", "id": "openai/gpt-5.2-pro", "price_in": 6.3, "price_out": 50.4},
    "gpt-5.2":        {"type": "text", "id": "openai/gpt-5.2", "price_in": 4.0, "price_out": 3.5},
    "gpt-5.1":        {"type": "text", "id": "openai/gpt-5.1", "price_in": 0.35, "price_out": 2.8},
    "gpt-5":          {"type": "text", "id": "openai/gpt-5", "price_in": 0.35, "price_out": 2.8},
    "gpt-4.1":        {"type": "text", "id": "openai/gpt-4.1", "price_in": 0.6, "price_out": 2.4},
    "gpt-4o":         {"type": "text", "id": "openai/gpt-4o", "price_in": 1.35, "price_out": 2.7},
    "gpt-4o-mini":    {"type": "text", "id": "openai/gpt-4o-mini", "price_in": 0.12, "price_out": 0.48},
    "o1":             {"type": "text", "id": "openai/o1", "price_in": 4.5, "price_out": 18.0},
    "o3":             {"type": "text", "id": "openai/o3", "price_in": 0.8, "price_out": 3.2},
    "o1-mini":        {"type": "text", "id": "openai/o1-mini", "price_in": 0.3, "price_out": 1.3},

    # --- CLAUDE (Текст) ---
    "claude-4.5-opus":   {"type": "text", "id": "anthropic/claude-4.5-opus", "price_in": 1.5, "price_out": 7.5},
    "claude-4.5-sonnet": {"type": "text", "id": "anthropic/claude-4.5-sonnet", "price_in": 1.2, "price_out": 6.0},
    "claude-3.7-sonnet": {"type": "text", "id": "anthropic/claude-3.7-sonnet", "price_in": 0.9, "price_out": 4.5},
    "claude-3.5-sonnet": {"type": "text", "id": "anthropic/claude-3.5-sonnet", "price_in": 1.08, "price_out": 5.4},
    "claude-3-opus":     {"type": "text", "id": "anthropic/claude-3-opus", "price_in": 3.75, "price_out": 18.75},

    # --- GOOGLE (Текст) ---
    "gemini-3-pro":      {"type": "text", "id": "google/gemini-3-pro-preview", "price_in": 0.6, "price_out": 3.0},
    "gemini-3-flash":    {"type": "text", "id": "google/gemini-3-flash", "price_in": 0.001, "price_out": 0.006},
    "gemini-2.5-pro":    {"type": "text", "id": "google/gemini-2.5-pro", "price_in": 0.35, "price_out": 1.5},
    "gemini-2.0-flash":  {"type": "text", "id": "google/gemini-2.0-flash-exp", "price_in": 0.1, "price_out": 0.4},
    "gemini-1.5-pro":    {"type": "text", "id": "google/gemini-pro-1.5", "price_in": 2.0, "price_out": 6.0},

    # --- DEEPSEEK & OTHERS (Текст) ---
    "deepseek-r1":       {"type": "text", "id": "deepseek/deepseek-r1", "price_in": 3.2, "price_out": 4.8},
    "deepseek-v3":       {"type": "text", "id": "deepseek/deepseek-chat", "price_in": 0.14, "price_out": 0.28},
    "grok-3":            {"type": "text", "id": "xai/grok-3", "price_in": 0.6, "price_out": 3.0},
    "grok-2":            {"type": "text", "id": "xai/grok-2", "price_in": 0.6, "price_out": 3.0},
    "mistral-large":     {"type": "text", "id": "mistralai/mistral-large", "price_in": 1.0, "price_out": 2.4},
    "llama-3.3-70b":     {"type": "text", "id": "meta-llama/llama-3.3-70b-instruct", "price_in": 0.9, "price_out": 0.9},
    "sonar-deep":        {"type": "text", "id": "perplexity/sonar-deep-research", "price_in": 0.6, "price_out": 2.7},

    # --- ГЕНЕРАЦИЯ ВИДЕО (Fal.ai ID) ---
    "veo-3.1":           {"type": "video", "id": "fal-ai/veo-3.1", "price_fixed": 249},
    "veo-3":             {"type": "video", "id": "fal-ai/veo-3", "price_fixed": 480},
    "veo-2":             {"type": "video", "id": "fal-ai/veo-2", "price_fixed": 290},
    "sora-2":            {"type": "video", "id": "fal-ai/sora-2", "price_fixed": 37.5},
    "wan-2.6-1080p":     {"type": "video", "id": "fal-ai/wan-2.6/1080p", "price_fixed": 288},
    "wan-2.6-720p":      {"type": "video", "id": "fal-ai/wan-2.6/720p", "price_fixed": 192},
    "minimax-2.3":       {"type": "video", "id": "fal-ai/minimax/video-2.3", "price_fixed": 80},
    "kling-2.1-master":  {"type": "video", "id": "fal-ai/kling-2.1/master", "price_fixed": 498},
    "kling-2.1":         {"type": "video", "id": "fal-ai/kling-2.1/standard", "price_fixed": 178},
    "kling-2.0":         {"type": "video", "id": "fal-ai/kling-2.0", "price_fixed": 210},
    "runway-gen-3":      {"type": "video", "id": "fal-ai/runway-gen-3", "price_fixed": 48},
    "luma-ray-2":        {"type": "video", "id": "fal-ai/luma-dream-machine/ray-2", "price_fixed": 50},
    "seedance-pro":      {"type": "video", "id": "fal-ai/seedance/v1-pro", "price_fixed": 300},

    # --- ГЕНЕРАЦИЯ ФОТО (Fal.ai ID) ---
    "flux-1.1-ultra":    {"type": "image", "id": "fal-ai/flux-pro/v1.1-ultra", "price_fixed": 12},
    "flux-1.1-pro":      {"type": "image", "id": "fal-ai/flux-pro/v1.1", "price_fixed": 8},
    "flux-dev":          {"type": "image", "id": "fal-ai/flux/dev", "price_fixed": 5},
    "recraft-v3":        {"type": "image", "id": "fal-ai/recraft-v3", "price_fixed": 10},
    "midjourney":        {"type": "image", "id": "fal-ai/midjourney-v6", "price_fixed": 18},
    "dall-e-3":          {"type": "image", "id": "fal-ai/dall-e-3", "price_fixed": 16},
    "imagen-3":          {"type": "image", "id": "fal-ai/imagen-3", "price_fixed": 10},
    "sd-3.5":            {"type": "image", "id": "fal-ai/stable-diffusion-v3.5-large", "price_fixed": 8},

    # --- АУДИО ---
    "suno":              {"type": "audio", "id": "fal-ai/suno-v3", "price_fixed": 24},
    "udrum":             {"type": "audio", "id": "fal-ai/udrum", "price_fixed": 18},
}

def extract_image_url(text: str):
    """Ищет ссылку на картинку в формате [Файл: url] или (url)"""
    if not text: return None
    match = re.search(r'(?:\[Файл:|!\[.*?\]\()((https?://\S+?)(?:\.png|\.jpg|\.jpeg|\.webp))(?:\)|\]|\s)', text, re.IGNORECASE)
    if match:
        return match.group(1)
    return None

async def generate_ai_response(model_alias: str, messages: list, user_balance: float, temperature: float = 0.7, web_search: bool = False) -> tuple[str, float]:
    """
    Возвращает кортеж: (текст_ответа, стоимость_в_рублях)
    """
    # 1. Поиск модели
    model_info = MODEL_CONFIG.get(model_alias)
    if not model_info:
        # Если пришел прямой ID, пробуем найти конфиг
        for k, v in MODEL_CONFIG.items():
            if v["id"] == model_alias:
                model_info = v
                break
        if not model_info:
            model_info = {"type": "text", "id": model_alias, "price_in": 1, "price_out": 1}

    model_id = model_info["id"]
    model_type = model_info["type"]

    # 2. Проверка баланса (приблизительная)
    min_needed = model_info.get("price_fixed", 0.5) 
    if user_balance < min_needed:
        raise HTTPException(status_code=402, detail=f"Недостаточно средств. Нужно минимум {min_needed}₽.")

    # Получаем последний промпт
    last_msg_obj = next((m for m in reversed(messages) if m["role"] == "user"), None)
    prompt = last_msg_obj["content"] if last_msg_obj else "Hello"

    # === ГЕНЕРАЦИЯ МЕДИА (Fal.ai) ===
    if model_type in ["video", "image", "audio"]:
        if not FAL_KEY: raise Exception("Нет ключа FAL_KEY")
        
        cost = model_info.get("price_fixed", 0)
        clean_prompt = re.sub(r'\[Файл:.*?\]', '', prompt).strip()
        print(f"🎨 MEDIA ({model_id}): {clean_prompt[:40]}... Cost: {cost}₽")

        args = {"prompt": clean_prompt}
        if model_type == "image": args["image_size"] = "landscape_16_9"
        
        # Отправляем запрос в Fal.ai
        handler = await fal_client.submit_async(model_id, arguments=args)
        result = await handler.get()
        
        # Разбираем ответ (Fal возвращает разные структуры)
        media_url = None
        if 'video' in result and 'url' in result['video']: media_url = result['video']['url']
        elif 'images' in result: media_url = result['images'][0]['url']
        elif 'audio_url' in result: media_url = result['audio_url']
        elif 'file' in result: media_url = result['file']['url']
        else: media_url = str(result)

        saved_url = await upload_url_to_s3(media_url)
        prefix = "!" if model_type in ["image", "video"] else ""
        return f"{prefix}[Generated]({saved_url or media_url})", cost

    # === ГЕНЕРАЦИЯ ТЕКСТА (OpenRouter) ===
    else:
        if not text_client: raise Exception("OpenRouter Key не настроен")
        
        print(f"📝 TEXT ({model_id}) | Temp: {temperature} | Web: {web_search}")
        
        final_messages = []
        if web_search:
            # Вместо plugins (которые ломают код), используем системный промпт
            final_messages.append({
                "role": "system", 
                "content": "You have access to the internet. Please search the web to provide up-to-date and accurate information."
            })

        input_chars = 0
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            input_chars += len(content)
            
            img_url = extract_image_url(content)
            if img_url and role == "user":
                # Vision: отправляем картинку правильно
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

        params = {
            "model": model_id,
            "messages": final_messages,
            "temperature": float(temperature),
            "extra_headers": {"HTTP-Referer": "https://neirosetim.ru", "X-Title": "Neirosetim"}
        }
        
        # УДАЛЕНО: params["plugins"] - это вызывало ошибку!

        response = await text_client.chat.completions.create(**params)
        reply_text = response.choices[0].message.content
        
        # Расчет стоимости текста
        input_tokens = input_chars / 4
        output_tokens = len(reply_text) / 4
        price_in = model_info.get("price_in", 1)
        price_out = model_info.get("price_out", 1)
        
        cost = (input_tokens / 1000 * price_in) + (output_tokens / 1000 * price_out)
        cost = round(cost, 4)
        
        return reply_text, cost