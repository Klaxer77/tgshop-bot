# handlers/user.py
import logging
import json
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from database import Database
from keyboards import *
from states import *
from utils.validators import validate_phone
from utils.formatters import escape_markdown, format_number
from config import ORDER_STATUSES
from handlers.common import exit_handler

logger = logging.getLogger(__name__)
db = Database()

# Константы пагинации
CATEGORIES_PER_PAGE = 12
PRODUCTS_PER_PAGE = 5


# ========== СТАРТ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик /start"""
    user = update.effective_user
    
    logger.info(f"👤 Пользователь {user.id} ({user.first_name}) запустил бота")
    
    # Проверка реферальной ссылки
    args = context.args
    referrer_id = None
    if args and len(args) > 0:
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users WHERE referral_code = ?", (args[0],))
        result = cursor.fetchone()
        if result and result['user_id'] != user.id:
            referrer_id = result['user_id']
            logger.info(f"👤 Пользователь {user.id} перешел по реферальной ссылке от {referrer_id}")
        conn.close()
    
    db.register_user(user.id, user.username, user.first_name, user.last_name, referrer_id)
    context.user_data.clear()
    
    if db.is_superadmin(user.id):
        await update.message.reply_text(
            f"👑 *СУПЕРАДМИНИСТРАТОР*\n\n"
            f"Здравствуйте, {escape_markdown(user.first_name)}!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=superadmin_main_keyboard()
        )
        return SUPERADMIN
    elif db.is_manager(user.id):
        await update.message.reply_text(
            f"👔 *МЕНЕДЖЕР*\n\n"
            f"Здравствуйте, {escape_markdown(user.first_name)}!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=manager_main_keyboard()
        )
        return ADMIN
    else:
        await update.message.reply_text(
            f"👋 Привет, {escape_markdown(user.first_name)}! Добро пожаловать в магазин!",
            reply_markup=user_main_keyboard()
        )
        return MAIN


# ========== ОСНОВНОЙ ОБРАБОТЧИК ==========

async def user_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик для обычных пользователей"""
    text = update.message.text
    user_id = update.effective_user.id
    
    logger.info(f"👤 Пользователь {user_id}: {text}")
    
    if text == "💰 Прайс-лист":
        return await show_catalog(update, context)
    elif text == "📦 Оформить заказ":
        return await start_order(update, context)
    elif text == "📋 Мои заказы":
        return await show_my_orders(update, context)
    elif text == "🤝 Приведи друга":
        return await show_referral(update, context)
    elif text == "ℹ️ Помощь":
        return await show_help(update, context)
    elif text == "🚪 Выход":
        return await exit_handler(update, context)
    
    return MAIN


# ============================================================
# ⭐ НОВЫЙ КАТАЛОГ: категории → подкатегории → товары
# ============================================================

async def show_catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ каталога — все категории в ОДНОМ сообщении"""
    user_id = update.effective_user.id
    logger.info(f"👤 Пользователь {user_id}: открыл каталог")
    
    # Сбрасываем навигацию
    context.user_data['catalog'] = {'level': 'categories'}
    
    await render_categories(update, context, page=1, parent_id=None)
    return MAIN


async def render_categories(update: Update, context: ContextTypes.DEFAULT_TYPE, 
                            page: int = 1, parent_id: int = None):
    """Рендер одной страницы со всеми категориями + пагинация"""
    query = update.callback_query
    
    # Получаем категории
    all_categories = db.get_categories(parent_id=parent_id, active_only=True)
    
    if not all_categories:
        text = (
            "📂 *КАТАЛОГ*\n"
            f"{'=' * 30}\n\n"
            "📭 В этом разделе пока нет категорий.\n\n"
            "Перейдите во вкладку «Все товары»:"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🛒 Все товары", callback_data="all_products_1")],
            [InlineKeyboardButton("🏠 В меню", callback_data="back_to_main")]
        ])
        
        if query:
            await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
        else:
            await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
        return
    
    # Пагинация
    total = len(all_categories)
    total_pages = (total + CATEGORIES_PER_PAGE - 1) // CATEGORIES_PER_PAGE
    page = max(1, min(page, total_pages))
    
    start = (page - 1) * CATEGORIES_PER_PAGE
    end = start + CATEGORIES_PER_PAGE
    page_categories = all_categories[start:end]
    
    text = (
        f"📂 *КАТАЛОГ ТОВАРОВ*\n"
        f"{'=' * 30}\n\n"
        f"Выберите категорию:\n"
        f"📄 Страница {page} из {total_pages}\n"
        f"📊 Всего категорий: {total}"
    )
    
    keyboard = get_catalog_keyboard(page_categories, page, total_pages, parent_id)
    
    if query:
        try:
            await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
        except Exception as e:
            logger.error(f"Ошибка редактирования: {e}")
            await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)


