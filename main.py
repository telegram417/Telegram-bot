import os
import threading
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, CallbackQueryHandler
)

# 🔐 Tokens
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")

# 🌍 Create small Flask web server (for Render free hosting)
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Anonymous Telegram Bot is running!"

# 🧠 Data
users = {}
waiting = {"male": set(), "female": set(), "all": set()}
chats = {}

# 💬 Helper
def get_user_summary(user_id):
    user = users[user_id]
    return (
        f"👤 Gender: {user['gender']}\n"
        f"🎂 Age: {user['age']}\n"
        f"📍 Location: {user['location']}\n"
        f"🎯 Interest: {user['interest']}"
    )

# 🟢 /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    users[user_id] = {"stage": "gender"}
    await update.message.reply_text("👋 Welcome to *Anonymous Chat!*\n\nPlease enter your **gender** (Male/Female/Other):", parse_mode="Markdown")

# 🧍 Collect info
async def collect_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users:
        await update.message.reply_text("Please use /start first ⚙️")
        return

    user = users[user_id]
    text = update.message.text

    if user["stage"] == "gender":
        user["gender"] = text.lower()
        user["stage"] = "age"
        await update.message.reply_text("🎂 Enter your age:")
    elif user["stage"] == "age":
        user["age"] = text
        user["stage"] = "location"
        await update.message.reply_text("📍 Enter your location:")
    elif user["stage"] == "location":
        user["location"] = text
        user["stage"] = "interest"
        await update.message.reply_text("🎯 What are your interests?")
    elif user["stage"] == "interest":
        user["interest"] = text
        user["stage"] = "done"
        await update.message.reply_text("✅ Profile saved!\n\nUse /find to start chatting 🔍")
    else:
        if user_id in chats:
            partner_id = chats[user_id]
            await context.bot.send_message(partner_id, f"💬 Stranger: {text}")
        else:
            await update.message.reply_text("❗ You're not in a chat. Use /find to start.")

# 🔍 /find
async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users or users[user_id].get("stage") != "done":
        await update.message.reply_text("⚙️ Please complete your profile first with /start.")
        return

    if user_id in chats:
        await update.message.reply_text("❗ You're already chatting. Use /stop or /next.")
        return

    if waiting["all"]:
        partner_id = waiting["all"].pop()
        chats[user_id] = partner_id
        chats[partner_id] = user_id
        await context.bot.send_message(partner_id, f"🎉 Matched!\n\n{get_user_summary(user_id)}\n\nSay hi 👋")
        await update.message.reply_text(f"🎉 Found someone!\n\n{get_user_summary(partner_id)}\n\nStart chatting 👋")
    else:
        waiting["all"].add(user_id)
        await update.message.reply_text("🔎 Searching for someone... please wait!")

# ⏹️ /stop
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in chats:
        await update.message.reply_text("❗ You’re not in a chat.")
        return

    partner_id = chats.pop(user_id)
    chats.pop(partner_id, None)
    await context.bot.send_message(partner_id, "⚠️ The user left the chat.")

    keyboard = [
        [InlineKeyboardButton("👩 Search Female", callback_data="search_female")],
        [InlineKeyboardButton("👨 Search Male", callback_data="search_male")],
        [InlineKeyboardButton("🔁 Search Anyone", callback_data="search_any")]
    ]
    await update.message.reply_text(
        "✅ You left the chat.\nWant to find someone new?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# 🔄 /next
async def next_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await stop(update, context)
    await find(update, context)

# 📝 /edit
async def edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    users[user_id]["stage"] = "gender"
    await update.message.reply_text("📝 Let’s update your info!\nEnter your gender:")

# ℹ️ /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Anonymous Chat Commands*\n\n"
        "/start - Register 👤\n"
        "/find - Search 🔍\n"
        "/next - Find someone new 🔄\n"
        "/stop - Leave chat ⏹️\n"
        "/edit - Edit info 📝\n"
        "/help - Show help ℹ️\n\n"
        "You can send *text, stickers, voice, photos, and videos* 🎥🎤",
        parse_mode="Markdown"
    )

# 📸 Handle stickers, photos, etc.
async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in chats:
        partner_id = chats[user_id]
        if update.message.sticker:
            await context.bot.send_sticker(partner_id, update.message.sticker.file_id)
        elif update.message.photo:
            await context.bot.send_photo(partner_id, update.message.photo[-1].file_id)
        elif update.message.video:
            await context.bot.send_video(partner_id, update.message.video.file_id)
        elif update.message.voice:
            await context.bot.send_voice(partner_id, update.message.voice.file_id)
    else:
        await update.message.reply_text("❗ You're not chatting. Use /find to start.")

# 🔘 Buttons
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == "search_female":
        waiting["female"].add(user_id)
        await query.edit_message_text("🔎 Searching for a female...")
    elif data == "search_male":
        waiting["male"].add(user_id)
        await query.edit_message_text("🔎 Searching for a male...")
    elif data == "search_any":
        await find(update, context)

# 🧠 Bot thread
def run_bot():
    app_telegram = ApplicationBuilder().token(BOT_TOKEN).build()

    app_telegram.add_handler(CommandHandler("start", start))
    app_telegram.add_handler(CommandHandler("find", find))
    app_telegram.add_handler(CommandHandler("stop", stop))
    app_telegram.add_handler(CommandHandler("next", next_chat))
    app_telegram.add_handler(CommandHandler("edit", edit))
    app_telegram.add_handler(CommandHandler("help", help_command))
    app_telegram.add_handler(CallbackQueryHandler(button_handler))

    app_telegram.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, collect_info))
    app_telegram.add_handler(MessageHandler(filters.Sticker.ALL, handle_media))
    app_telegram.add_handler(MessageHandler(filters.PHOTO, handle_media))
    app_telegram.add_handler(MessageHandler(filters.VIDEO, handle_media))
    app_telegram.add_handler(MessageHandler(filters.VOICE, handle_media))

    print("🤖 Telegram bot running...")
    app_telegram.run_polling()

if __name__ == "__main__":
    # Run Telegram bot in separate thread
    threading.Thread(target=run_bot).start()

    # Run Flask web server for Render free plan
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
        
