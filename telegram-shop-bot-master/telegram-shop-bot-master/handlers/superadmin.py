# handlers/superadmin.py
import logging
import json
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import Database
from google_sheets import GoogleSheets
from keyboards import *
from states import *
from config import ORDER_STATUSES, SUPER_ADMIN_IDS, SPREADSHEET_ID
from handlers.back_handlers import back_to_superadmin
from handlers.common import exit_handler

logger = logging.getLogger(__name__)
db = Database()
gs = GoogleSheets() if SPREADSHEET_ID else None

# ========== ОСНОВНОЙ ОБРАБОТЧИК ==========

async def superadmin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик для суперадмина"""
    text = update.message.text
    user_id = update.effective_user.id
    
    logger.info(f"👑 Суперадмин {user_id}: {text}")
    
    if text == "💰 Управление прайсом":
        await update.message.reply_text(
            "⚙️ УПРАВЛЕНИЕ ПРАЙСОМ\n\nВыберите действие:",
            reply_markup=price_menu_keyboard()
        )
        return PRICE_MENU
    
    elif text == "📋 Заказы":
        await update.message.reply_text(
            "📋 УПРАВЛЕНИЕ ЗАКАЗАМИ\n\nВыберите период:",
            reply_markup=orders_menu_keyboard()
        )
        return ORDERS_MENU
    
    elif text == "👥 Связь с клиентами":
        await update.message.reply_text(
            "👥 ПОИСК КЛИЕНТА\n\n"
            "Введите номер заказа, телефон или ФИО клиента:",
            reply_markup=cancel_keyboard()
        )
        return SEARCH_CLIENT
    
    elif text == "📊 Статистика":
        return await show_stats(update, context)
    
    elif text == "📢 Рассылка":
        await update.message.reply_text(
            "📢 РАССЫЛКА\n\n"
            "Введите текст для рассылки:",
            reply_markup=cancel_keyboard()
        )
        return BROADCAST_TEXT
    
    elif text == "📤 Экспорт в Google Sheets":
        return await export_to_google(update, context)
    
    elif text == "📥 Импорт товаров":
        return await import_from_google(update, context)
    
    elif text == "👥 Управление менеджерами":
        return await show_managers_menu(update, context)
    
    elif text == "🚪 Выход":
        return await exit_handler(update, context)
    
    return SUPERADMIN

# ========== GOOGLE SHEETS ==========

async def export_to_google(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Экспорт товаров и заказов в Google Sheets"""
    user_id = update.effective_user.id
    logger.info(f"👑 Суперадмин {user_id}: экспорт в Google Sheets")
    
    if not gs:
        await update.message.reply_text(
            "❌ Google Sheets не настроен\n\n"
            "Проверьте SPREADSHEET_ID в файле .env"
        )
        return SUPERADMIN
    
    msg = await update.message.reply_text("📤 Экспортирую данные в Google Sheets...")
    
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        results = []
        
        # Экспорт товаров
        cursor.execute('''
            SELECT id, name, category, price, stock, 
                   COALESCE(photo_file_id, '') as photo, created_at 
            FROM products ORDER BY id
        ''')
        products = cursor.fetchall()
        
        if products:
            success, prod_msg = gs.export_products(products)
            results.append(prod_msg)
        else:
            results.append("⚠️ Нет товаров для экспорта")
        
        # Экспорт заказов
        cursor.execute('''
            SELECT order_id, user_name, user_phone, 
                   COALESCE(username, '') as username,
                   items, total_amount, delivery_address, status, created_at
            FROM orders ORDER BY created_at DESC
        ''')
        orders = cursor.fetchall()
        
        if orders:
            success, order_msg = gs.export_orders(orders)
            results.append(order_msg)
        else:
            results.append("⚠️ Нет заказов для экспорта")
        
        conn.close()
        
        await msg.edit_text(
            "✅ ЭКСПОРТ ЗАВЕРШЕН\n\n" + "\n".join(results)
        )
        
    except Exception as e:
        logger.error(f"❌ Ошибка экспорта: {e}")
        await msg.edit_text(f"❌ Ошибка экспорта: {str(e)[:200]}")
    
    await asyncio.sleep(2)
    return SUPERADMIN

