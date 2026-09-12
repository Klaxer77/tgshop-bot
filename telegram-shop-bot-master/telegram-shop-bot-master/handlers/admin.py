# handlers/admin.py
import logging
import json
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from database import Database
from google_sheets import GoogleSheets
from keyboards import *
from states import *
from config import ORDER_STATUSES, SPREADSHEET_ID
from handlers.back_handlers import back_to_admin
from handlers.common import exit_handler

logger = logging.getLogger(__name__)
db = Database()
gs = GoogleSheets() if SPREADSHEET_ID else None

# Константы пагинации
ADMIN_PRODUCTS_PER_PAGE = 8
CATEGORIES_PER_PAGE = 10


# ========== ОСНОВНОЙ ОБРАБОТЧИК ==========

async def admin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик для менеджеров"""
    text = update.message.text
    user_id = update.effective_user.id
    
    logger.info(f"👔 Менеджер {user_id}: {text}")
    
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
            "📢 РАССЫЛКА\n\nВведите текст для рассылки:",
            reply_markup=cancel_keyboard()
        )
        return BROADCAST_TEXT
    
    elif text == "📤 Экспорт в Google Sheets":
        return await export_to_google(update, context)
    
    elif text == "📥 Импорт товаров":
        return await import_from_google(update, context)
    
    elif text == "🚪 Выход":
        return await exit_handler(update, context)
    
    return ADMIN


# ============================================================
# GOOGLE SHEETS
# ============================================================

async def export_to_google(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Экспорт товаров, категорий и заказов в Google Sheets"""
    user_id = update.effective_user.id
    logger.info(f"👔 Менеджер {user_id}: экспорт в Google Sheets")
    
    if not gs:
        await update.message.reply_text(
            "❌ Google Sheets не настроен\n\nПроверьте SPREADSHEET_ID в .env"
        )
        return ADMIN
    
    msg = await update.message.reply_text("📤 Экспортирую данные...")
    
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        results = []
        
        # Экспорт товаров
        cursor.execute('''
            SELECT p.id, p.name, COALESCE(c.name, p.category, 'Общее') as category,
                   p.price, p.stock, COALESCE(p.photo_file_id, ''), p.created_at
            FROM products p
            LEFT JOIN categories c ON p.category_id = c.id
            ORDER BY p.id
        ''')
        products = cursor.fetchall()
        if products:
            success, msg_txt = gs.export_products(products)
            results.append(msg_txt)
        else:
            results.append("⚠️ Нет товаров")
        
        # ⭐ Экспорт категорий
        cursor.execute("SELECT id, name, parent_id, is_active FROM categories ORDER BY parent_id NULLS FIRST, id")
        categories = cursor.fetchall()
        if categories:
            success, msg_txt = gs.export_categories(categories)
            results.append(msg_txt)
        else:
            results.append("⚠️ Нет категорий")
        
        # Экспорт заказов
        cursor.execute('''
            SELECT order_id, user_name, user_phone, COALESCE(username, ''),
                   items, total_amount, delivery_address, status, created_at
            FROM orders ORDER BY created_at DESC
        ''')
        orders = cursor.fetchall()
        if orders:
            success, msg_txt = gs.export_orders(orders)
            results.append(msg_txt)
        else:
            results.append("⚠️ Нет заказов")
        
        conn.close()
        
        await msg.edit_text(
            "✅ ЭКСПОРТ ЗАВЕРШЕН\n\n" + "\n".join(results)
        )
    except Exception as e:
        logger.error(f"❌ Ошибка экспорта: {e}")
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")
    
    await asyncio.sleep(2)
    return ADMIN


