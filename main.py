import os
import asyncio
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, CallbackQueryHandler
)

# 🔐 Tokens (set in Render dashboard)
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")

# 🌍 Flask mini server to keep Render alive
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Anonymous Telegram Bot is alive and running!"

# 🧠 Data store (in memory)
users = {}
waiting = {"male": set(), "female": set(), "any": set()}
chats = {}

# 💬 Helper
def get_user_summary(uid):
    u = users[uid]
    return (
        f"👤 Gender: {u['gender']}\n"
        f"🎂 Age: {u['age']}\n"
        f"📍 Location: {u['location']}\n"
        f"🎯 Interest: {u['interest']}"
    )

# 🟢 /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    users[uid] = {"stage": "gender"}
    await update.message.reply_text("👋 Welcome to *Anonymous Chat!*\n\nPlease enter your **gender** (Male/Female/Other):", parse_mode="Markdown")

# 🧍 Collect user info
async def collect_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in users:
        await update.message.reply_text("Use /start to register ⚙️")
        return

    u = users[uid]
    msg = update.message.text

    if u["stage"] == "gender":
        u["gender"] = msg.lower()
        u["stage"] = "age"
        await update.message.reply_text("🎂 Enter your age:")
    elif u["stage"] == "age":
        u["age"] = msg
        u["stage"] = "location"
        await update.message.reply_text("📍 Enter your location:")
    elif u["stage"] == "location":
        u["location"] = msg
        u["stage"] = "interest"
        await update.message.reply_text("🎯 What are your interests?")
    elif u["stage"] == "interest":
        u["interest"] = msg
        u["stage"] = "done"
        await update.message.reply_text("✅ Profile saved!\n\nUse /find to start chatting 🔍")
    else:
        if uid in chats:
            partner = chats[uid]
            await context.bot.copy_message(
                chat_id=partner,
                from_chat_id=update.effective_chat.id,
                message_id=update.message.message_id
            )
        else:
            await update.message.reply_text("❗ Not in chat. Use /find to start.")

# 🔍 Find chat partner
async def find_partner(update: Update, context: ContextTypes.DEFAULT_TYPE, pref="any"):
    uid = update.effective_user.id
    if uid not in users or users[uid].get("stage") != "done":
        await update.message.reply_text("⚙️ Please complete your profile first using /start.")
        return

    if uid in chats:
        await update.message.reply_text("❗ You’re already chatting. Use /stop or /next.")
        return

    opp_gender = "female" if users[uid]["gender"] == "male" else "male"
    pool = waiting[pref]

    # Try to match
    if pool:
        partner = pool.pop()
        chats[uid] = partner
        chats[partner] = uid
        await context.bot.send_message(partner, f"🎉 Matched!\n\n{get_user_summary(uid)}\n\nSay hi 👋")
        await update.message.reply_text(f"🎉 Found someone!\n\n{get_user_summary(partner)}\n\nStart chatting 👋")
    else:
        waiting[pref].add(uid)
        await update.message.reply_text("🔎 Searching for someone... Please wait!")

# Commands for search preferences
async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await find_partner(update, context, "any")

async def male(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await find_partner(update, context, "male")

async def female(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await find_partner(update, context, "female")

# ⏹️ Stop chat
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in chats:
        await update.message.reply_text("❗ You’re not in a chat.")
        return

    partner = chats.pop(uid)
    chats.pop(partner, None)
    await context.bot.send_message(partner, "⚠️ Your partner left the chat.")

    keyboard = [
        [InlineKeyboardButton("👩 Search Female", callback_data="female")],
        [InlineKeyboardButton("👨 Search Male", callback_data="male")],
        [InlineKeyboardButton("🔁 Search Anyone", callback_data="any")],
    ]
    await update.message.reply_text(
        "✅ Chat ended. Want to find a new partner?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# 🔄 Next
async def next_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await stop(update, context)
    await find(update, context)

# 📝 Edit
async def edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    users[uid]["stage"] = "gender"
    await update.message.reply_text("📝 Let's update your profile.\nEnter your gender:")

# ℹ️ Help
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Anonymous Chat Commands*\n\n"
        "/start - Register 👤\n"
        "/find - Random match 🔍\n"
        "/male - Find a male 🧑\n"
        "/female - Find a female 👩\n"
        "/anyone - Find anyone 🔁\n"
        "/stop - Leave chat ⏹️\n"
        "/next - Next partner 🔄\n"
        "/edit - Edit profile 📝\n"
        "/help - Show this help ℹ️\n\n"
        "You can send *text, photos, videos, stickers, voice*, everything 🎥🎤",
        parse_mode="Markdown"
    )

# 📸 Handle media
async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid in chats:
        partner = chats[uid]
        await context.bot.copy_message(
            chat_id=partner,
            from_chat_id=update.effective_chat.id,
            message_id=update.message.message_id
        )
    else:
        await update.message.reply_text("❗ You're not chatting right now. Use /find to start.")

# 🔘 Button handler
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    pref = query.data
    await query.edit_message_text(f"🔍 Searching for {pref} users...")
    await find_partner(update, context, pref)

# 🧠 Run bot async
async def run_bot():
    app_tg = ApplicationBuilder().token(BOT_TOKEN).build()
    app_tg.add_handler(CommandHandler("start", start))
    app_tg.add_handler(CommandHandler("find", find))
    app_tg.add_handler(CommandHandler("male", male))
    app_tg.add_handler(CommandHandler("female", female))
    app_tg.add_handler(CommandHandler("anyone", find))
    app_tg.add_handler(CommandHandler("stop", stop))
    app_tg.add_handler(CommandHandler("next", next_chat))
    app_tg.add_handler(CommandHandler("edit", edit))
    app_tg.add_handler(CommandHandler("help", help_cmd))
    app_tg.add_handler(CallbackQueryHandler(button))
    app_tg.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, collect_info))
    app_tg.add_handler(MessageHandler(filters.ALL & filters.COMMAND, handle_media))
    await app_tg.run_polling()

# 🔥 Run everything
if __name__ == "__main__":
    import threading
    threading.Thread(target=lambda: asyncio.run(run_bot())).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
        