async def import_from_google(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Импорт товаров из Google Sheets"""
    user_id = update.effective_user.id
    logger.info(f"👑 Суперадмин {user_id}: импорт из Google Sheets")
    
    if not gs:
        await update.message.reply_text(
            "❌ Google Sheets не настроен\n\n"
            "Проверьте SPREADSHEET_ID в файле .env"
        )
        return SUPERADMIN
    
    await update.message.reply_text(
        "📥 ИМПОРТ ТОВАРОВ\n\n"
        "Сейчас будут импортированы товары из Google Sheets.\n"
        "Товары с такими же названиями будут пропущены.\n\n"
        "Продолжить?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Да, импортировать", callback_data="import_confirm")],
            [InlineKeyboardButton("❌ Отмена", callback_data="import_cancel")]
        ])
    )
    return IMPORT_PRODUCTS

async def import_products_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение импорта товаров"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    logger.info(f"👑 Суперадмин {user_id}: подтверждение импорта: {query.data}")
    
    if query.data == "import_cancel":
        await query.edit_message_text("❌ Импорт отменен")
        return SUPERADMIN
    
    await query.edit_message_text("📥 Импортирую товары из Google Sheets...")
    
    products, errors = gs.import_products()
    
    if not products:
        error_text = "\n".join(errors[:5]) if errors else "Неизвестная ошибка"
        await query.edit_message_text(f"❌ Не удалось импортировать товары:\n{error_text}")
        return SUPERADMIN
    
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        added = 0
        skipped = 0
        admin_id = user_id
        
        for p in products:
            cursor.execute('SELECT id FROM products WHERE name = ?', (p['name'],))
            existing = cursor.fetchone()
            
            if not existing:
                cursor.execute('''
                    INSERT INTO products 
                    (name, category, price, stock, photo_file_id, in_stock, created_at, created_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    p['name'], p['category'], p['price'], p['stock'], 
                    None,
                    1 if p['stock'] > 0 else 0,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    admin_id
                ))
                added += 1
            else:
                skipped += 1
        
        conn.commit()
        conn.close()
        
        result_text = f"✅ ИМПОРТ ЗАВЕРШЕН\n\n"
        result_text += f"📦 Добавлено новых товаров: {added}\n"
        result_text += f"⚠️ Пропущено (уже есть): {skipped}\n"
        
        if errors:
            result_text += f"\n❌ Ошибок при импорте: {len(errors)}\n"
            result_text += f"Первые ошибки:\n" + "\n".join(errors[:3])
        
        if added > 0:
            result_text += f"\n\n📸 Важно: Фото нужно добавить вручную через редактирование товара."
        
        await query.edit_message_text(result_text)
        
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения товаров: {e}")
        await query.edit_message_text(f"❌ Ошибка сохранения: {str(e)[:200]}")
    
    await asyncio.sleep(2)
    return SUPERADMIN

# ========== СТАТИСТИКА ==========

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ статистики"""
    user_id = update.effective_user.id
    logger.info(f"👑 Суперадмин {user_id}: просмотр статистики")
    
    try:
        stats = db.get_stats()
        
        text = (
            "👑 СТАТИСТИКА СУПЕРАДМИНИСТРАТОРА\n"
            f"{'=' * 40}\n\n"
            f"📦 ТОВАРЫ\n"
            f"  • Всего товаров: {stats['total_products']}\n"
            f"  • В наличии: {stats['in_stock']}\n"
            f"  • Общий склад: {stats['total_stock']} шт.\n\n"
            f"👥 ПОЛЬЗОВАТЕЛИ\n"
            f"  • Всего: {stats['total_users']}\n"
            f"  • Менеджеров: {stats['total_managers']}\n"
            f"  • По рефералкам: {stats['referred_users']}\n\n"
            f"📋 ЗАКАЗЫ\n"
            f"  • Всего: {stats['total_orders']}\n"
            f"  • Сегодня: {stats['orders_today']}\n"
            f"  • Средний чек: {stats['avg_order']:.0f}₽\n"
            f"  • Выручка всего: {stats['total_revenue']:.0f}₽\n"
            f"  • Выручка сегодня: {stats['revenue_today']:.0f}₽\n\n"
            f"🎁 РЕФЕРАЛЫ\n"
            f"  • Рефералов с заказами: {stats['referrals_with_orders']}\n"
        )
        
        if stats['top_referrers']:
            text += "\n🏆 ТОП ПРИГЛАШАЮЩИХ:\n"
            for i, ref in enumerate(stats['top_referrers'], 1):
                name = ref['first_name'] or ref['username'] or "Пользователь"
                username = f" (@{ref['username']})" if ref['username'] else ""
                text += f"  {i}. {name}{username} — {ref['ref_count']} пригл. ({ref['orders_made']} заказов)\n"
        
        await update.message.reply_text(text)
        
    except Exception as e:
        logger.error(f"❌ Ошибка статистики: {e}")
        await update.message.reply_text(f"❌ Ошибка загрузки статистики: {str(e)[:100]}")
    
    return SUPERADMIN

# ========== УПРАВЛЕНИЕ МЕНЕДЖЕРАМИ ==========

async def show_managers_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню управления менеджерами"""
    logger.info(f"👑 Суперадмин {update.effective_user.id}: открыл меню управления менеджерами")
    
    await update.message.reply_text(
        "👥 УПРАВЛЕНИЕ МЕНЕДЖЕРАМИ\n\nВыберите действие:",
        reply_markup=managers_menu_keyboard()
    )
    return VIEW_MANAGERS

async def managers_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка меню менеджеров"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    logger.info(f"👑 Суперадмин {user_id}: нажал {query.data}")
    
    if query.data == "manager_add":
        await query.edit_message_text(
            "➕ ДОБАВЛЕНИЕ МЕНЕДЖЕРА\n\n"
            "Введите Telegram ID пользователя, которого хотите сделать менеджером:\n\n"
            "🔍 Как узнать ID:\n"
            "1. Попросите пользователя написать боту @userinfobot\n"
            "2. Он пришлет свой ID\n"
            "3. Вставьте его сюда"
        )
        return ADD_MANAGER_ID
    
    elif query.data == "manager_remove":
        return await show_managers_for_remove(update, context)
    
    elif query.data == "manager_list":
        return await show_managers_list(update, context)
    
    elif query.data == "manager_back":
        return await back_to_superadmin(update, context)

async def show_managers_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список всех менеджеров"""
    query = update.callback_query
    
    managers = db.get_managers()
    
    # Получаем суперадминов
    superadmins = []
    for admin_id in SUPER_ADMIN_IDS:
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT first_name, username FROM users WHERE user_id = ?", (admin_id,))
        admin = cursor.fetchone()
        conn.close()
        if admin:
            superadmins.append({'id': admin_id, 'name': admin['first_name'], 'username': admin['username']})
    
    text = "👥 УПРАВЛЕНИЕ ПЕРСОНАЛОМ\n"
    text += "=" * 30 + "\n\n"
    
    # Суперадмины
    text += "👑 СУПЕРАДМИНИСТРАТОРЫ:\n"
    if superadmins:
        for sa in superadmins:
            name = sa['name'] or f"ID: {sa['id']}"
            username = f" (@{sa['username']})" if sa['username'] else ""
            text += f"  • {name}{username}\n"
    else:
        text += "  • Нет данных\n"
    text += "\n"
    
    # Активные менеджеры
    text += "✅ АКТИВНЫЕ МЕНЕДЖЕРЫ:\n"
    if managers:
        for m in managers:
            name = m['first_name'] or m['username'] or f"ID: {m['user_id']}"
            username = f" (@{m['username']})" if m['username'] else ""
            added = m['added_date'][:10] if m['added_date'] else "?"
            text += f"  • {name}{username} (с {added})\n"
    else:
        text += "  • Нет активных менеджеров\n"
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ Назад", callback_data="manager_back")
        ]])
    )
    return VIEW_MANAGERS