async def import_from_google(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Импорт товаров и категорий из Google Sheets"""
    if not gs:
        await update.message.reply_text(
            "❌ Google Sheets не настроен\n\nПроверьте SPREADSHEET_ID в .env"
        )
        return ADMIN
    
    await update.message.reply_text(
        "📥 ИМПОРТ ДАННЫХ\n\n"
        "Будут импортированы:\n"
        "• Категории (лист «Категории»)\n"
        "• Товары (лист «Товары»)\n\n"
        "Товары с такими же названиями будут пропущены.\n\n"
        "Продолжить?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Да, импортировать", callback_data="import_confirm")],
            [InlineKeyboardButton("❌ Отмена", callback_data="import_cancel")]
        ])
    )
    return IMPORT_PRODUCTS


async def import_products_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение импорта"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "import_cancel":
        await query.edit_message_text("❌ Импорт отменен")
        return ADMIN
    
    await query.edit_message_text("📥 Импортирую данные из Google Sheets...")
    
    # ===== ШАГ 1: Импорт категорий =====
    categories, cat_errors = gs.import_categories()
    
    cats_added = 0
    cat_map = {}  # name -> id
    
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Сначала главные категории
        for c in categories:
            if not c['parent_id']:
                cursor.execute(
                    "SELECT id FROM categories WHERE name = ? AND parent_id IS NULL",
                    (c['name'],)
                )
                existing = cursor.fetchone()
                if not existing:
                    cursor.execute(
                        "INSERT INTO categories (name, parent_id, created_at) VALUES (?, NULL, ?)",
                        (c['name'], datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    )
                    cat_map[c['name']] = cursor.lastrowid
                    cats_added += 1
                else:
                    cat_map[c['name']] = existing['id']
        
        # Затем подкатегории (2-й проход)
        for c in categories:
            if c['parent_id']:
                # Ищем родителя по ID из таблицы
                cursor.execute("SELECT id, name FROM categories WHERE id = ?", (c['parent_id'],))
                parent = cursor.fetchone()
                if not parent:
                    continue
                
                cursor.execute(
                    "SELECT id FROM categories WHERE name = ? AND parent_id = ?",
                    (c['name'], parent['id'])
                )
                existing = cursor.fetchone()
                if not existing:
                    cursor.execute(
                        "INSERT INTO categories (name, parent_id, created_at) VALUES (?, ?, ?)",
                        (c['name'], parent['id'], datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    )
                    cat_map[c['name']] = cursor.lastrowid
                    cats_added += 1
                else:
                    cat_map[c['name']] = existing['id']
        
        # Обновляем cat_map с уже существующими категориями
        cursor.execute("SELECT id, name FROM categories")
        for row in cursor.fetchall():
            cat_map[row['name']] = row['id']
        
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Ошибка импорта категорий: {e}")
        await query.edit_message_text(f"❌ Ошибка импорта категорий: {str(e)[:150]}")
        return ADMIN
    
    # ===== ШАГ 2: Импорт товаров =====
    products, prod_errors = gs.import_products()
    
    prod_added = 0
    prod_skipped = 0
    
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        for p in products:
            cursor.execute("SELECT id FROM products WHERE name = ?", (p['name'],))
            existing = cursor.fetchone()
            
            if not existing:
                # Ищем category_id по названию
                category_id = cat_map.get(p['category_name'])
                
                cursor.execute('''
                    INSERT INTO products 
                    (name, category, category_id, price, stock, in_stock, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    p['name'], p['category_name'], category_id,
                    p['price'], p['stock'],
                    1 if p['stock'] > 0 else 0,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ))
                prod_added += 1
            else:
                prod_skipped += 1
        
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Ошибка импорта товаров: {e}")
        await query.edit_message_text(f"❌ Ошибка: {str(e)[:150]}")
        return ADMIN
    
    # ===== ИТОГ =====
    text = (
        f"✅ ИМПОРТ ЗАВЕРШЕН\n\n"
        f"📂 КАТЕГОРИИ:\n"
        f"  • Добавлено: {cats_added}\n\n"
        f"📦 ТОВАРЫ:\n"
        f"  • Добавлено: {prod_added}\n"
        f"  • Пропущено: {prod_skipped}\n"
    )
    
    if cat_errors or prod_errors:
        text += f"\n⚠️ Ошибок: {len(cat_errors) + len(prod_errors)}"
    
    await query.edit_message_text(text)
    await asyncio.sleep(2)
    return ADMIN


# ========== СТАТИСТИКА ==========

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ статистики"""
    user_id = update.effective_user.id
    logger.info(f"👔 Менеджер {user_id}: просмотр статистики")
    
    try:
        stats = db.get_stats()
        
        text = (
            "👔 СТАТИСТИКА МЕНЕДЖЕРА\n"
            f"{'=' * 30}\n\n"
            f"📦 ТОВАРЫ\n"
            f"  • Всего: {stats['total_products']}\n"
            f"  • В наличии: {stats['in_stock']}\n"
            f"  • Общий склад: {stats['total_stock']} шт.\n\n"
            f"📂 КАТЕГОРИИ\n"
            f"  • Категорий: {stats.get('total_categories', 0)}\n"
            f"  • Подкатегорий: {stats.get('total_subcategories', 0)}\n\n"
            f"👥 ПОЛЬЗОВАТЕЛИ\n"
            f"  • Всего: {stats['total_users']}\n\n"
            f"📋 ЗАКАЗЫ\n"
            f"  • Всего: {stats['total_orders']}\n"
            f"  • Сегодня: {stats['orders_today']}\n"
            f"  • Средний чек: {stats['avg_order']:.0f}₽\n"
            f"  • Выручка: {stats['total_revenue']:.0f}₽\n"
            f"  • Выручка сегодня: {stats['revenue_today']:.0f}₽"
        )
        
        await update.message.reply_text(text)
    except Exception as e:
        logger.error(f"❌ Ошибка статистики: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")
    
    return ADMIN


# ============================================================
# УПРАВЛЕНИЕ ПРАЙСОМ
# ============================================================

async def price_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка меню прайса"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    logger.info(f"👔 Менеджер {user_id}: нажал {query.data}")
    
    if query.data == "price_add":
        # Начинаем добавление — сначала выбор категории
        await query.edit_message_text(
            "➕ ДОБАВЛЕНИЕ ТОВАРА\n\nШаг 1/6: Введите название товара:"
        )
        return ADD_PRODUCT_NAME
    elif query.data == "price_edit":
        return await show_products_for_edit(update, context, page=1)
    elif query.data == "price_delete":
        return await show_products_for_delete(update, context, page=1)
    elif query.data == "price_toggle":
        return await show_products_for_toggle(update, context, page=1)
    elif query.data == "categories_menu":
        return await categories_menu(update, context)
    elif query.data == "price_export":
        return await export_to_google(update, context)
    elif query.data == "price_back":
        return await back_to_admin(update, context)


# --- Редактирование товара с пагинацией ---

async def show_products_for_edit(update: Update, context: ContextTypes.DEFAULT_TYPE, page=1):
    """Показать товары для редактирования"""
    query = update.callback_query
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM products")
    total = cursor.fetchone()[0]
    
    if total == 0:
        conn.close()
        await query.edit_message_text(
            "📭 Товаров нет",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="price_back")
            ]])
        )
        return PRICE_MENU
    
    total_pages = (total + ADMIN_PRODUCTS_PER_PAGE - 1) // ADMIN_PRODUCTS_PER_PAGE
    page = max(1, min(page, total_pages))
    offset = (page - 1) * ADMIN_PRODUCTS_PER_PAGE
    
    cursor.execute(
        "SELECT id, name, price FROM products ORDER BY name LIMIT ? OFFSET ?",
        (ADMIN_PRODUCTS_PER_PAGE, offset)
    )
    products = cursor.fetchall()
    conn.close()
    
    text = f"✏️ ВЫБЕРИТЕ ТОВАР\n\n📄 Страница {page}/{total_pages}\n📦 Всего: {total}"
    
    keyboard = get_admin_products_keyboard(products, page, total_pages, action='edit')
    await query.edit_message_text(text, reply_markup=keyboard)
    return EDIT_PRODUCT_SELECT


