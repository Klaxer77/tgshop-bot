import requests
import logging
from config import FORMSPREE_ENDPOINT

logger = logging.getLogger(__name__)

class Formspree:
    """Класс для отправки заказов в Formspree"""
    
    def __init__(self):
        self.endpoint = FORMSPREE_ENDPOINT
    
    def send_order(self, order_data):
        """Отправка заказа в Formspree"""
        if not self.endpoint:
            logger.warning("⚠️ Formspree endpoint не настроен")
            return False
        
        try:
            # Подготовка данных для отправки
            data = {
                'order_id': order_data['order_id'],
                'customer_name': order_data['user_name'],
                'customer_phone': order_data['user_phone'],
                'customer_username': order_data['username'],
                'items': order_data['items'],
                'total': order_data['total_amount'],
                'address': order_data['delivery_address'],
                'comment': order_data.get('comment', ''),
                'created_at': order_data['created_at']
            }
            
            response = requests.post(
                self.endpoint,
                data=data,
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info(f"✅ Заказ {order_data['order_id']} отправлен в Formspree")
                return True
            else:
                logger.error(f"❌ Ошибка Formspree: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка отправки в Formspree: {e}")
            return False