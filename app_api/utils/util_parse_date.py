from datetime import datetime

def parse_date(date_str):
    """
    Преобразует строку даты/времени в объект date или datetime.
    Если строка пустая или некорректная, возвращает None.
    ---
    Поддерживаемые форматы:
        - YYYY-MM-DD
        - DD.MM.YYYY
        - YYYY-MM-DD HH:MM:SS
    """
    if not date_str:
        return None

    # Список возможных форматов даты
    date_formats = [
        "%Y-%m-%d",  # YYYY-MM-DD
        "%d.%m.%Y",  # DD.MM.YYYY
        "%Y-%m-%d %H:%M:%S",  # YYYY-MM-DD HH:MM:SS
    ]

    for fmt in date_formats:
        try:
            # Пытаемся преобразовать строку в дату/время
            parsed_date = datetime.strptime(date_str, fmt)
            return parsed_date.date() if " " not in fmt else parsed_date
        except ValueError:
            continue

    # Если ни один формат не подходит
    return None