async def render_subcategories(update: Update, context: ContextTypes.DEFAULT_TYPE, 
                                parent_id: int, page: int = 1):
    """Рендер подкатегорий внутри категории"""
    query = update.callback_query
    
    subcategories = db.get_categories(parent_id=parent_id, active_only=True)
    parent = db.get_category(parent_id)
    parent_name = parent['name'] if parent else "Категория"
    
    if not subcategories:
        # Если нет подкатегорий — показываем товары этой категории
        await render_products(update, context, category_id=parent_id, page=1)
        return
    
    # Пагинация подкатегорий
    total = len(subcategories)
    total_pages = (total + CATEGORIES_PER_PAGE - 1) // CATEGORIES_PER_PAGE
    page = max(1, min(page, total_pages))
    
    start = (page - 1) * CATEGORIES_PER_PAGE
    end = start + CATEGORIES_PER_PAGE
    page_subcategories = subcategories[start:end]
    
    text = (
        f"📁 *{escape_markdown(parent_name)}*\n"
        f"{'=' * 30}\n\n"
        f"Выберите подкатегорию:\n"
        f"📄 Страница {page} из {total_pages}\n"
        f"📊 Всего подкатегорий: {total}"
    )
    
    keyboard = get_subcategories_keyboard(page_subcategories, parent_id, page, total_pages)
    
    try:
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Ошибка: {e}")


async def render_products(update: Update, context: ContextTypes.DEFAULT_TYPE, 
                          category_id, page: int = 1):
    """Рендер товаров категории с пагинацией по 5 штук"""
    query = update.callback_query
    
    # Получаем товары
    if category_id == 'all':
        result = db.get_all_products_paginated(page=page, per_page=PRODUCTS_PER_PAGE)
        title = "🛒 Все товары"
        back_callback = "back_to_categories"
    else:
        result = db.get_products_by_category(category_id, page=page, per_page=PRODUCTS_PER_PAGE)
        category = db.get_category(category_id)
        title = f"📦 {escape_markdown(category['name']) if category else 'Товары'}"
        back_callback = "back_to_categories"
    
    products = result['products']
    total = result['total']
    total_pages = result['pages']
    current_page = result['current_page']
    
    if not products:
        text = (
            f"{title}\n"
            f"{'=' * 30}\n\n"
            f"📭 В этом разделе пока нет товаров"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ Назад", callback_data=back_callback)],
            [InlineKeyboardButton("🏠 В меню", callback_data="back_to_main")]
        ])
        
        try:
            await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
        except Exception as e:
            logger.error(f"Ошибка: {e}")
        return
    
    # Формируем текст
    text = (
        f"{title}\n"
        f"{'=' * 30}\n\n"
        f"📊 Найдено товаров: {total}\n"
        f"📄 Страница {current_page} из {total_pages}\n\n"
    )
    
    for i, p in enumerate(products, 1):
        price = format_number(p['price'])
        stock_icon = "✅" if p['stock'] > 0 else "❌"
        text += f"{i}. {stock_icon} *{escape_markdown(p['name'])}*\n"
        text += f"    💰 {price}₽  |  📦 {p['stock']} шт.\n\n"
    
    keyboard = get_products_paginated_keyboard(
        products, 
        category_id, 
        current_page, 
        total_pages
    )
    
    try:
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Ошибка: {e}")


