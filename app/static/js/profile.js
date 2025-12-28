/**
 * Profile Page Logic
 * YooKassa виджет оплаты
 */

let checkout = null;

function closeModal() {
    const modal = document.getElementById('payment-modal');
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
    const amount = document.getElementById('amount-input').value;
    const btn = document.getElementById('pay-btn');
    const errorMsg = document.getElementById('error-msg');
    const modal = document.getElementById('payment-modal');
    
    if (amount < 10) { 
        alert("Минимум 10р"); 
        return; 
    }
    
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
        checkout = new window.YooMoneyCheckoutWidget({
            confirmation_token: data.confirmation_token,
            return_url: window.location.href,
            customization: {
                colors: {
                    control_primary: '#27ae60',
                    control_primary_content: '#FFFFFF',
                    background: '#161616',
                    border: '#333333',
                    text: '#FFFFFF',
                    control_secondary: '#2a2a2a'
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
            alert("Оплата прошла!"); 
            window.location.reload(); 
        });
        
        checkout.on('fail', () => { 
            checkout.destroy(); 
            closeModal(); 
        });

    } catch (e) {
        errorMsg.innerText = e.message;
    } finally {
        btn.disabled = false; 
        btn.innerText = "Пополнить";
    }
}
