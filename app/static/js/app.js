/**
 * ==========================================
 * NEIROSETIM AI — MAIN APPLICATION SCRIPT
 * Объединяет: Theme, Chat Logic, Sidebar, Profile/Payment
 * ==========================================
 */

// ==========================================
// 1. THEME MANAGEMENT
// ==========================================
(function() {
    function getPreferredTheme() {
        const saved = localStorage.getItem('theme');
        if (saved) return saved;
        return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
    }
    
    function applyTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('theme', theme);
    }
    
    window.toggleTheme = function() {
        const current = document.documentElement.getAttribute('data-theme') || 'dark';
        const next = current === 'dark' ? 'light' : 'dark';
        applyTheme(next);
    };
    
    applyTheme(getPreferredTheme());
    
    window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', (e) => {
        if (!localStorage.getItem('theme')) {
            applyTheme(e.matches ? 'light' : 'dark');
        }
    });
})();


// ==========================================
// 2. CHAT & APP LOGIC
// ==========================================

const MODEL_CAPABILITIES = {
    'default': { vision: true, web: true },
    // Модели без зрения и поиска
    'o1-preview': { vision: false, web: false },
    'o1-mini': { vision: false, web: false },
    'deepseek-r1': { vision: false, web: false },
    // Картинки и видео
    'recraft-v3': { vision: false, web: false },
    'flux-pro/v1.1-ultra': { vision: false, web: false },
    'kling-video/v1.5/pro': { vision: false, web: false },
    'midjourney-v6': { vision: false, web: false },
};

function chatApp() {
    return {
        // --- UI State ---
        sidebarOpen: false,
        sidebarCollapsed: localStorage.getItem('sidebarCollapsed') === 'true',
        isTyping: false,
        isUploading: false,
        
        // --- Chat Data ---
        messages: [],
        userInput: '',
        activeChatId: null,
        chats: [],
        aiGroups: [], 
        chatSearch: '',
        
        // ВАЖНО: Используем полный ID модели по умолчанию
        model: 'openai/gpt-4o', 
        
        // --- Features State ---
        attachedFileUrl: null,
        canVision: true,
        canSearch: true,
        webSearch: false,
        temperature: 0.7,
        replyContext: null,
        isTempChat: false,
        
        // --- Menus State ---
        historyMenuOpen: false,
        renamingChatId: null,
        renameTitle: '',
        
        // --- Toast ---
        toast: { show: false, message: '', type: 'info', timeout: null },

        init() {
            this.loadChats();
            this.loadModels(); 
            this.setupMarkdown();

            const path = window.location.pathname;
            const match = path.match(/\/chat\/(\d+)/);
            if (match) {
                this.loadChat(match[1]);
            }
        },

        // --- MODELS LOGIC ---
        
        async loadModels() {
            try {
                const res = await fetch('/chats/models');
                if (res.ok) {
                    this.aiGroups = await res.json();
                    this.updateCapabilities();
                }
            } catch (e) {
                console.error("Failed to load models", e);
                this.showToast("Ошибка загрузки списка моделей", "error");
            }
        },

        setModel(id, name) {
            this.model = id;
            this.updateCapabilities();
        },

        get currentModelName() {
            for (const group of this.aiGroups) {
                const found = group.models.find(m => m.id === this.model);
                if (found) return found.name;
            }
            return this.model; 
        },

        getCurrentGroupIcon() {
            for (const group of this.aiGroups) {
                if (group.models.find(m => m.id === this.model)) {
                    return group.icon;
                }
            }
            return `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm0 18a8 8 0 1 1 8-8 8 8 0 0 1-8 8z"/></svg>`; 
        },

        updateCapabilities() {
            let cap = MODEL_CAPABILITIES[this.model] || MODEL_CAPABILITIES['default'];
            
            if (!MODEL_CAPABILITIES[this.model]) {
                if (this.model.includes('claude-3')) cap = { vision: true, web: true };
                else if (this.model.includes('gpt-4')) cap = { vision: true, web: true };
            }

            this.canVision = cap.vision;
            this.canSearch = cap.web;
        },

        get currentModel() {
            return this.model;
        },

        // --- SIDEBAR LOGIC ---

        toggleSidebarCollapse() {
            this.sidebarCollapsed = !this.sidebarCollapsed;
            localStorage.setItem('sidebarCollapsed', this.sidebarCollapsed);
            setTimeout(() => { window.dispatchEvent(new Event('resize')); }, 300);
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
            window.history.pushState({}, '', '/');
        },

        toggleTempChat() {
            this.isTempChat = !this.isTempChat;
            if (this.isTempChat) {
                this.startNewChat();
                this.showToast('Включен временный чат (24ч)', 'info');
            } else {
                this.startNewChat();
                this.showToast('Обычный режим', 'success');
            }
        },

        async loadChat(id) {
            try {
                this.activeChatId = id;
                this.sidebarOpen = false; 
                
                const res = await fetch(`/chats/${id}`);
                if (!res.ok) throw new Error("Chat not found");
                
                const data = await res.json();
                this.messages = data.messages || [];
                
                if (data.model) {
                    this.model = data.model;
                    this.updateCapabilities();
                }
                
                this.isTempChat = !!data.expires_at;
                
                window.history.pushState({}, '', `/chat/${id}`);
                this.scrollToBottom();
                
            } catch (e) {
                this.showToast(e.message, 'error');
            }
        },

        async sendMessage() {
            const text = this.userInput.trim();
            if ((!text && !this.attachedFileUrl) || this.isTyping) return;

            const userMsg = {
                id: Date.now(),
                role: 'user',
                content: text,
                image_url: this.attachedFileUrl
            };
            this.messages.push(userMsg);
            
            this.userInput = '';
            const fileUrl = this.attachedFileUrl;
            this.attachedFileUrl = null;
            if (this.$refs.chatInput) this.$refs.chatInput.style.height = 'auto';
            this.scrollToBottom();

            this.isTyping = true;

            try {
                let url = this.activeChatId 
                    ? `/chats/${this.activeChatId}/message` 
                    : '/chats/new';

                const payload = {
                    message: text,
                    model: this.model,
                    attachment_url: fileUrl,
                    is_temporary: this.isTempChat
                };

                const response = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                if (!response.ok) throw new Error('Network error');

                if (!this.activeChatId) {
                    const idHeader = response.headers.get('X-Chat-Id');
                    if (idHeader) {
                        this.activeChatId = parseInt(idHeader);
                        window.history.pushState({}, '', `/chat/${this.activeChatId}`);
                        this.loadChats();
                    }
                }

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                
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
                    const lines = chunk.split('\n');
                    
                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            try {
                                const json = JSON.parse(line.slice(6));
                                if (json.content) {
                                    botContent += json.content;
                                    this.messages[this.messages.length - 1].content = botContent;
                                    this.scrollToBottom();
                                }
                            } catch (e) {}
                        }
                    }
                }

                this.messages[this.messages.length - 1].isStreaming = false;

            } catch (e) {
                console.error(e);
                this.showToast('Ошибка отправки', 'error');
                this.isTyping = false;
            } finally {
                this.isTyping = false;
                this.loadChats();
            }
        },

        // --- HISTORY & MANAGEMENT ---

        async deleteHistory(range) {
            if (!confirm('Вы уверены?')) return;
            try {
                const res = await fetch(`/chats/history/clear?range=${range}`, { method: 'DELETE' });
                if (res.ok) {
                    this.showToast('История очищена', 'success');
                    this.loadChats();
                    if (range === 'all' || range === 'last_24h') this.startNewChat();
                }
            } catch (e) { this.showToast('Ошибка', 'error'); }
            this.historyMenuOpen = false;
        },

        async deleteChat(id) {
            if (!confirm("Удалить чат?")) return;
            try {
                const res = await fetch(`/chats/${id}`, { method: 'DELETE' });
                if (res.ok) {
                    if (this.activeChatId === id) this.startNewChat();
                    this.loadChats();
                }
            } catch (e) { console.error(e); }
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
                    this.showToast('Ссылка скопирована', 'success');
                }
            } catch (e) { this.showToast('Ошибка', 'error'); }
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
            } catch(e) {}
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
                const res = await fetch('/api/upload', { method: 'POST', body: formData });
                if (!res.ok) throw new Error('Upload failed');
                const data = await res.json();
                this.attachedFileUrl = data.url;
                this.showToast('Файл загружен', 'success');
            } catch (e) {
                this.showToast('Ошибка загрузки', 'error');
            } finally {
                this.isUploading = false;
                event.target.value = '';
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
            this.toast.timeout = setTimeout(() => { this.toast.show = false; }, 3000);
        },
        
        scrollToBottom() {
            this.$nextTick(() => {
                const el = document.getElementById('chat-container');
                if (el) el.scrollTop = el.scrollHeight;
            });
        },
        
        setupMarkdown() {
            if (window.marked) {
                window.parseMarkdown = (text) => window.marked.parse(text);
            } else {
                window.parseMarkdown = (text) => text;
            }
        },
        
        stopGeneration() {
            window.location.reload(); 
        },
        
        regenerate() {
            this.showToast('Функция в разработке', 'info');
        }
    };
}


