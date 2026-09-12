# keyboards.py
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton

# ========== ОСНОВНЫЕ КЛАВИАТУРЫ ==========

def user_main_keyboard():
    """Клавиатура обычного пользователя"""
    keyboard = [
        [KeyboardButton("💰 Прайс-лист"), KeyboardButton("📦 Оформить заказ")],
        [KeyboardButton("📋 Мои заказы"), KeyboardButton("🤝 Приведи друга")],
        [KeyboardButton("🚪 Выход"), KeyboardButton("ℹ️ Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def manager_main_keyboard():
    """Клавиатура менеджера"""
    keyboard = [
        [KeyboardButton("💰 Управление прайсом"), KeyboardButton("📋 Заказы")],
        [KeyboardButton("👥 Связь с клиентами"), KeyboardButton("📊 Статистика")],
        [KeyboardButton("📢 Рассылка"), KeyboardButton("📤 Экспорт в Google Sheets")],
        [KeyboardButton("📥 Импорт товаров"), KeyboardButton("🚪 Выход")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def superadmin_main_keyboard():
    """Клавиатура суперадмина"""
    keyboard = [
        [KeyboardButton("💰 Управление прайсом"), KeyboardButton("📋 Заказы")],
        [KeyboardButton("👥 Связь с клиентами"), KeyboardButton("📊 Статистика")],
        [KeyboardButton("📢 Рассылка"), KeyboardButton("📤 Экспорт в Google Sheets")],
        [KeyboardButton("📥 Импорт товаров"), KeyboardButton("👥 Управление менеджерами")],
        [KeyboardButton("🚪 Выход")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_admin_keyboard(user_id, db):
    """Получение клавиатуры по роли"""
    if db.is_superadmin(user_id):
        return superadmin_main_keyboard()
    else:
        return manager_main_keyboard()

# ========== ВСПОМОГАТЕЛЬНЫЕ КЛАВИАТУРЫ ==========

def cancel_keyboard():
    """Клавиатура с отменой и выходом"""
    keyboard = [["❌ Отмена"], ["🚪 Выход"]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ========== INLINE КЛАВИАТУРЫ ==========

def price_menu_keyboard():
    """Меню управления прайсом"""
    keyboard = [
        [InlineKeyboardButton("➕ Добавить товар", callback_data="price_add")],
        [InlineKeyboardButton("✏️ Редактировать товар", callback_data="price_edit")],
        [InlineKeyboardButton("🗑 Удалить товар", callback_data="price_delete")],
        [InlineKeyboardButton("📊 Статус наличия", callback_data="price_toggle")],
        [InlineKeyboardButton("📂 Управление категориями", callback_data="categories_menu")],
        [InlineKeyboardButton("📤 Экспорт в Google Sheets", callback_data="price_export")],
        [InlineKeyboardButton("◀️ Назад", callback_data="price_back")]
    ]
    return InlineKeyboardMarkup(keyboard)

def orders_menu_keyboard():
    """Меню заказов"""
    keyboard = [
        [InlineKeyboardButton("📅 За сегодня", callback_data="orders_today")],
        [InlineKeyboardButton("📆 За месяц", callback_data="orders_month")],
        [InlineKeyboardButton("📅 За период", callback_data="orders_period")],
        [InlineKeyboardButton("📤 Экспорт в Google Sheets", callback_data="orders_export")],
        [InlineKeyboardButton("◀️ Назад", callback_data="orders_back")]
    ]
    return InlineKeyboardMarkup(keyboard)

def managers_menu_keyboard():
    """Меню управления менеджерами"""
    keyboard = [
        [InlineKeyboardButton("➕ Добавить менеджера", callback_data="manager_add")],
        [InlineKeyboardButton("🗑 Удалить менеджера", callback_data="manager_remove")],
        [InlineKeyboardButton("📋 Список менеджеров", callback_data="manager_list")],
        [InlineKeyboardButton("◀️ Назад", callback_data="manager_back")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_status_keyboard(order_id):
    """Клавиатура выбора статуса заказа"""
    from config import AVAILABLE_STATUSES
    keyboard = []
    for status_key, status_value in AVAILABLE_STATUSES.items():
        keyboard.append([InlineKeyboardButton(
            status_value, 
            callback_data=f"set_status_{order_id}_{status_key}"
        )])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_orders")])
    return InlineKeyboardMarkup(keyboard)


# ============================================================
# ⭐ НОВОЕ: КАТАЛОГ ДЛЯ ПОЛЬЗОВАТЕЛЕЙ (категории + пагинация)
# ============================================================

def get_catalog_keyboard(categories, page=1, total_pages=1, parent_id=None):
    """
    Клавиатура со ВСЕМИ категориями в одном сообщении + пагинация
    
    Args:
        categories: список категорий для текущей страницы
        page: текущая страница
        total_pages: всего страниц
        parent_id: ID родительской категории (None = верхний уровень)
    """
    keyboard = []
    
    # Категории — по 2 в ряд
    row = []
    for cat in categories:
        row.append(InlineKeyboardButton(
            f"📂 {cat['name']}", 
            callback_data=f"cat_{cat['id']}"
        ))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    # Навигация по страницам (если больше 1 страницы)
    if total_pages > 1:
        nav = []
        if page > 1:
            nav.append(InlineKeyboardButton("◀️", callback_data=f"catpage_{page-1}_{parent_id or 0}"))
        
        start_page = max(1, page - 2)
        end_page = min(total_pages, page + 2)
        
        for p in range(start_page, end_page + 1):
            if p == page:
                nav.append(InlineKeyboardButton(f"· {p} ·", callback_data="noop"))
            else:
                nav.append(InlineKeyboardButton(str(p), callback_data=f"catpage_{p}_{parent_id or 0}"))
        
        if page < total_pages:
            nav.append(InlineKeyboardButton("▶️", callback_data=f"catpage_{page+1}_{parent_id or 0}"))
        
        if nav:
            keyboard.append(nav)
    
    # Нижние кнопки
    keyboard.append([
        InlineKeyboardButton("🛒 Все товары", callback_data="all_products_1"),
        InlineKeyboardButton("🏠 В меню", callback_data="back_to_main")
    ])
    
    return InlineKeyboardMarkup(keyboard)


def get_subcategories_keyboard(subcategories, parent_id, page=1, total_pages=1):
    """Клавиатура подкатегорий внутри категории"""
    keyboard = []
    
    for cat in subcategories:
        keyboard.append([InlineKeyboardButton(
            f"📁 {cat['name']}", 
            callback_data=f"cat_{cat['id']}"
        )])
    
    # Навигация
    if total_pages > 1:
        nav = []
        if page > 1:
            nav.append(InlineKeyboardButton("◀️", callback_data=f"subcatpage_{page-1}_{parent_id}"))
        nav.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
        if page < total_pages:
            nav.append(InlineKeyboardButton("▶️", callback_data=f"subcatpage_{page+1}_{parent_id}"))
        keyboard.append(nav)
    
    keyboard.append([
        InlineKeyboardButton("◀️ К категориям", callback_data="back_to_categories"),
        InlineKeyboardButton("🏠 В меню", callback_data="back_to_main")
    ])
    
    return InlineKeyboardMarkup(keyboard)


def get_products_paginated_keyboard(products, category_id, page=1, total_pages=1):
    """
    Клавиатура товаров с пагинацией (по 5 шт)
    
    Args:
        products: список товаров на странице
        category_id: ID категории ('all' — все товары)
        page: текущая страница
        total_pages: всего страниц
    """
    keyboard = []
    
    # Каждый товар — отдельная кнопка
    for p in products:
        price_str = f"{p['price']:.0f}₽"
        # Обрезаем длинные названия
        name = p['name'][:35] + "..." if len(p['name']) > 35 else p['name']
        keyboard.append([InlineKeyboardButton(
            f"📦 {name} — {price_str}",
            callback_data=f"view_product_{p['id']}"
        )])
    
    # Навигация по страницам
    if total_pages > 1:
        nav = []
        if page > 1:
            nav.append(InlineKeyboardButton("◀️", callback_data=f"prodpage_{category_id}_{page-1}"))
        
        start_page = max(1, page - 2)
        end_page = min(total_pages, page + 2)
        
        for p in range(start_page, end_page + 1):
            if p == page:
                nav.append(InlineKeyboardButton(f"· {p} ·", callback_data="noop"))
            else:
                nav.append(InlineKeyboardButton(str(p), callback_data=f"prodpage_{category_id}_{p}"))
        
        if page < total_pages:
            nav.append(InlineKeyboardButton("▶️", callback_data=f"prodpage_{category_id}_{page+1}"))
        
        if nav:
            keyboard.append(nav)
    
    # Кнопки навигации
    back_btn = "◀️ К категориям" if category_id == 'all' else f"◀️ Назад"
    back_cb = "back_to_categories" if category_id == 'all' else "back_to_categories"
    
    keyboard.append([
        InlineKeyboardButton(back_btn, callback_data=back_cb),
        InlineKeyboardButton("🏠 В меню", callback_data="back_to_main")
    ])
    
    return InlineKeyboardMarkup(keyboard)


def get_product_detail_keyboard(product_id, category_id):
    """Клавиатура для просмотра товара"""
    keyboard = [
        [InlineKeyboardButton("🛒 Купить", callback_data=f"buy_product_{product_id}")],
        [InlineKeyboardButton("◀️ Назад", callback_data=f"cat_{category_id}")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ============================================================
# ⭐ НОВОЕ: УПРАВЛЕНИЕ КАТЕГОРИЯМИ (для админа)
# ============================================================

def categories_menu_keyboard():
    """Меню управления категориями"""
    keyboard = [
        [InlineKeyboardButton("➕ Добавить категорию", callback_data="cat_add")],
        [InlineKeyboardButton("➕ Добавить подкатегорию", callback_data="subcat_add")],
        [InlineKeyboardButton("📋 Список категорий", callback_data="cat_list")],
        [InlineKeyboardButton("✏️ Переименовать категорию", callback_data="cat_rename")],
        [InlineKeyboardButton("🗑 Удалить категорию", callback_data="cat_delete")],
        [InlineKeyboardButton("◀️ Назад", callback_data="cat_back")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_category_select_keyboard(categories, callback_prefix, back_callback="cat_back"):
    """
    Универсальная клавиатура выбора категории
    
    Args:
        categories: список категорий
        callback_prefix: префикс callback (например 'cat_del_' или 'subcat_parent_')
        back_callback: callback для кнопки Назад
    """
    keyboard = []
    for c in categories:
        keyboard.append([InlineKeyboardButton(
            f"📂 {c['name']}", 
            callback_data=f"{callback_prefix}{c['id']}"
        )])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data=back_callback)])
    return InlineKeyboardMarkup(keyboard)


def get_category_picker_for_product(categories, page=1, total_pages=1):
    """
    Клавиатура выбора категории при добавлении/редактировании товара
    
    Args:
        categories: список категорий
        page: текущая страница
        total_pages: всего страниц
    """
    keyboard = []
    
    row = []
    for c in categories:
        row.append(InlineKeyboardButton(
            f"📂 {c['name']}", 
            callback_data=f"pickcat_{c['id']}"
        ))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    # Навигация
    if total_pages > 1:
        nav = []
        if page > 1:
            nav.append(InlineKeyboardButton("◀️", callback_data=f"pickcatpage_{page-1}"))
        nav.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
        if page < total_pages:
            nav.append(InlineKeyboardButton("▶️", callback_data=f"pickcatpage_{page+1}"))
        keyboard.append(nav)
    
    keyboard.append([
        InlineKeyboardButton("🚫 Без категории", callback_data="pickcat_none"),
        InlineKeyboardButton("◀️ Отмена", callback_data="pickcat_cancel")
    ])
    
    return InlineKeyboardMarkup(keyboard)


def get_subcategory_picker_for_product(subcategories, parent_id):
    """Клавиатура выбора подкатегории при добавлении товара"""
    keyboard = []
    
    for c in subcategories:
        keyboard.append([InlineKeyboardButton(
            f"📁 {c['name']}", 
            callback_data=f"picksubcat_{c['id']}"
        )])
    
    keyboard.append([
        InlineKeyboardButton("⏭ Пропустить", callback_data=f"picksubcat_skip_{parent_id}"),
    ])
    
    return InlineKeyboardMarkup(keyboard)


def confirm_delete_category_keyboard(category_id):
    """Подтверждение удаления категории"""
    keyboard = [
        [
            InlineKeyboardButton("✅ Да, удалить", callback_data=f"cat_confirmdel_{category_id}"),
            InlineKeyboardButton("❌ Нет", callback_data="cat_delete")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


# ============================================================
# ⭐ НОВОЕ: ПАГИНАЦИЯ ТОВАРОВ В АДМИНКЕ
# ============================================================

def get_admin_products_keyboard(products, page=1, total_pages=1, action='edit'):
    """
    Клавиатура товаров для админа с пагинацией
    
    Args:
        products: список товаров
        page: текущая страница
        total_pages: всего страниц
        action: 'edit', 'delete', 'toggle' — для какого действия
    """
    keyboard = []
    
    action_prefix = {
        'edit': 'edit_select_',
        'delete': 'delete_',
        'toggle': 'toggle_'
    }.get(action, 'edit_select_')
    
    for p in products:
        keyboard.append([InlineKeyboardButton(
            f"📦 {p['name'][:35]} — {p['price']:.0f}₽", 
            callback_data=f"{action_prefix}{p['id']}"
        )])
    
    # Навигация
    if total_pages > 1:
        nav = []
        if page > 1:
            nav.append(InlineKeyboardButton("◀️", callback_data=f"admprod_{action}_{page-1}"))
        nav.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
        if page < total_pages:
            nav.append(InlineKeyboardButton("▶️", callback_data=f"admprod_{action}_{page+1}"))
        keyboard.append(nav)
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="price_back")])
    
    return InlineKeyboardMarkup(keyboard)