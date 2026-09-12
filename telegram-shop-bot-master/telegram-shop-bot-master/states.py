# states.py
from telegram.ext import ConversationHandler

# ========== ОСНОВНЫЕ СОСТОЯНИЯ ==========
MAIN, ADMIN, SUPERADMIN = range(3)

# ========== УПРАВЛЕНИЕ ПРАЙСОМ ==========
PRICE_MENU, ORDERS_MENU = range(3, 5)
ADD_PRODUCT_NAME, ADD_PRODUCT_CATEGORY, ADD_PRODUCT_PRICE, ADD_PRODUCT_STOCK, ADD_PRODUCT_PHOTO = range(5, 10)
EDIT_PRODUCT_SELECT, EDIT_PRODUCT_FIELD, EDIT_PRODUCT_VALUE = range(10, 13)
DELETE_PRODUCT_SELECT, TOGGLE_STOCK_SELECT = range(13, 15)

# ========== ОФОРМЛЕНИЕ ЗАКАЗА ==========
ORDER_FIO, ORDER_PHONE, ORDER_PRODUCT, ORDER_QUANTITY, ORDER_ADDRESS, ORDER_COMMENT, ORDER_CONFIRM = range(15, 22)

# ========== УПРАВЛЕНИЕ КЛИЕНТАМИ ==========
SEARCH_CLIENT, SEND_MESSAGE, BROADCAST_TEXT, BROADCAST_CONFIRM = range(22, 26)

# ========== РЕФЕРАЛЫ И ЗАКАЗЫ ==========
REFERRAL, MY_ORDERS, PERIOD_START, PERIOD_END = range(26, 30)

# ========== УПРАВЛЕНИЕ МЕНЕДЖЕРАМИ И ИМПОРТ ==========
IMPORT_PRODUCTS, VIEW_MANAGERS, ADD_MANAGER_ID, REMOVE_MANAGER_ID = range(30, 34)

# ========== ⭐ УПРАВЛЕНИЕ КАТЕГОРИЯМИ (НОВОЕ) ==========
CATEGORY_MENU = 34              # Меню управления категориями
ADD_CATEGORY_NAME = 35          # Ввод названия новой категории
ADD_SUBCATEGORY_PARENT = 36     # Выбор родительской категории
ADD_SUBCATEGORY_NAME = 37       # Ввод названия подкатегории
DELETE_CATEGORY_SELECT = 38     # Выбор категории для удаления
EDIT_CATEGORY_SELECT = 39       # Выбор категории для редактирования
EDIT_CATEGORY_NAME = 40         # Ввод нового названия категории

# ========== ⭐ ВЫБОР КАТЕГОРИИ ПРИ ДОБАВЛЕНИИ ТОВАРА (НОВОЕ) ==========
SELECT_PRODUCT_CATEGORY = 41    # Выбор категории при добавлении товара
SELECT_PRODUCT_SUBCATEGORY = 42 # Выбор подкатегории при добавлении товара