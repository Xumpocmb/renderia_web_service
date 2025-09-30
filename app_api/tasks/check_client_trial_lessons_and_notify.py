import requests
from celery import shared_task
from django.conf import settings

from app_kiberclub.models import Client, AppUser
from django.utils import timezone
import logging
from app_api.alfa_crm_service.crm_service import get_taught_trial_lesson, get_client_lessons
from datetime import datetime, timedelta



@shared_task
def check_clients_lessons_before():
    """
    Проверяет клиентов и отправляет уведомления тем, у кого пробные занятия завтра
    """
    logger.info("Запущена проверка пробных и первых занятий клиентов...")
    
    # Получаем клиентов с количеством оплаченных занятий меньше 1
    clients = Client.objects.filter(paid_lesson_count__lt=1).prefetch_related('users')
    
    notification_count = 0
    tomorrow_date = (timezone.now() + timezone.timedelta(days=1)).strftime("%Y-%m-%d")

    for client in clients:
        # Пропускаем клиентов без необходимых данных
        if not client.crm_id or not client.branch_id:
            continue
        
        # Получаем всех пользователей, связанных с клиентом
        users = client.users.all()
        
        if not users.exists():
            continue

        # 1. ПРОВЕРКА ПРОБНЫХ ЗАНЯТИЙ
        try:
            lesson_response = get_client_lessons(
                user_crm_id=client.crm_id, 
                branch_id=client.branch_id, 
                lesson_status=1, 
                lesson_type=3
            )
            
            total_trial_lessons = lesson_response.get("total", 0)
            
            if total_trial_lessons > 0:
                trial_lesson = lesson_response.get("items", [])[0]
                lesson_date = trial_lesson.get("date", None)
                lesson_time = f"{trial_lesson.get('time_from', '').split(' ')[1][:-3]}" if trial_lesson.get('time_from') else "время не указано"
                room_id = trial_lesson.get("room_id", None)
                
                # Проверяем, что пробное занятие завтра
                if lesson_date == tomorrow_date:
                    # Поиск локации
                    location = Location.objects.filter(location_crm_id=room_id).first()
                    
                    if location:
                        message = (
                            f"🔔 Ваше пробное занятие в RENDERIA уже завтра!\n"
                            f"Дата: {lesson_date.split('-')[2]}.{lesson_date.split('-')[1]}\n"
                            f"Время: {lesson_time}\n"
                            f"Адрес: {location.name}\n{location.map_url}\n\n"
                        )
                        
                        # Отправляем сообщение всем связанным пользователям
                        for user in users:
                            if not user.telegram_id:
                                continue
                                
                            try:
                                send_telegram_message(user.telegram_id, message)
                                notification_count += 1
                                logger.info(f"Уведомление о пробном занятии отправлено пользователю {user.telegram_id}")
                            except Exception as e:
                                logger.error(f"Ошибка при отправке уведомления о пробном занятии пользователю {user.telegram_id}: {e}")
        except Exception as e:
            logger.error(f"Ошибка при проверке пробных занятий для клиента {client.id}: {e}")

        # 2. НАПОМИНАНИЕ О ПЕРВОМ ЗАНЯТИИ
        try:
            # Запланированные уроки
            lesson_response = get_client_lessons(
                user_crm_id=client.crm_id, 
                branch_id=client.branch_id, 
                lesson_status=1, 
                lesson_type=2
            )
            
            planned_lessons_count = lesson_response.get("total", 0)
            
            if planned_lessons_count > 0:
                # Проведенные уроки
                user_taught_lessons = get_client_lessons(
                    user_crm_id=client.crm_id, 
                    branch_id=client.branch_id, 
                    lesson_status=3, 
                    lesson_type=2
                )
                
                # Если нет посещенных уроков
                taught_lessons_count = user_taught_lessons.get("total", 0)
                
                if taught_lessons_count == 0:
                    # Забираем последний запланированный урок
                    if lesson_response.get('total', 0) > lesson_response.get('count', 0):
                        page = lesson_response.get('total', 0) // lesson_response.get('count', 1)
                    else:
                        page = 0
                    
                    lesson_response = get_client_lessons(
                        user_crm_id=client.crm_id, 
                        branch_id=client.branch_id, 
                        lesson_status=1, 
                        lesson_type=2, 
                        page=page
                    )
                    
                    items = lesson_response.get("items", [])
                    if not items:
                        continue
                        
                    last_user_lesson = items[-1]
                    next_lesson_date = last_user_lesson.get("lesson_date") or last_user_lesson.get("date")
                    
                    room_id = last_user_lesson.get("room_id", None)
                    location = Location.objects.filter(location_crm_id=room_id).first()
                    
                    # Проверяем, что урок завтра
                    if next_lesson_date == tomorrow_date:
                        lesson_time = f"{last_user_lesson.get('time_from', '').split(' ')[1][:-3]}" if last_user_lesson.get('time_from') else "время не указано"
                        
                        message = (
                            f"🔔 Ваше первое занятие в RENDERIA уже завтра!\n"
                            f"Дата: {next_lesson_date.split('-')[2]}.{next_lesson_date.split('-')[1]}\n"
                            f"Время: {lesson_time}\n"
                            f"Адрес: {location.name if location else 'адрес не указан'}\n"
                            f"{location.map_url if location else ''}\n\n"
                        )
                        
                        # Отправляем сообщение всем связанным пользователям
                        for user in users:
                            if not user.telegram_id:
                                continue
                                
                            try:
                                send_telegram_message(user.telegram_id, message)
                                notification_count += 1
                                logger.info(f"Уведомление о первом занятии отправлено пользователю {user.telegram_id}")
                            except Exception as e:
                                logger.error(f"Ошибка при отправке уведомления о первом занятии пользователю {user.telegram_id}: {e}")
        except Exception as e:
            logger.error(f"Ошибка при проверке первых занятий для клиента {client.id}: {e}")

    logger.info(f"Проверка занятий завершена. Отправлено уведомлений: {notification_count}")



