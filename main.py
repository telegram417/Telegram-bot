import os
import asyncio
import threading
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = "YOUR_BOT_TOKEN"
app = Application.builder().token(TOKEN).build()

# --- Fake webserver for Render ---
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)

# --- Bot Storage ---
users = {}
premium_users = set()
ref_links = {}

# --- Bot Commands ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.id
    text = (
        "👋 Welcome to *Anonymous Chat Bot!*\n\n"
        "Use these commands:\n"
        "/find - Find random chat (premium only)\n"
        "/stop - Stop chat\n"
        "/ref - Get your referral link to unlock premium\n\n"
        "Invite 3 people to unlock *Premium for 3 days!*"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def ref(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    link = f"https://t.me/{context.bot.username}?start=ref_{user_id}"
    ref_links[user_id] = ref_links.get(user_id, {"count": 0, "link": link})
    await update.message.reply_text(
        f"🎁 Your referral link:\n{link}\n\nShare it with friends!\n"
        "When 3 people click and start the bot, you’ll get Premium for 3 days."
    )

async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in premium_users:
        await update.message.reply_text("⚠️ You need *Premium* to use /find.\nUse /ref to unlock it!")
        return
    await update.message.reply_text("🔍 Searching for a partner... (coming soon)")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Chat stopped.")

# --- Handlers ---
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("ref", ref))
app.add_handler(CommandHandler("find", find))
app.add_handler(CommandHandler("stop", stop))

# --- Run Bot + Flask ---
def run_bot():
    asyncio.run(app.run_polling())

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    run_bot()
    