async def view_product_detail(update: Update, context: ContextTypes.DEFAULT_TYPE, product_id: int):
    """Просмотр карточки товара с кнопкой Купить"""
    query = update.callback_query
    
    product = db.get_product(product_id)
    
    if not product:
        await query.answer("❌ Товар не найден", show_alert=True)
        return
    
    text = (
        f"📦 *{escape_markdown(product['name'])}*\n"
        f"{'=' * 30}\n\n"
        f"💰 *Цена:* {format_number(product['price'])}₽\n"
        f"📊 *В наличии:* {product['stock']} шт.\n"
        f"🆔 *ID:* `{product['id']}`\n\n"
        f"Чтобы оформить заказ — нажмите «Купить» или используйте ID товара"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Купить", callback_data=f"buy_product_{product_id}")],
        [InlineKeyboardButton("◀️ К списку", callback_data=f"cat_{product.get('category_id') or 'all'}")],
        [InlineKeyboardButton("🏠 В меню", callback_data="back_to_main")]
    ])
    
    # Если есть фото — отправляем с фото
    if product.get('photo_file_id'):
        try:
            await query.message.delete()
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=product['photo_file_id'],
                caption=text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )
            return
        except Exception as e:
            logger.error(f"Ошибка отправки фото: {e}")
    
    try:
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Ошибка: {e}")


async def start_order_with_product(update: Update, context: ContextTypes.DEFAULT_TYPE, product_id: int):
    """Начать оформление заказа с выбранным товаром"""
    query = update.callback_query
    await query.answer()
    
    product = db.get_product(product_id)
    if not product or product['stock'] <= 0:
        await query.answer("❌ Товар недоступен", show_alert=True)
        return
    
    # Инициализируем заказ с выбранным товаром
    context.user_data['order'] = {}
    context.user_data['preselected_product'] = product
    
    await query.message.reply_text(
        f"📝 *ОФОРМЛЕНИЕ ЗАКАЗА*\n\n"
        f"Товар: *{escape_markdown(product['name'])}*\n"
        f"Цена: {format_number(product['price'])}₽\n\n"
        f"Шаг 1/6: Введите ваше ФИО:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=cancel_keyboard()
    )
    return ORDER_FIO


# ========== ОБРАБОТЧИК CALLBACK КАТАЛОГА ==========

async def catalog_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик всех callback-ов каталога"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = update.effective_user.id
    logger.info(f"👤 Пользователь {user_id}: catalog callback {data}")
    
    # Заглушка
    if data == "noop":
        return
    
    # --- Пагинация категорий ---
    if data.startswith("catpage_"):
        parts = data.split("_")
        page = int(parts[1])
        parent_id = int(parts[2]) if parts[2] != "0" else None
        
        if parent_id is None:
            await render_categories(update, context, page=page, parent_id=None)
        else:
            await render_subcategories(update, context, parent_id, page=page)
        return
    
    # --- Пагинация подкатегорий ---
    if data.startswith("subcatpage_"):
        parts = data.split("_")
        page = int(parts[1])
        parent_id = int(parts[2])
        await render_subcategories(update, context, parent_id, page=page)
        return
    
    # --- Клик по категории/подкатегории ---
    if data.startswith("cat_"):
        category_id = int(data.split("_")[1])
        
        # Если есть подкатегории — показываем их
        if db.has_subcategories(category_id):
            await render_subcategories(update, context, category_id, page=1)
        else:
            # Иначе показываем товары
            await render_products(update, context, category_id=category_id, page=1)
        return
    
    # --- Возврат к категориям ---
    if data == "back_to_categories":
        await render_categories(update, context, page=1, parent_id=None)
        return
    
    # --- Пагинация товаров ---
    if data.startswith("prodpage_"):
        parts = data.split("_")
        category_id = parts[1]
        page = int(parts[2])
        
        if category_id == 'all':
            await render_products(update, context, category_id='all', page=page)
        else:
            await render_products(update, context, category_id=int(category_id), page=page)
        return
    
    # --- Все товары ---
    if data.startswith("all_products_"):
        page = int(data.split("_")[2])
        await render_products(update, context, category_id='all', page=page)
        return
    
    # --- Просмотр товара ---
    if data.startswith("view_product_"):
        product_id = int(data.split("_")[2])
        await view_product_detail(update, context, product_id)
        return
    
    # --- Купить товар ---
    if data.startswith("buy_product_"):
        product_id = int(data.split("_")[2])
        return await start_order_with_product(update, context, product_id)


