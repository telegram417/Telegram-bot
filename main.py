import logging
import threading
from flask import Flask, request
from telegram import Update, Bot
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
import asyncio
import os

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN environment variable missing!")

bot = Bot(token=TOKEN)

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger("AnonChatPlush")

# Flask app
app = Flask(__name__)

# Store anonymous chat pairs
waiting_users = set()
active_chats = {}

# ========================= Telegram Bot =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Welcome to *AnonChat+!* Type /find to connect!", parse_mode="Markdown")

async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in active_chats:
        await update.message.reply_text("⚠️ You are already chatting. Type /end to leave first.")
        return

    if waiting_users:
        partner = waiting_users.pop()
        active_chats[user_id] = partner
        active_chats[partner] = user_id
        await context.bot.send_message(partner, "🎯 You’ve been connected! Say hi 👋")
        await update.message.reply_text("✅ Partner found! Start chatting.")
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

async def msg_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in active_chats:
        partner = active_chats[user_id]
        await context.bot.send_message(partner, update.message.text)
    else:
        await update.message.reply_text("💬 Use /find to start chatting with someone!")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📘 *Commands List:*\n"
        "/start - Start the bot\n"
        "/find - Find a chat partner\n"
        "/end - End your chat\n"
        "/help - Show help message"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# ========================= Flask Routes =========================
@app.route('/')
def home():
    return "AnonChat+ is running ✅"

@app.route(f'/{TOKEN}', methods