@shared_task
def check_client_passed_trial_lessons():
    """
    Проверяет пробные занятия всех клиентов и отправляет уведомления о посещенных занятиях.
    """
    logger.info("Старт задачи проверки пробных занятий для всех пользователей")

    users_qs = AppUser.objects.prefetch_related("clients__branch").all()
    notification_count = 0

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
                continue

            try:
                lessons_response = get_taught_trial_lesson(customer_id=client_crm_id, branch_id=branch_id)
                items = []
                
                if lessons_response is not None:
                    try:
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
                            notification_count += 1
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

                logger.info(f"user={user.id} client_crm_id={client_crm_id} attended_yesterday_trial={attended}")

            except Exception as e:
                logger.error(f"Ошибка при проверке пробных занятий для клиента {client_crm_id} (user={user.id}): {e}")

    logger.info(f"Завершена проверка пробных занятий. Отправлено уведомлений: {notification_count}")


@shared_task
def send_birthday_congratulations():
    """
    Проверяет клиентов и отправляет персонализированные поздравления
    """
    today = date.today()
    logger.info("Запущена проверка дней рождения клиентов и отправка поздравлений...")

    # Получаем клиентов с днем рождения сегодня
    clients = Client.objects.filter(
        dob__day=today.day,
        dob__month=today.month,
        dob__isnull=False
    ).prefetch_related('users')
    
    congratulation_count = 0
    
    for client in clients:
        if not client.name:
            continue
            
        # Рассчитываем возраст
        age = None
        if client.dob:
            age = today.year - client.dob.year
            # Корректируем, если день рождения еще не наступил в этом году
            if today < client.dob.replace(year=today.year):
                age -= 1

        users = client.users.all()
        
        for user in users:
            if not user.telegram_id:
                continue
                
            # Формируем персонализированное сообщение
            if age:
                message = (
                    f"🎂 Поздравляем с Днем Рождения! 🎉\n\n"
                    f"Сегодня {client.name} исполняется {age} лет!\n\n"
                    f"Команда RENDERIA желает успехов в учебе, новых открытий и достижений!\n\n"
                    f"Пусть этот день будет наполнен радостью и счастьем!\n\n"
                    f"Твоя RENDERIA! ❤️"
                )
            else:
                message = (
                    f"🎂 Поздравляем с Днем Рождения, {client.name}! 🎉\n\n"
                    f"Команда RENDERIA желает тебе успехов в учебе, новых открытий и достижений!\n\n"
                    f"Пусть этот день будет наполнен радостью и счастьем!\n\n"
                    f"Твоя RENDERIA! ❤️"
                )

            try:
                send_telegram_message(user.telegram_id, message)
                congratulation_count += 1
                logger.info(f"Поздравление отправлено пользователю {user.telegram_id} для {client.name}")
            except Exception as e:
                logger.error(f"Ошибка при отправке пользователю {user.telegram_id}: {e}")

    logger.info(f"Отправлено {congratulation_count} поздравлений с днем рождения")