async def show_products_for_delete(update: Update, context: ContextTypes.DEFAULT_TYPE, page=1):
    """Показать товары для удаления"""
    query = update.callback_query
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM products")
    total = cursor.fetchone()[0]
    
    if total == 0:
        conn.close()
        await query.edit_message_text(
            "📭 Товаров нет",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="price_back")
            ]])
        )
        return PRICE_MENU
    
    total_pages = (total + ADMIN_PRODUCTS_PER_PAGE - 1) // ADMIN_PRODUCTS_PER_PAGE
    page = max(1, min(page, total_pages))
    offset = (page - 1) * ADMIN_PRODUCTS_PER_PAGE
    
    cursor.execute(
        "SELECT id, name, price FROM products ORDER BY name LIMIT ? OFFSET ?",
        (ADMIN_PRODUCTS_PER_PAGE, offset)
    )
    products = cursor.fetchall()
    conn.close()
    
    text = f"🗑 ВЫБЕРИТЕ ТОВАР ДЛЯ УДАЛЕНИЯ\n\n📄 Страница {page}/{total_pages}\n📦 Всего: {total}"
    
    keyboard = get_admin_products_keyboard(products, page, total_pages, action='delete')
    await query.edit_message_text(text, reply_markup=keyboard)
    return DELETE_PRODUCT_SELECT


async def show_products_for_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE, page=1):
    """Показать товары для изменения статуса наличия"""
    query = update.callback_query
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM products")
    total = cursor.fetchone()[0]
    
    if total == 0:
        conn.close()
        await query.edit_message_text(
            "📭 Товаров нет",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="price_back")
            ]])
        )
        return PRICE_MENU
    
    total_pages = (total + ADMIN_PRODUCTS_PER_PAGE - 1) // ADMIN_PRODUCTS_PER_PAGE
    page = max(1, min(page, total_pages))
    offset = (page - 1) * ADMIN_PRODUCTS_PER_PAGE
    
    cursor.execute(
        "SELECT id, name, price FROM products ORDER BY name LIMIT ? OFFSET ?",
        (ADMIN_PRODUCTS_PER_PAGE, offset)
    )
    products = cursor.fetchall()
    conn.close()
    
    text = f"📊 СТАТУС НАЛИЧИЯ\n\n📄 Страница {page}/{total_pages}\n📦 Всего: {total}"
    
    keyboard = get_admin_products_keyboard(products, page, total_pages, action='toggle')
    await query.edit_message_text(text, reply_markup=keyboard)
    return TOGGLE_STOCK_SELECT