# ========== ПОМОЩЬ ==========

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ помощи"""
    user_id = update.effective_user.id
    logger.info(f"👤 Пользователь {user_id}: открыл помощь")
    
    manager_contact = "@helper_pods"
    
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT username FROM users 
            WHERE role = 'manager' AND username IS NOT NULL 
            LIMIT 1
        ''')
        manager = cursor.fetchone()
        conn.close()
        
        if manager and manager['username']:
            manager_contact = f"@{manager['username']}"
    except Exception as e:
        logger.error(f"Ошибка получения контакта: {e}")
    
    text = (
        "🔹 ПОМОЩЬ ПО ИСПОЛЬЗОВАНИЮ БОТА 🔹\n\n"
        "ОСНОВНЫЕ КОМАНДЫ:\n"
        "💰 Прайс-лист - каталог товаров\n"
        "📦 Оформить заказ - создание заказа\n"
        "📋 Мои заказы - история заказов\n"
        "🤝 Приведи друга - реферальная программа\n"
        "🚪 Выход - вернуться в главное меню\n\n"
        "КАК СДЕЛАТЬ ЗАКАЗ:\n"
        "1. Откройте '💰 Прайс-лист'\n"
        "2. Выберите категорию → подкатегорию\n"
        "3. Выберите товар и нажмите «Купить»\n"
        "4. Заполните данные\n"
        "5. Подтвердите заказ\n\n"
        "РЕФЕРАЛЬНАЯ ПРОГРАММА:\n"
        "• Приглашайте друзей по уникальной ссылке\n"
        "• Когда друг сделает первый заказ — вы получите бонус\n\n"
        f"СВЯЗЬ С МЕНЕДЖЕРОМ:\n{manager_contact}"
    )
    
    await update.message.reply_text(text)
    return MAIN


# ========== ОФОРМЛЕНИЕ ЗАКАЗА ==========

async def start_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало оформления заказа"""
    user_id = update.effective_user.id
    logger.info(f"👤 Пользователь {user_id}: начал оформление заказа")
    
    context.user_data['order'] = {}
    await update.message.reply_text(
        "📝 *ОФОРМЛЕНИЕ ЗАКАЗА*\n\n"
        "Шаг 1/6: Введите ваше ФИО:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=cancel_keyboard()
    )
    return ORDER_FIO


async def order_fio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение ФИО"""
    text = update.message.text
    user_id = update.effective_user.id
    
    if text in ["❌ Отмена", "🚪 Выход"]:
        return await exit_handler(update, context)
    
    context.user_data['order']['fio'] = text
    logger.info(f"👤 Пользователь {user_id}: ввел ФИО")
    
    await update.message.reply_text(
        "📞 Шаг 2/6: Введите номер телефона (например: +7 999 123-45-67):",
        reply_markup=cancel_keyboard()
    )
    return ORDER_PHONE


async def order_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение телефона"""
    text = update.message.text
    user_id = update.effective_user.id
    
    if text in ["❌ Отмена", "🚪 Выход"]:
        return await exit_handler(update, context)
    
    is_valid, phone = validate_phone(text)
    if not is_valid:
        await update.message.reply_text(
            f"❌ Ошибка\n\n{phone}\n\n"
            "✅ Примеры: +7 999 123-45-67, 89991234567",
            reply_markup=cancel_keyboard()
        )
        return ORDER_PHONE
    
    context.user_data['order']['phone'] = phone
    
    # Если товар уже выбран из каталога — пропускаем шаг выбора
    if context.user_data.get('preselected_product'):
        product = context.user_data['preselected_product']
        context.user_data['order']['product_id'] = product['id']
        context.user_data['order']['product_name'] = product['name']
        context.user_data['order']['product_price'] = product['price']
        context.user_data['order']['max_stock'] = product['stock']
        
        await update.message.reply_text(
            f"🔢 Шаг 4/6: Введите количество (до {product['stock']} шт.):",
            reply_markup=cancel_keyboard()
        )
        return ORDER_QUANTITY
    
    # Иначе показываем список товаров
    products = db.get_products(only_in_stock=True)
    if not products:
        await update.message.reply_text("😕 Товаров нет", reply_markup=user_main_keyboard())
        return MAIN
    
    text = "🛒 Шаг 3/6: Введите ID товара:\n\n"
    for p in products[:15]:
        text += f"`{p['id']}` — {escape_markdown(p['name'])} — {format_number(p['price'])}₽\n"
    
    context.user_data['available_products'] = products
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=cancel_keyboard())
    return ORDER_PRODUCT