async def show_managers_for_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список менеджеров для удаления"""
    query = update.callback_query
    
    managers = db.get_managers()
    
    if not managers:
        await query.edit_message_text(
            "📭 Нет менеджеров для удаления",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="manager_back")
            ]])
        )
        return VIEW_MANAGERS
    
    text = "🗑 ВЫБЕРИТЕ МЕНЕДЖЕРА ДЛЯ УДАЛЕНИЯ\n\n"
    keyboard = []
    
    for m in managers:
        name = m['first_name'] or m['username'] or f"ID: {m['user_id']}"
        username = f" (@{m['username']})" if m['username'] else ""
        added_date = m['added_date'][:10] if m['added_date'] else "?"
        text += f"  • {name}{username} (добавлен: {added_date})\n"
        
        keyboard.append([InlineKeyboardButton(
            f"❌ Удалить {name[:30]}",
            callback_data=f"remove_manager_{m['user_id']}"
        )])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="manager_back")])
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return REMOVE_MANAGER_ID

async def remove_manager(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаление менеджера"""
    query = update.callback_query
    await query.answer()
    
    manager_id = int(query.data.split('_')[2])
    superadmin_id = update.effective_user.id
    
    logger.info(f"👑 Суперадмин {superadmin_id} удаляет менеджера {manager_id}")
    
    # Получаем информацию о менеджере
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT first_name, username FROM users WHERE user_id = ?", (manager_id,))
    manager = cursor.fetchone()
    conn.close()
    
    db.remove_manager(manager_id)
    
    name = manager['first_name'] if manager else f"ID: {manager_id}"
    username = f" (@{manager['username']})" if manager and manager['username'] else ""
    
    await query.edit_message_text(
        f"✅ МЕНЕДЖЕР УДАЛЕН!\n\n"
        f"👤 Пользователь: {name}{username}\n"
        f"🆔 ID: {manager_id}"
    )
    
    # Уведомляем бывшего менеджера
    try:
        await context.bot.send_message(
            manager_id,
            f"📨 Уведомление\n\n"
            f"Ваши права менеджера были отозваны."
        )
        logger.info(f"✅ Уведомление отправлено бывшему менеджеру {manager_id}")
    except Exception as e:
        logger.error(f"❌ Не удалось уведомить бывшего менеджера: {e}")
    
    await asyncio.sleep(2)
    return await show_managers_menu(update, context)

async def add_manager_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавление менеджера по ID"""
    text = update.message.text
    user_id = update.effective_user.id
    
    if text in ["❌ Отмена", "🚪 Выход"]:
        return await exit_handler(update, context)
    
    logger.info(f"👑 Суперадмин {user_id}: добавляет менеджера с ID {text}")
    
    try:
        manager_id = int(text.strip())
        
        # Проверка на суперадмина
        if manager_id in SUPER_ADMIN_IDS:
            await update.message.reply_text(
                "❌ Ошибка!\n\n"
                "Этот пользователь является суперадмином!\n"
                "Нельзя изменить роль суперадмина.",
                reply_markup=superadmin_main_keyboard()
            )
            return SUPERADMIN
        
        # Проверяем существование пользователя
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, first_name, username, role FROM users WHERE user_id = ?", (manager_id,))
        user = cursor.fetchone()
        
        if user and user['role'] == 'manager':
            await update.message.reply_text(
                f"❌ Ошибка!\n\n"
                f"Пользователь {user['first_name'] or manager_id} уже является менеджером!",
                reply_markup=superadmin_main_keyboard()
            )
            conn.close()
            return SUPERADMIN
        
        # Добавляем менеджера
        db.add_manager(manager_id, user_id)
        
        # Получаем имя пользователя
        if user:
            user_name = user['first_name'] or user['username'] or str(manager_id)
        else:
            user_name = str(manager_id)
        
        await update.message.reply_text(
            f"✅ МЕНЕДЖЕР УСПЕШНО ДОБАВЛЕН!\n\n"
            f"👤 Пользователь: {user_name}\n"
            f"🆔 ID: {manager_id}",
            reply_markup=superadmin_main_keyboard()
        )
        
        # Уведомляем нового менеджера
        try:
            await context.bot.send_message(
                manager_id,
                f"👔 ПОЗДРАВЛЯЕМ!\n\n"
                f"Вам назначена роль МЕНЕДЖЕРА в боте-магазине.\n"
                f"Теперь у вас есть доступ к админ-панели.\n\n"
                f"Напишите /start чтобы начать работу."
            )
            logger.info(f"✅ Уведомление отправлено менеджеру {manager_id}")
        except Exception as e:
            logger.error(f"❌ Не удалось уведомить менеджера {manager_id}: {e}")
            await update.message.reply_text(
                f"⚠️ Менеджер добавлен, но не удалось его уведомить.\n"
                f"Возможно, он не начинал диалог с ботом.",
                reply_markup=superadmin_main_keyboard()
            )
        
        conn.close()
        
    except ValueError:
        await update.message.reply_text(
            "❌ Ошибка!\n\n"
            "Введите корректный числовой ID!\n\n"
            "Пример: 123456789",
            reply_markup=superadmin_main_keyboard()
        )
    
    return SUPERADMIN

# ========== УПРАВЛЕНИЕ ПРАЙСОМ ==========

async def price_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка меню прайса"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    logger.info(f"👑 Суперадмин {user_id}: нажал {query.data}")
    
    if query.data == "price_add":
        await query.edit_message_text(
            "➕ ДОБАВЛЕНИЕ ТОВАРА\n\nШаг 1/5: Введите название товара:"
        )
        return ADD_PRODUCT_NAME
    elif query.data == "price_edit":
        return await show_products_for_edit(update, context)
    elif query.data == "price_delete":
        return await show_products_for_delete(update, context)
    elif query.data == "price_toggle":
        return await show_products_for_toggle(update, context)
    elif query.data == "price_export":
        return await export_to_google(update, context)
    elif query.data == "price_back":
        return await back_to_superadmin(update, context)

async def show_products_for_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать товары для редактирования"""
    query = update.callback_query
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, price, category, stock FROM products ORDER BY id")
    products = cursor.fetchall()
    conn.close()
    
    if not products:
        await query.edit_message_text(
            "📭 Товаров нет",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="price_back")
            ]])
        )
        return PRICE_MENU
    
    text = "✏️ ВЫБЕРИТЕ ТОВАР ДЛЯ РЕДАКТИРОВАНИЯ\n\n"
    keyboard = []
    
    for p in products:
        text += f"ID {p['id']}: {p['name']} - {p['price']}₽ [{p['category']}]\n"
        keyboard.append([InlineKeyboardButton(
            f"✏️ {p['name'][:30]}", 
            callback_data=f"edit_select_{p['id']}"
        )])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="price_back")])
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return EDIT_PRODUCT_SELECT

