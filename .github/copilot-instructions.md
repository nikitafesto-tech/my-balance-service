# Copilot Instructions for my-balance-service (ChadGPT Analogue)

## Project Overview
**MyService** — FastAPI-based personal account system with OAuth integration through Casdoor and payment processing via YooKassa.
**Goal**: Create a full analogue of [ChadGPT](https://ask.chadgpt.ru), featuring multi-model AI chat, media generation (Image/Video/Audio), assistants, and knowledge base.

**Key Architecture Insight**: The app acts as an OAuth "bridge" — it handles OAuth callbacks from social networks (VK, Google, Yandex) instead of using Casdoor's standard UI. It then syncs user data with Casdoor and manages a custom `wallets` table for balances.

## Critical Architecture Patterns

### 1. Auth Flow (OAuth Bridge Pattern)
- **File**: `app/routers/auth.py`
- **Pattern**: User → Social Auth → FastAPI callback → Sync with Casdoor → Create/Update wallet
- **Key Functions**:
  - `sync_user_to_casdoor()` in `app/services/casdoor.py`: Creates user in Casdoor if not exists. **Must** include `"signupApplication": "Myservice"` so user appears in Casdoor admin UI.
  - `finalize_login()` & `update_session_cookie()`: Handles local session creation and cookie setting.
  - **Session Storage**: `UserSession` table maps `session_id` (UUID) to `casdoor_id`.
  - **Redirects**: Redirect URIs must match `SITE_URL` env var (localhost:8081 locally, https://lk.neirosetim.ru in prod).

### 2. Payment Flow (YooKassa Embedded Widget)
- **File**: `app/main.py` (payment routes), `app/routers/auth.py` (webhook handler)
- **Critical Constraint**: When using `confirmation: { type: "embedded" }` (pop-up widget), **never pass `payment_method_data`**. The widget must choose (Card/SBP) internally. Violating this causes `invalid_request` error.
- **Data Flow**: 
  1. Create payment in YooKassa → get `confirmation_token`
  2. Frontend renders JS widget with token
  3. YooKassa webhook calls `/api/payment/webhook`
  4. On `status: succeeded`, update `wallets.balance` and call `update_casdoor_balance()`

### 3. Balance Sync (Dual Tracking)
- **Primary**: `wallets` table (source of truth for users).
- **Secondary**: Casdoor `balance` or `score` field (for admin dashboard display).
- **Function**: `update_casdoor_balance()` in `app/services/casdoor.py` attempts to write to Casdoor, falls back from `balance` → `score` if needed.

### 4. Routing Organization
- **Hybrid Routing**: `app/main.py` handles both HTML pages (Jinja2) and API endpoints.
- **API Routes**: Should be prefixed with `/api/` to trigger JSON 404 responses (see `custom_http_exception_handler` in main.py).
- **Async**: All route handlers use `async def`.

## Environment & Deployment

### Local Development
- Run: `docker compose up -d --build`
- App: http://localhost:8081
- Casdoor: http://localhost:8000
- DB: localhost:5432
- **Secrets**: `.env` file (template in README.md).

### Production
- App behind Caddy (HTTPS).
- `.env` auto-generated from GitHub Secrets.

## Roadmap to ChadGPT Analogue (Plan of Changes)

### Phase 1: Real Media Generation (Priority)
- **Current State**: `generate_ai_response_media` in `ai_generation.py` is a stub (sleeps 2s, returns placeholder).
- **Action**: Implement `fal-client` integration.
- **Models to Support**:
  - **Image**: Flux Pro/Realism, Recraft V3, Midjourney v6.
  - **Video**: Kling 1.5, Luma Ray, Runway Gen-3, Minimax, Hailuo.
  - **Audio**: Suno, Udio (via Fal or other provider).
- **Technical**: Handle async polling for video generation (it takes time).

### Phase 2: Assistants & Personas
- **Goal**: Allow users to choose "Assistants" (e.g., "Coder", "Copywriter") with predefined system prompts.
- **Changes**:
  - New DB Model: `Assistant` (name, icon, system_prompt, is_public, user_id).
  - API: `GET /api/assistants`.
  - UI: Add "Assistants" tab in sidebar.

### Phase 3: Knowledge Base (File Context)
- **Goal**: Allow users to upload docs (PDF, TXT) and chat with them.
- **Changes**:
  - Enhance `upload_file_to_s3` to also extract text from documents.
  - Store extracted text in `FileContext` table or inject into Chat context window.
  - UI: "Attach to Knowledge Base" button.

### Phase 4: UI/UX Polish
- **Goal**: Match ChadGPT's clean, icon-heavy aesthetic.
- **Changes**:
  - "Auto" model selector (routes to cheap/fast or smart model automatically).
  - Improved Model Selector with categories (already started in `ai_generation.py`).

## Known Issues & Refactoring Targets
1.  **Media Generation Stub**: `app/services/ai_generation.py` mocks media generation. Needs real implementation.
2.  **Hardcoded Internal URLs**: `app/services/casdoor.py` uses `http://casdoor:8000`. Move to `CASDOOR_INTERNAL_URL`.
3.  **Blocking Email**: `send_email_via_smtp` is synchronous. Use `fastapi-mail` or `BackgroundTasks`.
4.  **Session Cleanup**: `UserSession` table has no expiration.
5.  **Database Migrations**: Project uses `Base.metadata.create_all()`. **Use Alembic**.

## Code Conventions

1.  **API Response Format**: Always use `JSONResponse` for `/api/` routes.
2.  **Error Handling**: Use `custom_http_exception_handler` for 404s; log exceptions with `logger.error()`.
3.  **Dependencies**: `get_current_user()` validates session from cookies.
4.  **Jinja2 Context**: Always pass `request` object to TemplateResponse.

## Key Files Reference
- `app/main.py`: App init, page routes, error handlers.
- `app/routers/auth.py`: OAuth flow.
- `app/routers/chats.py`: Chat logic, message handling.
- `app/services/ai_generation.py`: **Master Config** for models (`AI_MODELS_GROUPS`), generation logic.
- `app/services/s3.py`: S3 upload logic.
- `app/models.py`: DB Models (`UserWallet`, `Chat`, `Message`, `Payment`).

---

## ⚠️ CRITICAL: Do Not Break These Components

### Database Models (app/models.py)
**DO NOT modify existing columns without migration:**
```python
# UserWallet - PRIMARY user data
- casdoor_id: String (UNIQUE, format: "{provider}_{user_id}")
- balance: Float

# Chat & Message
- Chat.model: String (stores model ID from AI_MODELS_GROUPS)
- Message.image_url: String (S3 URL for generated images)
```

### AI Models Config (app/services/ai_generation.py)
**Structure must match frontend expectations:**
```python
AI_MODELS_GROUPS = [
    {
        "name": "Group Name",
        "icon": "<svg>...</svg>",
        "models": [
            {
                "id": "provider/model-name",
                "name": "Display Name",
                "cost_input": 2.5,
                "cost_output": 10
            }
        ]
    }
]
```

### Chat Streaming Protocol (NDJSON)
```json
{"type": "meta", "chat_id": 123}
{"type": "content", "text": "Hello"}
{"type": "balance", "balance": 99.50}
{"type": "error", "text": "Error msg"}
```

### Media Models Detection
```python
# In chats.py - determines stream vs sync response
media_models_keywords = ["recraft", "flux", "midjourney", "veo", "sora", "luma", "video", "image"]
is_media = any(kw in model.lower() for kw in media_models_keywords)
```

### S3 Upload (app/services/s3.py)
```python
# Public URL construction
if S3_PUBLIC_DOMAIN:
    return f"{S3_PUBLIC_DOMAIN}/{unique_filename}"
else:
    return f"{ENDPOINT_URL}/{BUCKET_NAME}/{unique_filename}"
```

---

## 🔧 Safe Modification Guidelines

### Adding New AI Model
1. Add to `AI_MODELS_GROUPS` in `ai_generation.py`.
2. If media model → add keyword to `media_models_keywords` in `chats.py`.
3. Set correct `cost_input`/`cost_output`.

### Implementing Media Generation
1. Modify `generate_ai_response_media` in `ai_generation.py`.
2. Use `fal-client` to call the specific model API.
3. Return the resulting image/video URL and cost.

### Modifying Database Schema
1. **NEVER** use `Base.metadata.create_all()` for changes.
2. Create Alembic migration: `alembic revision --autogenerate`.
3. Apply: `alembic upgrade head`.

---

## 📊 Current Working State (Dec 2025)

### Functional Features ✅
- OAuth: VK, Google, Yandex, Telegram, Email.
- Payments: YooKassa embedded widget.
- AI Chat: Text streaming (OpenRouter).
- File uploads: Images to S3.
- Vision: Attach images to prompts.

### Missing / In Progress 🚧
- **Media Generation**: Currently mocked (returns placeholder).
- **Assistants**: Not implemented.
- **Knowledge Base**: Not implemented.
- **Video/Audio**: Not implemented.

### Environment Variables Required
```env
# Core
SITE_URL, AUTH_URL, DB_URL

# AI
OPENROUTER_API_KEY, FAL_KEY
AI_PROXY_URL (Optional)

# Storage
S3_ACCESS_KEY, S3_SECRET_KEY, S3_BUCKET_NAME, S3_ENDPOINT_URL, S3_PUBLIC_DOMAIN
```
