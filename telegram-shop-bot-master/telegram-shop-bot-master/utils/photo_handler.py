import os
import aiofiles
import logging
from config import PHOTOS_DIR

logger = logging.getLogger(__name__)

class PhotoHandler:
    """Класс для работы с фото товаров"""
    
    def __init__(self):
        os.makedirs(PHOTOS_DIR, exist_ok=True)
    
    async def save_photo(self, file_id, bot, product_id=None):
        """Сохраняет фото локально и возвращает путь"""
        try:
            file = await bot.get_file(file_id)
            
            if product_id:
                filename = f"product_{product_id}.jpg"
            else:
                filename = f"{file_id}.jpg"
            
            file_path = os.path.join(PHOTOS_DIR, filename)
            await file.download_to_drive(file_path)
            
            logger.info(f"✅ Фото сохранено: {file_path}")
            return file_path
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения фото: {e}")
            return None
    
    async def get_photo(self, file_id, bot):
        """Получает фото из Telegram по file_id"""
        try:
            return await bot.get_file(file_id)
        except Exception as e:
            logger.error(f"❌ Ошибка получения фото: {e}")
            return None
    
    def get_photo_path(self, product_id):
        """Получает путь к фото товара"""
        return os.path.join(PHOTOS_DIR, f"product_{product_id}.jpg")
    
    def photo_exists(self, product_id):
        """Проверяет, существует ли фото товара"""
        return os.path.exists(self.get_photo_path(product_id))