async def order_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор товара по ID"""
    text = update.message.text
    user_id = update.effective_user.id
    
    if text in ["❌ Отмена", "🚪 Выход"]:
        return await exit_handler(update, context)
    
    try:
        product_id = int(text)
        products = context.user_data.get('available_products', [])
        selected = next((p for p in products if p['id'] == product_id), None)
        
        if not selected:
            await update.message.reply_text("❌ Товар не найден, попробуйте снова")
            return ORDER_PRODUCT
        
        context.user_data['order']['product_id'] = product_id
        context.user_data['order']['product_name'] = selected['name']
        context.user_data['order']['product_price'] = selected['price']
        context.user_data['order']['max_stock'] = selected['stock']
        
        await update.message.reply_text(
            f"🔢 Шаг 4/6: Введите количество (до {selected['stock']} шт.):",
            reply_markup=cancel_keyboard()
        )
        return ORDER_QUANTITY
        
    except ValueError:
        await update.message.reply_text("❌ Введите число")
        return ORDER_PRODUCT


async def order_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение количества"""
    text = update.message.text
    user_id = update.effective_user.id
    
    if text in ["❌ Отмена", "🚪 Выход"]:
        return await exit_handler(update, context)
    
    try:
        qty = int(text)
        max_stock = context.user_data['order']['max_stock']
        
        if qty <= 0 or qty > max_stock:
            await update.message.reply_text(f"❌ Введите число от 1 до {max_stock}")
            return ORDER_QUANTITY
        
        context.user_data['order']['quantity'] = qty
        
        await update.message.reply_text(
            "📍 Шаг 5/6: Введите адрес доставки:",
            reply_markup=cancel_keyboard()
        )
        return ORDER_ADDRESS
        
    except ValueError:
        await update.message.reply_text("❌ Введите число")
        return ORDER_QUANTITY


