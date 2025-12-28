# Copilot Instructions for my-balance-service

## Project Overview
**MyService** — FastAPI-based personal account system with OAuth integration through Casdoor and payment processing via YooKassa.

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

## Known Issues & Refactoring Targets (Prioritize Fixing)
1.  **Hardcoded Internal URLs**: `app/services/casdoor.py` uses `http://casdoor:8000`. This should be moved to `CASDOOR_INTERNAL_URL` env var.
2.  **Blocking Email**: `send_email_via_smtp` in `auth.py` is synchronous. Refactor to use `fastapi-mail` or `BackgroundTasks` to avoid blocking the event loop.
3.  **Session Cleanup**: `UserSession` table has no expiration. Old sessions accumulate indefinitely.
4.  **Database Migrations**: Project uses `Base.metadata.create_all()`. **Use Alembic** for any future schema changes.
5.  **Testing**: No tests exist. New features must include `pytest` tests in `tests/` folder.

## Code Conventions

1.  **API Response Format**: Always use `JSONResponse` for `/api/` routes.
2.  **Error Handling**: Use `custom_http_exception_handler` for 404s; log exceptions with `logger.error()`.
3.  **Dependencies**: `get_current_user()` validates session from cookies.
4.  **Jinja2 Context**: Always pass `request` object to TemplateResponse.

## Key Files Reference
- `app/main.py`: App init, page routes, error handlers.
- `app/routers/auth.py`: OAuth flow (VK, Google, Yandex, Email, Telegram).
- `app/services/casdoor.py`: User sync & balance sync.
- `app/models.py`: SQLAlchemy models (`UserWallet`, `Payment`, `UserSession`, `Chat`).
- `docker-compose.yml`: Services definition.

---

## ⚠️ CRITICAL: Do Not Break These Components

### Database Models (app/models.py)
**DO NOT modify existing columns without migration:**
```python
# UserWallet - PRIMARY user data
- casdoor_id: String (UNIQUE, format: "{provider}_{user_id}", e.g., "vk_123456")
- email, name, avatar, phone, balance

# UserSession - Auth sessions  
- session_id: String (UUID, PRIMARY KEY)
- token: String (stores casdoor_id, NOT actual token)

# Payment - Transaction history
- yookassa_payment_id: String (UNIQUE, for idempotency)
- user_id: String (references casdoor_id, NOT foreign key)
- status: String (default "pending", changes to "succeeded")

# Chat & Message - AI conversations
- Chat.user_casdoor_id: ForeignKey to wallets.casdoor_id
- Chat.model: String (AI model ID, e.g., "openai/gpt-4o")
- Message.image_url / attachment_url: S3 URLs
```

### Authentication Flow (DO NOT CHANGE ORDER)
```
1. OAuth callback receives `code`
2. Exchange code → access_token  
3. Fetch user profile from provider
4. Build `clean_data = {id, name, email, avatar, phone}`
5. await finalize_login(clean_data, prefix, db)  # Syncs to Casdoor
6. return update_session_cookie(response, clean_data, prefix, db)  # Sets cookie
```
**Breaking this order = broken auth!**

### Session Cookie Settings
```python
response.set_cookie(
    key="session_id", 
    value=new_session_id, 
    httponly=True,      # MUST be True (security)
    samesite="lax"      # MUST be "lax" for OAuth redirects
)
```

### AI Models Config (app/services/ai_generation.py)
**Structure must match frontend expectations:**
```python
AI_MODELS_GROUPS = [
    {
        "name": "Group Name",           # Display name
        "icon": "<svg>...</svg>",       # SVG string for UI
        "models": [
            {
                "id": "provider/model-name",  # OpenRouter format
                "name": "Display Name",
                "cost_input": 2.5,            # $ per 1M input tokens
                "cost_output": 10             # $ per 1M output tokens
            }
        ]
    }
]
```
**Frontend reads this via `GET /api/chats/models`**

### Chat Streaming Protocol (NDJSON)
```json
{"type": "meta", "chat_id": 123}        // First message
{"type": "content", "text": "Hello"}    // Streamed chunks
{"type": "balance", "balance": 99.50}   // Final balance
{"type": "error", "text": "Error msg"}  // On failure
```
**Frontend in chat.html expects exactly these types!**