async def admin_products_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пагинация товаров в админке"""
    query = update.callback_query
    await query.answer()
    
    # admprod_{action}_{page}
    parts = query.data.split("_")
    action = parts[1]
    page = int(parts[2])
    
    if action == 'edit':
        return await show_products_for_edit(update, context, page)
    elif action == 'delete':
        return await show_products_for_delete(update, context, page)
    elif action == 'toggle':
        return await show_products_for_toggle(update, context, page)


# --- Редактирование товара ---

async def edit_product_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор товара для редактирования"""
    query = update.callback_query
    await query.answer()
    
    product_id = int(query.data.split('_')[2])
    context.user_data['edit_product_id'] = product_id
    
    product = db.get_product(product_id)
    
    if not product:
        await query.edit_message_text("❌ Товар не найден")
        return PRICE_MENU
    
    photo_status = "✅ есть" if product['photo_file_id'] else "❌ нет"
    
    text = (
        f"✏️ РЕДАКТИРОВАНИЕ ТОВАРА\n\n"
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
    elif field == 'category':
        # Показываем выбор категории
        return await show_category_picker_for_product(update, context)
    else:
        field_names = {
            'name': 'новое название',
            'price': 'новую цену (только цифры)',
            'stock': 'новое количество'
        }
        await query.edit_message_text(
            f"✏️ Введите {field_names.get(field, 'новое значение')}:"
        )
    
    return EDIT_PRODUCT_VALUE


async def edit_product_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ввод нового значения"""
    text = update.message.text
    field = context.user_data.get('edit_field')
    
    if text in ["❌ Отмена", "🚪 Выход"]:
        return await exit_handler(update, context)
    
    product_id = context.user_data.get('edit_product_id')
    
    if not product_id or not field:
        await update.message.reply_text("❌ Ошибка")
        return ADMIN
    
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
    return await back_to_admin(update, context)


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
    
    await asyncio.sleep(1)
    return await back_to_admin(update, context)


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
    
    await asyncio.sleep(1)
    return await back_to_admin(update, context)


# ============================================================
# ⭐ УПРАВЛЕНИЕ КАТЕГОРИЯМИ
# ============================================================

async def categories_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню управления категориями"""
    query = update.callback_query
    
    await query.edit_message_text(
        "📂 УПРАВЛЕНИЕ КАТЕГОРИЯМИ\n\nВыберите действие:",
        reply_markup=categories_menu_keyboard()
    )
    return CATEGORY_MENU


async def categories_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка меню категорий"""
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id
    
    logger.info(f"👔 Менеджер {user_id}: categories callback {data}")
    
    # --- Добавить категорию ---
    if data == "cat_add":
        await query.edit_message_text(
            "➕ ДОБАВЛЕНИЕ КАТЕГОРИИ\n\nВведите название категории:"
        )
        return ADD_CATEGORY_NAME
    
    # --- Добавить подкатегорию ---
    if data == "subcat_add":
        cats = db.get_categories(parent_id=None)
        if not cats:
            await query.edit_message_text(
                "❌ Сначала создайте хотя бы одну категорию",
                reply_markup=categories_menu_keyboard()
            )
            return CATEGORY_MENU
        
        keyboard = get_category_select_keyboard(cats, callback_prefix="subcat_parent_")
        await query.edit_message_text(
            "➕ ДОБАВЛЕНИЕ ПОДКАТЕГОРИИ\n\nВыберите родительскую категорию:",
            reply_markup=keyboard
        )
        return ADD_SUBCATEGORY_PARENT
    
    # --- Список категорий ---
    if data == "cat_list":
        cats = db.get_categories(parent_id=None, active_only=False)
        text = "📋 СПИСОК КАТЕГОРИЙ\n\n"
        
        if not cats:
            text += "Категорий нет"
        else:
            for c in cats:
                subcats = db.get_categories(parent_id=c['id'], active_only=False)
                text += f"📂 {c['name']}\n"
                for s in subcats:
                    text += f"   📁 {s['name']}\n"
                if subcats:
                    text += "\n"
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="cat_back")
            ]])
        )
        return CATEGORY_MENU
    
    # --- Удалить категорию ---
    if data == "cat_delete":
        cats = db.get_categories(parent_id=None, active_only=False)
        if not cats:
            await query.edit_message_text(
                "📭 Категорий нет",
                reply_markup=categories_menu_keyboard()
            )
            return CATEGORY_MENU
        
        keyboard = get_category_select_keyboard(cats, callback_prefix="cat_del_")
        await query.edit_message_text(
            "🗑 УДАЛЕНИЕ КАТЕГОРИИ\n\n"
            "⚠️ Вместе с категорией удалятся её подкатегории\n\n"
            "Выберите категорию:",
            reply_markup=keyboard
        )
        return DELETE_CATEGORY_SELECT
    
    # --- Переименовать категорию ---
    if data == "cat_rename":
        cats = db.get_categories(parent_id=None, active_only=False)
        if not cats:
            await query.edit_message_text(
                "📭 Категорий нет",
                reply_markup=categories_menu_keyboard()
            )
            return CATEGORY_MENU
        
        keyboard = get_category_select_keyboard(cats, callback_prefix="cat_ren_")
        await query.edit_message_text(
            "✏️ ПЕРЕИМЕНОВАНИЕ\n\nВыберите категорию:",
            reply_markup=keyboard
        )
        return EDIT_CATEGORY_SELECT
    
    # --- Выбор родителя для подкатегории ---
    if data.startswith("subcat_parent_"):
        parent_id = int(data.split("_")[2])
        context.user_data['subcat_parent_id'] = parent_id
        parent = db.get_category(parent_id)
        
        await query.edit_message_text(
            f"➕ ПОДКАТЕГОРИЯ В «{parent['name']}»\n\n"
            f"Введите название подкатегории:"
        )
        return ADD_SUBCATEGORY_NAME
    
    # --- Удаление категории (выбор) ---
    if data.startswith("cat_del_"):
        cat_id = int(data.split("_")[2])
        cat = db.get_category(cat_id)
        
        await query.edit_message_text(
            f"🗑 УДАЛИТЬ «{cat['name']}»?\n\n"
            f"⚠️ Все подкатегории будут удалены!",
            reply_markup=confirm_delete_category_keyboard(cat_id)
        )
        return DELETE_CATEGORY_SELECT
    
    if data.startswith("cat_confirmdel_"):
        cat_id = int(data.split("_")[2])
        db.delete_category(cat_id)
        await query.edit_message_text("✅ Категория удалена")
        await asyncio.sleep(1)
        return await categories_menu(update, context)
    
    # --- Переименование категории ---
    if data.startswith("cat_ren_"):
        cat_id = int(data.split("_")[2])
        context.user_data['rename_cat_id'] = cat_id
        cat = db.get_category(cat_id)
        
        await query.edit_message_text(
            f"✏️ Введите новое название для «{cat['name']}»:"
        )
        return EDIT_CATEGORY_NAME
    
    # --- Назад ---
    if data == "cat_back":
        return await price_menu_back(update, context)


async def add_category_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавление новой категории"""
    text = update.message.text
    if text in ["❌ Отмена", "🚪 Выход"]:
        return await exit_handler(update, context)
    
    db.add_category(text, parent_id=None)
    await update.message.reply_text(f"✅ Категория «{text}» добавлена!")
    
    # Показываем меню
    await update.message.reply_text(
        "📂 УПРАВЛЕНИЕ КАТЕГОРИЯМИ",
        reply_markup=categories_menu_keyboard()
    )
    return CATEGORY_MENU


async def add_subcategory_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавление подкатегории"""
    text = update.message.text
    if text in ["❌ Отмена", "🚪 Выход"]:
        return await exit_handler(update, context)
    
    parent_id = context.user_data.get('subcat_parent_id')
    if not parent_id:
        await update.message.reply_text("❌ Ошибка: родитель не выбран")
        return CATEGORY_MENU
    
    db.add_category(text, parent_id=parent_id)
    parent = db.get_category(parent_id)
    await update.message.reply_text(f"✅ Подкатегория «{text}» добавлена в «{parent['name']}»!")
    
    await update.message.reply_text(
        "📂 УПРАВЛЕНИЕ КАТЕГОРИЯМИ",
        reply_markup=categories_menu_keyboard()
    )
    return CATEGORY_MENU


async def edit_category_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переименование категории"""
    text = update.message.text
    if text in ["❌ Отмена", "🚪 Выход"]:
        return await exit_handler(update, context)
    
    cat_id = context.user_data.get('rename_cat_id')
    if not cat_id:
        await update.message.reply_text("❌ Ошибка")
        return CATEGORY_MENU
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE categories SET name = ? WHERE id = ?", (text, cat_id))
    conn.commit()
    conn.close()
    db._cache_clear("categories_")
    
    await update.message.reply_text(f"✅ Категория переименована в «{text}»")
    context.user_data.pop('rename_cat_id', None)
    
    await update.message.reply_text(
        "📂 УПРАВЛЕНИЕ КАТЕГОРИЯМИ",
        reply_markup=categories_menu_keyboard()
    )
    return CATEGORY_MENU


# ============================================================
# ⭐ ВЫБОР КАТЕГОРИИ ПРИ ДОБАВЛЕНИИ ТОВАРА
# ============================================================

async def show_category_picker_for_product(update: Update, context: ContextTypes.DEFAULT_TYPE, 
                                            page: int = 1):
    """Показать выбор категории при добавлении/редактировании товара"""
    query = update.callback_query
    
    cats = db.get_categories(parent_id=None, active_only=True)
    
    if not cats:
        # Если категорий нет — пропускаем выбор
        if context.user_data.get('new_product'):
            context.user_data['new_product']['category_id'] = None
            context.user_data['new_product']['category'] = 'Общее'
            await query.edit_message_text(
                "⚠️ Категорий нет. Товар попадёт в «Общее»\n\n"
                "Шаг 3/6: Введите цену (только цифры):"
            )
            return ADD_PRODUCT_PRICE
        else:
            # Редактирование
            db.update_product(context.user_data.get('edit_product_id'), 
                            category_id=None, category='Общее')
            await query.edit_message_text("✅ Категория сброшена на «Общее»")
            return await back_to_admin(update, context)
    
    total = len(cats)
    total_pages = (total + CATEGORIES_PER_PAGE - 1) // CATEGORIES_PER_PAGE
    page = max(1, min(page, total_pages))
    offset = (page - 1) * CATEGORIES_PER_PAGE
    page_cats = cats[offset:offset + CATEGORIES_PER_PAGE]
    
    title = "📂 ВЫБЕРИТЕ КАТЕГОРИЮ" if context.user_data.get('new_product') else "📂 НОВАЯ КАТЕГОРИЯ"
    
    keyboard = get_category_picker_for_product(page_cats, page, total_pages)
    
    if query:
        await query.edit_message_text(
            f"{title}\n\n📄 Страница {page}/{total_pages}",
            reply_markup=keyboard
        )
    return SELECT_PRODUCT_CATEGORY


async def pick_category_for_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора категории при добавлении товара"""
    query = update.callback_query
    await query.answer()
    data = query.data
    
    # Отмена
    if data == "pickcat_cancel":
        context.user_data.pop('new_product', None)
        return await back_to_admin(update, context)
    
    # Без категории
    if data == "pickcat_none":
        if context.user_data.get('new_product'):
            context.user_data['new_product']['category_id'] = None
            context.user_data['new_product']['category'] = 'Общее'
            await query.edit_message_text(
                "✅ Категория: Общее\n\n"
                "Шаг 3/6: Введите цену (только цифры):"
            )
            return ADD_PRODUCT_PRICE
        else:
            product_id = context.user_data.get('edit_product_id')
            db.update_product(product_id, category_id=None, category='Общее')
            await query.edit_message_text("✅ Категория: Общее")
            await asyncio.sleep(1)
            return await back_to_admin(update, context)
    
    # Пагинация
    if data.startswith("pickcatpage_"):
        page = int(data.split("_")[1])
        return await show_category_picker_for_product(update, context, page)
    
    # Выбор категории
    if data.startswith("pickcat_"):
        cat_id = int(data.split("_")[1])
        
        # Проверяем подкатегории
        if db.has_subcategories(cat_id):
            # Показываем подкатегории
            subcats = db.get_categories(parent_id=cat_id, active_only=True)
            keyboard = get_subcategory_picker_for_product(subcats, cat_id)
            await query.edit_message_text(
                f"📁 Выберите подкатегорию:",
                reply_markup=keyboard
            )
            return SELECT_PRODUCT_SUBCATEGORY
        
        # Нет подкатегорий — используем категорию
        cat = db.get_category(cat_id)
        
        if context.user_data.get('new_product'):
            context.user_data['new_product']['category_id'] = cat_id
            context.user_data['new_product']['category'] = cat['name']
            await query.edit_message_text(
                f"✅ Категория: {cat['name']}\n\n"
                f"Шаг 3/6: Введите цену (только цифры):"
            )
            return ADD_PRODUCT_PRICE
        else:
            product_id = context.user_data.get('edit_product_id')
            db.update_product(product_id, category_id=cat_id, category=cat['name'])
            await query.edit_message_text(f"✅ Категория обновлена: {cat['name']}")
            await asyncio.sleep(1)
            return await back_to_admin(update, context)


async def pick_subcategory_for_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора подкатегории"""
    query = update.callback_query
    await query.answer()
    data = query.data
    
    # Пропустить подкатегорию
    if data.startswith("picksubcat_skip_"):
        parent_id = int(data.split("_")[2])
        cat = db.get_category(parent_id)
        
        if context.user_data.get('new_product'):
            context.user_data['new_product']['category_id'] = parent_id
            context.user_data['new_product']['category'] = cat['name']
            await query.edit_message_text(
                f"✅ Категория: {cat['name']}\n\n"
                f"Шаг 3/6: Введите цену (только цифры):"
            )
            return ADD_PRODUCT_PRICE
        else:
            product_id = context.user_data.get('edit_product_id')
            db.update_product(product_id, category_id=parent_id, category=cat['name'])
            await query.edit_message_text(f"✅ Категория: {cat['name']}")
            await asyncio.sleep(1)
            return await back_to_admin(update, context)
    
    # Выбор подкатегории
    if data.startswith("picksubcat_"):
        cat_id = int(data.split("_")[1])
        cat = db.get_category(cat_id)
        
        if context.user_data.get('new_product'):
            context.user_data['new_product']['category_id'] = cat_id
            context.user_data['new_product']['category'] = cat['name']
            await query.edit_message_text(
                f"✅ Подкатегория: {cat['name']}\n\n"
                f"Шаг 3/6: Введите цену (только цифры):"
            )
            return ADD_PRODUCT_PRICE
        else:
            product_id = context.user_data.get('edit_product_id')
            db.update_product(product_id, category_id=cat_id, category=cat['name'])
            await query.edit_message_text(f"✅ Категория обновлена: {cat['name']}")
            await asyncio.sleep(1)
            return await back_to_admin(update, context)


# ============================================================
# ДОБАВЛЕНИЕ ТОВАРА
# ============================================================

async def add_product_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ввод названия товара"""
    text = update.message.text
    if text in ["❌ Отмена", "🚪 Выход"]:
        return await exit_handler(update, context)
    
    context.user_data['new_product'] = {'name': text}
    
    # Показываем выбор категории
    return await show_category_picker_for_product(update, context)


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
        "✅ Цена сохранена!\n\nШаг 4/6: Введите количество (или 0):",
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
        "Шаг 5/6: Отправьте фото товара (или '-' чтобы пропустить):",
        reply_markup=cancel_keyboard()
    )
    return ADD_PRODUCT_PHOTO


async def add_product_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение фото и сохранение"""
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
            product.get('category', 'Общее'),
            product['price'],
            product['stock'],
            photo_id,
            user_id,
            category_id=product.get('category_id')
        )
        
        response = (
            f"✅ ТОВАР ДОБАВЛЕН!\n\n"
            f"📦 {product['name']}\n"
            f"📂 {product.get('category', 'Общее')}\n"
            f"💰 {product['price']}₽\n"
            f"📊 {product['stock']} шт.\n"
            f"📸 {'✅' if photo_id else '❌'}"
        )
        await update.message.reply_text(response)
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")
    
    context.user_data.pop('new_product', None)
    return await back_to_admin(update, context)


