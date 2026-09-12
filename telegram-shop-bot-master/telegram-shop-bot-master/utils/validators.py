import re

def validate_phone(phone):
    """Проверка корректности номера телефона и форматирование"""
    # Удаляем все кроме цифр
    digits = re.sub(r'\D', '', phone)
    
    if not digits:
        return False, "❌ Телефон не может быть пустым"
    
    if len(digits) < 10 or len(digits) > 15:
        return False, "❌ Номер должен содержать 10-15 цифр"
    
    # Форматируем номер
    if len(digits) == 11 and digits.startswith('8'):
        formatted = f"+7 ({digits[1:4]}) {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"
    elif len(digits) == 11 and digits.startswith('7'):
        formatted = f"+7 ({digits[1:4]}) {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"
    elif len(digits) == 10:
        formatted = f"+7 ({digits[0:3]}) {digits[3:6]}-{digits[6:8]}-{digits[8:10]}"
    else:
        formatted = f"+{digits}"
    
    return True, formatted