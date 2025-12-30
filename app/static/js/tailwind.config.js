/**
 * Tailwind CSS Configuration
 * Подключается перед загрузкой самого Tailwind в base.html
 */

tailwind.config = {
    // Настройка темной темы через класс (работает с вашим theme.js)
    darkMode: ['selector', '[data-theme="dark"]'],
    
    theme: {
        extend: {
            colors: {
                /* === ФОНОВЫЕ ЦВЕТА === */
                // Ссылаются на CSS переменные из styles.css
                
                // Основные слои (Legacy)
                'bg': 'var(--color-bg)',
                'bg-secondary': 'var(--color-bg-secondary)', 
                'bg-tertiary': 'var(--color-bg-tertiary)',
                'bg-elevated': 'var(--color-bg-elevated)',
                'bg-hover': 'var(--color-bg-hover)',

                /* 👇 НОВЫЕ ПЕРЕМЕННЫЕ (Для новой авторизации) 👇 */
                // Связываем классы tailwind напрямую с переменными из вашего styles.css
                'bg-surface': 'var(--bg-surface)',         // Основной фон карточек (#18181b / #ffffff)
                'bg-input': 'var(--bg-input)',             // Фон полей ввода
                'bg-glass': 'var(--bg-surface-glass)',     // Эффект стекла
                
                /* === ТЕКСТ === */
                'text-primary': 'var(--color-text)',
                'text-secondary': 'var(--color-text-secondary)',
                'text-muted': 'var(--color-text-muted)',
                'text-inverse': 'var(--color-text-inverse)',
                
                /* === РАМКИ === */
                'border': 'var(--color-border)',
                
                /* === АКЦЕНТНЫЙ (Сиреневый) === */
                'primary': {
                    DEFAULT: 'var(--color-primary)', // #a855f7
                    hover: 'var(--color-primary-hover)',
                    text: 'var(--color-primary-text)',
                    // Добавляем прозрачность для эффектов свечения (glow)
                    '20': 'rgba(168, 85, 247, 0.2)', 
                },
                
                /* === ОШИБКИ === */
                'danger': {
                    DEFAULT: 'var(--color-danger)',
                },
                
                // Хардкод цвета для JS-логики
                'green': '#a855f7', 
            },
            
            fontFamily: {
                sans: ['var(--font-sans)', 'ui-sans-serif', 'system-ui', 'sans-serif'],
                mono: ['var(--font-mono)', 'ui-monospace', 'SFMono-Regular', 'monospace'],
            },
            
            borderRadius: {
                'xl': '1rem',
                '2xl': '1.5rem',
                '3xl': '2rem',
                // Можно добавить 4xl для особо крупных скруглений, если нужно
                '4xl': '2.5rem', 
            }
        }
    }
}