# ============================================================
# УПРАВЛЕНИЕ ЗАКАЗАМИ (без изменений)
# ============================================================

async def orders_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка меню заказов"""
    query = update.callback_query
    await query.answer()
    
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
        return await back_to_admin(update, context)
    elif query.data.startswith("view_order_"):
        return await show_order_details(update, context)
    elif query.data.startswith("change_status_"):
        return await change_status_menu(update, context)
    elif query.data.startswith("set_status_"):
        return await set_order_status(update, context)
    elif query.data == "back_to_orders":
        return await back_to_orders(update, context)


async def show_orders_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Заказы за сегодня"""
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
        
        text = f"ЗАКАЗЫ ЗА СЕГОДНЯ ({len(orders)} шт.)\n" + "=" * 30 + "\n\n"
        keyboard = []
        total_sum = 0
        
        for o in orders:
            items = json.loads(o['items']) if o['items'] else []
            items_text = ", ".join([f"{i['name']} x{i['quantity']}" for i in items])
            total_sum += o['total_amount']
            
            text += f"📦 №{o['order_id']}\n👤 {o['user_name']}\n📞 {o['user_phone']}\n"
            text += f"🛒 {items_text}\n💰 {o['total_amount']}₽\n📊 {o['status']}\n\n"
            
            keyboard.append([InlineKeyboardButton(
                f"📋 Детали {o['order_id']}",
                callback_data=f"view_order_{o['order_id']}"
            )])
        
        text += f"ИТОГО: {total_sum}₽"
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="orders_back")])
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await query.edit_message_text(f"❌ Ошибка: {str(e)[:100]}")
    
    return ORDERS_MENU


