/**
 * Signin Page Logic (Tailwind Compatible)
 * Логика страницы входа с переключением классов visibility
 */

let step = 1; // 1 = ввод email, 2 = ввод кода

// Вспомогательные функции для работы с Tailwind
function show(id) {
    const el = document.getElementById(id);
    if (el) el.classList.remove('hidden');
}

function hide(id) {
    const el = document.getElementById(id);
    if (el) el.classList.add('hidden');
}

function showEmailForm() {
    hide('social-login-block');
    show('email-section');
    document.getElementById('email-input').focus();
}

function showSocialLogin() {
    hide('email-section');
    show('social-login-block');
    resetEmailForm();
}

function resetEmailForm() {
    step = 1;
    hide('code-input-group');
    
    const emailInput = document.getElementById('email-input');
    emailInput.disabled = false;
    
    const btn = document.getElementById('email-action-btn');
    btn.innerText = "Получить код";
    btn.disabled = false;
    
    document.getElementById('email-title').innerText = "Вход по почте";
    document.getElementById('email-subtitle').innerText = "Введите ваш email адрес";
    
    const errorDiv = document.getElementById('email-error');
    errorDiv.innerText = "";
    hide('email-error');
}

async function handleEmailAction() {
    const emailInput = document.getElementById('email-input');
    const email = emailInput.value;
    const btn = document.getElementById('email-action-btn');

    if (!email.includes('@')) {
        showError('Введите корректный email');
        return;
    }

    hide('email-error');
    btn.disabled = true;

    if (step === 1) {
        // ШАГ 1: Отправляем код
        const originalText = btn.innerText;
        btn.innerText = "Отправка...";
        
        try {
            const res = await fetch('/auth/email/request-code', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: email })
            });
            const data = await res.json();
            
            if (data.error) throw new Error(data.error);

            // Успех, переходим к шагу 2
            step = 2;
            show('code-input-group');
            emailInput.disabled = true;
            btn.innerText = "Войти";
            
            document.getElementById('email-title').innerText = "Введите код";
            document.getElementById('email-subtitle').innerText = "Мы отправили код на вашу почту";
            document.getElementById('code-input').focus();

        } catch (e) {
            showError(e.message || "Ошибка сервера");
            btn.innerText = originalText;
        } finally {
            btn.disabled = false;
        }
    } else {
        // ШАГ 2: Проверяем код
        const codeInput = document.getElementById('code-input');
        const code = codeInput.value;
        
        if (code.length < 4) {
            showError("Введите полный код");
            btn.disabled = false;
            return;
        }

        btn.innerText = "Проверка...";
        try {
            const res = await fetch('/auth/email/verify-code', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: email, code: code })
            });
            const data = await res.json();
            
            if (data.error) throw new Error(data.error);

            // Успех!
            window.location.href = "/";

        } catch (e) {
            showError(e.message || "Неверный код");
            btn.innerText = "Войти";
            btn.disabled = false;
        }
    }
}

function showError(msg) {
    const el = document.getElementById('email-error');
    el.innerText = msg;
    show('email-error');
}