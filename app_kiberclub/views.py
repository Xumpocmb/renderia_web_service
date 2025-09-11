import json
from datetime import datetime
import logging
import gspread
import re
import requests
from bs4 import BeautifulSoup
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from oauth2client.service_account import ServiceAccountCredentials

from app_api.alfa_crm_service.crm_service import (
    get_client_lessons,
    get_client_lesson_name,
    get_client_kiberons,
)
from app_kiberclub.models import AppUser, Client, Location
from app_kibershop.models import ClientKiberons

from googleapiclient.discovery import build
from google.oauth2 import service_account

logger = logging.getLogger(__name__)

CREDENTIALS_FILE = "kiberone-tg-bot-a43691efe721.json"


def index(request: HttpRequest) -> HttpResponse:
    logger.debug("Начало выполнения функции index")

    context = {
        "title": "KIBERone",
    }

    try:
        telegram_id_from_req = request.GET.get("user_tg_id")
        logger.debug(f"Получен user_tg_id из GET: {telegram_id_from_req}")

        if telegram_id_from_req:
            request.session["tg_id"] = telegram_id_from_req
            logger.debug(f"Сохранён tg_id в сессию: {telegram_id_from_req}")
        else:
            telegram_id_from_req = request.session.get("tg_id")
            logger.debug(f"Получен tg_id из сессии: {telegram_id_from_req}")
            if not telegram_id_from_req:
                logger.warning(
                    "tg_id отсутствует в сессии и запросе. Перенаправление на страницу ошибки."
                )
                return redirect("app_kiberclub:error_page")

        bot_user = get_object_or_404(AppUser, telegram_id=telegram_id_from_req)
        logger.debug(f"Найден пользователь: {bot_user.telegram_id}")

        user_clients = Client.objects.filter(user=bot_user)
        logger.debug(f"Найдено профилей клиентов: {user_clients.count()}")
        context.update({"profiles": user_clients})

    except AppUser.DoesNotExist:
        logger.error("Пользователь не найден", exc_info=True)
        return redirect("app_kiberclub:error_page")
    except Exception as e:
        logger.exception(f"Неожиданная ошибка: {e}")
        return redirect("app_kiberclub:error_page")

    logger.debug("Завершение функции index. Рендеринг шаблона.")
    return render(request, "app_kiberclub/index.html", context=context)


