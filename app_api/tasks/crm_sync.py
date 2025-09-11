import logging

from app_api.alfa_crm_service.crm_service import find_client_by_id
from app_api.utils.util_parse_date import parse_date
from app_api.views import update_bot_user_status
from app_kiberclub.models import Client
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def sync_all_users_with_crm():
    """
    Синхронизирует всех клиентов из CRM и обновляет их данные в БД.
    """
    clients = Client.objects.select_related("user", "branch").exclude(crm_id__isnull=True).exclude(crm_id="")

    for client in clients:
        logger.info(f"Синхронизация клиента {client.crm_id} (Пользователь: {client.user.id})")
        try:
            crm_response = find_client_by_id(branch_id=client.branch.branch_id, crm_id=client.crm_id)
            logger.info(crm_response)

            if not crm_response:
                logger.warning(f"Нет данных для клиента {client.crm_id} в CRM")
                continue

            if crm_response.get("total", 0) == 0:
                logger.warning(f"Нет данных для клиента {client.crm_id} в CRM. Удаляю.")
                client.delete()
                continue

            items = crm_response.get("items")
            if not items or not isinstance(items, list):
                logger.warning(f"CRM вернул некорректные данные для клиента {client.crm_id}")
                continue

            item = items[0]
            update_client_from_crm(client, item)
            update_bot_user_status(client.user)

        except Exception as e:
            logger.exception(f"Ошибка при синхронизации клиента {client.crm_id}: {e}")


def update_client_from_crm(client: Client, crm_data: dict):
    """
    Обновляет данные клиента на основе данных из CRM.
    """
    try:
        client.name = crm_data.get("name")
        client.is_study = bool(crm_data.get("is_study"))
        client.dob = parse_date(crm_data.get("dob"))
        client.balance = crm_data.get("balance")
        client.next_lesson_date = parse_date(crm_data.get("next_lesson_date"))
        client.paid_till = parse_date(crm_data.get("paid_till"))
        client.note = crm_data.get("note")
        client.paid_lesson_count = crm_data.get("paid_lesson_count")

        client.save()
        logger.info(f"Клиент {client.crm_id} успешно обновлен")



    except Exception as e:
        logger.exception(f"Не удалось обновить клиента {client.crm_id}: {e}")
