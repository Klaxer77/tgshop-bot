# handlers/common.py
import logging
from telegram import Update
from telegram.ext import ContextTypes
from database import Database
from keyboards import *
from states import *

logger = logging.getLogger(__name__)
db = Database()

async def exit_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выхода в главное меню"""
    user = update.effective_user
    user_id = user.id
    
    logger.info(f"🚪 Выход в главное меню пользователем {user_id}")
    
    context.user_data.clear()
    
    if db.is_superadmin(user_id):
        await update.message.reply_text(
            "👑 ГЛАВНОЕ МЕНЮ СУПЕРАДМИНИСТРАТОРА",
            reply_markup=superadmin_main_keyboard()
        )
        return SUPERADMIN
    elif db.is_manager(user_id):
        await update.message.reply_text(
            "👔 ГЛАВНОЕ МЕНЮ МЕНЕДЖЕРА",
            reply_markup=manager_main_keyboard()
        )
        return ADMIN
    else:
        await update.message.reply_text(
            "🏠 ГЛАВНОЕ МЕНЮ",
            reply_markup=user_main_keyboard()
        )
        return MAIN