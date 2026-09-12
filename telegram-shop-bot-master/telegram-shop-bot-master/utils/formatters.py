def format_phone(phone):
    """Форматирует номер телефона в читаемый вид"""
    # Если номер уже отформатирован, возвращаем как есть
    if '(' in phone and ')' in phone:
        return phone
    
    # Удаляем все кроме цифр
    digits = ''.join(filter(str.isdigit, phone))
    
    if len(digits) == 11:
        if digits.startswith('8'):
            return f"+7 ({digits[1:4]}) {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"
        elif digits.startswith('7'):
            return f"+7 ({digits[1:4]}) {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"
    elif len(digits) == 10:
        return f"+7 ({digits[0:3]}) {digits[3:6]}-{digits[6:8]}-{digits[8:10]}"
    
    return phone

def format_number(num):
    """Форматирование чисел с пробелами"""
    return f"{num:,.0f}".replace(",", " ")

def escape_markdown(text):
    """Экранирование спецсимволов для Markdown"""
    if not text:
        return ""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text