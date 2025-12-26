import os
import re
import fal_client
import httpx
import base64
from openai import AsyncOpenAI
from fastapi import HTTPException
from app.services.s3 import upload_url_to_s3

# === 1. НАСТРОЙКИ ===
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
FAL_KEY = os.getenv("FAL_KEY")
PROXY_URL = os.getenv("AI_PROXY_URL")

# Прокси через переменные окружения
if PROXY_URL:
    os.environ["HTTP_PROXY"] = PROXY_URL
    os.environ["HTTPS_PROXY"] = PROXY_URL
    print(f"🌍 PROXY ACTIVATED via ENV: {PROXY_URL}")

text_client = None
init_error = None

if OPENROUTER_KEY:
    try:
        http_client = httpx.AsyncClient(verify=False)
        text_client = AsyncOpenAI(
            api_key=OPENROUTER_KEY,
            base_url="https://openrouter.ai/api/v1",
            http_client=http_client,
        )
        print("✅ OpenRouter Client Initialized")
    except Exception as e:
        init_error = str(e)
        print(f"❌ Error initializing OpenAI: {e}")
else:
    init_error = "OpenRouter API Key not found"

# === 2. ТВОЙ ПОЛНЫЙ СПИСОК МОДЕЛЕЙ ===
MODEL_CONFIG = {
    # --- OPENAI (CHATGPT) ---
    "gpt-5.2":            {"type": "text", "id": "openai/gpt-5.2", "price_in": 2.5, "price_out": 10},
    "gpt-5.2-chat":       {"type": "text", "id": "openai/gpt-5.2-chat", "price_in": 2.5, "price_out": 10},
    "gpt-5.2-pro":        {"type": "text", "id": "openai/gpt-5.2-pro", "price_in": 2.5, "price_out": 10},
    "gpt-5.1":            {"type": "text", "id": "openai/gpt-5.1", "price_in": 0.15, "price_out": 0.6},
    "gpt-5.1-codex":      {"type": "text", "id": "openai/gpt-5.1-codex", "price_in": 0.15, "price_out": 0.6},
    "gpt-5.1-codex-max":  {"type": "text", "id": "openai/gpt-5.1-codex-max", "price_in": 3, "price_out": 12},
    "gpt-5.1-codex-mini": {"type": "text", "id": "openai/gpt-5.1-codex-mini", "price_in": 3, "price_out": 12},
    "gpt-5.1-chat":       {"type": "text", "id": "openai/gpt-5.1-chat", "price_in": 2.5, "price_out": 10},
    "gpt-5-mini":         {"type": "text", "id": "openai/gpt-5-mini", "price_in": 2.5, "price_out": 10},
    "gpt-5-chat":         {"type": "text", "id": "openai/gpt-5-chat", "price_in": 15, "price_out": 60},
    "gpt-5-nano":         {"type": "text", "id": "openai/gpt-5-nano", "price_in": 2.5, "price_out": 10},
    "gpt-5-codex":        {"type": "text", "id": "openai/gpt-5-codex", "price_in": 2.5, "price_out": 10},
    "gpt-5":              {"type": "text", "id": "openai/gpt-5", "price_in": 2.5, "price_out": 10},
    "o1-preview":         {"type": "text", "id": "openai/o1-preview", "price_in": 15, "price_out": 60},
    "o1-mini":            {"type": "text", "id": "openai/o1-mini", "price_in": 3, "price_out": 12},
    "gpt-oss-120b":       {"type": "text", "id": "openai/gpt-oss-120b", "price_in": 3, "price_out": 12},
    "gpt-oss-20b":        {"type": "text", "id": "openai/gpt-oss-20b", "price_in": 3, "price_out": 12},
    "gpt-4.1-mini":       {"type": "text", "id": "openai/gpt-4.1-mini", "price_in": 3, "price_out": 12},
    "gpt-4.1":            {"type": "text", "id": "openai/gpt-4.1", "price_in": 3, "price_out": 12},
    "gpt-4.1-nano":       {"type": "text", "id": "openai/gpt-4.1-nano", "price_in": 3, "price_out": 12},
    "gpt-4o":             {"type": "text", "id": "openai/gpt-4o", "price_in": 2.5, "price_out": 10},
    "gpt-4o-mini":        {"type": "text", "id": "openai/gpt-4o-mini", "price_in": 0.15, "price_out": 0.6},

    # --- ANTHROPIC (CLAUDE) ---
    "claude-4.5-sonnet":  {"type": "text", "id": "anthropic/claude-sonnet-4.5", "price_in": 3, "price_out": 15},
    "claude-opus-4.5":    {"type": "text", "id": "anthropic/claude-opus-4.5", "price_in": 3, "price_out": 15},
    "claude-haiku-4.5":   {"type": "text", "id": "anthropic/claude-haiku-4.5", "price_in": 3, "price_out": 15},
    "claude-4-sonnet":    {"type": "text", "id": "anthropic/claude-sonnet-4", "price_in": 3, "price_out": 15},
    "claude-opus-4":      {"type": "text", "id": "anthropic/claude-opus-4", "price_in": 3, "price_out": 15},
    "claude-3.7-sonnet":  {"type": "text", "id": "anthropic/claude-3.7-sonnet", "price_in": 3, "price_out": 15},
    "claude-3.7-thinking":{"type": "text", "id": "anthropic/claude-3.7-sonnet:thinking", "price_in": 3, "price_out": 15},
    "claude-3.5-sonnet":  {"type": "text", "id": "anthropic/claude-3.5-sonnet", "price_in": 3, "price_out": 15},
    "claude-3-opus":      {"type": "text", "id": "anthropic/claude-3-opus", "price_in": 15, "price_out": 75},
    "claude-3-haiku":     {"type": "text", "id": "anthropic/claude-3-haiku", "price_in": 0.25, "price_out": 1.25},

    # --- GOOGLE (GEMINI) ---
    "gemini-3-pro":       {"type": "text", "id": "google/gemini-3-pro-preview", "price_in": 3.5, "price_out": 10.5},
    "gemini-3-flash":     {"type": "text", "id": "google/gemini-3-flash-preview", "price_in": 3.5, "price_out": 10.5},
    "gemini-2.5-flash":   {"type": "text", "id": "google/gemini-2.5-flash", "price_in": 3.5, "price_out": 10.5},
    "gemini-2.5-lite":    {"type": "text", "id": "google/gemini-2.5-flash-lite", "price_in": 3.5, "price_out": 10.5},
    "gemini-free":        {"type": "text", "id": "google/gemini-2.0-flash-exp:free", "price_in": 0, "price_out": 0},

    # --- xAI (GROK) ---
    "grok-4.1-fast":      {"type": "text", "id": "x-ai/grok-4.1-fast", "price_in": 2, "price_out": 10},
    "grok-4-fast":        {"type": "text", "id": "x-ai/grok-4-fast", "price_in": 2, "price_out": 10},
    "grok-4":             {"type": "text", "id": "x-ai/grok-4", "price_in": 2, "price_out": 10},
    "grok-3":             {"type": "text", "id": "x-ai/grok-3", "price_in": 2, "price_out": 10},
    "grok-code-fast":     {"type": "text", "id": "x-ai/grok-code-fast-1", "price_in": 2, "price_out": 10},

    # --- DEEPSEEK ---
    "deepseek-v3.2":      {"type": "text", "id": "deepseek/deepseek-v3.2", "price_in": 0.14, "price_out": 0.28},
    "deepseek-v3":        {"type": "text", "id": "deepseek/deepseek-chat-v3-0324", "price_in": 0.14, "price_out": 0.28},
    "deepseek-r1":        {"type": "text", "id": "tngtech/deepseek-r1t2-chimera:free", "price_in": 0.14, "price_out": 0.28},
    "deepseek-3.1":       {"type": "text", "id": "deepseek/deepseek-chat-v3.1", "price_in": 0.14, "price_out": 0.28},
    "deepseek-nex":       {"type": "text", "id": "nex-agi/deepseek-v3.1-nex-n1:free", "price_in": 0.14, "price_out": 0.28},

    # --- MISTRAL ---
    "mistral-small":      {"type": "text", "id": "mistralai/mistral-small-3.2-24b-instruct", "price_in": 0.14, "price_out": 0.28},
    "mistral-nemo":       {"type": "text", "id": "mistralai/mistral-nemo", "price_in": 0.14, "price_out": 0.28},
    "mistral-24b":        {"type": "text", "id": "cognitivecomputations/dolphin-mistral-24b-venice-edition:free", "price_in": 0.14, "price_out": 0.28},

    # --- PERPLEXITY ---
    "sonar-deep":         {"type": "text", "id": "perplexity/sonar-deep-research", "price_in": 1, "price_out": 5},
    "sonar":              {"type": "text", "id": "perplexity/sonar", "price_in": 1, "price_out": 5},
    "sonar-pro":          {"type": "text", "id": "perplexity/sonar-pro-search", "price_in": 1, "price_out": 5},
    "sonar-reasoning":    {"type": "text", "id": "perplexity/sonar-reasoning-pro", "price_in": 1, "price_out": 5},

    # --- MOONSHOT ---
    "kimi-k2":            {"type": "text", "id": "moonshotai/kimi-k2-0905", "price_in": 1, "price_out": 5},
    "kimi-k2-think":      {"type": "text", "id": "moonshotai/kimi-k2-thinking", "price_in": 1, "price_out": 5},
    "kimi-free":          {"type": "text", "id": "moonshotai/kimi-k2:free", "price_in": 1, "price_out": 5},

    # --- LLaMA ---
    "llama-4-mav":        {"type": "text", "id": "meta-llama/llama-4-maverick", "price_in": 1, "price_out": 5},
    "llama-4-scout":      {"type": "text", "id": "meta-llama/llama-4-scout", "price_in": 1, "price_out": 5},
    "llama-3.3-70b":      {"type": "text", "id": "meta-llama/llama-3.3-70b-instruct:free", "price_in": 1, "price_out": 5},
    
    # --- ВИДЕО / ФОТО (FAL.AI) ---
    "recraft-v3":         {"type": "image", "id": "fal-ai/recraft-v3", "price_fixed": 10},
    "flux-1.1-ultra":     {"type": "image", "id": "fal-ai/flux-pro/v1.1-ultra", "price_fixed": 12},
    "luma-ray-2":         {"type": "video", "id": "fal-ai/luma-dream-machine/ray-2", "price_fixed": 50},
    "veo-3.1":            {"type": "video", "id": "fal-ai/veo-3.1", "price_fixed": 249},
}

