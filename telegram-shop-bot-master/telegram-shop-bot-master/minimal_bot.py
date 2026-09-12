# minimal_bot.py
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

BOT_TOKEN = "8249331971:AAHB1vD72TwGNKVMNYVwLuVbkN_W1Kwqbcc"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Бот работает!")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    print("✅ Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()