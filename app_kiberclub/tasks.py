import logging
from time import sleep

import requests
from celery import shared_task
from django.conf import settings
from django.core.files.storage import default_storage

from .models import BroadcastMessage, AppUser

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def send_broadcast_task(self, broadcast_id):
    """
    Задача Celery для отправки рассылки
    """
    broadcast = BroadcastMessage.objects.get(id=broadcast_id)
    users = AppUser.objects.exclude(telegram_id__isnull=True).exclude(telegram_id__exact='')

    if broadcast.status_filter:
        users = users.filter(status=broadcast.status_filter)

    total = users.count()
    success = 0
    fail = 0

    for i, user in enumerate(users, 1):
        try:
            # Отправка сообщения
            if send_telegram_message(
                    chat_id=user.telegram_id,
                    text=broadcast.message_text,
                    image_path=broadcast.image.path if broadcast.image else None
            ):
                success += 1
            else:
                fail += 1

            # Обновляем прогресс каждые 10 сообщений
            if i % 10 == 0:
                self.update_state(
                    state='PROGRESS',
                    meta={
                        'current': i,
                        'total': total,
                        'success': success,
                        'fail': fail
                    }
                )

            if i % 30 == 0:
                sleep(1)

        except Exception as e:
            logger.error(f"Ошибка при отправке пользователю {user.telegram_id}: {e}")
            fail += 1

    return {
        'total': total,
        'success': success,
        'fail': fail,
        'broadcast_id': broadcast_id
    }


def send_telegram_message(chat_id, text, image_path=None):
    """
    Функция отправки сообщения через Telegram API
    """
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN не установлен в settings.py")
        return False

    base_url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/"

    try:
        if image_path:
            # Проверка размера изображения (Telegram имеет лимит 10MB)
            if default_storage.size(image_path) > 10 * 1024 * 1024:
                logger.error(f"Изображение слишком большое: {image_path}")
                return False

            url = base_url + "sendPhoto"
            with default_storage.open(image_path, 'rb') as photo:
                files = {'photo': photo}
                data = {'chat_id': chat_id, 'caption': text}
                response = requests.post(url, files=files, data=data)
        else:
            url = base_url + "sendMessage"
            data = {
                'chat_id': chat_id,
                'text': text,
                'parse_mode': 'HTML'
            }
            response = requests.post(url, data=data)

        if response.status_code != 200:
            logger.error(f"Ошибка Telegram API: {response.status_code} - {response.text}")
            return False

        return True

    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения: {str(e)}")
        return False