async def encode_image(url):
    """Скачивает картинку с S3 и кодирует в base64 (без прокси)"""
    try:
        async with httpx.AsyncClient(verify=False, trust_env=False) as client:
            resp = await client.get(url, timeout=30.0)
            if resp.status_code == 200:
                return base64.b64encode(resp.content).decode('utf-8')
    except Exception as e:
        print(f"Error encoding image: {e}")
    return None

# === НОВАЯ ФУНКЦИЯ: СТРИМИНГ ТЕКСТА ===
async def generate_ai_response_stream(model_alias, messages, user_balance, temp, web, attach_url):
    """Генератор: возвращает (кусок_текста, накопленная_цена)"""
    model_info = MODEL_CONFIG.get(model_alias)
    if not model_info: model_info = MODEL_CONFIG["gpt-4o"]

    if user_balance < 0.1:
        yield "Недостаточно средств.", 0
        return

    # Подготовка сообщений
    last_msg = messages[-1]
    final_messages = messages[:-1]
    
    # Vision (Картинки) - конвертируем ссылку в base64
    if attach_url and last_msg["role"] == "user":
        b64 = await encode_image(attach_url)
        if b64:
            new_content = [
                {"type": "text", "text": last_msg["content"]},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
            ]
            final_messages.append({"role": "user", "content": new_content})
        else:
            final_messages.append(last_msg)
    else:
        final_messages.append(last_msg)

    # Веб-поиск
    if web:
        final_messages.insert(0, {"role": "system", "content": "You have access to the internet. Please search the web to provide accurate info."})

    if not text_client:
        yield f"System Error: {init_error}", 0
        return

    try:
        # Запрос с stream=True
        stream = await text_client.chat.completions.create(
            model=model_info["id"],
            messages=final_messages,
            temperature=float(temp),
            stream=True, # Включаем стриминг
            extra_headers={
                "HTTP-Referer": "https://neirosetim.ru",
                "X-Title": "Neirosetim"
            }
        )

        full_text = ""
        # Грубый подсчет токенов
        input_tokens = sum(len(str(m)) for m in final_messages) / 4 
        
        async for chunk in stream:
            content = chunk.choices[0].delta.content
            if content:
                full_text += content
                # Считаем цену
                output_tokens = len(full_text) / 4
                current_cost = (input_tokens/1000 * model_info.get("price_in", 1)) + \
                               (output_tokens/1000 * model_info.get("price_out", 1))
                
                yield content, round(current_cost, 4)

    except Exception as e:
        yield f"\n[Error: {str(e)}]", 0

# === ОБЫЧНАЯ ГЕНЕРАЦИЯ (ДЛЯ МЕДИА) ===
async def generate_ai_response_media(model_alias, messages, user_balance, attach_url):
    model_info = MODEL_CONFIG.get(model_alias)
    cost = model_info.get("price_fixed", 10)
    
    if user_balance < cost: return "Недостаточно средств", 0
    if not FAL_KEY: return "Error: FAL_KEY missing", 0

    prompt = messages[-1]["content"]
    args = {"prompt": prompt}
    if model_info["type"] == "image": args["image_size"] = "landscape_16_9"

    try:
        handler = await fal_client.submit_async(model_info["id"], arguments=args)
        result = await handler.get()
        
        media_url = None
        if 'images' in result: media_url = result['images'][0]['url']
        elif 'video' in result: media_url = result['video']['url']
        else: media_url = str(result)
        
        saved = await upload_url_to_s3(media_url)
        return f"![Generated]({saved or media_url})", cost
    except Exception as e:
        return f"Error: {e}", 0