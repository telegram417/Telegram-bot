import logging
import threading
import asyncio
import os
from flask import Flask
from telegram import Update, Bot
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# Telegram token from Render environment
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN environment variable is missing!")

bot = Bot(token=TOKEN)

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger("AnonChatBot")

# Flask app for Render health check
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ AnonChat Bot is alive and running on Render!"

# Anonymous chat state
waiting_users = set()
active_chats = {}

# ==================== BOT COMMANDS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to *AnonChat+!*\nType /find to meet someone new 👀",
        parse_mode="Markdown"
    )

async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in active_chats:
        await update.message.reply_text("⚠️ You’re already in a chat! Use /end to leave.")
        return

    if waiting_users:
        partner = waiting_users.pop()
        active_chats[user_id] = partner
        active_chats[partner] = user_id

        await context.bot.send_message(partner, "✅ Partner found! Say hi 👋")
        await update.message.reply_text("🎯 You’ve been connected! Start chatting.")
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
        await context.bot.send_message(partner, "❌ Your partner has left the chat.")
    await update.message.reply_text("👋 You left the chat.")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📘 *Commands List:*\n"
        "/start - Start the bot\n"
        "/find - Find a chat partner\n"
        "/end - End your chat\n"
        "/help - Show this message",
        parse_mode="Markdown"
    )

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in active_chats:
        partner = active_chats[user_id]
        await context.bot.send_message(partner, update.message.text)
    else:
        await update.message.reply_text("💬 Use /find to start chatting!")

# ==================== RUN BOTH BOT + FLASK ====================

async def run_bot():
    app_tg = ApplicationBuilder().token(TOKEN).build()

    app_tg.add_handler(CommandHandler("start", start))
    app_tg.add_handler(CommandHandler("find", find))
    app_tg.add_handler(CommandHandler("end", end))
    app_tg.add_handler(CommandHandler("help", help_cmd))
    app_tg.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    logger.info("🚀 Telegram bot started successfully.")
    await app_tg.run_polling()

def start_bot_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_bot())

if __name__ == "__main__":
    # Run bot in background thread
    threading.Thread(target=start_bot_thread, daemon=True).start()

    # Run Flask app
    app.run(host="0.0.0.0", port=10000)
