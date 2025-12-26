import os
import json
import logging
import httpx
from openai import AsyncOpenAI

# Настраиваем логгер
logger = logging.getLogger(__name__)

# Настройка клиентов
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
FAL_KEY = os.getenv("FAL_KEY")

client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

if not OPENROUTER_API_KEY:
    logger.warning("OPENROUTER_API_KEY is not set!")

# ==============================================================================
# ЕДИНЫЙ ИСТОЧНИК МОДЕЛЕЙ (MASTER CONFIG - DEC 2025)
# ==============================================================================

AI_MODELS_GROUPS = [
    {
        "name": "OpenAI",
        "icon": """<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M22.2819 9.8211a5.9847 5.9847 0 0 0-.5157-4.9108 6.0462 6.0462 0 0 0-6.5098-2.9A6.0651 6.0651 0 0 0 4.9807 4.1818a5.9847 5.9847 0 0 0-3.9977 2.9 6.0462 6.0462 0 0 0 .7427 7.0966 5.98 5.98 0 0 0 .511 4.9107 6.051 6.051 0 0 0 6.5146 2.9001A5.9847 5.9847 0 0 0 13.2599 24a6.0557 6.0557 0 0 0 5.7718-4.2058 5.9894 5.9894 0 0 0 3.9977-2.9001 6.0557 6.0557 0 0 0-.7475-7.0729zm-9.022 12.6081a4.4755 4.4755 0 0 1-2.8764-1.0408l.1419-.0804 4.7783-2.7582a.7948.7948 0 0 0 .3927-.6813v-6.7369l2.02 1.1686a1.54 1.54 0 0 1 .8312 1.2095v5.39a4.4844 4.4844 0 0 1-5.2877 3.5295zm-6.9735-3.2221a4.5496 4.5496 0 0 1 .7314-5.3374V13.85a.7939.7939 0 0 0 .3927.6813l5.8108 3.3662v2.3324a1.5298 1.5298 0 0 1-.827 1.3418 1.5298 1.5298 0 0 1-1.6163-.1273l-4.4916-2.6738zM5.7347 13.633a4.5153 4.5153 0 0 1-3.2699-4.3218l.0195-.0053 4.8023-2.7718a.7948.7948 0 0 0 .3976-.6772V1.6997a1.5573 1.5573 0 0 1 1.382 1.3223v5.1639l-3.3315 1.9213a4.5147 4.5147 0 0 1 0 3.5258zm2.6732-9.255a4.5428 4.5428 0 0 1 5.297-.7324l.0039.0016-2.0238 1.1685a.7932.7932 0 0 0-.3976.6772v6.694l-5.8108-3.3667V6.4883a1.5408 1.5408 0 0 1 2.9313-2.1105zm10.15 2.1523a4.5153 4.5153 0 0 1 3.2699 4.3218l-.0145.0009-4.8023 2.7718a.7948.7948 0 0 0-.3976.6772v4.1611a1.5573 1.5573 0 0 1-1.382-1.3223v-5.1639l3.3265-1.9213a4.5147 4.5147 0 0 1 0-3.5254zm-2.9103 7.7695l-2.6622-1.5367-2.667 1.5367V9.897l2.667-1.5367 2.6622 1.5367v4.4031z" fill="currentColor"/></svg>""",
        "models": [
            {"id": "openai/gpt-5.2", "name": "GPT-5.2", "cost_input": 2.5, "cost_output": 10},
            {"id": "openai/gpt-5.2-chat", "name": "GPT-5.2 Chat", "cost_input": 2.5, "cost_output": 10},
            {"id": "openai/gpt-5.2-pro", "name": "GPT-5.2 Pro", "cost_input": 2.5, "cost_output": 10},
            {"id": "openai/gpt-5.1", "name": "GPT-5.1", "cost_input": 0.15, "cost_output": 0.6},
            {"id": "openai/gpt-5.1-codex", "name": "GPT-5.1 Codex", "cost_input": 0.15, "cost_output": 0.6},
            {"id": "openai/gpt-5.1-codex-max", "name": "GPT-5.1 Codex Max", "cost_input": 3, "cost_output": 12},
            {"id": "openai/gpt-5.1-codex-mini", "name": "GPT-5.1 Codex Mini", "cost_input": 3, "cost_output": 12},
            {"id": "openai/gpt-5.1-chat", "name": "GPT-5.1 Chat", "cost_input": 2.5, "cost_output": 10},
            {"id": "openai/gpt-5-mini", "name": "GPT-5 Mini", "cost_input": 2.5, "cost_output": 10},
            {"id": "openai/gpt-5-chat", "name": "GPT-5 Chat", "cost_input": 15, "cost_output": 60},
            {"id": "openai/gpt-5-nano", "name": "GPT-5 Nano", "cost_input": 2.5, "cost_output": 10},
            {"id": "openai/gpt-5-codex", "name": "GPT-5 Codex", "cost_input": 2.5, "cost_output": 10},
            {"id": "openai/gpt-5", "name": "GPT-5", "cost_input": 2.5, "cost_output": 10},
            {"id": "openai/o1-preview", "name": "o1 Preview", "cost_input": 15, "cost_output": 60},
            {"id": "openai/o1-mini", "name": "o1 Mini", "cost_input": 3, "cost_output": 12},
            {"id": "openai/gpt-oss-120b", "name": "GPT OSS 120B", "cost_input": 3, "cost_output": 12},
            {"id": "openai/gpt-oss-20b", "name": "GPT OSS 20B", "cost_input": 3, "cost_output": 12},
            {"id": "openai/gpt-4.1-mini", "name": "GPT-4.1 Mini", "cost_input": 3, "cost_output": 12},
            {"id": "openai/gpt-4.1", "name": "GPT-4.1", "cost_input": 3, "cost_output": 12},
            {"id": "openai/gpt-4.1-nano", "name": "GPT-4.1 Nano", "cost_input": 3, "cost_output": 12},
            {"id": "openai/gpt-4o", "name": "GPT-4o", "cost_input": 2.5, "cost_output": 10},
            {"id": "openai/gpt-4o-mini", "name": "GPT-4o Mini", "cost_input": 0.15, "cost_output": 0.6},
        ]
    },
    {
        "name": "Anthropic",
        "icon": """<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M17.422 17.5c-1.33.663-2.73 1.054-4.192 1.168v-4.526h.01c2.253 0 4.226-1.113 5.426-2.827l2.81 1.725c-1.875 2.678-4.956 4.417-8.47 4.46h-.015V22H11v-4.5H9.682c-3.513-.043-6.594-1.782-8.469-4.46l2.81-1.725c1.2 1.714 3.173 2.827 5.426 2.827h.01v4.526c-1.462-.114-2.862-.505-4.192-1.168l-1.973 2.553C5.12 21.173 7.917 22 11 22c3.082 0 5.88-.827 7.907-2.247l-1.485-2.253ZM11 2C7.362 2 4.182 4.09 2.457 7.234l2.81 1.726C6.467 7.246 8.56 6.1 11 6.1s4.533 1.146 5.733 2.86l2.81-1.726C17.818 4.09 14.638 2 11 2Z" fill="currentColor"/></svg>""",
        "models": [
            {"id": "anthropic/claude-sonnet-4.5", "name": "Claude 4.5 Sonnet", "cost_input": 3, "cost_output": 15},
            {"id": "anthropic/claude-opus-4.5", "name": "Claude 4.5 Opus", "cost_input": 3, "cost_output": 15},
            {"id": "anthropic/claude-haiku-4.5", "name": "Claude 4.5 Haiku", "cost_input": 3, "cost_output": 15},
            {"id": "anthropic/claude-sonnet-4", "name": "Claude 4 Sonnet", "cost_input": 3, "cost_output": 15},
            {"id": "anthropic/claude-opus-4", "name": "Claude 4 Opus", "cost_input": 3, "cost_output": 15},
            {"id": "anthropic/claude-3.7-sonnet", "name": "Claude 3.7 Sonnet", "cost_input": 3, "cost_output": 15},
            {"id": "anthropic/claude-3.7-sonnet:thinking", "name": "Claude 3.7 Thinking", "cost_input": 3, "cost_output": 15},
            {"id": "anthropic/claude-3.5-sonnet", "name": "Claude 3.5 Sonnet", "cost_input": 3, "cost_output": 15},
            {"id": "anthropic/claude-3-opus", "name": "Claude 3 Opus", "cost_input": 15, "cost_output": 75},
            {"id": "anthropic/claude-3-haiku", "name": "Claude 3 Haiku", "cost_input": 0.25, "cost_output": 1.25},
        ]
    },
    {
        "name": "Google",
        "icon": """<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/></svg>""",
        "models": [
            {"id": "google/gemini-3-pro-preview", "name": "Gemini 3 Pro", "cost_input": 3.5, "cost_output": 10.5},
            {"id": "google/gemini-3-flash-preview", "name": "Gemini 3 Flash", "cost_input": 3.5, "cost_output": 10.5},
            {"id": "google/gemini-2.5-flash", "name": "Gemini 2.5 Flash", "cost_input": 3.5, "cost_output": 10.5},
            {"id": "google/gemini-2.5-flash-lite", "name": "Gemini 2.5 Flash Lite", "cost_input": 3.5, "cost_output": 10.5},
            {"id": "google/gemini-2.0-flash-exp:free", "name": "Gemini 2.0 Free", "cost_input": 3.5, "cost_output": 10.5},
        ]
    },
    {
        "name": "xAI (Grok)",
        "icon": """<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M16.9207 4H20.2507L12.9747 12.316L21.5337 23.682H14.8317L9.58169 16.815L3.57369 23.682H0.241688L7.96269 14.856L-0.207312 4H6.67469L11.4727 10.37L16.9207 4ZM15.7527 21.688H17.5977L5.68469 5.882H3.70469L15.7527 21.688Z" fill="currentColor"/></svg>""",
        "models": [
            {"id": "x-ai/grok-4.1-fast", "name": "Grok 4.1 Fast", "cost_input": 2, "cost_output": 10},
            {"id": "x-ai/grok-4-fast", "name": "Grok 4 Fast", "cost_input": 2, "cost_output": 10},
            {"id": "x-ai/grok-4", "name": "Grok 4", "cost_input": 2, "cost_output": 10},
            {"id": "x-ai/grok-3", "name": "Grok 3", "cost_input": 2, "cost_output": 10},
            {"id": "x-ai/grok-code-fast-1", "name": "Grok Code Fast", "cost_input": 2, "cost_output": 10},
        ]
    },
    {
        "name": "DeepSeek",
        "icon": """<svg viewBox="0 0 1024 1024" xmlns="http://www.w3.org/2000/svg"><path d="M333.6 470.4c-15.8 26.6-47.8 35.2-74.4 19.4s-35.2-47.8-19.4-74.4c15.8-26.6 47.8-35.2 74.4-19.4s35.4 47.8 19.4 74.4zM512 256c-176.8 0-320 143.2-320 320 0 32 4.8 63 13.6 92.4 20.2-12 43.8-19.2 68.8-19.2 57.2 0 106.2 36.6 123.6 86.8h228c17.4-50.2 66.4-86.8 123.6-86.8 25 0 48.6 7.2 68.8 19.2 9-29.4 13.6-60.4 13.6-92.4-0.2-176.8-143.4-320-320.2-320z m252.8 140c26.6 15.8 35.2 47.8 19.4 74.4s-47.8 35.2-74.4 19.4-35.2-47.8-19.4-74.4 47.8-35.2 74.4-19.4z" fill="currentColor"/></svg>""",
        "models": [
            {"id": "deepseek/deepseek-v3.2", "name": "DeepSeek V3.2", "cost_input": 0.14, "cost_output": 0.28},
            {"id": "deepseek/deepseek-chat-v3-0324", "name": "DeepSeek V3", "cost_input": 0.14, "cost_output": 0.28},
            {"id": "tngtech/deepseek-r1t2-chimera:free", "name": "DeepSeek R1", "cost_input": 0.14, "cost_output": 0.28},
            {"id": "deepseek/deepseek-chat-v3.1", "name": "DeepSeek 3.1", "cost_input": 0.14, "cost_output": 0.28},
            {"id": "nex-agi/deepseek-v3.1-nex-n1:free", "name": "DeepSeek V3.1 Nex", "cost_input": 0.14, "cost_output": 0.28},
        ]
    },
    {
        "name": "Mistral",
        "icon": """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg"><path d="M19.9 83.2V32.4L37 16.7l17.1 15.7 17.1-15.7 17.1 15.7v50.8L71.2 99V48.1L54.1 32.4 37 48.1v50.9z" fill="currentColor"/></svg>""",
        "models": [
            {"id": "mistralai/mistral-small-3.2-24b-instruct", "name": "Mistral Small 3.2 24B", "cost_input": 0.14, "cost_output": 0.28},
            {"id": "mistralai/mistral-nemo", "name": "Mistral Nemo", "cost_input": 0.14, "cost_output": 0.28},
            {"id": "cognitivecomputations/dolphin-mistral-24b-venice-edition:free", "name": "Mistral 24B", "cost_input": 0.14, "cost_output": 0.28},
        ]
    },
    {
        "name": "Perplexity",
        "icon": """<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M12 22C17.5228 22 22 17.5228 22 12C22 6.47715 17.5228 2 12 2C6.47715 2 2 6.47715 2 12C2 17.5228 6.47715 22 12 22Z" stroke="currentColor" stroke-width="2" fill="none"/><path d="M8 12L12 8L16 12M12 16V8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>""",
        "models": [
            {"id": "perplexity/sonar-deep-research", "name": "Sonar Deep Research", "cost_input": 1, "cost_output": 5},
            {"id": "perplexity/sonar", "name": "Sonar", "cost_input": 1, "cost_output": 5},
            {"id": "perplexity/sonar-pro-search", "name": "Sonar Reasoning Pro", "cost_input": 1, "cost_output": 5},
            {"id": "perplexity/sonar-reasoning-pro", "name": "Sonar Pro Search", "cost_input": 1, "cost_output": 5},
        ]
    },
    {
        "name": "Moonshot",
        "icon": """<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" xmlns="http://www.w3.org/2000/svg"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>""",
        "models": [
            {"id": "moonshotai/kimi-k2-0905", "name": "Kimi k2", "cost_input": 1, "cost_output": 5},
            {"id": "moonshotai/kimi-k2-thinking", "name": "Kimi k2 Thinking", "cost_input": 1, "cost_output": 5},
            {"id": "moonshotai/kimi-k2:free", "name": "Kimi k2 Free", "cost_input": 1, "cost_output": 5},
        ]
    },
    {
        "name": "Meta (LLaMA)",
        "icon": """<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M16.29 4c2.58 0 4.56 1.5 4.56 3.91 0 1.25-.56 2.12-1.39 3.03-.84.92-1.92 1.63-2.98 2.29-2.14 1.34-4.22 2.5-4.22 4.77h-.04c0-2.28-2.09-3.43-4.23-4.77-1.06-.66-2.14-1.37-2.98-2.29C4.18 10.03 3.62 9.16 3.62 7.91 3.62 5.5 5.6 4 8.18 4c1.61 0 2.92.76 3.82 2.06C12.9 4.76 14.21 4 15.82 4h.47z" stroke="currentColor" stroke-width="2" fill="none"/></svg>""",
        "models": [
            {"id": "meta-llama/llama-4-maverick", "name": "Llama 4 Maverick", "cost_input": 1, "cost_output": 5},
            {"id": "meta-llama/llama-4-scout", "name": "Llama 4 Scout", "cost_input": 1, "cost_output": 5},
            {"id": "meta-llama/llama-3.3-70b-instruct:free", "name": "Llama 3.3 70B", "cost_input": 1, "cost_output": 5},
        ]
    },
    {
        "name": "Медиа (Видео/Фото)",
        "icon": """<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M4 4h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zm0 2v12h16V6H4zm3 3a2 2 0 1 1 0 4 2 2 0 0 1 0-4zm10 8H7v-1l4-4 2 2 3-3 3 3v3z" fill="currentColor"/></svg>""",
        "models": [
            {"id": "fal-ai/kling-video/v1.5/pro", "name": "Kling 1.5", "cost_input": 0, "cost_output": 90},
            {"id": "fal-ai/luma-dream-machine", "name": "Luma Ray", "cost_input": 0, "cost_output": 45},
            {"id": "fal-ai/runway-gen3/turbo/image-to-video", "name": "Runway Gen3", "cost_input": 0, "cost_output": 40},
            {"id": "fal-ai/minimax/video-01", "name": "Minimax", "cost_input": 0, "cost_output": 70},
            {"id": "fal-ai/hailuo/video", "name": "Hailuo", "cost_input": 0, "cost_output": 60},
            {"id": "fal-ai/flux-pro/v1.1-ultra", "name": "Flux Pro", "cost_input": 0, "cost_output": 6},
            {"id": "fal-ai/flux-realism", "name": "Flux Realism", "cost_input": 0, "cost_output": 5},
            {"id": "fal-ai/recraft-v3", "name": "Recraft V3", "cost_input": 0, "cost_output": 8},
            {"id": "fal-ai/ideogram/v2", "name": "Ideogram", "cost_input": 0, "cost_output": 12},
            {"id": "fal-ai/midjourney-v6", "name": "Midjourney", "cost_input": 0, "cost_output": 15},
        ]
    }
]

