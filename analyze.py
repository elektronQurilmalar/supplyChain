import requests
import pandas as pd
from jinja2 import Environment, FileSystemLoader
from datetime import datetime


class BOMAnalyzer:
    def __init__(self, api_keys):
        """
        Инициализирует анализатор со словарем API ключей.
        """
        if not api_keys or not any(api_keys.values()):
            raise ValueError("Необходимо указать действительный API ключ.")
        self.api_keys = api_keys

    def get_part_info(self, part_number):
        """
        Опрашивает все активные API и возвращает агрегированные данные.
        В текущей реализации используется только Mouser.
        """
        if 'mouser' in self.api_keys and self.api_keys['mouser']:
            return self.get_mouser_part_info(part_number, self.api_keys['mouser'])
        return None

    def get_mouser_part_info(self, part_number, api_key):
        """Запрашивает информацию о компоненте у Mouser Part Search API."""
        api_url = "https://api.mouser.com/api/v1.0/search/partnumber"
        headers = {'Content-Type': 'application/json'}
        payload = {
            "SearchByPartRequest": {
                "mouserPartNumber": part_number,
                "partSearchOptions": "1"
            }
        }
        params = {'apiKey': api_key}
        try:
            response = requests.post(api_url, headers=headers, json=payload, params=params)
            response.raise_for_status()
            data = response.json()
            if not data.get('SearchResults') or not data['SearchResults']['Parts']:
                return None
            part = data['SearchResults']['Parts'][0]
            # Возвращаем расширенный набор данных, включая описание
            return {
                "manufacturer": part.get('Manufacturer', 'N/A'),
                "stock": int(part.get('AvailabilityInStock', 0)),
                "lifecycle_status": part.get('LifecycleStatus', 'Unknown') or 'Unknown',
                "description": part.get('Description', '')
            }
        except requests.exceptions.RequestException:
            return {"error": True}

    def find_replacements(self, original_part_info, original_part_number):
        """Ищет замены для компонента, используя Keyword Search API."""
        if not 'mouser' in self.api_keys or not original_part_info or not original_part_info.get('description'):
            return []

        # Эвристика для поиска: используем первые 4 слова из описания.
        # Это помогает отсечь лишние детали (типа упаковки) и сфокусироваться на функции.
        keywords = ' '.join(original_part_info['description'].split()[:4])

        api_url = "https://api.mouser.com/api/v1.0/search/keyword"
        payload = {
            "SearchByKeywordRequest": {
                "keyword": keywords,
                "records": 5,  # Ищем 5 кандидатов, чтобы было из чего выбрать
                "startingRecord": 0,
                "searchOptions": "InStock",  # Искать только те, что в наличии
                "searchWithYourSignUpLanguage": "true"
            }
        }
        params = {'apiKey': self.api_keys['mouser']}

        try:
            response = requests.post(api_url, headers=headers, json=payload, params=params)
            response.raise_for_status()
            data = response.json()

            if not data.get('SearchResults') or not data['SearchResults']['Parts']:
                return []

            replacements = []
            for part in data['SearchResults']['Parts']:
                # Условие 1: Не предлагать сам исходный компонент
                if part.get('MouserPartNumber') == original_part_number:
                    continue
                # Условие 2: Предлагать только активные компоненты (пустой статус часто означает "активный")
                if part.get('LifecycleStatus', '').lower() in ['active', '']:
                    replacements.append({
                        'part_number': part.get('MouserPartNumber'),
                        'manufacturer': part.get('Manufacturer'),
                        'stock': part.get('AvailabilityInStock', '0'),
                        'description': part.get('Description')
                    })
            return replacements[:3]  # Возвращаем не более 3 лучших вариантов
        except requests.exceptions.RequestException:
            return []

    def analyze_risk(self, part_info):
        """Анализирует информацию о компоненте и возвращает уровень риска."""
        # ... (код этого метода без изменений) ...
        if part_info is None: return "Не найден", "risk-not-found"
        if part_info.get("error"): return "Ошибка API", "risk-critical"
        score = 0
        lifecycle = part_info.get('lifecycle_status', 'Unknown').lower()
        stock = part_info.get('stock', 0)
        if "obsolete" in lifecycle or "eol" in lifecycle:
            score += 10
        elif "nrnd" in lifecycle or "not recommended" in lifecycle:
            score += 5
        if stock == 0:
            score += 4
        elif stock < 100:
            score += 2
        if score >= 10:
            return "Критический", "risk-critical"
        elif score >= 5:
            return "Высокий", "risk-high"
        elif score >= 2:
            return "Средний", "risk-medium"
        else:
            return "Низкий", "risk-low"

    def process_bom_file(self, file_path, status_callback):
        """Основной метод, обрабатывающий BOM файл."""
        try:
            bom_df = pd.read_csv(file_path)
            if 'PartNumber' not in bom_df.columns:
                raise ValueError("В файле BOM отсутствует обязательная колонка 'PartNumber'.")
        except Exception as e:
            status_callback(f"Ошибка чтения файла: {e}", "red")
            return

        report_data = []
        total_rows = len(bom_df)

        for index, row in bom_df.iterrows():
            status_callback(f"Обработка {index + 1}/{total_rows}: {row['PartNumber']}...", "gray")
            part_number = row['PartNumber']
            part_info = self.get_part_info(part_number)
            risk_level, risk_class = self.analyze_risk(part_info)

            report_item = row.to_dict()
            if part_info and not part_info.get("error"):
                report_item.update(part_info)
            else:
                report_item.update({"manufacturer": "N/A", "stock": 0, "lifecycle_status": "N/A", "description": "N/A"})

            report_item['risk_level'] = risk_level
            report_item['risk_class'] = risk_class
            report_item['replacements'] = []  # Инициализируем поле для замен

            # Триггер для поиска замен: высокий или критический риск
            if risk_level in ["Высокий", "Критический"]:
                status_callback(f"Поиск замен для {part_number}...", "blue")
                replacements = self.find_replacements(part_info, part_number)
                report_item['replacements'] = replacements

            report_data.append(report_item)

        self.generate_report(report_data, status_callback)

    def generate_report(self, report_data, status_callback):
        """Генерирует HTML-отчет."""
        # ... (код этого метода без изменений) ...
        summary = {level: 0 for level in ["Низкий", "Средний", "Высокий", "Критический", "Не найден", "Ошибка API"]}
        for item in report_data:
            if item['risk_level'] in summary: summary[item['risk_level']] += 1
        env = Environment(loader=FileSystemLoader('.'))
        template = env.get_template('template.html')
        html_output = template.render(
            components=report_data, summary=summary,
            report_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        output_filename = 'bom_risk_report.html'
        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write(html_output)
        status_callback(f"Готово! Отчет сохранен в {output_filename}", "green")