async def edit_product_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор товара для редактирования"""
    query = update.callback_query
    await query.answer()
    
    product_id = int(query.data.split('_')[2])
    context.user_data['edit_product_id'] = product_id
    
    product = db.get_product(product_id)
    
    if not product:
        await query.edit_message_text(
            "❌ Товар не найден",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="price_edit")
            ]])
        )
        return PRICE_MENU
    
    photo_status = "✅ есть" if product['photo_file_id'] else "❌ нет"
    
    text = (
        f"✏️ РЕДАКТИРОВАНИЕ ТОВАРА\n\n"
        f"Текущие данные:\n"
        f"📦 Название: {product['name']}\n"
        f"💰 Цена: {product['price']}₽\n"
        f"📂 Категория: {product['category']}\n"
        f"📊 В наличии: {product['stock']} шт.\n"
        f"📸 Фото: {photo_status}\n\n"
        f"Что хотите изменить?"
    )
    
    keyboard = [
        [InlineKeyboardButton("📦 Название", callback_data="edit_field_name")],
        [InlineKeyboardButton("💰 Цену", callback_data="edit_field_price")],
        [InlineKeyboardButton("📂 Категорию", callback_data="edit_field_category")],
        [InlineKeyboardButton("📊 Наличие", callback_data="edit_field_stock")],
        [InlineKeyboardButton("📸 Фото", callback_data="edit_field_photo")],
        [InlineKeyboardButton("◀️ Назад", callback_data="price_edit")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    return EDIT_PRODUCT_FIELD

async def edit_product_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор поля для редактирования"""
    query = update.callback_query
    await query.answer()
    
    field = query.data.split('_')[2]
    context.user_data['edit_field'] = field
    
    if field == 'photo':
        await query.edit_message_text(
            "📸 Отправьте новое фото товара (или '-' чтобы оставить текущее):"
        )
    else:
        field_names = {
            'name': 'новое название',
            'price': 'новую цену (только цифры)',
            'category': 'новую категорию',
            'stock': 'новое количество'
        }
        await query.edit_message_text(
            f"✏️ Введите {field_names.get(field, 'новое значение')}:"
        )
    
    return EDIT_PRODUCT_VALUE

async def edit_product_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ввод нового значения и сохранение"""
    text = update.message.text
    field = context.user_data.get('edit_field')
    user_id = update.effective_user.id
    
    if text in ["❌ Отмена", "🚪 Выход"]:
        return await exit_handler(update, context)
    
    product_id = context.user_data.get('edit_product_id')
    
    if not product_id or not field:
        await update.message.reply_text("❌ Ошибка")
        return SUPERADMIN
    
    try:
        if field == 'photo':
            if update.message.photo:
                photo = update.message.photo[-1]
                value = photo.file_id
            elif text == '-':
                product = db.get_product(product_id)
                value = product['photo_file_id']
            else:
                await update.message.reply_text("❌ Отправьте фото или '-'")
                return EDIT_PRODUCT_VALUE
            
            db.update_product(product_id, photo_file_id=value)
            await update.message.reply_text("✅ Фото обновлено!")
            
        elif field == 'price':
            try:
                value = float(text)
                db.update_product(product_id, price=value)
                await update.message.reply_text("✅ Цена обновлена!")
            except:
                await update.message.reply_text("❌ Введите число!")
                return EDIT_PRODUCT_VALUE
                
        elif field == 'stock':
            try:
                value = int(text)
                in_stock = 1 if value > 0 else 0
                db.update_product(product_id, stock=value, in_stock=in_stock)
                await update.message.reply_text("✅ Количество обновлено!")
            except:
                await update.message.reply_text("❌ Введите число!")
                return EDIT_PRODUCT_VALUE
                
        else:
            db.update_product(product_id, **{field: text})
            await update.message.reply_text(f"✅ {field} обновлено!")
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")
    
    context.user_data.pop('edit_product_id', None)
    context.user_data.pop('edit_field', None)
    
    return await back_to_superadmin(update, context)

async def show_products_for_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать товары для удаления"""
    query = update.callback_query
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM products ORDER BY id")
    products = cursor.fetchall()
    conn.close()
    
    if not products:
        await query.edit_message_text(
            "📭 Товаров нет",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="price_back")
            ]])
        )
        return PRICE_MENU
    
    text = "🗑 ВЫБЕРИТЕ ТОВАР ДЛЯ УДАЛЕНИЯ\n\n"
    keyboard = []
    
    for p in products:
        text += f"ID {p['id']}: {p['name']}\n"
        keyboard.append([InlineKeyboardButton(
            f"🗑 {p['name'][:30]}", 
            callback_data=f"delete_{p['id']}"
        )])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="price_back")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    return DELETE_PRODUCT_SELECT

