/**
 * Chat Page Logic (Alpine.js)
 * Основная логика чата с AI
 * 
 * ВАЖНО: Jinja2 переменные передаются через data-атрибуты:
 * - data-balance: начальный баланс пользователя
 * - data-user-id: ID пользователя (casdoor_id)
 */

// Возможности моделей (vision, web search)
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
 * Alpine.js компонент чата
 * Использование: x-data="chatApp()"
 */
function chatApp() {
    return {
        // UI State
        sidebarOpen: false,
        isTyping: false,
        isUploading: false,
        
        // Model State
        currentModel: 'openai/gpt-4o',
        currentModelName: 'GPT-4o',
        aiGroups: [],
        
        // Chat State
        userInput: '',
        attachedFileUrl: null,
        activeChatId: null,
        chatHistory: [],
        messages: [],
        replyContext: null,
        chatSearch: '',  // Поиск по чатам
        
        // Settings
        temperature: 0.7,
        webSearch: false,
        
        // Streaming control
        abortController: null,
        lastUserMessage: null,  // Для регенерации
        
        // Toast уведомления
        toast: { show: false, message: '', type: 'success' },
        
        // User Data (из data-атрибутов)
        balance: 0,

        // Computed: фильтрация чатов по поиску
        get filteredChats() {
            if (!this.chatSearch.trim()) return this.chatHistory;
            const query = this.chatSearch.toLowerCase();
            return this.chatHistory.filter(chat => 
                chat.title.toLowerCase().includes(query)
            );
        },

        // Computed
        get canVision() { 
            return (MODEL_CAPABILITIES[this.currentModel] || MODEL_CAPABILITIES['default']).vision; 
        },
        
        get canSearch() { 
            return (MODEL_CAPABILITIES[this.currentModel] || MODEL_CAPABILITIES['default']).web; 
        },
        
        getCurrentGroupIcon() {
            if (!this.aiGroups || this.aiGroups.length === 0) return "";
            for (const group of this.aiGroups) {
                if (group.models.find(m => m.id === this.currentModel)) {
                    return group.icon;
                }
            }
            return this.aiGroups[0].icon;
        },

        // Lifecycle
        async init() {
            // Читаем данные из data-атрибутов корневого элемента
            const root = this.$el;
            this.balance = parseFloat(root.dataset.balance || 0);
            
            await this.loadModels();
            await this.loadHistory();
        },

        // API Methods
        async loadModels() {
            try {
                const res = await fetch('/api/chats/models');
                if (res.ok) {
                    this.aiGroups = await res.json();
                    if (!this.currentModel && this.aiGroups.length > 0) {
                        const first = this.aiGroups[0].models[0];
                        this.setModel(first.id, first.name);
                    }
                }
            } catch (e) {
                console.error("Models load error", e);
            }
        },

        async loadHistory() {
            try {
                const res = await fetch('/api/chats');
                if (res.ok) {
                    this.chatHistory = await res.json();
                }
            } catch (e) {
                console.error("History load error", e);
            }
        },
        
        async loadChat(id) {
            this.activeChatId = id;
            this.messages = [];
            this.sidebarOpen = false;
            
            try {
                const res = await fetch(`/api/chats/${id}`);
                if (res.ok) {
                    const data = await res.json();
                    this.messages = data.messages || [];
                    
                    if (data.model) {
                        let foundName = data.model;
                        if (this.aiGroups.length > 0) {
                            for (const group of this.aiGroups) {
                                const m = group.models.find(x => x.id === data.model);
                                if (m) foundName = m.name;
                            }
                        }
                        this.currentModel = data.model;
                        this.currentModelName = foundName;
                    }
                    
                    this.scrollToBottom();
                }
            } catch (e) {
                console.error("Failed to load chat", e);
            }
        },
        
        // Actions
        setModel(id, name) {
            this.currentModel = id;
            this.currentModelName = name;
            if (this.messages.length > 0 && this.activeChatId) {
                this.startNewChat();
            }
        },
        
        startNewChat() {
            this.activeChatId = null;
            this.messages = [];
            this.userInput = '';
            this.attachedFileUrl = null;
            this.replyContext = null;
            this.$nextTick(() => this.$refs.chatInput.focus());
        },
        
        async deleteChat(chatId) {
            if (!confirm('Удалить этот чат?')) return;
            
            try {
                const res = await fetch(`/api/chats/${chatId}`, { method: 'DELETE' });
                if (res.ok) {
                    // Убираем из списка
                    this.chatHistory = this.chatHistory.filter(c => c.id !== chatId);
                    // Если удалили активный чат — очищаем
                    if (this.activeChatId === chatId) {
                        this.startNewChat();
                    }
                }
            } catch (e) {
                console.error("Delete failed", e);
            }
        },
        
        async renameChat(chatId, newTitle) {
            if (!newTitle.trim()) return;
            
            try {
                const res = await fetch(`/api/chats/${chatId}`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ title: newTitle })
                });
                if (res.ok) {
                    const data = await res.json();
                    // Обновляем название в списке
                    const chat = this.chatHistory.find(c => c.id === chatId);
                    if (chat) chat.title = data.title;
                }
            } catch (e) {
                console.error("Rename failed", e);
            }
        },
        
        showToast(message, type = 'success') {
            this.toast = { show: true, message, type };
            setTimeout(() => { this.toast.show = false; }, 2500);
        },
        
        copyToClipboard(text) {
            navigator.clipboard.writeText(text);
            this.showToast('Скопировано!');
        },
        
        exportChat() {
            if (this.messages.length === 0) return;
            
            const chat = this.chatHistory.find(c => c.id === this.activeChatId);
            const title = chat ? chat.title : 'chat';
            
            let content = `# ${title}\n\n`;
            for (const msg of this.messages) {
                const role = msg.role === 'user' ? '👤 Вы' : '🤖 AI';
                content += `## ${role}\n${msg.content}\n\n`;
            }
            
            const blob = new Blob([content], { type: 'text/markdown' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${title.replace(/[^a-zа-яё0-9]/gi, '_')}.md`;
            a.click();
            URL.revokeObjectURL(url);
            
            this.showToast('Чат экспортирован');
        },
        
        replyToMessage(msg) {
            const preview = msg.content.substring(0, 60) + (msg.content.length > 60 ? '...' : '');
            this.replyContext = { id: msg.id, content: msg.content, preview: preview };
            this.$refs.chatInput.focus();
        },
        
        stopGeneration() {
            if (this.abortController) {
                this.abortController.abort();
                this.abortController = null;
            }
            this.isTyping = false;
            // Убираем индикатор стриминга
            const lastMsg = this.messages[this.messages.length - 1];
            if (lastMsg && lastMsg.isStreaming) {
                lastMsg.isStreaming = false;
                lastMsg.content += ' [Остановлено]';
            }
        },
        
        async regenerate() {
            if (this.isTyping) return;
            
            // Если lastUserMessage пуст (например, после перезагрузки), ищем последнее сообщение пользователя
            if (!this.lastUserMessage) {
                const lastUserMsg = this.messages.slice().reverse().find(m => m.role === 'user');
                if (lastUserMsg) {
                    this.lastUserMessage = lastUserMsg.content;
                } else {
                    return;
                }
            }
            
            // Удаляем последний ответ ассистента
            if (this.messages.length > 0 && this.messages[this.messages.length - 1].role === 'assistant') {
                this.messages.pop();
            }
            
            // Повторно отправляем
            this.userInput = this.lastUserMessage;
            await this.sendMessage();
        },

        async sendMessage() {
            if (!this.userInput.trim() && !this.attachedFileUrl) return;
            
            let textToSend = this.userInput;
            if (this.replyContext) {
                const quotePrefix = this.replyContext.content.split('\n').map(line => `> ${line}`).join('\n');
                textToSend = `${quotePrefix}\n\n${this.userInput}`;
            }

            const fileUrl = this.attachedFileUrl;
            this.userInput = '';
            this.attachedFileUrl = null;
            this.replyContext = null;
            this.lastUserMessage = textToSend;  // Сохраняем для регенерации
            this.$refs.chatInput.style.height = 'auto';

            const userMsgId = Date.now();
            this.messages.push({ role: 'user', content: textToSend, attachment_url: fileUrl, id: userMsgId });
            
            const botMsgId = userMsgId + 1;
            this.messages.push({ role: 'assistant', content: '', id: botMsgId, isStreaming: true });
            
            this.scrollToBottom();
            this.isTyping = true;
            
            // Создаём контроллер для отмены
            this.abortController = new AbortController();

            try {
                const payload = {
                    message: textToSend,
                    model: this.currentModel,
                    temperature: parseFloat(this.temperature),
                    web_search: this.webSearch && this.canSearch,
                    attachment_url: fileUrl
                };
                
                const url = !this.activeChatId ? '/api/chats/new' : `/api/chats/${this.activeChatId}/message`;
                const response = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                    signal: this.abortController.signal
                });
                
                if (response.status === 402) {
                    const errData = await response.json();
                    const msg = this.messages.find(m => m.id === botMsgId);
                    if (msg) {
                        msg.content = "⛔ " + errData.detail;
                        msg.isStreaming = false;
                    }
                    return;
                }

                const contentType = response.headers.get("content-type");
                
                if (contentType && contentType.includes("application/json")) {
                    // Синхронный ответ (медиа-модели)
                    const data = await response.json();
                    if (!this.activeChatId && data.chat_id) {
                        this.activeChatId = data.chat_id;
                        await this.loadHistory();
                    }
                    if (data.balance !== undefined) {
                        this.balance = data.balance;
                    }

                    const msgIndex = this.messages.findIndex(m => m.id === botMsgId);
                    if (msgIndex !== -1) {
                        const lastMsg = data.messages[data.messages.length - 1];
                        this.messages[msgIndex] = {
                            ...this.messages[msgIndex],
                            content: lastMsg.content,
                            image_url: lastMsg.image_url,
                            isStreaming: false
                        };
                    }
                } else {
                    // Стриминг ответ (текстовые модели)
                    const reader = response.body.getReader();
                    const decoder = new TextDecoder();
                    let botText = "";
                    let buffer = "";

                    while (true) {
                        const { done, value } = await reader.read();
                        if (done) break;
                        
                        buffer += decoder.decode(value, { stream: true });
                        const lines = buffer.split('\n');
                        buffer = lines.pop(); // Keep the last partial line in buffer
                        
                        for (const line of lines) {
                            if (!line.trim()) continue;
                            try {
                                const json = JSON.parse(line);
                                
                                if (json.type === 'meta' && !this.activeChatId) {
                                    this.activeChatId = json.chat_id;
                                    await this.loadHistory();
                                }
                                else if (json.type === 'content') {
                                    botText += json.text;
                                    const msg = this.messages.find(m => m.id === botMsgId);
                                    if (msg) msg.content = botText;
                                    this.scrollToBottom();
                                }
                                else if (json.type === 'balance') {
                                    this.balance = json.balance;
                                }
                                else if (json.type === 'error') {
                                    botText += `\n[Ошибка: ${json.text}]`;
                                    const msg = this.messages.find(m => m.id === botMsgId);
                                    if (msg) msg.content = botText;
                                }
                            } catch (e) {
                                // Ignore parse errors
                            }
                        }
                    }
                    
                    const msg = this.messages.find(m => m.id === botMsgId);
                    if (msg) msg.isStreaming = false;
                }

            } catch (e) {
                const msg = this.messages.find(m => m.id === botMsgId);
                if (msg) {
                    msg.content = '⚠️ Ошибка при генерации.';
                    msg.isStreaming = false;
                }
            } finally {
                this.isTyping = false;
                this.scrollToBottom();
            }
        },

        async uploadFile(event) {
            const file = event.target.files[0];
            if (!file) return;
            
            this.isUploading = true;
            
            const formData = new FormData();
            formData.append('file', file);
            
            try {
                const res = await fetch('/api/upload', { method: 'POST', body: formData });
                const data = await res.json();
                if (data.url) {
                    this.attachedFileUrl = data.url;
                    this.$refs.fileInput.value = '';
                }
            } catch (e) {
                alert("Ошибка загрузки");
            } finally {
                this.isUploading = false;
            }
        },

        // Markdown Parsing
        parseMarkdown(text) {
            if (!text) return "";
            
            // Обработка блоков <think> (в том числе незакрытых при стриминге)
            // Если есть открывающий тег, но нет закрывающего - считаем всё до конца "мыслями"
            if (text.includes('<think>') && !text.includes('</think>')) {
                text = text.replace('<think>', '<details class="reasoning" open><summary>Размышления</summary><div class="reasoning-content">') + '</div></details>';
            } else {
                text = text.replace(
                    /<think>([\s\S]*?)<\/think>/g,
                    '<details class="reasoning"><summary>Размышления</summary><div class="reasoning-content">$1</div></details>'
                );
            }
            
            let html = marked.parse(text);
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, 'text/html');
            
            // Добавляем обёртку и кнопку копирования для блоков кода
            doc.querySelectorAll('pre code').forEach((block) => {
                let lang = "Code";
                block.classList.forEach(cls => {
                    if (cls.startsWith('language-')) {
                        lang = cls.replace('language-', '');
                    }
                });
                
                const pre = block.parentElement;
                const wrapper = document.createElement('div');
                wrapper.className = 'code-wrapper';
                
                const header = document.createElement('div');
                header.className = 'code-header';
                header.innerHTML = `<span>${lang}</span> <span class="copy-code-btn" onclick="navigator.clipboard.writeText(this.parentElement.nextElementSibling.innerText)">📋 Копировать</span>`;
                
                pre.parentNode.insertBefore(wrapper, pre);
                wrapper.appendChild(header);
                wrapper.appendChild(pre);
                
                hljs.highlightElement(block);
            });

            // Рендеринг формул KaTeX
            // Проверяем наличие функции и пробуем отрендерить
            if (window.renderMathInElement) {
                try {
                    renderMathInElement(doc.body, {
                        delimiters: [
                            {left: '$$', right: '$$', display: true},
                            {left: '$', right: '$', display: false},
                            {left: '\\(', right: '\\)', display: false},
                            {left: '\\[', right: '\\]', display: true}
                        ],
                        throwOnError: false,
                        errorColor: '#cc0000'
                    });
                } catch (e) {
                    console.warn("KaTeX render error:", e);
                }
            }
            
            return doc.body.innerHTML;
        },
        
        scrollToBottom() {
            this.$nextTick(() => {
                const el = document.getElementById('chat-container');
                if (el) {
                    // Умный скролл: скроллим только если пользователь внизу или чат только начался
                    const isAtBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 100;
                    if (isAtBottom || this.messages.length <= 2) {
                        el.scrollTop = el.scrollHeight;
                    }
                }
            });
        }
    };
}