// ==========================================
// 3. PROFILE & PAYMENT LOGIC
// ==========================================

let checkout = null;

function closeModal() {
    const modal = document.getElementById('payment-modal');
    if (!modal) return;
    
    modal.classList.remove('active');
    setTimeout(() => {
        modal.style.display = 'none';
        if (checkout) { checkout.destroy(); checkout = null; }
    }, 300);
}

async function openPaymentModal() {
    const amountInput = document.getElementById('amount-input');
    const btn = document.getElementById('pay-btn');
    const errorMsg = document.getElementById('error-msg');
    const modal = document.getElementById('payment-modal');
    
    if (!amountInput || !btn || !modal) return;

    const amount = amountInput.value;
    if (amount < 10) { alert("Минимум 10р"); return; }
    
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

        modal.style.display = 'flex';
        setTimeout(() => { modal.classList.add('active'); }, 10);
        
        if (window.YooMoneyCheckoutWidget) {
            checkout = new window.YooMoneyCheckoutWidget({
                confirmation_token: data.confirmation_token,
                return_url: window.location.href,
                customization: {
                    colors: {
                        control_primary: '#a855f7',
                        control_primary_content: '#FFFFFF',
                        background: '#18181b',
                        border: '#3f3f46',
                        text: '#FFFFFF',
                        control_secondary: '#27272a'
                    },
                    modal: false
                },
                error_callback: function(error) { console.log(error); closeModal(); }
            });
            checkout.render('yookassa-widget');
            checkout.on('success', () => { 
                checkout.destroy(); 
                closeModal(); 
                alert("Оплата прошла успешно!"); 
                window.location.reload(); 
            });
            checkout.on('fail', () => { checkout.destroy(); closeModal(); });
        } else {
            alert("Ошибка платежной системы");
        }

    } catch (e) {
        if (errorMsg) errorMsg.innerText = e.message;
        alert(e.message);
    } finally {
        btn.disabled = false;
        btn.innerText = originalText;
    }
}