async def delete_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаление товара"""
    query = update.callback_query
    await query.answer()
    
    product_id = int(query.data.split('_')[1])
    
    try:
        db.delete_product(product_id)
        await query.edit_message_text("✅ Товар удален!")
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка: {str(e)[:100]}")
    
    return await back_to_superadmin(update, context)

async def show_products_for_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать товары для изменения статуса наличия"""
    query = update.callback_query
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, stock, in_stock FROM products ORDER BY id")
    products = cursor.fetchall()
    conn.close()
    
    if not products:
        await query.edit_message_text(
            "📭 Товаров нет",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="price_back")
            ]])
        )
        return PRICE_MENU
    
    text = "📊 СТАТУС НАЛИЧИЯ\n\n"
    keyboard = []
    
    for p in products:
        status = "✅ В наличии" if p['in_stock'] else "❌ Нет в наличии"
        text += f"ID {p['id']}: {p['name']} - {status} (склад: {p['stock']} шт.)\n"
        keyboard.append([InlineKeyboardButton(
            f"{'✅' if p['in_stock'] else '❌'} {p['name'][:30]}",
            callback_data=f"toggle_{p['id']}"
        )])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="price_back")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    return TOGGLE_STOCK_SELECT

async def toggle_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Изменение статуса наличия"""
    query = update.callback_query
    await query.answer()
    
    product_id = int(query.data.split('_')[1])
    
    try:
        new_status = db.toggle_stock(product_id)
        status_text = "✅ В наличии" if new_status else "❌ Нет в наличии"
        await query.edit_message_text(f"Статус изменен на: {status_text}")
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка: {str(e)[:100]}")
    
    return await back_to_superadmin(update, context)

# ========== ДОБАВЛЕНИЕ ТОВАРА ==========

async def add_product_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ввод названия товара"""
    text = update.message.text
    if text in ["❌ Отмена", "🚪 Выход"]:
        return await exit_handler(update, context)
    
    context.user_data['new_product'] = {'name': text}
    await update.message.reply_text(
        "✅ Название сохранено!\n\nШаг 2/5: Введите категорию (или '-' для 'Общее'):",
        reply_markup=cancel_keyboard()
    )
    return ADD_PRODUCT_CATEGORY

async def add_product_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ввод категории"""
    text = update.message.text
    if text in ["❌ Отмена", "🚪 Выход"]:
        return await exit_handler(update, context)
    
    category = text if text != "-" else "Общее"
    context.user_data['new_product']['category'] = category
    
    await update.message.reply_text(
        "✅ Категория сохранена!\n\nШаг 3/5: Введите цену (только цифры):",
        reply_markup=cancel_keyboard()
    )
    return ADD_PRODUCT_PRICE

async def add_product_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ввод цены"""
    text = update.message.text
    if text in ["❌ Отмена", "🚪 Выход"]:
        return await exit_handler(update, context)
    
    try:
        price = float(text)
        context.user_data['new_product']['price'] = price
    except:
        await update.message.reply_text("❌ Введите число!")
        return ADD_PRODUCT_PRICE
    
    await update.message.reply_text(
        "✅ Цена сохранена!\n\nШаг 4/5: Введите количество (или 0):",
        reply_markup=cancel_keyboard()
    )
    return ADD_PRODUCT_STOCK

async def add_product_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ввод количества"""
    text = update.message.text
    if text in ["❌ Отмена", "🚪 Выход"]:
        return await exit_handler(update, context)
    
    try:
        stock = int(text) if text else 0
        context.user_data['new_product']['stock'] = stock
    except:
        await update.message.reply_text("❌ Введите число!")
        return ADD_PRODUCT_STOCK
    
    await update.message.reply_text(
        "✅ Количество сохранено!\n\n"
        "Шаг 5/5: Отправьте *фото товара* (или '-' чтобы пропустить):",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=cancel_keyboard()
    )
    return ADD_PRODUCT_PHOTO

async def add_product_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение фото товара и сохранение"""
    text = update.message.text
    photo_id = None
    user_id = update.effective_user.id
    
    if text in ["❌ Отмена", "🚪 Выход"]:
        return await exit_handler(update, context)
    
    if update.message.photo:
        photo = update.message.photo[-1]
        photo_id = photo.file_id
        await update.message.reply_text("✅ Фото получено!")
    elif text == "-":
        await update.message.reply_text("✅ Фото пропущено")
    else:
        await update.message.reply_text("❌ Отправьте фото или '-'")
        return ADD_PRODUCT_PHOTO
    
    product = context.user_data['new_product']
    
    try:
        db.add_product(
            product['name'], 
            product['category'], 
            product['price'], 
            product['stock'], 
            photo_id,
            user_id
        )
        
        response = f"✅ ТОВАР ДОБАВЛЕН!\n\n"
        response += f"📦 Название: {product['name']}\n"
        response += f"📂 Категория: {product['category']}\n"
        response += f"💰 Цена: {product['price']}₽\n"
        response += f"📊 В наличии: {product['stock']} шт.\n"
        response += f"📸 Фото: {'✅' if photo_id else '❌'}"
        
        await update.message.reply_text(response)
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")
    
    context.user_data.pop('new_product', None)
    return await back_to_superadmin(update, context)

# ========== УПРАВЛЕНИЕ ЗАКАЗАМИ ==========