def open_profile(request):
    """
    Отображает профиль выбранного клиента.
    """
    logger.debug("Начало выполнения функции open_profile")

    if request.method == "POST":
        client_id = request.POST.get("client_id")
        logger.debug(f"Получен client_id из POST: {client_id}")

        if client_id:
            request.session["client_id"] = client_id
            logger.debug(f"Сохранён client_id в сессию: {client_id}")
        else:
            logger.warning("client_id отсутствует в POST-запросе")
            return redirect("app_kiberclub:error_page")
    else:
        client_id = request.session.get("client_id")
        logger.debug(f"Получен client_id из сессии: {client_id}")

    try:
        client = get_object_or_404(Client, crm_id=client_id)
        logger.debug(f"Найден клиент: {client.crm_id}, имя: {client.name}")

        context = {
            "title": "KIBERone - Профиль",
            "client": {
                "client_id": client_id,
                "crm_id": client.crm_id,
                "name": client.name,
                "dob": client.dob.strftime("%d.%m.%Y") if client.dob else "Не указано",
                "balance": client.balance,
                "paid_count": client.paid_lesson_count,
                "next_lesson_date": (
                    client.next_lesson_date.strftime("%d.%m.%Y")
                    if client.next_lesson_date
                    else "Нет запланированных уроков"
                ),
                "paid_till": (
                    client.paid_till.strftime("%d.%m.%Y")
                    if client.paid_till
                    else "Не указано"
                ),
                "note": client.note or "Нет заметок",
                "branch": client.branch.name if client.branch else "Не указано",
                "is_study": "Да" if client.is_study else "Нет",
                "has_scheduled_lessons": (
                    "Да" if client.has_scheduled_lessons else "Нет"
                ),
            },
        }

        portfolio_link = get_portfolio_link(client.name)
        logger.debug(f"Портфолио для клиента {client.name}: {portfolio_link}")
        context.update({"portfolio_link": portfolio_link})

        branch_id = int(client.branch.branch_id)
        logger.debug(f"Определён branch_id: {branch_id}")

        lessons_data = get_client_lessons(
            client_id, branch_id, lesson_status=1, lesson_type=2
        )
        logger.debug(
            f"Получены данные об уроках для клиента {client_id}: {lessons_data}"
        )

        if lessons_data and lessons_data.get("total", 0) > 0:
            lesson = lessons_data.get("items", [])[-1]
            room_id = lesson.get("room_id")
            subject_id = lesson.get("subject_id")
            logger.debug(f"Последний урок: room_id={room_id}, subject_id={subject_id}")

            lesson_info = get_client_lesson_name(branch_id, subject_id)
            logger.debug(f"Информация о названии урока: {lesson_info}")

            if lesson_info.get("total") > 0:
                all_lesson_items = lesson_info.get("items")
                lesson_name = ""
                for item in all_lesson_items:
                    if item.get("id") == subject_id:
                        lesson_name = item.get("name", "")
                        logger.debug(f"Название урока найдено: {lesson_name}")

            if room_id:
                logger.debug(f"Установлен room_id в сессию: {room_id}")
                request.session["room_id"] = room_id

                location = Location.objects.filter(location_crm_id=room_id).first()
                if location:
                    location_sheet_name = location.sheet_name
                    logger.debug(
                        f"Локация найдена: {location.name}, sheet_name: {location_sheet_name}"
                    )

                    client_resume = get_resume_from_google_sheet(
                        client.branch.sheet_url, location_sheet_name, client.crm_id
                    )
                    logger.debug(f"Резюме клиента: {client_resume}")

                    context["client"].update(
                        {
                            "location_name": location.name,
                            "lesson_name": lesson_name if lesson_name else "",
                            "resume": (
                                client_resume if client_resume else "Появится позже"
                            ),
                            "room_id": room_id,
                        }
                    )

                kiberons = get_client_kiberons(branch_id, client.crm_id)

                context["client"].update(
                    {
                        "kiberons_count": kiberons if kiberons else "0",
                    }
                )

                return render(request, "app_kiberclub/client_card.html", context)
            else:
                logger.warning(f"room_id не найден для урока клиента {client_id}")
                return redirect("app_kiberclub:error_page")
        else:
            logger.warning(f"У клиента {client_id} нет активных уроков")
            return redirect("app_kiberclub:error_page")
    except Exception as e:
        logger.exception(f"Произошла ошибка при выполнении open_profile: {e}")
        return redirect("app_kiberclub:error_page")


def error_page_view(request):
    return render(request, "app_kiberclub/error_page.html")


def get_resume_from_google_sheet(sheet_url: str, sheet_name: str, child_id: str):
    """
    Загружает резюме ребенка из Google Таблицы.
    """
    credentials_path = CREDENTIALS_FILE

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = ServiceAccountCredentials.from_json_keyfile_name(
        credentials_path, scope
    )
    client = gspread.authorize(credentials)

    try:
        sheet = client.open_by_url(sheet_url).worksheet(sheet_name)
    except Exception as e:
        logger.error(f"Не удалось открыть лист {sheet_name} в таблице {sheet_url}: {e}")
        return "Появится позже"

    try:
        # Получаем все значения в виде списка списков
        all_values = sheet.get_all_values()

        if len(all_values) < 2:
            logger.warning("Таблица пустая или содержит только заголовки")
            return "Появится позже"

        headers = all_values[0]
        data_rows = all_values[1:]

        # Находим индексы нужных колонок
        try:
            id_col_index = headers.index("ID ребенка")
        except ValueError:
            logger.error("В таблице нет столбца 'ID ребенка'")
            return "Появится позже"

        try:
            resume_col_index = headers.index("Резюме май 2025")
        except ValueError:
            logger.error("В таблице нет столбца 'Резюме май 2025'")
            return "Появится позже"

        # Поиск нужной строки
        for row in data_rows:
            if len(row) > max(id_col_index, resume_col_index) and str(
                row[id_col_index]
            ) == str(child_id):
                resume = row[resume_col_index].strip()
                return resume or "Появится позже"

        logger.info(f"Ребенок с ID {child_id} не найден в таблице.")
        return "Появится позже"

    except Exception as e:
        logger.exception(f"Ошибка при чтении данных из таблицы: {e}")
        return "Появится позже"


