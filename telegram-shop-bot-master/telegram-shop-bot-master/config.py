import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPER_ADMIN_IDS = [int(id.strip()) for id in os.getenv("SUPER_ADMIN_IDS", "").split(",") if id.strip()]

# Google Sheets
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

# Formspree
FORMSPREE_ENDPOINT = os.getenv("FORMSPREE_ENDPOINT")

# Настройки
PHOTOS_DIR = os.getenv("PHOTOS_DIR", "product_photos")

# Статусы заказов
ORDER_STATUSES = {
    'new': '🆕 Новый',
    'confirmed': '✅ Подтвержден',
    'processing': '🔄 В обработке',
    'paid': '💰 Оплачен',
    'shipped': '🚚 Отправлен',
    'delivered': '📦 Получен',
    'cancelled': '❌ Отменен'
}

# Доступные статусы для изменения
AVAILABLE_STATUSES = {
    'confirmed': '✅ Подтвержден',
    'processing': '🔄 В обработке',
    'paid': '💰 Оплачен',
    'shipped': '🚚 В пути',
    'delivered': '📬 Получен',
    'cancelled': '❌ Отменен'
}