async def orders_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка меню заказов"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    logger.info(f"👑 Суперадмин {user_id}: нажал {query.data}")
    
    if query.data == "orders_today":
        return await show_orders_today(update, context)
    elif query.data == "orders_month":
        return await show_orders_month(update, context)
    elif query.data == "orders_period":
        await query.edit_message_text(
            "📅 Введите начальную дату (ДД.ММ.ГГГГ):",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="orders_back")
            ]])
        )
        return PERIOD_START
    elif query.data == "orders_export":
        return await export_to_google(update, context)
    elif query.data == "orders_back":
        return await back_to_superadmin(update, context)
    elif query.data.startswith("view_order_"):
        return await show_order_details(update, context)
    elif query.data.startswith("change_status_"):
        return await change_status_menu(update, context)
    elif query.data.startswith("set_status_"):
        return await set_order_status(update, context)
    elif query.data == "back_to_orders":
        return await back_to_orders(update, context)

async def show_orders_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ заказов за сегодня"""
    query = update.callback_query
    
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT order_id, user_name, user_phone, items, total_amount, status, 
                   strftime('%d.%m.%Y %H:%M', created_at) as created, username
            FROM orders 
            WHERE date(created_at) = date('now', 'localtime')
            ORDER BY created_at DESC
        ''')
        orders = cursor.fetchall()
        conn.close()
        
        if not orders:
            await query.edit_message_text(
                "📭 Заказов за сегодня нет",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Назад", callback_data="orders_back")
                ]])
            )
            return ORDERS_MENU
        
        text = f"ЗАКАЗЫ ЗА СЕГОДНЯ ({len(orders)} шт.)\n"
        text += "=" * 30 + "\n\n"
        keyboard = []
        total_sum = 0
        
        for o in orders:
            items = json.loads(o['items']) if o['items'] else []
            items_text = ", ".join([f"{i['name']} x{i['quantity']}" for i in items])
            total_sum += o['total_amount']
            
            text += f"📦 Заказ №{o['order_id']}\n"
            text += f"👤 {o['user_name']}"
            if o['username']:
                text += f" (@{o['username']})"
            text += f"\n📞 {o['user_phone']}\n"
            text += f"🛒 {items_text}\n"
            text += f"💰 {o['total_amount']}₽\n"
            text += f"📊 Статус: {o['status']}\n"
            text += f"📅 {o['created']}\n\n"
            
            keyboard.append([InlineKeyboardButton(
                f"📋 Детали заказа {o['order_id']}",
                callback_data=f"view_order_{o['order_id']}"
            )])
        
        text += f"ИТОГО: {total_sum}₽"
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="orders_back")])
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await query.edit_message_text(f"❌ Ошибка: {str(e)[:100]}")
    
    return ORDERS_MENU

async def show_orders_month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ заказов за месяц"""
    query = update.callback_query
    
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT order_id, user_name, user_phone, items, total_amount, status,
                   strftime('%d.%m.%Y %H:%M', created_at) as created, username
            FROM orders 
            WHERE created_at >= datetime('now', '-30 days')
            ORDER BY created_at DESC
        ''')
        orders = cursor.fetchall()
        conn.close()
        
        if not orders:
            await query.edit_message_text(
                "📭 Заказов за месяц нет",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Назад", callback_data="orders_back")
                ]])
            )
            return ORDERS_MENU
        
        text = f"ЗАКАЗЫ ЗА МЕСЯЦ ({len(orders)} шт.)\n"
        text += "=" * 30 + "\n\n"
        keyboard = []
        total_sum = 0
        
        for o in orders[:15]:
            items = json.loads(o['items']) if o['items'] else []
            total_sum += o['total_amount']
            text += f"📦 {o['order_id']} - {o['user_name']} - {o['total_amount']}₽\n"
        
        text += f"\nИТОГО: {total_sum}₽"
        
        keyboard.append([InlineKeyboardButton(
            "📋 Показать все заказы", 
            callback_data="orders_period"
        )])
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="orders_back")])
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await query.edit_message_text(f"❌ Ошибка: {str(e)[:100]}")
    
    return ORDERS_MENU

async def show_order_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ деталей заказа"""
    query = update.callback_query
    await query.answer()
    
    order_id = query.data.split('_')[2]
    
    order = db.get_order(order_id)
    
    if not order:
        await query.edit_message_text("❌ Заказ не найден")
        return ORDERS_MENU
    
    # Парсим товары
    items = []
    try:
        items = json.loads(order['items']) if order['items'] else []
    except:
        items = []
    
    items_text = ""
    for i in items:
        items_text += f"  • {i['name']} x{i['quantity']} = {i['price'] * i['quantity']}₽\n"
    
    # Получаем историю статусов
    history_text = ""
    try:
        if order['status_history']:
            history = json.loads(order['status_history'])
            if history:
                history_text = "\n\n📋 История изменений:\n"
                for h in history[-3:]:
                    date = h['changed_at'][:16]
                    history_text += f"  {date}: {h['from']} → {h['to']}\n"
    except:
        history_text = ""
    
    username_display = f" (@{order['username']})" if order['username'] else ""
    
    text = (
        f"📦 ЗАКАЗ №{order['order_id']}\n"
        f"{'=' * 30}\n\n"
        f"👤 Клиент: {order['user_name']}{username_display}\n"
        f"📞 Телефон: {order['user_phone']}\n"
        f"📅 Создан: {order['created_at'][:16]}\n"
        f"📅 Обновлен: {order['updated_at'][:16] if order['updated_at'] else order['created_at'][:16]}\n\n"
        f"🛒 ТОВАРЫ:\n{items_text}\n"
        f"💰 Сумма: {order['total_amount']} ₽\n"
        f"📍 Адрес: {order['delivery_address']}\n"
        f"💬 Комментарий: {order['comment'] or '—'}\n\n"
        f"📊 Текущий статус: {order['status']}"
        f"{history_text}"
    )
    
    keyboard = [
        [InlineKeyboardButton("📊 Изменить статус", callback_data=f"change_status_{order_id}")],
        [InlineKeyboardButton("◀️ Назад к заказам", callback_data="back_to_orders")]
    ]
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def change_status_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню выбора нового статуса"""
    query = update.callback_query
    await query.answer()
    
    order_id = query.data.split('_')[2]
    
    # Получаем текущий статус
    order = db.get_order(order_id)
    current_status = order['status'] if order else 'неизвестно'
    
    text = (
        f"📊 ВЫБЕРИТЕ НОВЫЙ СТАТУС\n"
        f"{'=' * 25}\n\n"
        f"Заказ №{order_id}\n"
        f"Текущий статус: {current_status}\n\n"
        f"Доступные статусы:"
    )
    
    await query.edit_message_text(
        text,
        reply_markup=get_status_keyboard(order_id)
    )

async def set_order_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Установка нового статуса заказа"""
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split('_')
    order_id = parts[2]
    new_status = parts[3]
    admin_id = update.effective_user.id
    
    logger.info(f"👑 Суперадмин {admin_id}: установка статуса {new_status} для заказа {order_id}")
    
    success, result = db.update_order_status(order_id, new_status, admin_id)
    
    if not success:
        await query.edit_message_text(f"❌ Ошибка: {result}")
        return ORDERS_MENU
    
    # Уведомляем пользователя
    try:
        await context.bot.send_message(
            result['user_id'],
            f"📦 ОБНОВЛЕНИЕ СТАТУСА ЗАКАЗА\n\n"
            f"Заказ №{order_id}\n"
            f"Новый статус: {new_status}",
        )
    except Exception as e:
        logger.error(f"❌ Не удалось уведомить пользователя: {e}")
    
    await query.edit_message_text(
        f"✅ СТАТУС ОБНОВЛЕН!\n\n"
        f"Заказ №{order_id}\n"
        f"Новый статус: {ORDER_STATUSES.get(new_status, new_status)}\n\n"
        f"Пользователь уведомлен."
    )
    
    await asyncio.sleep(2)
    await back_to_orders(update, context)

async def back_to_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат к меню заказов"""
    query = update.callback_query
    
    await query.edit_message_text(
        "📋 УПРАВЛЕНИЕ ЗАКАЗАМИ\n\nВыберите период:",
        reply_markup=orders_menu_keyboard()
    )
    return ORDERS_MENU

# ========== СВЯЗЬ С КЛИЕНТАМИ ==========

async def search_client(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Поиск клиента"""
    query_text = update.message.text
    user_id = update.effective_user.id
    
    if query_text in ["❌ Отмена", "🚪 Выход"]:
        return await exit_handler(update, context)
    
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT DISTINCT 
                o.user_id, 
                o.user_name, 
                o.user_phone, 
                o.username,
                COUNT(o.id) as orders_count,
                SUM(o.total_amount) as total_spent,
                MAX(o.created_at) as last_order
            FROM orders o
            WHERE o.order_id LIKE ? 
               OR o.user_name LIKE ? 
               OR o.user_phone LIKE ?
               OR o.username LIKE ?
            GROUP BY o.user_id
            ORDER BY last_order DESC
            LIMIT 10
        ''', (
            f'%{query_text}%', 
            f'%{query_text}%', 
            f'%{query_text}%',
            f'%{query_text}%'
        ))
        
        clients = cursor.fetchall()
        conn.close()
        
        if not clients:
            await update.message.reply_text(
                "❌ Клиенты не найдены",
                reply_markup=get_admin_keyboard(user_id, db)
            )
            return SUPERADMIN
        
        text = "👥 НАЙДЕННЫЕ КЛИЕНТЫ\n\n"
        keyboard = []
        
        for c in clients:
            username = f" (@{c['username']})" if c['username'] else ""
            last_order = c['last_order'][:10] if c['last_order'] else "никогда"
            
            text += f"👤 {c['user_name']}{username}\n"
            text += f"📞 {c['user_phone']}\n"
            text += f"📦 Заказов: {c['orders_count']}\n"
            text += f"💰 На сумму: {c['total_spent'] or 0}₽\n"
            text += f"📅 Последний заказ: {last_order}\n\n"
            
            keyboard.append([InlineKeyboardButton(
                f"💬 Написать {c['user_name'][:20]}",
                callback_data=f"message_user_{c['user_id']}"
            )])
        
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="superadmin_back")])
        
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"❌ Ошибка поиска: {e}")
        await update.message.reply_text(f"❌ Ошибка поиска: {str(e)[:100]}")
        return SUPERADMIN
    
    return SEND_MESSAGE

