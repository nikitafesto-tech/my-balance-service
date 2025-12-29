/**
 * Tailwind CSS Configuration
 * Подключается перед загрузкой самого Tailwind в base.html
 */

tailwind.config = {
    darkMode: ['selector', '[data-theme="dark"]'],
    theme: {
        extend: {
            colors: {
                // Основные фоны (ссылаются на CSS переменные с поддержкой alpha-канала для стекла)
                'bg': 'var(--color-bg)',
                'bg-secondary': 'var(--color-bg-secondary)', // Теперь это стекло!
                'bg-tertiary': 'var(--color-bg-tertiary)',
                'bg-elevated': 'var(--color-bg-elevated)',
                'bg-hover': 'var(--color-bg-hover)',
                
                // Текст
                'text-primary': 'var(--color-text)',
                'text-secondary': 'var(--color-text-secondary)',
                'text-muted': 'var(--color-text-muted)',
                'text-inverse': 'var(--color-text-inverse)',
                
                // Рамки
                'border': 'var(--color-border)',
                
                // Акцентный (Сиреневый)
                'primary': {
                    DEFAULT: 'var(--color-primary)', // #a855f7
                    hover: 'var(--color-primary-hover)',
                    text: 'var(--color-primary-text)'
                },
                
                // Ошибки
                'danger': {
                    DEFAULT: 'var(--color-danger)',
                },
                
                // Хардкод цвета для логики, где нужны JS константы
                'green': '#a855f7', // Переопределяем зеленый на сиреневый для совместимости
            },
            fontFamily: {
                sans: ['var(--font-sans)', 'ui-sans-serif', 'system-ui', 'sans-serif'],
                mono: ['var(--font-mono)', 'ui-monospace', 'SFMono-Regular', 'monospace'],
            },
            borderRadius: {
                'xl': '1rem',
                '2xl': '1.5rem',
                '3xl': '2rem',
            }
        }
    }
}