async def show_orders_month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Заказы за месяц"""
    query = update.callback_query
    
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT order_id, user_name, items, total_amount, status
            FROM orders WHERE created_at >= datetime('now', '-30 days')
            ORDER BY created_at DESC
        ''')
        orders = cursor.fetchall()
        conn.close()
        
        if not orders:
            await query.edit_message_text("📭 Заказов за месяц нет")
            return ORDERS_MENU
        
        text = f"ЗАКАЗЫ ЗА МЕСЯЦ ({len(orders)} шт.)\n" + "=" * 30 + "\n\n"
        total_sum = 0
        
        for o in orders[:15]:
            total_sum += o['total_amount']
            text += f"📦 {o['order_id']} - {o['user_name']} - {o['total_amount']}₽\n"
        
        text += f"\nИТОГО: {total_sum}₽"
        
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="orders_back")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
    
    return ORDERS_MENU


async def show_order_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Детали заказа"""
    query = update.callback_query
    await query.answer()
    
    order_id = query.data.split('_')[2]
    order = db.get_order(order_id)
    
    if not order:
        await query.edit_message_text("❌ Заказ не найден")
        return ORDERS_MENU
    
    items = json.loads(order['items']) if order['items'] else []
    items_text = ""
    for i in items:
        items_text += f"  • {i['name']} x{i['quantity']} = {i['price'] * i['quantity']}₽\n"
    
    username_display = f" (@{order['username']})" if order['username'] else ""
    
    text = (
        f"📦 ЗАКАЗ №{order['order_id']}\n"
        f"{'=' * 30}\n\n"
        f"👤 {order['user_name']}{username_display}\n"
        f"📞 {order['user_phone']}\n"
        f"📅 {order['created_at'][:16]}\n\n"
        f"🛒 ТОВАРЫ:\n{items_text}\n"
        f"💰 Сумма: {order['total_amount']}₽\n"
        f"📍 {order['delivery_address']}\n"
        f"💬 {order['comment'] or '—'}\n\n"
        f"📊 Статус: {order['status']}"
    )
    
    keyboard = [
        [InlineKeyboardButton("📊 Изменить статус", callback_data=f"change_status_{order_id}")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_orders")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def change_status_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню выбора статуса"""
    query = update.callback_query
    await query.answer()
    
    order_id = query.data.split('_')[2]
    order = db.get_order(order_id)
    current_status = order['status'] if order else 'неизвестно'
    
    await query.edit_message_text(
        f"📊 ВЫБЕРИТЕ СТАТУС\n\nЗаказ №{order_id}\nТекущий: {current_status}",
        reply_markup=get_status_keyboard(order_id)
    )


async def set_order_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Установка статуса"""
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split('_')
    order_id = parts[2]
    new_status = parts[3]
    admin_id = update.effective_user.id
    
    success, result = db.update_order_status(order_id, new_status, admin_id)
    
    if not success:
        await query.edit_message_text(f"❌ Ошибка: {result}")
        return ORDERS_MENU
    
    try:
        await context.bot.send_message(
            result['user_id'],
            f"📦 Статус заказа №{order_id} обновлён:\n{ORDER_STATUSES.get(new_status, new_status)}"
        )
    except:
        pass
    
    await query.edit_message_text(
        f"✅ Статус обновлён: {ORDER_STATUSES.get(new_status, new_status)}"
    )
    await asyncio.sleep(2)
    return await back_to_orders(update, context)


async def back_to_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат к меню заказов"""
    query = update.callback_query
    await query.edit_message_text(
        "📋 УПРАВЛЕНИЕ ЗАКАЗАМИ\n\nВыберите период:",
        reply_markup=orders_menu_keyboard()
    )
    return ORDERS_MENU


# ============================================================
# СВЯЗЬ С КЛИЕНТАМИ, РАССЫЛКА, ПЕРИОД
# ============================================================

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
            SELECT DISTINCT o.user_id, o.user_name, o.user_phone, o.username,
                   COUNT(o.id) as orders_count, SUM(o.total_amount) as total_spent,
                   MAX(o.created_at) as last_order
            FROM orders o
            WHERE o.order_id LIKE ? OR o.user_name LIKE ? 
               OR o.user_phone LIKE ? OR o.username LIKE ?
            GROUP BY o.user_id ORDER BY last_order DESC LIMIT 10
        ''', (f'%{query_text}%', f'%{query_text}%', f'%{query_text}%', f'%{query_text}%'))
        clients = cursor.fetchall()
        conn.close()
        
        if not clients:
            await update.message.reply_text(
                "❌ Клиенты не найдены",
                reply_markup=get_admin_keyboard(user_id, db)
            )
            return ADMIN
        
        text = "👥 НАЙДЕННЫЕ КЛИЕНТЫ\n\n"
        keyboard = []
        
        for c in clients:
            username = f" (@{c['username']})" if c['username'] else ""
            text += f"👤 {c['user_name']}{username}\n📞 {c['user_phone']}\n"
            text += f"📦 {c['orders_count']} заказов на {c['total_spent'] or 0}₽\n\n"
            
            keyboard.append([InlineKeyboardButton(
                f"💬 Написать {c['user_name'][:20]}",
                callback_data=f"message_user_{c['user_id']}"
            )])
        
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_back")])
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        logger.error(f"❌ Ошибка поиска: {e}")
    
    return SEND_MESSAGE


async def send_message_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало отправки сообщения"""
    query = update.callback_query
    await query.answer()
    
    user_id = int(query.data.split('_')[2])
    context.user_data['target_user'] = user_id
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT first_name FROM users WHERE user_id = ?", (user_id,))
    user_info = cursor.fetchone()
    conn.close()
    
    user_name = user_info['first_name'] if user_info else str(user_id)
    
    await query.edit_message_text(
        f"💬 ОТПРАВКА\n\nПолучатель: {user_name}\n\nВведите текст:"
    )
    return SEND_MESSAGE


async def send_message_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправка сообщения"""
    text = update.message.text
    target_user = context.user_data.get('target_user')
    admin_id = update.effective_user.id
    
    if text in ["❌ Отмена", "🚪 Выход"]:
        return await exit_handler(update, context)
    
    if not target_user:
        await update.message.reply_text("❌ Ошибка")
        return ADMIN
    
    try:
        await context.bot.send_message(target_user, f"📨 От администратора:\n\n{text}")
        await update.message.reply_text("✅ Отправлено!", reply_markup=get_admin_keyboard(admin_id, db))
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")
    
    context.user_data.pop('target_user', None)
    return ADMIN


async def broadcast_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ввод текста рассылки"""
    text = update.message.text
    if text in ["❌ Отмена", "🚪 Выход"]:
        return await exit_handler(update, context)
    
    context.user_data['broadcast_text'] = text
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    total = cursor.fetchone()[0]
    conn.close()
    
    await update.message.reply_text(
        f"📢 ПОДТВЕРЖДЕНИЕ\n\nТекст:\n{text}\n\nПолучателей: {total}\n\nОтправить?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Да", callback_data="broadcast_confirm")],
            [InlineKeyboardButton("❌ Нет", callback_data="broadcast_cancel")]
        ])
    )
    return BROADCAST_CONFIRM


async def broadcast_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение рассылки"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "broadcast_cancel":
        await query.edit_message_text("❌ Отменено")
        return ADMIN
    
    text = context.user_data.get('broadcast_text')
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()
    
    await query.edit_message_text(f"📤 Отправка {len(users)} сообщений...")
    
    sent = failed = 0
    for user in users:
        try:
            await context.bot.send_message(user['user_id'], f"📢 {text}")
            sent += 1
            await asyncio.sleep(0.05)
        except:
            failed += 1
    
    await query.edit_message_text(f"✅ Готово!\n📨 Отправлено: {sent}\n❌ Ошибок: {failed}")
    context.user_data.pop('broadcast_text', None)
    await asyncio.sleep(2)
    return await back_to_admin(update, context)


async def period_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начальная дата"""
    text = update.message.text
    if text in ["❌ Отмена", "🚪 Выход"]:
        return await exit_handler(update, context)
    
    try:
        start = datetime.strptime(text, "%d.%m.%Y")
        context.user_data['period_start'] = start
        await update.message.reply_text("📅 Введите конечную дату (ДД.ММ.ГГГГ):", reply_markup=cancel_keyboard())
        return PERIOD_END
    except:
        await update.message.reply_text("❌ Неверный формат")
        return PERIOD_START


async def period_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Конечная дата"""
    text = update.message.text
    if text in ["❌ Отмена", "🚪 Выход"]:
        return await exit_handler(update, context)
    
    try:
        end = datetime.strptime(text, "%d.%m.%Y")
        start = context.user_data.get('period_start')
        
        if end < start:
            await update.message.reply_text("❌ Конец раньше начала")
            return PERIOD_END
        
        orders = db.get_orders(period='all')
        filtered = []
        total = 0
        for o in orders:
            order_date = datetime.strptime(o['created_at'][:10], "%Y-%m-%d")
            if start.date() <= order_date.date() <= end.date():
                filtered.append(o)
                total += o['total_amount']
        
        if not filtered:
            await update.message.reply_text("📭 Заказов нет")
            return ADMIN
        
        text = f"📋 ЗАКАЗЫ ({start.strftime('%d.%m.%Y')} - {end.strftime('%d.%m.%Y')})\n\n"
        for o in filtered[:10]:
            text += f"📦 {o['order_id']} - {o['user_name']} - {o['total_amount']}₽\n"
        text += f"\nИТОГО: {total}₽"
        
        await update.message.reply_text(text)
        context.user_data.pop('period_start', None)
        return ADMIN
    except Exception as e:
        await update.message.reply_text("❌ Неверный формат")
        return PERIOD_END


# ========== ВСПОМОГАТЕЛЬНЫЕ ==========

async def price_menu_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат в меню прайса"""
    query = update.callback_query
    await query.edit_message_text(
        "⚙️ УПРАВЛЕНИЕ ПРАЙСОМ\n\nВыберите действие:",
        reply_markup=price_menu_keyboard()
    )
    return PRICE_MENU


async def admin_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback для Назад"""
    return await back_to_admin(update, context)