async def order_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение адреса"""
    text = update.message.text
    
    if text in ["❌ Отмена", "🚪 Выход"]:
        return await exit_handler(update, context)
    
    context.user_data['order']['address'] = text
    
    await update.message.reply_text(
        "💬 Шаг 6/6: Комментарий (или отправьте '-' если нет):",
        reply_markup=cancel_keyboard()
    )
    return ORDER_COMMENT


async def order_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение комментария и подтверждение"""
    text = update.message.text
    user_id = update.effective_user.id
    
    if text in ["❌ Отмена", "🚪 Выход"]:
        return await exit_handler(update, context)
    
    order = context.user_data['order']
    order['comment'] = "" if text == "-" else text
    
    total = order['product_price'] * order['quantity']
    
    confirm_text = (
        "📋 *ПРОВЕРЬТЕ ЗАКАЗ*\n\n"
        f"👤 ФИО: {escape_markdown(order['fio'])}\n"
        f"📞 Телефон: {order['phone']}\n"
        f"🛒 Товар: {escape_markdown(order['product_name'])}\n"
        f"🔢 Количество: {order['quantity']}\n"
        f"💰 Сумма: {format_number(total)}₽\n"
        f"📍 Адрес: {escape_markdown(order['address'])}\n"
        f"💬 Комментарий: {escape_markdown(order['comment']) or '—'}\n\n"
        "✅ Подтверждаете заказ?"
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ Да, подтвердить", callback_data="confirm_order")],
        [InlineKeyboardButton("❌ Отменить", callback_data="cancel_order")]
    ]
    
    await update.message.reply_text(
        confirm_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ORDER_CONFIRM


async def confirm_order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение заказа"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    if query.data == "cancel_order":
        await query.edit_message_text("❌ Заказ отменен")
        await query.message.reply_text("Главное меню", reply_markup=user_main_keyboard())
        context.user_data.clear()
        return MAIN
    
    order = context.user_data.get('order', {})
    if not order:
        await query.edit_message_text("❌ Ошибка")
        return MAIN
    
    user = update.effective_user
    items = [{
        'product_id': order['product_id'],
        'name': order['product_name'],
        'price': order['product_price'],
        'quantity': order['quantity']
    }]
    total = order['product_price'] * order['quantity']
    
    order_id = db.create_order(
        user.id, order['fio'], order['phone'], user.username,
        items, total, order['address'], order.get('comment', '')
    )
    
    logger.info(f"✅ Пользователь {user_id} оформил заказ №{order_id}")
    
    await query.edit_message_text(
        f"✅ *ЗАКАЗ №{order_id} ПОДТВЕРЖДЕН!*\n\n"
        f"Спасибо за покупку!\n"
        f"Менеджер свяжется с вами в ближайшее время.",
        parse_mode=ParseMode.MARKDOWN
    )
    
    await notify_admins(update, context, order_id, order, user, total)
    
    await query.message.reply_text("Главное меню", reply_markup=user_main_keyboard())
    context.user_data.clear()
    return MAIN


# ========== МОИ ЗАКАЗЫ ==========

async def show_my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ заказов пользователя"""
    user_id = update.effective_user.id
    orders = db.get_orders(user_id=user_id)
    
    if not orders:
        await update.message.reply_text("📭 У вас пока нет заказов")
        return MAIN
    
    text = "📋 *МОИ ЗАКАЗЫ*\n\n"
    for o in orders[:5]:
        items = json.loads(o['items'])
        items_text = ", ".join([f"{i['name']} x{i['quantity']}" for i in items])
        status = ORDER_STATUSES.get(o['status'], o['status'])
        
        text += f"🔹 *Заказ №{o['order_id']}*\n"
        text += f"📅 {o['created_at'][:10]}\n"
        text += f"🛒 {items_text}\n"
        text += f"💰 {format_number(o['total_amount'])}₽\n"
        text += f"📊 Статус: {status}\n\n"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    return MAIN


# ========== РЕФЕРАЛЬНАЯ ПРОГРАММА ==========

async def show_referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ реферальной программы"""
    user_id = update.effective_user.id
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT referral_code, referral_count FROM users WHERE user_id = ?", (user_id,))
    user_data = cursor.fetchone()
    
    cursor.execute('''
        SELECT referral_name, referral_username, order_made, registered_at
        FROM referrals WHERE referrer_id = ?
        ORDER BY registered_at DESC
    ''', (user_id,))
    referrals = cursor.fetchall()
    conn.close()
    
    if not user_data:
        await update.message.reply_text("❌ Ошибка")
        return MAIN
    
    referral_code = user_data['referral_code']
    count = user_data['referral_count'] or 0
    
    bot = await context.bot.get_me()
    link = f"https://t.me/{bot.username}?start={referral_code}"
    
    text = (
        "🤝 *РЕФЕРАЛЬНАЯ ПРОГРАММА*\n\n"
        f"🔗 *Ваша уникальная ссылка:*\n`{link}`\n\n"
        f"📊 *Ваша статистика:*\n"
        f"• Приглашено друзей: {count}\n\n"
        f"🎁 *Как это работает:*\n"
        f"1️⃣ Отправьте ссылку другу\n"
        f"2️⃣ Друг регистрируется в боте\n"
        f"3️⃣ Когда друг сделает первый заказ — вы получите бонус\n"
        f"4️⃣ Размер бонуса уточняйте у менеджера\n\n"
    )
    
    if referrals:
        text += "👥 *Приглашенные друзья:*\n"
        for ref in referrals[:5]:
            name = ref['referral_name'] or ref['referral_username'] or "Пользователь"
            username = f" (@{ref['referral_username']})" if ref['referral_username'] else ""
            status = "✅ Сделал заказ" if ref['order_made'] else "⏳ Ожидает"
            date = ref['registered_at'][:10] if ref['registered_at'] else ""
            text += f"• {escape_markdown(name)}{username} — {status} ({date})\n"
    else:
        text += "👥 У вас пока нет приглашенных друзей"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    return MAIN


# ========== УВЕДОМЛЕНИЯ ==========

async def notify_admins(update, context, order_id, order, user, total):
    """Уведомление админов о новом заказе"""
    username = f" (@{user.username})" if user.username else ""
    msg = (
        f"🆕 *НОВЫЙ ЗАКАЗ!*\n\n"
        f"📦 №: {order_id}\n"
        f"👤 Клиент: {escape_markdown(order['fio'])}{escape_markdown(username)}\n"
        f"📞 Телефон: {order['phone']}\n"
        f"🛒 Товар: {escape_markdown(order['product_name'])} x{order['quantity']}\n"
        f"💰 Сумма: {format_number(total)}₽\n"
        f"📍 Адрес: {escape_markdown(order['address'])}\n"
        f"💬 Комментарий: {escape_markdown(order.get('comment', '')) or '—'}"
    )
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE role IN ('superadmin', 'manager')")
    admins = cursor.fetchall()
    conn.close()
    
    for admin in admins:
        try:
            await context.bot.send_message(admin['user_id'], msg, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.error(f"❌ Не удалось уведомить {admin['user_id']}: {e}")