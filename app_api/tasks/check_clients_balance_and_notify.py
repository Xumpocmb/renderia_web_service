import requests
from celery import shared_task
from django.conf import settings

from app_kiberclub.models import Client, AppUser
from django.utils import timezone
import logging


logger = logging.getLogger(__name__)

def send_telegram_message(chat_id, text):
    token = getattr(settings, "TELEGRAM_BOT_TOKEN", None)
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN не настроен")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, json=payload)
        if not response.ok:
            raise Exception(f"Ошибка Telegram API: {response.text}")
    except Exception as e:
        logger.error(e)

    logger.info(f"[Telegram] Отправлено сообщение для {chat_id}: {text}")
    pass


@shared_task
def check_clients_balance_and_notify():
    """
    Проверяет клиентов и отправляет уведомления тем, у кого paid_lesson_count < 1
    """
    now = timezone.now()
    logger.info("Запущена проверка баланса клиентов и отправка уведомлений...")

    clients = Client.objects.select_related("user").filter(paid_lesson_count__lt=1)

    for client in clients:
        user: AppUser = client.user
        if not user or not user.telegram_id:
            continue

        message = (
            f"🔔 Это PUSH уведомление о необходимости пополнить KIBERказну\n\n"
            "Чтобы оплатить обучение KIBERone, нажмите на боковую кнопку Меню->КИБЕРменю->Оплатить\n\n"
            "Ваш KIBERone!\n"
        )

        try:
            send_telegram_message(user.telegram_id, message)
            logger.info(f"Уведомление отправлено пользователю {user.telegram_id}")
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения пользователю {user.telegram_id}: {e}")