### Media Models Detection
```python
# In chats.py - determines stream vs sync response
media_models_keywords = ["recraft", "flux", "midjourney", "veo", "sora", "luma", "video", "image"]
is_media = any(kw in model.lower() for kw in media_models_keywords)
```
**Adding new media model? Add keyword here!**

### S3 Upload (app/services/s3.py)
```python
# Public URL construction - DO NOT CHANGE without updating frontend
if S3_PUBLIC_DOMAIN:
    return f"{S3_PUBLIC_DOMAIN}/{unique_filename}"
else:
    return f"{ENDPOINT_URL}/{BUCKET_NAME}/{unique_filename}"
```

### YooKassa Payment Creation
```python
# CRITICAL: Never include payment_method_data with embedded widget!
payment = YooPayment.create({
    "amount": {"value": str(amount), "currency": "RUB"},
    "confirmation": {"type": "embedded"},  # Triggers widget
    "capture": True,
    "description": f"Пополнение {user.email}",
    "metadata": {"user_id": user.casdoor_id}
})
```

### Frontend Dependencies (chat.html)
```html
<!-- DO NOT REMOVE - Required libraries -->
<script src="https://cdn.tailwindcss.com"></script>
<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<script src="https://unpkg.com/@phosphor-icons/web"></script>
```

### Template Variables (Jinja2 Context)
```python
# chat.html expects these variables:
{
    "request": request,      # Required by Jinja2
    "name": user.name,
    "email": user.email, 
    "balance": int(user.balance),
    "avatar": user.avatar,
    "user_id": user.casdoor_id
}

# profile.html expects:
{"request", "name", "balance", "email", "avatar"}
```

---

## 🔧 Safe Modification Guidelines

### Adding New OAuth Provider
1. Add env vars: `{PROVIDER}_CLIENT_ID`, `{PROVIDER}_CLIENT_SECRET`
2. Create `/login/{provider}-direct` route (redirect to OAuth)
3. Create `/callback/{provider}` route (handle callback)
4. Build `clean_data` dict with required fields
5. Call `finalize_login()` + `update_session_cookie()`

### Adding New AI Model
1. Add to `AI_MODELS_GROUPS` in `ai_generation.py`
2. If media model → add keyword to `media_models_keywords` in `chats.py`
3. Set correct `cost_input`/`cost_output`
4. Test via UI model selector

### Adding New API Endpoint
1. Use `/api/` prefix for JSON responses
2. Add to appropriate router (`auth.py`, `chats.py`) or `main.py`
3. Use `get_current_user(request, db)` for auth
4. Return `JSONResponse` or `StreamingResponse`
5. Handle 401/402/404 with `HTTPException`

### Modifying Database Schema
1. **NEVER** use `Base.metadata.create_all()` for changes
2. Create Alembic migration: `alembic revision --autogenerate`
3. Test migration locally first
4. Apply: `alembic upgrade head`

---

## 📊 Current Working State (Dec 2025)

### Functional Features ✅
- OAuth: VK, Google, Yandex, Telegram, Email
- Payments: YooKassa embedded widget
- AI Chat: 50+ models, streaming, markdown
- File uploads: Images to S3
- Vision: Attach images to prompts
- Media generation: Fal.ai integration (partial)

### Environment Variables Required
```env
# Core
SITE_URL, AUTH_URL, DB_URL

# Casdoor
CASDOOR_CLIENT_ID, CASDOOR_CLIENT_SECRET, CASDOOR_CERT_FILE

# OAuth Providers  
VK_CLIENT_ID, VK_CLIENT_SECRET
GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
YANDEX_CLIENT_ID, YANDEX_CLIENT_SECRET
TELEGRAM_BOT_TOKEN

# Payments
YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY

# Email
SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD

# S3 Storage
S3_ACCESS_KEY, S3_SECRET_KEY, S3_BUCKET_NAME
S3_ENDPOINT_URL, S3_REGION_NAME, S3_PUBLIC_DOMAIN

# AI
OPENROUTER_API_KEY, FAL_KEY
```

### Docker Services
```yaml
db:       PostgreSQL 15 (port 5432)
casdoor:  Identity Provider (port 8000)
app:      FastAPI (port 8081)
caddy:    Reverse Proxy (ports 80, 443)
```
