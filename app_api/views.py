from django.db.models import QuerySet
from django.shortcuts import render
import logging

from rest_framework.decorators import api_view
from app_api.alfa_crm_service.crm_service import (
    find_user_by_phone,
    create_user_in_crm,
    get_client_lessons,
    get_user_groups_from_crm,
    get_group_link_from_crm,
    find_client_by_id,
    get_manager_from_crm,
)
from rest_framework import status
from rest_framework.response import Response

from app_api.utils.util_erip import set_pay
from app_api.utils.util_parse_date import parse_date
from app_kiberclub.models import AppUser, Client, Branch, ClientBonus, EripPaymentHelp, Location, PartnerCategory, PartnerClientBonus, QuestionsAnswers, SalesManager, SocialLink

logger = logging.getLogger(__name__)


@api_view(["POST"])
def find_user_by_phone_view(request) -> Response:
    phone_number = request.data.get("phone_number")
    if not phone_number:
        return Response(
            {"success": False, "message": "Номер телефона обязателен"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    search_result = find_user_by_phone(phone_number)
    if search_result.get("total", 0) > 0:
        return Response(
            {
                "success": True,
                "message": "Пользователь найден в CRM",
                "user": search_result,
            },
            status=status.HTTP_200_OK,
        )
    else:
        return Response(
            {"success": False, "message": "Пользователь не найден в CRM", "user": None},
            status=status.HTTP_404_NOT_FOUND,
        )


@api_view(["POST"])
def register_user_in_crm_view(request) -> Response:
    """
    Регистрация нового пользователя в CRM.
    """
    user_data = request.data
    required_fields = ["first_name", "last_name", "username", "phone_number"]
    if not all(field in user_data for field in required_fields):
        logger.error("Не все обязательные поля указаны")
        return Response(
            {"success": False, "message": "Не все обязательные поля указаны"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    result: dict = create_user_in_crm(user_data)

    if result:
        logger.info("Пользователь успешно зарегистрирован в CRM")
        return Response(
            {
                "success": True,
                "message": "Пользователь успешно зарегистрирован в CRM",
            },
            status=status.HTTP_201_CREATED,
        )
    else:
        logger.error("Ошибка при регистрации в CRM")
        return Response(
            {"success": False, "message": "Ошибка при регистрации в CRM"},
            status=status.HTTP_400_BAD_REQUEST,
        )


# ------------------- DB USERS --------------------
@api_view(["POST"])
def find_user_in_db_view(request) -> Response:
    telegram_id = request.data.get("telegram_id")
    if not telegram_id:
        return Response(
            {"success": False, "message": "telegram_id обязателен"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        user = AppUser.objects.filter(telegram_id=telegram_id).first()
        if user:
            return Response(
                {
                    "success": True,
                    "message": "Пользователь найден в базе данных",
                    "user": {
                        "id": user.id,
                        "telegram_id": user.telegram_id,
                        "username": user.username,
                        "phone_number": user.phone_number,
                        "status": user.status,
                    },
                },
                status=status.HTTP_200_OK,
            )
        else:
            return Response({"success": False, "message": "Пользователь не найден"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response(
            {"success": False, "message": f"Ошибка при поиске пользователя: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
def register_user_in_db_view(request) -> Response:
    """
    Регистрация нового пользователя в базе данных Django.
    """

    try:
        telegram_id = request.data.get("telegram_id")
        username = request.data.get("username")
        phone_number = request.data.get("phone_number")

        if not all([telegram_id, username, phone_number]):
            return Response(
                {
                    "success": False,
                    "message": "Необходимо указать telegram_id, username и phone_number",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        user, created = AppUser.objects.get_or_create(
            telegram_id=telegram_id,
            defaults={
                "username": username,
                "phone_number": phone_number,
            },
        )

        if created:
            return Response(
                {
                    "success": True,
                    "message": "Пользователь успешно зарегистрирован в базе данных",
                    "user": {
                        "id": user.id,
                        "telegram_id": user.telegram_id,
                        "username": user.username,
                        "phone_number": user.phone_number,
                    },
                },
                status=status.HTTP_201_CREATED,
            )
        else:
            return Response(
                {
                    "success": False,
                    "message": "Пользователь уже зарегистрирован в базе данных",
                    "user": {
                        "id": user.id,
                        "telegram_id": user.telegram_id,
                        "username": user.username,
                        "phone_number": user.phone_number,
                    },
                },
                status=status.HTTP_200_OK,
            )
    except Exception as e:
        return Response(
            {
                "success": False,
                "message": f"Ошибка на сервере при регистрации пользователя: {str(e)}",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ------------------- DB CLIENTS --------------------


@api_view(["GET"])
def get_clients_by_user(request, user_id: int):
    """
    Получение списка клиентов для указанного пользователя через отношение М:М.
    """
    try:
        # Сначала находим пользователя
        try:
            user = AppUser.objects.get(id=user_id)
        except AppUser.DoesNotExist:
            return Response(
                {"success": False, "message": "Пользователь не найден"},
                status=404,
            )

        # Получаем клиентов через отношение многие-ко-многим
        clients = user.clients.all().select_related("branch")

        data = [
            {
                "id": client.id,
                "name": client.name,
                "branch_name": client.branch.name if client.branch else None,
                "branch_id": client.branch.branch_id if client.branch else None,
                "crm_id": client.crm_id,
                "is_study": client.is_study,
                "dob": client.dob.isoformat() if client.dob else None,
                "balance": float(client.balance) if client.balance else 0.0,
                "next_lesson_date": client.next_lesson_date.isoformat() if client.next_lesson_date else None,
                "paid_till": client.paid_till.isoformat() if client.paid_till else None,
                "note": client.note,
                "paid_lesson_count": client.paid_lesson_count,
                "has_scheduled_lessons": client.has_scheduled_lessons,
            }
            for client in clients
        ]

        return Response(
            {"success": True, "data": data},
            status=200,
        )

    except Exception as e:
        logger.error(f"Ошибка в get_clients_by_user: {str(e)}")
        return Response(
            {"success": False, "message": f"Ошибка сервера: {str(e)}"},
            status=500,
        )


@api_view(["POST"])
def create_or_update_clients_in_db_view(request) -> Response:
    """
    Создает, обновляет или удаляет клиентов в базе данных с учетом отношения М:М.
    Если CRM возвращает пустой список, удаляются все клиенты пользователя.
    """
    try:
        user_id: int = request.data.get("user_id")
        crm_items: list = request.data.get("crm_items", [])

        logger.info(f"Начало обработки user_id={user_id}, crm_items_count={len(crm_items)}")

        if not user_id or not isinstance(crm_items, list):
            logger.error("Отсутствуют обязательные поля: user_id или crm_items")
            return Response(
                {
                    "success": False,
                    "message": "Необходимо указать user_id и список crm_items",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user: AppUser = AppUser.objects.get(id=user_id)
            logger.info(f"Пользователь найден: {user}")
        except AppUser.DoesNotExist:
            logger.error(f"Пользователь с user_id={user_id} не найден в базе данных")
            return Response(
                {
                    "success": False,
                    "message": "Пользователь с указанным user_id не найден в базе данных",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Если CRM вернул пустой список, удаляем всех клиентов пользователя
        if not crm_items:
            logger.info(f"CRM вернул пустой список клиентов для user_id={user_id}. Удаляем клиентов.")
            
            # Получаем всех клиентов пользователя
            user_clients = user.clients.all()
            clients_count = user_clients.count()
            deleted_clients_count = 0
            
            if clients_count > 0:
                for client in user_clients:
                    # Проверяем, связан ли клиент с другими пользователями
                    other_users_count = client.users.exclude(id=user.id).count()
                    
                    if other_users_count == 0:
                        # Клиент не связан с другими пользователями - удаляем полностью
                        client.delete()
                        deleted_clients_count += 1
                        logger.info(f"Удален клиент: {client.crm_id} (без других связей)")
                    else:
                        # Клиент связан с другими пользователями - удаляем только связь
                        user.clients.remove(client)
                        logger.info(f"Удалена связь с клиентом: {client.crm_id} (есть другие пользователи: {other_users_count})")
                
                logger.info(f"Удалено клиентов: {deleted_clients_count}, удалено связей: {clients_count - deleted_clients_count}")
            else:
                logger.info(f"У пользователя {user_id} нет клиентов для удаления")
            
            # Обновляем статус пользователя
            update_bot_user_status(user)
            logger.info(f"Статус пользователя обновлен: {user.status}")
            
            return Response(
                {
                    "success": True,
                    "message": "Обработка пустого ответа от CRM завершена",
                    "deleted_clients": deleted_clients_count,
                    "removed_relations": clients_count - deleted_clients_count,
                },
                status=status.HTTP_200_OK,
            )

        # Обрабатываем непустой список клиентов из CRM
        crm_ids: set = {str(item["id"]) for item in crm_items}
        logger.info(f"CRM IDs из запроса: {crm_ids}")

        # Получаем текущих клиентов пользователя
        existing_clients: QuerySet = user.clients.all()
        existing_crm_ids: set = {client.crm_id for client in existing_clients if client.crm_id}
        logger.info(f"Существующие CRM IDs: {existing_crm_ids}")

        # Удаляем связи с клиентами, которых нет в новом ответе от CRM
        crm_ids_to_remove: set = existing_crm_ids - crm_ids
        removed_relations_count: int = 0

        if crm_ids_to_remove:
            logger.info(f"CRM IDs для удаления связей: {crm_ids_to_remove}")
            clients_to_remove = Client.objects.filter(crm_id__in=crm_ids_to_remove)
            for client in clients_to_remove:
                user.clients.remove(client)
                removed_relations_count += 1
                logger.info(f"Удалена связь с клиентом: {client.crm_id}")
            logger.info(f"Удалено связей с клиентами: {removed_relations_count}")

        # Создание и обновление клиентов
        created_count: int = 0
        updated_count: int = 0

        for item in crm_items:
            crm_id = str(item["id"])
            logger.info(f"Обработка клиента crm_id={crm_id}")

            try:
                branch = Branch.objects.get(branch_id=item["branch_ids"][0])
                logger.info(f"Филиал найден: {branch}")
            except Branch.DoesNotExist:
                logger.error(f"Филиал с branch_id={item['branch_ids'][0]} не найден")
                continue
            except (IndexError, KeyError) as e:
                logger.error(f"Некорректные данные branch_ids для клиента crm_id={crm_id}: {e}")
                continue

            # Получаем информацию об уроках
            lessons: dict = get_client_lessons(
                user_crm_id=int(item["id"]),
                branch_id=int(item["branch_ids"][0]),
                lesson_status=1,
                lesson_type=2,
            )
            has_scheduled_lessons: bool = bool(lessons and lessons.get("total", 0) > 0)
            logger.info(f"Клиент crm_id={crm_id} has_scheduled_lessons={has_scheduled_lessons}")

            # Создаем или обновляем клиента
            try:
                client, created = Client.objects.update_or_create(
                    crm_id=crm_id,
                    defaults={
                        "branch": branch,
                        "is_study": bool(item.get("is_study", False)),
                        "name": item.get("name"),
                        "dob": parse_date(item.get("dob")),
                        "balance": item.get("balance"),
                        "next_lesson_date": parse_date(item.get("next_lesson_date")),
                        "paid_till": parse_date(item.get("paid_till")),
                        "note": item.get("note"),
                        "paid_lesson_count": item.get("paid_lesson_count"),
                        "has_scheduled_lessons": has_scheduled_lessons,
                    },
                )
                logger.info(f"Клиент {'создан' if created else 'обновлен'}: {client}")

                # Добавляем связь многие-ко-многим, если ее еще нет
                if not user.clients.filter(id=client.id).exists():
                    user.clients.add(client)
                    logger.info(f"Добавлена связь пользователь-клиент: {user.id} - {client.id}")

                if created:
                    created_count += 1
                else:
                    updated_count += 1

            except Exception as e:
                logger.error(f"Ошибка при создании/обновлении клиента crm_id={crm_id}: {e}")
                continue

        logger.info(f"Итоги: создано={created_count}, обновлено={updated_count}, удалено связей={removed_relations_count}")

        # Обновляем статус пользователя
        update_bot_user_status(user)
        logger.info(f"Статус пользователя обновлен: {user.status}")

        return Response(
            {
                "success": True,
                "message": "Клиенты успешно обновлены",
                "created": created_count,
                "updated": updated_count,
                "removed_relations": removed_relations_count,
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        logger.error(f"Внутренняя ошибка сервера: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "message": f"Внутренняя ошибка сервера: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def update_bot_user_status(user):
    """
    Обновляет статус пользователя на основе статусов его клиентов.
    Теперь работает с отношением многие-ко-многим.
    ---
    Алгоритм:
    1. Если у пользователя есть хотя бы один клиент с is_study=True,
       устанавливаем статус пользователя в "2" (Клиент).
    2. Иначе, если у пользователя есть хотя бы один клиент с has_scheduled_lessons=True,
       устанавливаем статус пользователя в "1" (Lead с группой).
    3. Иначе, устанавливаем статус пользователя в "0" (Lead).
    """
    # Получаем всех клиентов пользователя через отношение М:М
    clients = user.clients.all()

    # Проверяем, есть ли хотя бы один клиент с is_study=True
    has_active_clients = clients.filter(is_study=True).exists()

    # Если нет активных клиентов, проверяем наличие запланированных уроков
    if not has_active_clients:
        has_scheduled_lessons = clients.filter(has_scheduled_lessons=True).exists()
        user.status = "1" if has_scheduled_lessons else "0"
    else:
        user.status = "2"  # Клиент

    user.save()
    logger.info(f"Статус пользователя {user.id} обновлен: {user.status}")


@api_view(["GET"])
def get_all_questions(request):
    """
    Получение списка всех вопросов.
    """
    try:
        questions = QuestionsAnswers.objects.all()
        data = [{"id": qa.id, "question": qa.question} for qa in questions]
        return Response(
            {"success": True, "data": data},
            status=status.HTTP_200_OK,
        )
    except Exception as e:
        return Response(
            {"success": False, "message": f"Ошибка при получении вопросов: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
def get_answer_by_question_id(request, question_id):
    """
    Получение ответа на вопрос по его ID.
    """
    try:
        qa = QuestionsAnswers.objects.get(id=question_id)
        data = {
            "id": qa.id,
            "question": qa.question,
            "answer": qa.answer,
        }
        return Response(
            {"success": True, "data": data},
            status=status.HTTP_200_OK,
        )
    except QuestionsAnswers.DoesNotExist:
        return Response(
            {"success": False, "message": "Вопрос не найден"},
            status=status.HTTP_404_NOT_FOUND,
        )
    except Exception as e:
        return Response(
            {"success": False, "message": f"Ошибка при получении ответа: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
def get_erip_payment_help(request):
    """
    Получение инструкции по оплате через ЕРИП.
    """
    try:
        help_data = EripPaymentHelp.objects.first()
        if help_data:
            return Response(
                {
                    "success": True,
                    "data": {
                        "erip_link": help_data.erip_link,
                        "erip_instructions": help_data.erip_instructions,
                    },
                },
                status=200,
            )
        else:
            return Response(
                {"success": False, "message": "Инструкция не найдена"},
                status=404,
            )
    except Exception as e:
        return Response(
            {"success": False, "message": f"Ошибка сервера: {str(e)}"},
            status=500,
        )


@api_view(["GET"])
def get_partner_categories_view(request) -> Response:
    """
    Получение списка всех категорий партнеров.
    """
    try:
        categories = PartnerCategory.objects.all()
        data = [
            {
                "id": category.id,
                "name": category.name,
            }
            for category in categories
        ]
        logger.info("Категории партнеров успешно получены.")
        return Response(
            {"success": True, "data": data},
            status=status.HTTP_200_OK,
        )
    except Exception as e:
        logger.error(f"Ошибка при получении категорий: {str(e)}")
        return Response(
            {"success": False, "message": "Ошибка сервера при получении категорий."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
def get_partners_by_category_view(request, category_id: int) -> Response:
    """
    Получение списка партнеров и их бонусов по ID категории.
    """
    try:
        partners = PartnerClientBonus.objects.filter(category_id=category_id)
        data = [
            {
                "id": partner.id,
                "partner_name": partner.partner_name,
                "description": partner.description,
                "code": partner.code,
            }
            for partner in partners
        ]
        logger.info(f"Партнеры категории {category_id} успешно получены.")
        return Response(
            {"success": True, "data": data},
            status=status.HTTP_200_OK,
        )
    except PartnerCategory.DoesNotExist:
        logger.error(f"Категория с ID={category_id} не найдена.")
        return Response(
            {"success": False, "message": "Категория не найдена."},
            status=status.HTTP_404_NOT_FOUND,
        )
    except Exception as e:
        logger.error(f"Ошибка при получении партнеров: {str(e)}")
        return Response(
            {"success": False, "message": "Ошибка сервера при получении партнеров."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
def get_partner_by_id_view(request, partner_id: int) -> Response:
    """
    Получение информации о партнере по его ID.
    """
    try:
        partner = PartnerClientBonus.objects.get(id=partner_id)
        data = {
            "id": partner.id,
            "partner_name": partner.partner_name,
            "description": partner.description,
            "code": partner.code,
            "category": partner.category.id,
        }
        logger.info(f"Информация о партнере {partner_id} успешно получена.")
        return Response(
            {"success": True, "data": data},
            status=status.HTTP_200_OK,
        )
    except PartnerClientBonus.DoesNotExist:
        logger.error(f"Партнер с ID={partner_id} не найден.")
        return Response(
            {"success": False, "message": "Партнер не найден."},
            status=status.HTTP_404_NOT_FOUND,
        )
    except Exception as e:
        logger.error(f"Ошибка при получении партнера: {str(e)}")
        return Response(
            {"success": False, "message": "Ошибка сервера при получении партнера."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
def get_client_bonuses(request):
    """
    Получение списка всех бонусов для клиентов.
    """
    try:
        bonuses = ClientBonus.objects.all()
        data = [
            {
                "id": bonus.id,
                "bonus": bonus.bonus,
                "description": bonus.description,
            }
            for bonus in bonuses
        ]
        return Response(
            {"success": True, "data": data},
            status=200,
        )
    except Exception as e:
        return Response(
            {"success": False, "message": f"Ошибка сервера: {str(e)}"},
            status=500,
        )


@api_view(["GET"])
def get_bonus_by_id_view(request, bonus_id: int) -> Response:
    """
    Получение информации о бонусе по его ID.
    """
    try:
        bonus = ClientBonus.objects.get(id=bonus_id)
        data = {
            "id": bonus.id,
            "bonus": bonus.bonus,
            "description": bonus.description,
        }
        return Response(
            {"success": True, "data": data},
            status=200,
        )
    except ClientBonus.DoesNotExist:
        return Response(
            {"success": False, "message": "Бонус не найден."},
            status=404,
        )
    except Exception as e:
        return Response(
            {"success": False, "message": f"Ошибка сервера: {str(e)}"},
            status=500,
        )


@api_view(["GET"])
def get_sales_managers(request):
    """
    Получение списка менеджеров
    """
    try:
        managers = SalesManager.objects.all()
        data = [
            {
                "id": manager.id,
                "name": manager.name,
                "telegram_link": manager.telegram_link,
            }
            for manager in managers
        ]
        return Response(
            {"success": True, "data": data},
            status=status.HTTP_200_OK,
        )
    except Exception as e:
        return Response(
            {"success": False, "message": f"Ошибка сервера: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
def get_social_links(request):
    """
    Получение списка всех социальных ссылок.
    """
    try:
        links = SocialLink.objects.all()
        data = [
            {
                "id": link.id,
                "name": link.name,
                "link": link.link,
            }
            for link in links
        ]
        return Response(
            {"success": True, "data": data},
            status=status.HTTP_200_OK,
        )
    except Exception as e:
        return Response(
            {"success": False, "message": f"Ошибка сервера: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
def get_user_lessons_view(request) -> Response:
    """
    Получение уроков пользователя по его CRM ID и branch_id.
    """
    try:
        user_crm_id = request.data.get("user_crm_id")
        branch_id = request.data.get("branch_id")
        lesson_status = request.data.get("lesson_status", 1)
        lesson_type = request.data.get("lesson_type", 2)  # групповые

        if not user_crm_id or not branch_id:
            return Response(
                {
                    "success": False,
                    "message": "Необходимо указать user_crm_id и branch_id",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        lessons_data = get_client_lessons(user_crm_id, branch_id, lesson_status=lesson_status, lesson_type=lesson_type)
        if lessons_data and lessons_data.get("total", 0) > 0:
            return Response(
                {"success": True, "data": lessons_data},
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"success": False, "message": "Уроки не найдены"},
                status=status.HTTP_404_NOT_FOUND,
            )
    except Exception as e:
        return Response(
            {"success": False, "message": f"Ошибка сервера: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
def get_location_by_id(request, location_id: int):
    """
    Получение локации по room_id.
    """
    try:
        location = Location.objects.filter(location_crm_id=location_id).first()
        if not location:
            return Response(
                {"success": False, "message": "Локация не найдена."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Получаем данные менеджера, если он есть
        manager_data = None
        if location.location_manager:
            manager_data = {"id": location.location_manager.id, "name": location.location_manager.name, "telegram_link": location.location_manager.telegram_link}

        data = {
            "id": location.id,
            "branch_id": location.branch.id if location.branch else None,
            "name": location.name,
            "sheet_name": location.sheet_name,
            "location_manager": manager_data,
            "map_url": location.map_url,
        }
        return Response(
            {"success": True, "data": data},
            status=status.HTTP_200_OK,
        )
    except Exception as e:
        return Response(
            {"success": False, "message": f"Ошибка сервера: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
def get_manager(request, branch_id, user_crm_id):
    """Получение менеджера"""
    # 1. Находим клиента
    client = find_client_by_id(branch_id, user_crm_id)
    if not client:
        return Response(
            {"success": False, "message": "Клиент не найден."},
            status=status.HTTP_404_NOT_FOUND,
        )

    # 2. Проверяем назначенного менеджера
    client_assigned_id = client.get("assigned_id")

    if client_assigned_id:
        # 3. Если есть назначенный менеджер - ищем его
        MAX_PAGES = 20
        curr_page = 0

        while curr_page < MAX_PAGES:
            managers = get_manager_from_crm(branch_id, page=curr_page)
            if not managers:
                break

            managers_items = managers.get("items", [])
            if not managers_items:
                break

            for manager in managers_items:
                if manager.get("id") == client_assigned_id:
                    return Response(
                        {"success": True, "data": manager, "has_assigned": True, "is_study": client.get("is_study", False)},
                        status=status.HTTP_200_OK,
                    )

            curr_page += 1

        # Если прошли все страницы и не нашли менеджера
        return Response(
            {"success": False, "message": "Менеджер с ID {} не найден.".format(client_assigned_id)},
            status=status.HTTP_200_OK,
        )
    else:
        return Response(
            {"success": False, "message": "У клиента нет назначенного менеджера."},
            status=status.HTTP_200_OK,
        )


@api_view(["POST"])
def get_user_balances(request) -> Response:
    """
    Получение баланса для всех клиентов пользователя через отношение М:М.
    """
    try:
        telegram_id = request.data.get("telegram_id")
        if not telegram_id:
            return Response(
                {"success": False, "message": "telegram_id обязателен"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Находим пользователя
        user = AppUser.objects.filter(telegram_id=telegram_id).first()
        if not user:
            return Response(
                {"success": False, "message": "Пользователь не найден"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Исправлено: получаем клиентов через отношение многие-ко-многим
        clients = user.clients.all()

        if not clients.exists():
            return Response(
                {"success": False, "message": "У пользователя нет клиентов"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Формируем данные о балансе для каждого клиента
        balances = [
            {
                "client_id": client.id,
                "client_name": client.name or "Неизвестный",
                "balance": float(client.balance) if client.balance else 0.0,
            }
            for client in clients
        ]

        return Response(
            {"success": True, "data": balances},
            status=status.HTTP_200_OK,
        )
    except Exception as e:
        logger.error(f"Ошибка в get_user_balances: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "message": f"Ошибка сервера: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
def get_client_payment_data(request) -> Response:
    try:
        logger.info("Начало обработки get_client_payment_data")

        user_id = request.data.get("user_id")
        if not user_id:
            logger.warning("Не передан user_id")
            return Response(
                {"success": False, "message": "user_id обязателен"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Находим пользователя
        logger.debug(f"Поиск пользователя с telegram_id={user_id}")
        user = AppUser.objects.filter(telegram_id=user_id).first()
        if not user:
            logger.warning(f"Пользователь с telegram_id={user_id} не найден")
            return Response(
                {"success": False, "message": "Пользователь не найден"},
                status=status.HTTP_404_NOT_FOUND,
            )

        logger.debug(f"Поиск клиентов для пользователя {user_id}")
        # Исправлено: получаем клиентов через отношение многие-ко-многим
        clients = user.clients.all().select_related("branch")

        if not clients.exists():
            logger.warning(f"У пользователя {user_id} нет клиентов")
            return Response(
                {"success": False, "message": "У пользователя нет клиентов"},
                status=status.HTTP_404_NOT_FOUND,
            )

        logger.debug(f"Сбор данных по клиентам пользователя {user_id}")
        clients_data = [
            {
                "crm_id": client.crm_id,
                "branch_id": client.branch.branch_id if client.branch else None,  # Исправлено: branch_id из связанной модели
                "balance": float(client.balance) if client.balance else 0.0,
                "name": client.name,
            }
            for client in clients
            if client.crm_id  # Добавлена проверка на наличие crm_id
        ]

        # Фильтруем клиентов без crm_id
        clients_data = [client for client in clients_data if client["crm_id"]]

        if not clients_data:
            logger.warning(f"У клиентов пользователя {user_id} нет crm_id")
            return Response(
                {"success": False, "message": "У клиентов нет CRM идентификаторов"},
                status=status.HTTP_404_NOT_FOUND,
            )

        logger.debug(f"Обработка платежных данных для {len(clients_data)} клиентов")
        payment_data = []
        for client_data in clients_data:
            # Добавляем проверку на наличие branch_id
            if not client_data.get("branch_id"):
                logger.warning(f"Клиент {client_data.get('name')} не имеет branch_id, пропускаем")
                continue

            processed = set_pay(client_data)
            if processed:  # Добавляем проверку на результат обработки
                payment_data.append(processed)

        logger.info(f"Данные успешно обработаны для {len(payment_data)} клиентов")
        return Response(
            {"success": True, "data": payment_data},
            status=status.HTTP_200_OK,
        )
    except Exception as e:
        logger.error(f"Ошибка сервера: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "message": f"Ошибка сервера: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
def get_user_tg_links(request) -> Response:
    try:
        # Для GET запроса параметры обычно передаются в query params, а не в body
        user_id = request.GET.get("user_id")  # Изменено с request.data на request.GET

        if not user_id:
            return Response(
                {"success": False, "message": "user_id обязателен"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = AppUser.objects.filter(telegram_id=user_id).first()
        if not user:
            return Response(
                {"success": False, "message": "Пользователь не найден"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Исправлено: получаем клиентов через отношение многие-ко-многим
        clients = user.clients.all().select_related("branch")  # Добавлен select_related для оптимизации

        if not clients.exists():
            return Response(
                {"success": False, "message": "У пользователя нет клиентов"},
                status=status.HTTP_404_NOT_FOUND,
            )

        group_tg_links: list = []
        for client in clients:
            # Добавим проверку на наличие branch_id и crm_id
            if not client.branch_id or not client.crm_id:
                continue

            user_groups_data: dict = get_user_groups_from_crm(client.branch.branch_id, client.crm_id)

            if user_groups_data.get("total", 0) > 0:
                from datetime import datetime

                current_date = datetime.now().date()

                for group_item in user_groups_data["items"]:
                    # Проверяем актуальность участия ученика в группе по дате окончания обучения
                    e_date_str = group_item.get("e_date")
                    if e_date_str:
                        try:
                            e_date = datetime.strptime(e_date_str, "%d.%m.%Y").date()
                            # Если дата окончания обучения уже прошла, пропускаем эту группу
                            if e_date < current_date:
                                continue
                        except (ValueError, TypeError):
                            # Если не удалось преобразовать дату, считаем группу актуальной
                            pass

                    group_id = group_item.get("group_id")
                    if not group_id:
                        continue

                    group_link_data = get_group_link_from_crm(client.branch.branch_id, group_id)
                    if group_link_data.get("total", 0) > 0:
                        items = group_link_data.get("items", [])
                        if items:
                            group_tg_link = items[0].get("note")
                            if group_tg_link and group_tg_link not in group_tg_links:
                                group_tg_links.append(group_tg_link)

        return Response({"success": True, "data": group_tg_links}, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Ошибка в get_user_tg_links: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "message": f"Ошибка сервера: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
def find_client_by_id_view(request) -> Response:
    """
    Получение данных клиентов из CRM по Telegram ID пользователя.

    Эта функция выполняет следующие действия:
    1. Проверяет наличие user_id (Telegram ID) в запросе
    2. Находит пользователя (AppUser) по указанному Telegram ID
    3. Получает список всех клиентов (детей), связанных с этим пользователем
    4. Для каждого клиента запрашивает актуальные данные из CRM системы
    5. Формирует и возвращает результаты в виде JSON-ответа

    Параметры запроса:
    - user_id (str): Telegram ID пользователя (обязательный параметр)

    Возвращает:
    - Response: JSON-ответ со следующей структурой:
      - success (bool): Статус выполнения запроса
      - results (list): Список результатов для каждого клиента, где каждый элемент содержит:
        - client_crm_id (str): ID клиента в CRM системе
        - data (dict): Данные клиента из CRM или
        - error (str): Сообщение об ошибке, если данные не удалось получить

    Коды ответа:
    - 200 OK: Запрос выполнен успешно
    - 400 Bad Request: Отсутствует обязательный параметр user_id
    - 404 Not Found: Пользователь не найден или у пользователя нет клиентов
    - 500 Internal Server Error: Внутренняя ошибка сервера

    Пример успешного ответа:
    {
        "success": true,
        "results": [
            {
                "client_crm_id": "12345",
                "data": { ... данные клиента из CRM ... }
            },
            {
                "client_crm_id": "67890",
                "data": { ... данные клиента из CRM ... }
            }
        ]
    }

    Пример ответа с ошибкой:
    {
        "success": false,
        "message": "Пользователь не найден"
    }

    Зависимости:
    - find_client_by_id: Функция для получения данных клиента из CRM по ID
    - AppUser: Модель пользователя (родителя)
    - Client: Модель клиента (ребенка)
    """
    try:
        user_id = request.data.get("user_id")
        if not user_id:
            return Response(
                {"success": False, "message": "user_id обязателен"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = AppUser.objects.filter(telegram_id=user_id).first()
        if not user:
            return Response(
                {"success": False, "message": "Пользователь не найден"},
                status=status.HTTP_404_NOT_FOUND,
            )

        clients = Client.objects.filter(user=user)
        if not clients.exists():
            return Response(
                {"success": False, "message": "У пользователя нет клиентов"},
                status=status.HTTP_404_NOT_FOUND,
            )

        results = []
        for client in clients:
            result = find_client_by_id(client.branch_id, client.crm_id)
            if result:
                results.append({"client_crm_id": client.crm_id, "data": result})
            else:
                results.append({"client_crm_id": client.crm_id, "error": "Не удалось получить данные"})

        return Response({"success": True, "results": results}, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception(f"Ошибка при поиске клиента: {e}")
        return Response({"success": False, "message": f"Внутренняя ошибка сервера: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
def telegram_callback_handler(request) -> Response:
    """
    Обработчик callback запросов от Telegram бота для инлайн кнопок
    """
    try:
        callback_query = request.data.get('callback_query')
        if not callback_query:
            return Response({"success": False, "message": "Нет callback_query"}, status=status.HTTP_400_BAD_REQUEST)
        
        callback_data = callback_query.get('data')
        chat_id = callback_query.get('from', {}).get('id')
        
        if not chat_id:
            return Response({"success": False, "message": "Нет chat_id"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Обработка callback для получения подарка
        if callback_data == "get_gift":
            from app_api.tasks.check_client_trial_lessons_and_notify import send_telegram_document
            import os
            from django.conf import settings
            
            # Путь к файлу
            file_path = os.path.join(settings.BASE_DIR, 'static', 'files', 'Roblox_animation_guide.pdf')
            
            try:
                send_telegram_document(
                    chat_id=chat_id,
                    file_path=file_path,
                    caption="🎁 Ваш подарок - гайд по анимации в ROBLOX! Изучайте и создавайте крутые анимации! 🚀"
                )
                
                return Response({"success": True, "message": "Файл отправлен"}, status=status.HTTP_200_OK)
                
            except Exception as e:
                logger.error(f"Ошибка при отправке файла пользователю {chat_id}: {e}")
                return Response({"success": False, "message": f"Ошибка отправки файла: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response({"success": False, "message": "Неизвестный callback"}, status=status.HTTP_400_BAD_REQUEST)
        
    except Exception as e:
        logger.error(f"Ошибка в telegram_callback_handler: {e}")
        return Response({"success": False, "message": f"Внутренняя ошибка: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
