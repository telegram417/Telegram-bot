import os
import asyncio
from flask import Flask
from telegram import (
    Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    CommandHandler, MessageHandler, filters,
    CallbackQueryHandler, ApplicationBuilder, ContextTypes
)

# ---------------- CONFIG ----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
BASE_URL = os.environ.get("BASE_URL")
PORT = int(os.environ.get("PORT", 8080))

if not BOT_TOKEN or not BASE_URL:
    raise RuntimeError("❌ Set BOT_TOKEN and BASE_URL environment variables in Render settings.")

bot = Bot(token=BOT_TOKEN)
app = Flask(__name__)

# ---------------- DATABASE ----------------
users = {}
searching = set()
chats = {}

# ---------------- UTILITIES ----------------
def find_match(user_id):
    for uid in searching:
        if uid != user_id and users[uid]["gender"] != users[user_id]["gender"]:
            return uid
    return None

def user_info(uid):
    u = users.get(uid, {})
    return (
        f"👤 *Name:* {u.get('name', 'Unknown')}\n"
        f"🎯 *Gender:* {u.get('gender', 'Not set')}\n"
        f"🎂 *Age:* {u.get('age', 'Not set')}\n"
        f"📍 *Location:* {u.get('location', 'Not set')}\n"
        f"💫 *Interest:* {u.get('interest', 'Not set')}"
    )

# ---------------- HANDLERS ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    users[user.id] = {
        "name": user.first_name,
        "gender": "Not set",
        "age": "Not set",
        "location": "Not set",
        "interest": "Not set"
    }
    await update.message.reply_text(
        f"✨ Welcome {user.first_name}!\n"
        f"Use /profile to view your info 🪞\n"
        f"Use /edit to edit your profile ✏️\n"
        f"Use /find to start chatting 💬\n"
        f"Use /stop to end a chat ❌\n"
        f"Use /ref to find another user 🔁"
    )

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(user_info(update.effective_user.id), parse_mode="Markdown")

async def edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("👫 Gender", callback_data="edit_gender")],
        [InlineKeyboardButton("🎂 Age", callback_data="edit_age")],
        [InlineKeyboardButton("📍 Location", callback_data="edit_location")],
        [InlineKeyboardButton("💫 Interest", callback_data="edit_interest")],
    ]
    await update.message.reply_text("✨ Choose what to edit:", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    context.user_data["edit_field"] = query.data.split("_")[1]
    await query.edit_message_text(f"✏️ Send your new {context.user_data['edit_field']} value:")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if "edit_field" in context.user_data:
        field = context.user_data.pop("edit_field")
        users[uid][field] = update.message.text
        await update.message.reply_text(f"✅ {field.capitalize()} updated!")
        return

    if uid in chats:
        partner = chats[uid]
        msg = update.message
        if msg.text:
            await bot.send_message(partner, f"💬 Stranger: {msg.text}")
        elif msg.photo:
            await bot.send_photo(partner, msg.photo[-1].file_id)
        elif msg.video:
            await bot.send_video(partner, msg.video.file_id)
        elif msg.voice:
            await bot.send_voice(partner, msg.voice.file_id)
        elif msg.sticker:
            await bot.send_sticker(partner, msg.sticker.file_id)
    else:
        await update.message.reply_text("⚠️ You are not in a chat. Use /find to start.")

async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid in chats:
        await update.message.reply_text("🔸 You are already chatting!")
        return
    if uid in searching:
        await update.message.reply_text("⏳ Searching already...")
        return
    searching.add(uid)
    await update.message.reply_text("🔍 Looking for a match...")

    match = find_match(uid)
    if match:
        searching.remove(uid)
        searching.remove(match)
        chats[uid] = match
        chats[match] = uid
        await bot.send_message(uid, "💞 You are now connected! Say hi 👋")
        await bot.send_message(match, "💞 You are now connected! Say hi 👋")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid in chats:
        partner = chats.pop(uid)
        chats.pop(partner, None)
        await bot.send_message(partner, "🚫 Stranger left the chat.")
        await update.message.reply_text("❌ Chat ended.")
    else:
        await update.message.reply_text("⚠️ You are not in a chat.")

async def ref(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await stop(update, context)
    await find(update, context)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🧭 *Commands:*\n"
        "/find - Find a chat 💬\n"
        "/stop - End chat ❌\n"
        "/ref - Find new chat 🔁\n"
        "/profile - View your info 👤\n"
        "/edit - Edit your profile ✏️\n"
        "/help - Show this help menu 📘",
        parse_mode="Markdown"
    )

# ---------------- FLASK ROUTE ----------------
@app.route("/")
def home():
    return "🚀 MeetAnonymousBot is live!"

# ---------------- BOT LAUNCH ----------------
async def run_bot():
    app_telegram = ApplicationBuilder().token(BOT_TOKEN).build()
    app_telegram.add_handler(CommandHandler("start", start))
    app_telegram.add_handler(CommandHandler("profile", profile))
    app_telegram.add_handler(CommandHandler("edit", edit))
    app_telegram.add_handler(CommandHandler("find", find))
    app_telegram.add_handler(CommandHandler("stop", stop))
    app_telegram.add_handler(CommandHandler("ref", ref))
    app_telegram.add_handler(CommandHandler("help", help_command))
    app_telegram.add_handler(CallbackQueryHandler(button_handler))
    app_telegram.add_handler(MessageHandler(filters.ALL, message_handler))

    await app_telegram.bot.set_webhook(url=f"{BASE_URL}/{BOT_TOKEN}")
    await app_telegram.initialize()
    await app_telegram.start()
    print("✅ Webhook set and bot started successfully!")

# --- safe loop start (no DeprecationWarning) ---
async def startup():
    asyncio.create_task(run_bot())

asyncio.run(startup())
