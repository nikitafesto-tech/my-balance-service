/**
 * Tailwind CSS Configuration
 * Подключается перед загрузкой самого Tailwind в base.html
 * Связывает классы Tailwind с CSS-переменными из styles.css
 */

tailwind.config = {
    // Включаем темную тему по селектору (атрибут data-theme="dark" на html теге)
    darkMode: ['selector', '[data-theme="dark"]'],
    
    theme: {
        extend: {
            // ЦВЕТОВАЯ ПАЛИТРА
            // Используем CSS-переменные для динамической смены тем
            colors: {
                // Основные фоны
                'bg': 'var(--color-bg)',
                'bg-secondary': 'var(--color-bg-secondary)', // Карточки, сайдбар
                'bg-tertiary': 'var(--color-bg-tertiary)',   // Поля ввода
                'bg-elevated': 'var(--color-bg-elevated)',   // Ховеры, кнопки
                'bg-hover': 'var(--color-bg-hover)',
                
                // Текст
                'text-primary': 'var(--color-text)',
                'text-secondary': 'var(--color-text-secondary)',
                'text-muted': 'var(--color-text-muted)',
                'text-inverse': 'var(--color-text-inverse)',
                
                // Рамки
                'border': 'var(--color-border)',
                'border-hover': 'var(--color-border-hover)',
                
                // Акцентный цвет (Зеленый)
                'primary': {
                    DEFAULT: 'var(--color-primary)',
                    hover: 'var(--color-primary-hover)',
                    text: 'var(--color-primary-text)'
                },
                
                // Ошибки / Danger
                'danger': {
                    DEFAULT: 'var(--color-danger)',
                    hover: 'var(--color-danger-hover)'
                },
                
                // Хардкод цвета (используется в JS логике чата)
                'green': '#22c55e', 
            },
            
            // ШРИФТЫ
            fontFamily: {
                sans: ['var(--font-sans)', 'ui-sans-serif', 'system-ui', 'sans-serif'],
                mono: ['var(--font-mono)', 'ui-monospace', 'SFMono-Regular', 'monospace'],
            },
            
            // АНИМАЦИИ (дублируем то, что было в CSS для использования через классы animate-*)
            animation: {
                'pulse-thinking': 'pulse-thinking 2s infinite ease-in-out',
                'bounce': 'bounce 1s infinite',
            },
            
            // KEYFRAMES для анимаций
            keyframes: {
                'pulse-thinking': {
                    '0%, 100%': { opacity: '0.4', transform: 'scale(0.95)' },
                    '50%': { opacity: '1', transform: 'scale(1.05)' },
                }
            },
            
            // Z-INDEX (согласуем с styles.css)
            zIndex: {
                'dropdown': '100',
                'sticky': '200',
                'modal': '1000',
            }
        }
    }
}