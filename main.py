import os
import threading
import asyncio
import logging
import time
from flask import Flask
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN is missing!")

app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot server is alive — Telegram bot connected!"

# Logger setup
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger("AnonChat")

waiting_users = set()
active_chats = {}

# ==== Commands ====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to *AnonChat+*!\nUse /find to connect with someone.",
        parse_mode="Markdown"
    )

async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in active_chats:
        await update.message.reply_text("⚠️ You’re already chatting! Use /end to leave.")
        return

    if waiting_users:
        partner = waiting_users.pop()
        active_chats[user_id] = partner
        active_chats[partner] = user_id
        await context.bot.send_message(partner, "✅ Partner found! Say hi 👋")
        await update.message.reply_text("🎯 Partner connected! Start chatting now.")
    else:
        waiting_users.add(user_id)
        await update.message.reply_text("⌛ Waiting for a partner...")

async def end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in active_chats:
        await update.message.reply_text("❌ You’re not chatting right now.")
        return

    partner = active_chats.pop(user_id)
    if partner in active_chats:
        active_chats.pop(partner)
        await context.bot.send_message(partner, "🚫 Your partner has left the chat.")
    await update.message.reply_text("👋 You left the chat.")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in active_chats:
        partner = active_chats[user_id]
        try:
            await context.bot.send_message(partner, update.message.text)
        except Exception as e:
            logger.error(f"Message failed: {e}")
    else:
        await update.message.reply_text("💬 Use /find to start chatting!")

# ==== Bot runner with reconnect ====

async def run_bot_forever():
    """Keeps reconnecting the bot if Telegram API disconnects."""
    while True:
        try:
            app_tg = (
                ApplicationBuilder()
                .token(TOKEN)
                .read_timeout(10)
                .write_timeout(10)
                .build()
            )

            app_tg.add_handler(CommandHandler("start", start))
            app_tg.add_handler(CommandHandler("find", find))
            app_tg.add_handler(CommandHandler("end", end))
            app_tg.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

            logger.info("🚀 Bot connected to Telegram successfully.")
            await app_tg.run_polling()
        except Exception as e:
            logger.error(f"Bot crashed: {e}, restarting in 5s...")
            time.sleep(5)

def start_bot_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_bot_forever())

if __name__ == "__main__":
    threading.Thread(target=start_bot_thread, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
