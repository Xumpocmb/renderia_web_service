import os
import json
from django.core.management.base import BaseCommand
from app_api.alfa_crm_service.crm_service import get_all_clients
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Получает всех клиентов из CRM по указанному branch_id и сохраняет в JSON-файл'

    def add_arguments(self, parser):
        parser.add_argument('branch_id', type=int, help='ID филиала в CRM')

    def handle(self, *args, **options):
        branch_id = options['branch_id']
        self.stdout.write(self.style.SUCCESS(f'Получение клиентов из CRM для филиала с ID: {branch_id}'))
        
        # Создаем директорию fixtures, если она не существует
        fixtures_dir = 'fixtures'
        os.makedirs(fixtures_dir, exist_ok=True)
        
        # Путь к файлу результатов
        output_file = os.path.join(fixtures_dir, f'crm_clients_branch_{branch_id}.json')
        
        try:
            # Получаем всех клиентов из CRM
            clients = get_all_clients(branch_id)
            
            if clients:
                # Сохраняем результаты в JSON-файл
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(clients, f, ensure_ascii=False, indent=4)
                
                self.stdout.write(self.style.SUCCESS(
                    f'Данные успешно получены и сохранены в {output_file}'
                ))
                self.stdout.write(self.style.SUCCESS(f'Всего получено клиентов: {len(clients)}'))
                
                # Выводим примеры полученных данных
                if len(clients) > 0:
                    self.stdout.write(self.style.SUCCESS('Примеры полученных данных:'))
                    for i, client in enumerate(clients[:3]):
                        self.stdout.write(f"Клиент {i+1}: {client.get('name', 'Нет имени')} (ID: {client.get('id', 'Нет ID')})")
                    if len(clients) > 3:
                        self.stdout.write(f"... и еще {len(clients) - 3} клиентов")
            else:
                self.stdout.write(self.style.WARNING('Не удалось получить данные клиентов из CRM'))
        
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Ошибка при получении данных из CRM: {e}'))