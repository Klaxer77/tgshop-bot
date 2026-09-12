# google_sheets.py
import logging
import os
import gspread
import json
from google.oauth2.service_account import Credentials
from config import SPREADSHEET_ID

logger = logging.getLogger(__name__)


class GoogleSheets:
    """Класс для работы с Google Sheets"""
    
    def __init__(self):
        self.client = None
        self.spreadsheet = None
        self.products_sheet = None
        self.categories_sheet = None
        self.orders_sheet = None
        self.init_google_sheets()
    
    def init_google_sheets(self):
        """Инициализация Google Sheets"""
        try:
            if not os.path.exists('credentials.json'):
                logger.warning("⚠️ Файл credentials.json не найден. Google Sheets отключен.")
                return
            
            scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
            creds = Credentials.from_service_account_file('credentials.json', scopes=scope)
            self.client = gspread.authorize(creds)
            
            # Открываем таблицу
            self.spreadsheet = self.client.open_by_key(SPREADSHEET_ID)
            
            # Лист с товарами
            try:
                self.products_sheet = self.spreadsheet.worksheet("Товары")
            except:
                self.products_sheet = self.spreadsheet.add_worksheet("Товары", 1000, 20)
                headers = [["ID", "Название", "Категория", "Цена", "В наличии", "Фото ID", "Дата добавления"]]
                self.products_sheet.append_rows(headers)
                logger.info("✅ Создан лист 'Товары'")
            
            # ⭐ НОВОЕ: Лист с категориями
            try:
                self.categories_sheet = self.spreadsheet.worksheet("Категории")
            except:
                self.categories_sheet = self.spreadsheet.add_worksheet("Категории", 1000, 10)
                headers = [["ID", "Название", "Родитель (ID)", "Активна"]]
                self.categories_sheet.append_rows(headers)
                logger.info("✅ Создан лист 'Категории'")
            
            # Лист с заказами
            try:
                self.orders_sheet = self.spreadsheet.worksheet("Заказы")
            except:
                self.orders_sheet = self.spreadsheet.add_worksheet("Заказы", 1000, 20)
                headers = [["№ заказа", "Клиент", "Username", "Телефон", "Товары", "Сумма", "Адрес", "Статус", "Дата"]]
                self.orders_sheet.append_rows(headers)
                logger.info("✅ Создан лист 'Заказы'")
            
            logger.info("✅ Google Sheets подключен")
        except Exception as e:
            logger.error(f"❌ Ошибка Google Sheets: {e}")
    
    # ============================================================
    # ЭКСПОРТ
    # ============================================================
    
    def export_products(self, products):
        """Экспорт товаров в Google Sheets"""
        if not self.client:
            return False, "❌ Google Sheets не подключен"
        
        try:
            self.products_sheet.batch_clear(['A2:G10000'])
            
            rows = []
            for p in products:
                # p: id, name, category, price, stock, photo, created_at
                rows.append([
                    str(p[0]), 
                    str(p[1]), 
                    str(p[2]), 
                    float(p[3]), 
                    int(p[4]), 
                    str(p[5]) if p[5] else "", 
                    str(p[6]) if len(p) > 6 else ""
                ])
            
            if rows:
                self.products_sheet.append_rows(rows)
            
            logger.info(f"✅ Экспортировано {len(products)} товаров")
            return True, f"✅ Экспортировано {len(products)} товаров"
        except Exception as e:
            logger.error(f"❌ Ошибка экспорта товаров: {e}")
            return False, f"❌ Ошибка: {str(e)[:100]}"
    
    def export_categories(self, categories):
        """
        ⭐ НОВОЕ: Экспорт категорий в Google Sheets
        
        Args:
            categories: список словарей {'id', 'name', 'parent_id', 'is_active'}
        """
        if not self.client or not self.categories_sheet:
            return False, "❌ Google Sheets не подключен"
        
        try:
            self.categories_sheet.batch_clear(['A2:D10000'])
            
            rows = []
            for c in categories:
                # Поддерживаем и dict, и sqlite3.Row
                if isinstance(c, dict):
                    cid = c.get('id', '')
                    name = c.get('name', '')
                    parent_id = c.get('parent_id', '')
                    is_active = c.get('is_active', 1)
                else:
                    # sqlite3.Row
                    cid = c['id']
                    name = c['name']
                    parent_id = c['parent_id'] if 'parent_id' in c.keys() else ''
                    is_active = c['is_active'] if 'is_active' in c.keys() else 1
                
                rows.append([
                    str(cid),
                    str(name),
                    str(parent_id) if parent_id else "",
                    'Да' if is_active else 'Нет'
                ])
            
            if rows:
                self.categories_sheet.append_rows(rows)
            
            logger.info(f"✅ Экспортировано {len(rows)} категорий")
            return True, f"✅ Экспортировано {len(rows)} категорий"
        except Exception as e:
            logger.error(f"❌ Ошибка экспорта категорий: {e}")
            return False, f"❌ Ошибка: {str(e)[:100]}"
    
    def export_orders(self, orders):
        """Экспорт заказов в Google Sheets"""
        if not self.client:
            return False, "❌ Google Sheets не подключен"
        
        try:
            self.orders_sheet.batch_clear(['A2:I10000'])
            
            rows = []
            for o in orders:
                try:
                    # o: order_id, user_name, user_phone, username, items, total, address, status, created_at
                    items = json.loads(o[4]) if o[4] else []
                    items_text = ", ".join([f"{i.get('name', '')} x{i.get('quantity', 0)}" for i in items])
                    rows.append([
                        str(o[0]), str(o[1]), str(o[3]), str(o[2]), 
                        items_text, float(o[5]), str(o[6]), str(o[7]), str(o[8][:10])
                    ])
                except Exception as e:
                    logger.error(f"Ошибка обработки заказа: {e}")
                    continue
            
            if rows:
                self.orders_sheet.append_rows(rows)
            
            logger.info(f"✅ Экспортировано {len(rows)} заказов")
            return True, f"✅ Экспортировано {len(rows)} заказов"
        except Exception as e:
            logger.error(f"❌ Ошибка экспорта заказов: {e}")
            return False, f"❌ Ошибка: {str(e)[:100]}"
    
    # ============================================================
    # ИМПОРТ
    # ============================================================
    
    def import_categories(self):
        """
        ⭐ НОВОЕ: Импорт категорий из Google Sheets
        
        Формат листа:
        | ID | Название | Родитель (ID) | Активна |
        
        Возвращает список словарей:
        [{'id': 1, 'name': 'Электроника', 'parent_id': None, 'is_active': True}, ...]
        """
        if not self.client or not self.categories_sheet:
            return [], ["❌ Google Sheets не подключен"]
        
        try:
            records = self.categories_sheet.get_all_values()
            
            # Проверяем, есть ли заголовки
            if not records:
                return [], []
            
            # Пропускаем первую строку (заголовки)
            records = records[1:]
            
            categories = []
            errors = []
            
            for i, row in enumerate(records, start=2):
                if len(row) >= 2 and row[1].strip():
                    try:
                        cat_id = int(row[0].strip()) if row[0].strip() else None
                        name = row[1].strip()
                        parent_id = int(row[2].strip()) if len(row) > 2 and row[2].strip() else None
                        is_active_str = row[3].strip().lower() if len(row) > 3 else 'да'
                        is_active = is_active_str in ['да', 'yes', '1', 'true', '+']
                        
                        categories.append({
                            'id': cat_id,
                            'name': name,
                            'parent_id': parent_id,
                            'is_active': is_active
                        })
                    except Exception as e:
                        errors.append(f"Строка {i}: {str(e)}")
            
            logger.info(f"✅ Импортировано {len(categories)} категорий")
            return categories, errors
        except Exception as e:
            logger.error(f"❌ Ошибка импорта категорий: {e}")
            return [], [str(e)]
    
    def import_products(self):
        """
        Импорт товаров из Google Sheets.
        
        Формат листа:
        | ID | Название | Категория | Цена | В наличии | Фото ID | Дата |
        
        ВАЖНО: колонка "Категория" содержит НАЗВАНИЕ категории (не ID).
        При импорте бот найдёт category_id по названию.
        """
        if not self.client:
            return [], ["❌ Google Sheets не подключен"]
        
        try:
            records = self.products_sheet.get_all_values()[1:]
            
            products = []
            errors = []
            
            for i, row in enumerate(records, start=2):
                if len(row) >= 4 and row[1].strip():
                    try:
                        name = row[1].strip()
                        category_name = row[2].strip() if len(row) > 2 and row[2].strip() else "Общее"
                        
                        # Парсим цену
                        price_str = row[3].strip().replace(',', '.').replace(' ', '')
                        price = float(price_str) if price_str else 0
                        
                        # Парсим количество
                        stock_str = row[4].strip() if len(row) > 4 and row[4].strip() else "0"
                        stock = int(float(stock_str)) if stock_str else 0
                        
                        # Фото ID (если есть)
                        photo_file_id = row[5].strip() if len(row) > 5 and row[5].strip() else None
                        
                        products.append({
                            'name': name,
                            'category_name': category_name,
                            'price': price,
                            'stock': stock,
                            'photo_file_id': photo_file_id
                        })
                    except Exception as e:
                        errors.append(f"Строка {i}: {str(e)}")
            
            logger.info(f"✅ Импортировано {len(products)} товаров")
            return products, errors
        except Exception as e:
            logger.error(f"❌ Ошибка импорта товаров: {e}")
            return [], [str(e)]