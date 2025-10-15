import os
import threading
import time
import requests
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, CallbackQueryHandler
)

# --- CONFIG ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
APP_URL = os.getenv("RENDER_EXTERNAL_URL", "https://your-app-name.onrender.com")

# --- FLASK APP ---
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Bot is alive and running!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# --- KEEP-ALIVE PINGER ---
def ping_self():
    while True:
        try:
            requests.get(APP_URL)
        except Exception:
            pass
        time.sleep(600)  # every 10 minutes

# --- TELEGRAM BOT LOGIC ---
users = {}
waiting = {"any": set()}
chats = {}

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Bot is alive and ready! Use /find to start chatting.")

async def find(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if waiting["any"]:
        partner = waiting["any"].pop()
        chats[uid] = partner
        chats[partner] = uid
        await ctx.bot.send_message(partner, "🎉 Matched! Say hi 👋")
        await update.message.reply_text("🎉 Found someone! Start chatting 👋")
    else:
        waiting["any"].add(uid)
        await update.message.reply_text("🔍 Searching... please wait!")

async def stop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in chats:
        await update.message.reply_text("❗ You are not in a chat.")
        return
    partner = chats.pop(uid)
    chats.pop(partner, None)
    await ctx.bot.send_message(partner, "⚠️ Partner left.")
    await update.message.reply_text("✅ Chat ended.")

async def relay(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid in chats:
        partner = chats[uid]
        await ctx.bot.copy_message(partner, update.effective_chat.id, update.message.message_id)
    else:
        await update.message.reply_text("❗ Not chatting. Use /find.")

def run_bot():
    app_tg = ApplicationBuilder().token(BOT_TOKEN).build()
    app_tg.add_handler(CommandHandler("start", start))
    app_tg.add_handler(CommandHandler("find", find))
    app_tg.add_handler(CommandHandler("stop", stop))
    app_tg.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, relay))
    app_tg.run_polling(drop_pending_updates=True)

# --- MAIN ENTRYPOINT ---
if __name__ == "__main__":
    # Run the Telegram bot in a background thread
    threading.Thread(target=run_bot, daemon=True).start()

    # Start keep-alive ping thread
    threading.Thread(target=ping_self, daemon=True).start()

    # Run Flask in main thread (Render requires this)
    run_flask()