# Генерируем словарь цен для быстрого доступа по ID модели
MODEL_PRICING = {}
for group in AI_MODELS_GROUPS:
    for m in group['models']:
        MODEL_PRICING[m['id']] = {
            "input": m.get("cost_input", 0),
            "output": m.get("cost_output", 0)
        }

def get_models_config():
    """Возвращает полный конфиг моделей для API"""
    return AI_MODELS_GROUPS

# ==============================================================================

async def generate_ai_response_stream(model_id: str, messages: list, user_balance: float, temperature: float = 0.7, web_search: bool = False, attachment_url: str = None):
    pricing = MODEL_PRICING.get(model_id)
    if not pricing:
        pricing = {"input": 0, "output": 0}
    
    # Подготовка сообщений (Vision)
    final_messages = []
    for msg in messages:
        content = msg["content"]
        role = msg["role"]
        
        if role == "user" and attachment_url and msg == messages[-1]:
            content_block = [{"type": "text", "text": content}]
            content_block.append({
                "type": "image_url",
                "image_url": {"url": attachment_url}
            })
            final_messages.append({"role": role, "content": content_block})
        else:
            final_messages.append({"role": role, "content": content})

    # Параметры OpenRouter
    extra_body = {}
    if web_search:
        extra_body["plugins"] = [{"id": "web_search"}] 

    try:
        stream = await client.chat.completions.create(
            model=model_id,
            messages=final_messages,
            temperature=temperature,
            stream=True,
            extra_body=extra_body
        )

        full_response = ""
        input_tokens_approx = sum(len(m['content']) for m in messages) / 4 
        
        async for chunk in stream:
            content = chunk.choices[0].delta.content
            if content:
                full_response += content
                yield content, 0.0

        # Финальный подсчет стоимости
        output_tokens = len(full_response) / 4
        total_cost = (input_tokens_approx / 1_000_000 * pricing['input']) + \
                     (output_tokens / 1_000_000 * pricing['output'])
        
        yield "", total_cost

    except Exception as e:
        logger.error(f"AI Generation Error: {e}")
        yield f"Error: {str(e)}", 0.0


async def generate_ai_response_media(model_id: str, messages: list, user_balance: float, attachment_url: str = None):
    """
    Генерация для медиа-моделей через Fal.ai (или другие API).
    """
    prompt = messages[-1]['content']
    pricing = MODEL_PRICING.get(model_id, {"input": 0, "output": 0})
    cost = pricing['output']

    if user_balance < cost:
        raise Exception("Недостаточно средств")

    try:
        # ЗАГЛУШКА: Эмуляция ответа для теста
        # В реальной версии здесь будет вызов Fal.ai
        import asyncio
        await asyncio.sleep(2)
        return f"![Generated Image](https://via.placeholder.com/1024x1024?text=Gen+{model_id.split('/')[-1]}) (Генерация {model_id})", cost

    except Exception as e:
        logger.error(f"Media Gen Error: {e}")
        raise e