async def send_message_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало отправки сообщения клиенту"""
    query = update.callback_query
    await query.answer()
    
    user_id = int(query.data.split('_')[2])
    context.user_data['target_user'] = user_id
    admin_id = update.effective_user.id
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT first_name, username FROM users WHERE user_id = ?", (user_id,))
    user_info = cursor.fetchone()
    conn.close()
    
    user_name = user_info['first_name'] or user_info['username'] or str(user_id)
    
    await query.edit_message_text(
        f"💬 ОТПРАВКА СООБЩЕНИЯ\n\n"
        f"Получатель: {user_name}\n\n"
        f"Введите текст сообщения:",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ Отмена", callback_data="superadmin_back")
        ]])
    )
    return SEND_MESSAGE

async def send_message_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправка сообщения клиенту"""
    text = update.message.text
    target_user = context.user_data.get('target_user')
    admin_id = update.effective_user.id
    
    if text in ["❌ Отмена", "🚪 Выход"]:
        return await exit_handler(update, context)
    
    if not target_user:
        await update.message.reply_text(
            "❌ Ошибка: получатель не найден",
            reply_markup=get_admin_keyboard(admin_id, db)
        )
        return SUPERADMIN
    
    try:
        await context.bot.send_message(
            target_user,
            f"📨 Сообщение от администратора:\n\n{text}",
        )
        
        await update.message.reply_text(
            "✅ Сообщение успешно отправлено!",
            reply_markup=get_admin_keyboard(admin_id, db)
        )
        
    except Exception as e:
        error_message = (
            "❌ Ошибка при отправке\n\n"
            f"Причина: {str(e)[:100]}\n\n"
            "Возможно, пользователь заблокировал бота."
        )
        
        await update.message.reply_text(
            error_message,
            reply_markup=get_admin_keyboard(admin_id, db)
        )
    
    context.user_data.pop('target_user', None)
    return SUPERADMIN

