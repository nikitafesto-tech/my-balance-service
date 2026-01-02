/**
 * ==========================================
 * NEIROSETIM AI — MAIN APPLICATION SCRIPT
 * Объединяет: Theme, Chat Logic, Sidebar, Profile/Payment
 * ==========================================
 */

// ==========================================
// 1. THEME MANAGEMENT (бывший theme.js)
// ==========================================
(function() {
    // Получить сохраненную тему или системную
    function getPreferredTheme() {
        const saved = localStorage.getItem('theme');
        if (saved) return saved;
        return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
    }
    
    // Применить тему к документу
    function applyTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('theme', theme);
    }
    
    // Глобальная функция переключения (используется в chatApp и кнопках)
    window.toggleTheme = function() {
        const current = document.documentElement.getAttribute('data-theme') || 'dark';
        const next = current === 'dark' ? 'light' : 'dark';
        applyTheme(next);
    };
    
    // Применить при загрузке
    applyTheme(getPreferredTheme());
    
    // Слушать системные изменения
    window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', (e) => {
        if (!localStorage.getItem('theme')) {
            applyTheme(e.matches ? 'light' : 'dark');
        }
    });
})();


// ==========================================
// 2. CHAT & APP LOGIC (бывший chat.js)
// ==========================================

// Возможности моделей
const MODEL_CAPABILITIES = {
    'default': { vision: true, web: true },
    'recraft-v3': { vision: false, web: false },
    'flux-1.1-ultra': { vision: false, web: false },
    'veo-3.1': { vision: false, web: false },
    'midjourney': { vision: false, web: false },
    'luma-ray-2': { vision: false, web: false },
    'o1-preview': { vision: false, web: false },
    'o1-mini': { vision: false, web: false },
    'deepseek-r1': { vision: false, web: false },
};

/**
 * Main Alpine.js Component
 * Подключается в base_app.html через x-data="chatApp()"
 */
