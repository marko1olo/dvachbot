# Этап 1: Установка зависимостей
FROM python:3.11-slim as builder

# Устанавливаем рабочую директорию
WORKDIR /app

# Обновляем pip и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Этап 2: Создание финального, легковесного образа
FROM python:3.11-slim

WORKDIR /app

# Копируем установленные зависимости из первого этапа
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

# Копируем все файлы проекта (main.py, deanonymizer.py и т.д.)
COPY . .

# Команда для запуска вашего бота
CMD ["python", "main.py"]