# ========== РАССЫЛКА ==========

async def broadcast_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ввод текста рассылки"""
    text = update.message.text
    admin_id = update.effective_user.id
    
    if text in ["❌ Отмена", "🚪 Выход"]:
        return await exit_handler(update, context)
    
    context.user_data['broadcast_text'] = text
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    conn.close()
    
    await update.message.reply_text(
        f"📢 ПОДТВЕРЖДЕНИЕ РАССЫЛКИ\n\n"
        f"Текст:\n{text}\n\n"
        f"Получателей: {total_users}\n\n"
        f"Отправить?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Да, отправить", callback_data="broadcast_confirm")],
            [InlineKeyboardButton("❌ Нет, отменить", callback_data="broadcast_cancel")]
        ])
    )
    return BROADCAST_CONFIRM

async def broadcast_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение и отправка рассылки"""
    query = update.callback_query
    await query.answer()
    
    admin_id = update.effective_user.id
    
    if query.data == "broadcast_cancel":
        await query.edit_message_text("❌ Рассылка отменена")
        return SUPERADMIN
    
    text = context.user_data.get('broadcast_text')
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()
    
    await query.edit_message_text(
        f"📤 Начинаю рассылку...\n\n"
        f"Всего получателей: {len(users)}"
    )
    
    sent = 0
    failed = 0
    
    for i, user in enumerate(users):
        try:
            await context.bot.send_message(
                user['user_id'],
                f"📢 РАССЫЛКА:\n\n{text}",
            )
            sent += 1
            
            if (i + 1) % 10 == 0:
                await query.edit_message_text(
                    f"📤 Рассылка...\n\n"
                    f"✅ Отправлено: {sent}\n"
                    f"❌ Ошибок: {failed}\n"
                    f"⏳ Прогресс: {i + 1}/{len(users)}"
                )
            
            await asyncio.sleep(0.05)
            
        except Exception as e:
            failed += 1
    
    await query.edit_message_text(
        f"✅ РАССЫЛКА ЗАВЕРШЕНА\n\n"
        f"📨 Отправлено: {sent}\n"
        f"❌ Ошибок: {failed}"
    )
    
    context.user_data.pop('broadcast_text', None)
    
    await asyncio.sleep(2)
    return await back_to_superadmin(update, context)

# ========== ПЕРИОД ==========

async def period_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ввод начальной даты"""
    text = update.message.text
    admin_id = update.effective_user.id
    
    if text in ["❌ Отмена", "🚪 Выход"]:
        return await exit_handler(update, context)
    
    try:
        start = datetime.strptime(text, "%d.%m.%Y")
        context.user_data['period_start'] = start
        await update.message.reply_text(
            "📅 Введите конечную дату (ДД.ММ.ГГГГ):",
            reply_markup=cancel_keyboard()
        )
        return PERIOD_END
    except:
        await update.message.reply_text("❌ Неверный формат. Используйте ДД.ММ.ГГГГ")
        return PERIOD_START

async def period_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ввод конечной даты"""
    text = update.message.text
    admin_id = update.effective_user.id
    
    if text in ["❌ Отмена", "🚪 Выход"]:
        return await exit_handler(update, context)
    
    try:
        end = datetime.strptime(text, "%d.%m.%Y")
        start = context.user_data.get('period_start')
        
        if end < start:
            await update.message.reply_text("❌ Конец не может быть раньше начала")
            return PERIOD_END
        
        orders = db.get_orders(period='all')
        
        if not orders:
            await update.message.reply_text("📭 Заказов за указанный период нет")
            return SUPERADMIN
        
        # Фильтруем по дате
        filtered = []
        total = 0
        for o in orders:
            order_date = datetime.strptime(o['created_at'][:10], "%Y-%m-%d")
            if start.date() <= order_date.date() <= end.date():
                filtered.append(o)
                total += o['total_amount']
        
        if not filtered:
            await update.message.reply_text("📭 Заказов за указанный период нет")
            return SUPERADMIN
        
        text = f"📋 ЗАКАЗЫ С {start.strftime('%d.%m.%Y')} ПО {end.strftime('%d.%m.%Y')}\n"
        text += "=" * 40 + "\n\n"
        keyboard = []
        
        for o in filtered[:10]:
            items = json.loads(o['items']) if o['items'] else []
            items_text = ", ".join([f"{i['name']} x{i['quantity']}" for i in items])
            
            text += f"📦 {o['order_id']} - {o['user_name']} - {o['total_amount']}₽\n"
            text += f"   {items_text}\n\n"
            
            keyboard.append([InlineKeyboardButton(
                f"📋 Детали {o['order_id']}",
                callback_data=f"view_order_{o['order_id']}"
            )])
        
        text += f"\nИТОГО: {total}₽"
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="superadmin_back")])
        
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        context.user_data.pop('period_start', None)
        return SUPERADMIN
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await update.message.reply_text("❌ Неверный формат даты")
        return PERIOD_END

# ========== ВСПОМОГАТЕЛЬНЫЕ ==========

async def back_to_superadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат в главное меню суперадмина"""
    if update.callback_query:
        await update.callback_query.edit_message_text("🔙 Возврат в главное меню...")
        await update.effective_chat.send_message(
            "👑 ГЛАВНОЕ МЕНЮ СУПЕРАДМИНИСТРАТОРА",
            reply_markup=superadmin_main_keyboard()
        )
    else:
        await update.message.reply_text(
            "👑 ГЛАВНОЕ МЕНЮ СУПЕРАДМИНИСТРАТОРА",
            reply_markup=superadmin_main_keyboard()
        )
    
    return SUPERADMIN

async def superadmin_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback для кнопки Назад"""
    return await back_to_superadmin(update, context)