function chatApp() {
    return {
        // --- UI State ---
        sidebarOpen: false, // Мобильное меню
        sidebarCollapsed: localStorage.getItem('sidebarCollapsed') === 'true', // Десктоп сворачивание
        isTyping: false,
        isUploading: false,
        
        // --- Chat Data ---
        messages: [],
        userInput: '',
        activeChatId: null,
        chats: [],
        chatSearch: '',
        model: 'gpt-4o',
        
        // --- Features State ---
        attachedFileUrl: null,
        canVision: true,
        replyContext: null,
        isTempChat: false, // Временный чат
        
        // --- Menus State ---
        historyMenuOpen: false, // Меню корзины
        renamingChatId: null,
        renameTitle: '',
        activeChatMenu: null, // Меню "три точки"

        // --- Toast Notifications ---
        toast: { show: false, message: '', type: 'info', timeout: null },

        init() {
            // Инициализация данных из HTML атрибутов
            const el = this.$el; 
            if (el) {
                // Если мы на странице чата или есть эти атрибуты
                if (el.dataset.balance) console.log('Balance loaded:', el.dataset.balance);
            }

            this.loadChats();
            
            // Если открыт конкретный чат (URL: /chat/123)
            const path = window.location.pathname;
            const match = path.match(/\/chat\/(\d+)/);
            if (match) {
                this.loadChat(match[1]);
            } else if (path === '/') {
                // Если главная - проверяем, нужно ли начать новый
            }

            // Настройка Markdown парсера
            this.setupMarkdown();
        },

        // --- SIDEBAR LOGIC ---

        toggleSidebarCollapse() {
            this.sidebarCollapsed = !this.sidebarCollapsed;
            localStorage.setItem('sidebarCollapsed', this.sidebarCollapsed);
            // Даем время CSS анимации отработать, если нужно
            setTimeout(() => {
                window.dispatchEvent(new Event('resize'));
            }, 300);
        },

        get filteredChats() {
            if (!this.chatSearch) return this.chats;
            const q = this.chatSearch.toLowerCase();
            return this.chats.filter(c => c.title.toLowerCase().includes(q));
        },

        async loadChats() {
            try {
                const res = await fetch('/chats/');
                if (res.ok) {
                    this.chats = await res.json();
                }
            } catch (e) {
                console.error("Failed to load chats", e);
            }
        },

        // --- CHAT LOGIC ---

        async startNewChat() {
            this.activeChatId = null;
            this.messages = [];
            this.attachedFileUrl = null;
            
            // Если включен временный режим - остаемся в нем, иначе сбрасываем
            // this.isTempChat = false; // (Опционально: можно сбрасывать)
            
            window.history.pushState({}, '', '/');
        },

        toggleTempChat() {
            this.isTempChat = !this.isTempChat;
            if (this.isTempChat) {
                this.startNewChat();
                this.showToast('Включен режим временного чата (24ч)', 'info');
            } else {
                this.startNewChat(); // Тоже сбрасываем, чтобы начать "чистый" постоянный чат
                this.showToast('Обычный режим (история сохраняется)', 'success');
            }
        },

        async loadChat(id) {
            try {
                this.activeChatId = id;
                // На мобильных закрываем меню при выборе
                this.sidebarOpen = false; 
                
                const res = await fetch(`/chats/${id}`);
                if (!res.ok) throw new Error("Chat not found");
                
                const data = await res.json();
                this.messages = data.messages || [];
                this.model = data.model;
                this.isTempChat = !!data.expires_at; // Если есть дата сгорания - это временный
                
                window.history.pushState({}, '', `/chat/${id}`);
                this.scrollToBottom();
                
            } catch (e) {
                this.showToast(e.message, 'error');
            }
        },

        async sendMessage() {
            const text = this.userInput.trim();
            if ((!text && !this.attachedFileUrl) || this.isTyping) return;

            // 1. Добавляем сообщение пользователя в UI
            const userMsg = {
                id: Date.now(),
                role: 'user',
                content: text,
                image_url: this.attachedFileUrl
            };
            this.messages.push(userMsg);
            
            // Сброс полей ввода
            this.userInput = '';
            const fileUrl = this.attachedFileUrl;
            this.attachedFileUrl = null;
            this.$refs.chatInput.style.height = 'auto';
            this.scrollToBottom();

            this.isTyping = true;

            try {
                // 2. Определяем URL (новый чат или продолжение)
                let url = this.activeChatId 
                    ? `/chats/${this.activeChatId}/message` 
                    : '/chats/new';

                const payload = {
                    message: text,
                    model: this.model,
                    attachment_url: fileUrl,
                    is_temporary: this.isTempChat // Передаем флаг временного чата
                };

                const response = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                if (!response.ok) throw new Error('Network error');

                // Если был новый чат - сохраняем его ID
                if (!this.activeChatId) {
                    const idHeader = response.headers.get('X-Chat-Id');
                    if (idHeader) {
                        this.activeChatId = parseInt(idHeader);
                        window.history.pushState({}, '', `/chat/${this.activeChatId}`);
                        this.loadChats(); // Обновляем сайдбар
                    }
                }

                // 3. Читаем стрим ответа (Streaming Response)
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                
                // Создаем пустое сообщение бота
                const botMsgId = Date.now() + 1;
                this.messages.push({
                    id: botMsgId,
                    role: 'assistant',
                    content: '',
                    isStreaming: true
                });

                let botContent = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    
                    const chunk = decoder.decode(value);
                    // Обработка SSE формата (data: ...)
                    const lines = chunk.split('\n');
                    
                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            try {
                                const json = JSON.parse(line.slice(6));
                                if (json.content) {
                                    botContent += json.content;
                                    // Обновляем последнее сообщение
                                    this.messages[this.messages.length - 1].content = botContent;
                                    this.scrollToBottom();
                                }
                            } catch (e) {
                                // Игнорируем ошибки парсинга чанков
                            }
                        }
                    }
                }

                this.messages[this.messages.length - 1].isStreaming = false;

            } catch (e) {
                console.error(e);
                this.showToast('Ошибка отправки сообщения', 'error');
                this.isTyping = false;
            } finally {
                this.isTyping = false;
                this.loadChats(); // Обновляем список (поднимаем чат наверх)
            }
        },

        // --- HISTORY & MANAGEMENT ---

        async deleteHistory(range) {
            if (!confirm('Вы уверены? Это действие нельзя отменить.')) return;
            
            try {
                const res = await fetch(`/chats/history/clear?range=${range}`, { method: 'DELETE' });
                if (res.ok) {
                    this.showToast('История очищена', 'success');
                    this.loadChats();
                    if (range === 'all' || range === 'last_24h') {
                        this.startNewChat();
                    }
                }
            } catch (e) {
                this.showToast('Ошибка удаления', 'error');
            }
            this.historyMenuOpen = false;
        },

        async deleteChat(id) {
            if (!confirm("Удалить этот чат?")) return;
            try {
                const res = await fetch(`/chats/${id}`, { method: 'DELETE' });
                if (res.ok) {
                    if (this.activeChatId === id) this.startNewChat();
                    this.loadChats();
                }
            } catch (e) {
                console.error(e);
            }
        },

        async togglePinChat(id) {
            try {
                const res = await fetch(`/chats/${id}/pin`, { method: 'PATCH' });
                if (res.ok) this.loadChats();
            } catch (e) { console.error(e); }
        },

        async shareChat(id) {
            try {
                const res = await fetch(`/chats/${id}/share`, { method: 'POST' });
                const data = await res.json();
                if (data.link) {
                    this.copyToClipboard(data.link);
                    this.showToast('Ссылка скопирована!', 'success');
                }
            } catch (e) {
                this.showToast('Ошибка создания ссылки', 'error');
            }
        },

        async startRenaming(id, oldTitle) {
            this.renamingChatId = id;
            this.renameTitle = oldTitle;
        },

        async submitRename() {
            if (!this.renamingChatId) return;
            try {
                await fetch(`/chats/${this.renamingChatId}`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ title: this.renameTitle })
                });
                this.loadChats();
            } catch(e) { console.error(e); }
            this.renamingChatId = null;
        },

        // --- UTILS ---

        async uploadFile(event) {
            const file = event.target.files[0];
            if (!file) return;

            this.isUploading = true;
            const formData = new FormData();
            formData.append('file', file);

            try {
                const res = await fetch('/upload', { method: 'POST', body: formData });
                if (!res.ok) throw new Error('Upload failed');
                const data = await res.json();
                this.attachedFileUrl = data.url;
                this.showToast('Файл прикреплен', 'success');
            } catch (e) {
                this.showToast('Ошибка загрузки', 'error');
            } finally {
                this.isUploading = false;
                event.target.value = ''; // сброс input
            }
        },

        copyToClipboard(text) {
            navigator.clipboard.writeText(text);
            this.showToast('Скопировано', 'success');
        },

        showToast(msg, type = 'info') {
            this.toast.message = msg;
            this.toast.type = type;
            this.toast.show = true;
            if (this.toast.timeout) clearTimeout(this.toast.timeout);
            this.toast.timeout = setTimeout(() => {
                this.toast.show = false;
            }, 3000);
        },
        
        scrollToBottom() {
            this.$nextTick(() => {
                const el = document.getElementById('chat-container');
                if (el) {
                    el.scrollTop = el.scrollHeight;
                }
            });
        },
        
        setupMarkdown() {
            // Инициализация Marked.js
            if (window.marked) {
                window.parseMarkdown = (text) => window.marked.parse(text);
            } else {
                window.parseMarkdown = (text) => text;
            }
        },
        
        stopGeneration() {
            // Реализация остановки генерации (нужен AbortController в fetch)
            window.location.reload(); // Временное решение
        },
        
        regenerate() {
            // Логика повторной отправки последнего промпта
            // (Пока оставим пустой или реализуем позже)
            this.showToast('Функция в разработке', 'info');
        }
    };
}


