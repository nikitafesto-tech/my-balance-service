# Используем ту же версию, что у тебя была
FROM python:3.11-slim

# Рабочая папка
WORKDIR /app

# 1. Копируем requirements из папки app
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2. Копируем ВЕСЬ проект (папку app, cert.pem и прочее) в контейнер
COPY . .

# 3. Запускаем. Так как мы в корне, путь к приложению теперь app.main:app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8081"]