def save_review_from_page(request):
    if request.method == "POST":
        crm_id = request.POST.get("crm_id")
        room_id = request.POST.get("room_id")
        feedback = request.POST.get("feedbackInput")

        client = get_object_or_404(Client, crm_id=crm_id)
        location = Location.objects.filter(location_crm_id=room_id).first()
        location_sheet_name = location.sheet_name

        success = save_review_to_google_sheet(
            sheet_url=client.branch.sheet_url,
            sheet_name=location_sheet_name,
            child_id=client.crm_id,
            feedback=f"{datetime.now().strftime("%Y-%m-%d")}\n{feedback}\n",
        )
        if success:
            return JsonResponse(
                {"status": "success", "message": "Ваш отзыв сохранен!"}, status=200
            )
        else:
            return JsonResponse(
                {
                    "status": "error",
                    "message": "Произошла ошибка при сохранении отзыва",
                },
                status=400,
            )


def save_review_to_google_sheet(
    sheet_url: str, sheet_name: str, child_id: str, feedback: str
):
    """
    Сохраняет отзыв родителя в Google Таблицу.
    """
    logger.debug("Начало выполнения функции save_review_to_google_sheet")

    credentials_path = CREDENTIALS_FILE

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    logger.debug(f"Загрузка учетных данных из файла: {credentials_path}")

    try:
        credentials = ServiceAccountCredentials.from_json_keyfile_name(
            credentials_path, scope
        )
        client = gspread.authorize(credentials)
    except Exception as e:
        logger.error(f"Ошибка при загрузке учетных данных: {e}", exc_info=True)
        return False

    try:
        logger.debug(f"Открытие таблицы по URL: {sheet_url}, лист: {sheet_name}")
        sheet = client.open_by_url(sheet_url).worksheet(sheet_name)
    except Exception as e:
        logger.error(f"Ошибка при открытии таблицы или листа: {e}", exc_info=True)
        return False

    logger.debug("Получение заголовков таблицы")
    headers = sheet.row_values(1)

    try:
        logger.debug("Поиск индекса столбца 'Отзыв родителя'")
        feedback_column_index = headers.index("Отзыв родителя") + 1
    except ValueError as e:
        logger.warning("Столбец 'Отзыв родителя' не найден в таблице")
        return False

    logger.debug("Получение всех записей из таблицы")
    data = sheet.get_all_records()

    logger.debug(f"Поиск ребенка с ID: {child_id} в таблице")
    for index, row in enumerate(data, start=2):
        if str(row.get("ID ребенка")) == str(child_id):
            logger.debug(
                f"Ребенок найден. Строка: {index - 1} (нумерация с 2), ID: {child_id}"
            )

            try:
                feedback = str(feedback).strip()
                if not feedback:
                    logger.warning("Отзыв пустой. Пропускаем обновление.")
                    return False

                logger.debug(
                    f"Получение текущего отзыва из ячейки: строка {index}, столбец {feedback_column_index}"
                )
                cell = sheet.cell(index, feedback_column_index)
                existing_feedback = cell.value or ""
                updated_feedback = f"{existing_feedback}\n{feedback}".strip()

                logger.debug(
                    f"Обновление ячейки: строка {index}, столбец {feedback_column_index}, новый отзыв: {updated_feedback}"
                )
                sheet.update_cell(index, feedback_column_index, updated_feedback)

                logger.info(f"Отзыв успешно обновлен для ребенка с ID {child_id}")
                return True
            except Exception as e:
                logger.exception(f"Ошибка при обновлении отзыва: {e}")
                return False

    logger.warning(f"Ребенок с ID {child_id} не найден в таблице")
    return False


def get_portfolio_link(client_name) -> str | None:
    SCOPES = ["https://www.googleapis.com/auth/drive "]
    CREDENTIALS_FILE = "portfolio-credentials.json"
    credentials = service_account.Credentials.from_service_account_file(
        CREDENTIALS_FILE, scopes=SCOPES
    )

    drive_service = build("drive", "v3", credentials=credentials)

    client_name = " ".join(client_name.split(" ")[:2])
    query = f"name contains '{client_name}' and mimeType='application/vnd.google-apps.folder'"
    results = (
        drive_service.files()
        .list(q=query, fields="nextPageToken, files(id, name, mimeType)")
        .execute()
    )

    folders = results.get("files", [])
    if not folders:
        return "#"

    folder_id = folders[0]["id"]
    folder_url = f"https://drive.google.com/drive/folders/{folder_id}"
    return folder_url