// ==========================================
// 3. PROFILE & PAYMENT LOGIC (бывший profile.js)
// ==========================================
// Оставляем эти функции в глобальной области видимости, 
// чтобы старые onclick="..." в HTML продолжали работать.

let checkout = null;

function closeModal() {
    const modal = document.getElementById('payment-modal');
    if (!modal) return;
    
    modal.classList.remove('active');
    setTimeout(() => {
        modal.style.display = 'none';
        if (checkout) { 
            checkout.destroy(); 
            checkout = null; 
        }
    }, 300);
}

async function openPaymentModal() {
    const amountInput = document.getElementById('amount-input');
    const btn = document.getElementById('pay-btn');
    const errorMsg = document.getElementById('error-msg');
    const modal = document.getElementById('payment-modal');
    
    if (!amountInput || !btn || !modal) {
        console.error("Payment modal elements not found");
        return;
    }

    const amount = amountInput.value;
    
    if (amount < 10) { 
        alert("Минимум 10р"); 
        return; 
    }
    
    const originalText = btn.innerText;
    btn.disabled = true; 
    btn.innerText = "...";
    
    try {
        const res = await fetch('/payment/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ amount: amount })
        });
        const data = await res.json();
        
        if (data.error) throw new Error(data.error);

        // Показываем модальное окно
        modal.style.display = 'flex';
        setTimeout(() => { modal.classList.add('active'); }, 10);
        
        // Инициализируем YooKassa виджет
        if (window.YooMoneyCheckoutWidget) {
            checkout = new window.YooMoneyCheckoutWidget({
                confirmation_token: data.confirmation_token,
                return_url: window.location.href,
                customization: {
                    colors: {
                        control_primary: '#a855f7', // Наш фиолетовый
                        control_primary_content: '#FFFFFF',
                        background: '#18181b',      // Наш темный фон
                        border: '#3f3f46',
                        text: '#FFFFFF',
                        control_secondary: '#27272a'
                    },
                    modal: false
                },
                error_callback: function(error) { 
                    console.log(error); 
                    closeModal(); 
                }
            });
            
            checkout.render('yookassa-widget');
            
            checkout.on('success', () => { 
                checkout.destroy(); 
                closeModal(); 
                alert("Оплата прошла успешно!"); 
                window.location.reload(); 
            });
            
            checkout.on('fail', () => { 
                checkout.destroy(); 
                closeModal(); 
            });
        } else {
            alert("Ошибка загрузки платежной системы");
        }

    } catch (e) {
        if (errorMsg) errorMsg.innerText = e.message;
        alert(e.message);
    } finally {
        btn.disabled = false;
        btn.innerText = originalText;
    }
}