@shared_task
def check_clients_balance_and_notify():
    """
    Проверяет клиентов и отправляет уведомления тем, у кого paid_lesson_count < 1
    В зависимости от даты отправляет разные сообщения:
    - до 10-го числа: обычное уведомление
    - после 10-го числа: напоминание с ссылкой на оплату
    """
    now = timezone.now()
    logger.info("Запущена проверка баланса клиентов и отправка уведомлений...")

    # Получаем клиентов с недостаточным количеством оплаченных уроков
    clients = Client.objects.filter(paid_lesson_count__lt=1).prefetch_related('users')

    notification_count = 0
    
    for client in clients:
        # Пропускаем клиентов без необходимых данных
        if not client.crm_id or not client.branch_id:
            logger.warning(f"Клиент {client.id} не имеет crm_id или branch_id")
            continue
        
        # Получаем всех пользователей, связанных с клиентом
        users = client.users.all()
        
        if not users.exists():
            logger.info(f"Клиент {client.id} не имеет связанных пользователей")
            continue

        # Получаем информацию об уроках клиента
        try:
            lesson_response = get_client_lessons(
                user_crm_id=client.crm_id, 
                branch_id=client.branch_id, 
                lesson_status=1, 
                lesson_type=2
            )
            planned_lessons_count = lesson_response.get("total", 0)
            
            # Если есть запланированные уроки, проверяем дату ближайшего
            if planned_lessons_count > 0:
                # Определяем страницу для получения последнего урока
                if lesson_response.get('total', 0) > lesson_response.get('count', 0):
                    page = lesson_response.get('total', 0) // lesson_response.get('count', 1)
                else:
                    page = 0
                
                logger.info(f"page: {page}")
                
                # Получаем последнюю страницу с уроками
                lesson_response = get_client_lessons(
                    user_crm_id=client.crm_id, 
                    branch_id=client.branch_id, 
                    lesson_status=1, 
                    lesson_type=2, 
                    page=page
                )
                
                items = lesson_response.get("items", [])
                if not items:
                    continue
                    
                last_user_lesson = items[-1]
                next_lesson_date = last_user_lesson.get("lesson_date") or last_user_lesson.get("date")
                
                # Если урок сегодня, отправляем уведомление всем связанным пользователям
                if next_lesson_date and timezone.now().strftime("%Y-%m-%d") == next_lesson_date:
                    # Формируем сообщения
                    message = (
                        f"🔔 Это PUSH уведомление о необходимости пополнить баланс\n\n"
                        "Чтобы оплатить обучение RENDERIA, нажмите на боковую кнопку Меню->RENDERIA меню->Оплатить\n\n"
                    )
                    
                    reminder_message = (
                        "Уважаемый клиент!\n"
                        "У нас не отобразилась ваша оплата за занятия.\n"
                        "Чтобы оплатить обучение RENDERIA, нажмите на боковую кнопку Меню->RENDERIA меню->Оплатить\n\n"
                    )

                    # Выбираем сообщение в зависимости от текущей даты
                    current_day = now.day
                    notification_text = message if current_day <= 10 else reminder_message

                    # Отправляем уведомление всем связанным пользователям
                    for user in users:
                        if not user.telegram_id:
                            continue
                            
                        try:
                            send_telegram_message(user.telegram_id, notification_text)
                            notification_count += 1
                            logger.info(f"Уведомление отправлено пользователю {user.telegram_id} для клиента {client.name or 'без имени'}")
                        except Exception as e:
                            logger.error(f"Ошибка при отправке сообщения пользователю {user.telegram_id}: {e}")
                            
        except Exception as e:
            logger.error(f"Ошибка при обработке клиента {client.id}: {e}")
            continue

    logger.info(f"Проверка баланса завершена. Отправлено уведомлений: {notification_count}")


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
