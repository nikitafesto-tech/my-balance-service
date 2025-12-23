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

# === ПОЛНЫЙ КАТАЛОГ МОДЕЛЕЙ (ДЕКАБРЬ 2025) ===
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
        # Fallback на случай, если фронт прислал что-то странное
        model_info = MODEL_CONFIG["gpt-4o"]

    model_id = model_info["id"]
    model_type = model_info["type"]

    # 2. Проверка баланса (мин. порог)
    if user_balance < 0.1:
        raise HTTPException(status_code=402, detail="Недостаточно средств. Пополните баланс.")

    # Для Vision и медиа берем последний промпт
    last_msg_obj = next((m for m in reversed(messages) if m["role"] == "user"), None)
    prompt = last_msg_obj["content"] if last_msg_obj else "Hello"

    if model_type == "text":
        if not text_client: raise Exception("OpenRouter Key is missing")
        
        final_messages = []
        if web_search:
            final_messages.append({
                "role": "system", 
                "content": "You have access to the internet. Please search the web to provide the most accurate and up-to-date information."
            })

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            # VISION LOGIC: Если это последнее сообщение и есть файл
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

        print(f"📝 REQUEST: {model_id} | Web: {web_search} | Attach: {bool(attachment_url)}")

        try:
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
            if "does not exist" in error_msg or "not found" in error_msg:
                return f"⚠️ Модель {model_id} временно недоступна. Попробуйте другую.", 0
            raise e

    return "Тип модели не поддерживается", 0