/**
 * Signin Page Logic
 * Логика страницы входа (email авторизация)
 */

let step = 1; // 1 = ввод email, 2 = ввод кода

function showEmailForm() {
    document.getElementById('social-login-block').style.display = 'none';
    document.getElementById('email-section').style.display = 'block';
    document.getElementById('email-input').focus();
}

function showSocialLogin() {
    document.getElementById('email-section').style.display = 'none';
    document.getElementById('social-login-block').style.display = 'block';
    resetEmailForm();
}

function resetEmailForm() {
    step = 1;
    document.getElementById('code-input-group').style.display = 'none';
    document.getElementById('email-input').disabled = false;
    document.getElementById('email-action-btn').innerText = "Получить код";
    document.getElementById('email-title').innerText = "Вход по почте";
    document.getElementById('email-subtitle').innerText = "Введите ваш email адрес";
    document.getElementById('email-error').innerText = "";
    document.getElementById('email-error').style.display = 'none';
}

async function handleEmailAction() {
    const email = document.getElementById('email-input').value;
    const errorDiv = document.getElementById('email-error');
    const btn = document.getElementById('email-action-btn');

    if (!email.includes('@')) {
        showError('Введите корректный email');
        return;
    }

    errorDiv.style.display = 'none';
    btn.disabled = true;

    if (step === 1) {
        // ШАГ 1: Отправляем код
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
            document.getElementById('code-input-group').style.display = 'block';
            document.getElementById('email-input').disabled = true;
            document.getElementById('email-action-btn').innerText = "Войти";
            document.getElementById('email-title').innerText = "Введите код";
            document.getElementById('email-subtitle').innerText = "Мы отправили код на вашу почту";
            document.getElementById('code-input').focus();

        } catch (e) {
            showError(e.message || "Ошибка сервера");
        } finally {
            btn.disabled = false;
            if (step === 1) btn.innerText = "Получить код";
        }
    } else {
        // ШАГ 2: Проверяем код
        const code = document.getElementById('code-input').value;
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
    el.style.display = 'block';
}
