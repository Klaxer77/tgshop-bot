# handlers/back_handlers.py
import logging
from telegram import Update
from telegram.ext import ContextTypes
from database import Database
from keyboards import *
from states import *  # ВАЖНО: импортируем все состояния

logger = logging.getLogger(__name__)
db = Database()

async def back_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Универсальный обработчик кнопки Назад"""
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("🔙 Возврат в главное меню...")
    
    user_id = update.effective_user.id
    logger.info(f"🔄 Кнопка 'Назад' нажата пользователем {user_id}")
    
    context.user_data.clear()
    
    if db.is_superadmin(user_id):
        await update.effective_chat.send_message(
            "👑 ГЛАВНОЕ МЕНЮ СУПЕРАДМИНИСТРАТОРА",
            reply_markup=superadmin_main_keyboard()
        )
        return SUPERADMIN
    elif db.is_manager(user_id):
        await update.effective_chat.send_message(
            "👔 ГЛАВНОЕ МЕНЮ МЕНЕДЖЕРА",
            reply_markup=manager_main_keyboard()
        )
        return ADMIN
    else:
        await update.effective_chat.send_message(
            "🏠 ГЛАВНОЕ МЕНЮ",
            reply_markup=user_main_keyboard()
        )
        return MAIN

async def back_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат в меню администратора"""
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("🔙 Возврат в главное меню...")
    
    await update.effective_chat.send_message(
        "👔 ГЛАВНОЕ МЕНЮ МЕНЕДЖЕРА",
        reply_markup=manager_main_keyboard()
    )
    return ADMIN

async def back_to_superadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат в меню суперадминистратора"""
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("🔙 Возврат в главное меню...")
    
    await update.effective_chat.send_message(
        "👑 ГЛАВНОЕ МЕНЮ СУПЕРАДМИНИСТРАТОРА",
        reply_markup=superadmin_main_keyboard()
    )
    return SUPERADMIN