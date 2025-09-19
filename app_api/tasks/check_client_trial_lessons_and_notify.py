import requests
from celery import shared_task
from django.conf import settings

from app_kiberclub.models import Client, AppUser
from django.utils import timezone
import logging
from app_api.alfa_crm_service.crm_service import get_taught_trial_lesson
from datetime import datetime, timedelta
from app_api.tasks.check_clients_balance_and_notify import send_telegram_message

logger = logging.getLogger(__name__)


@shared_task
def check_client_trial_lessons():
    """
    Получить всех AppUser и для каждого их клиента (Client) проверить пробные занятия.
    Возвращает список результатов с признаком посещения пробного занятия вчера.
    """
    logger.info("Старт задачи проверки пробных занятий для всех пользователей")
    results = []

    users_qs = AppUser.objects.prefetch_related("clients__branch").all()

    for user in users_qs:
        user_clients = user.clients.all()
        for client in user_clients:
            client_crm_id = client.crm_id
            branch_id = None
            try:
                branch_id = int(client.branch.branch_id) if client.branch and client.branch.branch_id else None
            except Exception:
                branch_id = None

            if not client_crm_id or not branch_id:
                logger.warning(f"Пропуск клиента без crm_id/branch_id: user={user.id} client={client.id}")
                results.append({
                    "user_id": user.id,
                    "telegram_id": user.telegram_id,
                    "client_id": client.id,
                    "client_crm_id": client_crm_id,
                    "branch_id": branch_id,
                    "attended_yesterday_trial": False,
                    "checked": False,
                })
                continue

            try:
                lessons_response = get_taught_trial_lesson(customer_id=client_crm_id, branch_id=branch_id)
                items = []
                if lessons_response is not None:
                    try:
                        # Функция get_taught_trial_lesson уже возвращает словарь, а не объект ответа
                        items = lessons_response.get("items", []) or []
                    except Exception as e:
                        logger.error(f"Ошибка обработки ответа CRM для клиента {client_crm_id}: {e}")

                attended = check_attend_on_lesson(items) if items else False

                # Отправка уведомления в Telegram при обнаружении пробного урока
                if attended:
                    if user.telegram_id:
                        message = (
                            "🔔 Пробное занятие посещено\n\n"
                            f"Ребёнок: {client.name or 'Клиент'}\n"
                            f"Дата: {(datetime.now() - timedelta(days=1)).strftime('%d.%m.%Y')}\n\n"
                            "Если всё понравилось, откройте в боте Меню -> RENDERIA меню, чтобы продолжить обучение.\n"
                            "Ваша RENDERIA!"
                        )
                        try:
                            send_telegram_message(user.telegram_id, message)
                            logger.info(
                                f"Уведомление о пробном занятии отправлено пользователю {user.telegram_id} (client_id={client.id})"
                            )
                        except Exception as e:
                            logger.error(
                                f"Ошибка при отправке уведомления о пробном занятии пользователю {user.telegram_id}: {e}"
                            )
                    else:
                        logger.info(
                            f"Пробное занятие обнаружено, но у пользователя user_id={user.id} отсутствует telegram_id"
                        )

                results.append({
                    "user_id": user.id,
                    "telegram_id": user.telegram_id,
                    "client_id": client.id,
                    "client_crm_id": client_crm_id,
                    "branch_id": branch_id,
                    "attended_yesterday_trial": attended,
                    "checked": True,
                })

                logger.info(f"user={user.id} client_crm_id={client_crm_id} attended_yesterday_trial={attended}")

            except Exception as e:
                logger.error(f"Ошибка при проверке пробных занятий для клиента {client_crm_id} (user={user.id}): {e}")
                results.append({
                    "user_id": user.id,
                    "telegram_id": user.telegram_id,
                    "client_id": client.id,
                    "client_crm_id": client_crm_id,
                    "branch_id": branch_id,
                    "attended_yesterday_trial": False,
                    "checked": False,
                    "error": str(e),
                })

    logger.info("Завершена проверка пробных занятий для всех пользователей")
    return results


def check_attend_on_lesson(lessons):
    for lesson in lessons:
        details = lesson.get("details") or []
        if not details:
            continue
        lesson_details = details[0]
        is_attend = lesson_details.get("is_attend", False)
        date_str = lesson.get("date")
        if not date_str:
            continue
        if date_str == str(datetime.now().date() - timedelta(1)) and is_attend:
            return True

    return False
