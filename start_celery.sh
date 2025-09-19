#!/bin/bash

# Перейти в корень проекта
cd /home/x93/x-code/RENDERIA/renderia_web_service || { echo "❌ Не удалось перейти в директорию проекта"; exit 1; }
# Проверяем, существует ли celery_app.py
if [ ! -f "celery_app.py" ]; then
    echo "❌ Файл celery_app.py не найден в текущей директории"
    exit 1
fi

# Проверяем, существует ли виртуальное окружение
if [ ! -d "venv" ]; then
    echo "❌ Виртуальное окружение 'venv' не найдено"
    exit 1
fi

# Активировать виртуальное окружение
source venv/bin/activate || { echo "❌ Не удалось активировать виртуальное окружение"; exit 1; }

# Создать папку для логов (если её нет)
mkdir -p logs

# Остановить старые процессы
echo "🛑 Останавливаем старые процессы Celery..."
pkill -f 'celery.*worker' || echo "ℹ️ Нет запущенных воркеров"
pkill -f 'celery.*beat' || echo "ℹ️ Нет запущенного beat"

# Пауза, чтобы процессы точно завершились
sleep 2

# Запустить Celery Worker
echo "🚀 Запускаем Celery Worker..."
nohup celery -A celery_app worker --loglevel=info >> logs/worker.log 2>&1 &

# Запустить Celery Beat
echo "🕒 Запускаем Celery Beat..."
nohup celery -A celery_app beat --loglevel=info >> logs/beat.log 2>&1 &

# Готово
echo "✅ Celery Worker и Beat успешно запущены."
echo "📄 Логи: logs/worker.log и logs/beat.log"
