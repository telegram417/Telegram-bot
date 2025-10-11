import asyncio
from flask import Flask
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

# --- Flask Setup (Render needs a running web server)
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "AnonChatPlush is running ✅"

@flask_app.route('/health')
def health():
    return "OK", 200

# --- Telegram Bot Setup ---
TOKEN = "YOUR_TELEGRAM_BOT_TOKEN_HERE"

# In-memory data
users = {}
chats = {}
premium_users = {}
ref_counts = {}

# --- Helper Functions ---
def is_free(user_id):
    return user_id not in premium_users

def user_profile(u):
    return users.get(u, {"gender": None, "age": None, "loc": None, "interest": None})

async def send_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🌐 *AnonChatPlush Commands:*\n\n"
        "💫 /start – Begin & set your profile\n"
        "🕵️ /find – Find someone to chat with\n"
        "⏹ /stop – End current chat\n"
        "🔁 /next – Skip to next chat\n"
        "💎 /ref – Share link to earn premium\n"
        "ℹ️ /help – Show this help message"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# --- Commands ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    users[uid] = {}
    await update.message.reply_text(
        "👋 Welcome to *AnonChatPlush*!\nLet's set up your profile 💫",
        parse_mode="Markdown"
    )
    await update.message.reply_text("👤 What's your gender? (Male/Female/Other)")
    context.user_data["setup"] = "gender"

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    msg = update.message.text

    if uid not in users:
        await update.message.reply_text("Type /start to begin 🚀")
        return

    setup_stage = context.user_data.get("setup")

    if setup_stage == "gender":
        users[uid]["gender"] = msg
        await update.message.reply_text("🎂 What's your age?")
        context.user_data["setup"] = "age"
    elif setup_stage == "age":
        users[uid]["age"] = msg
        await update.message.reply_text("📍 Your location?")
        context.user_data["setup"] = "loc"
    elif setup_stage == "loc":
        users[uid]["loc"] = msg
        await update.message.reply_text("💭 Your interests?")
        context.user_data["setup"] = "interest"
    elif setup_stage == "interest":
        users[uid]["interest"] = msg
        del context.user_data["setup"]
        await update.message.reply_text("✨ Profile saved! Use /find to meet someone.")
    elif uid in chats:
        partner = chats[uid]
        try:
            await context.bot.copy_message(chat_id=partner, from_chat_id=uid, message_id=update.message.message_id)
        except Exception:
            await update.message.reply_text("⚠️ Your partner left. Use /find again.")
            del chats[uid]
    else:
        await update.message.reply_text("You’re not in a chat. Use /find 💬")

async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if is_free(uid):
        await update.message.reply_text("💎 Premium only! Use /ref to unlock /find.")
        return

    for other_id in users:
        if other_id != uid and other_id not in chats:
            chats[uid] = other_id
            chats[other_id] = uid
            await update.message.reply_text("💞 Matched! Say hi 👋")
            await context.bot.send_message(other_id, "💞 Matched! Say hi 👋")
            return
    await update.message.reply_text("⌛ No one available now. Try again soon.")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    partner = chats.get(uid)
    if partner:
        await context.bot.send_message(partner, "❌ Partner left. Searching again...")
        del chats[partner]
        del chats[uid]
    await update.message.reply_text("🛑 You’ve left the chat.")

async def next_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await stop(update, context)
    await find(update, context)

async def ref(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ref_link = f"https://t.me/{context.bot.username}?start={uid}"
    ref_counts.setdefault(uid, 0)
    text = (
        f"🔗 Share this link:\n{ref_link}\n\n"
        "Invite 3 friends 🧑‍🤝‍🧑 to get 3 days of premium!\n"
        f"Progress: {ref_counts[uid]}/3"
    )
    await update.message.reply_text(text)

# --- Main Bot Runner ---
async def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", send_help))
    app.add_handler(CommandHandler("find", find))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("next", next_chat))
    app.add_handler(CommandHandler("ref", ref))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    print("Bot started successfully 🚀")
    await app.run_polling()

if __name__ == "__main__":
    import threading
    threading.Thread(target=lambda: flask_app.run(host="0.0.0.0", port=10000)).start()
    asyncio.run(main())
                    
