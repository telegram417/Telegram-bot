import os
import threading
from flask import Flask
import requests
from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, CallbackQueryHandler
)

# --- CONFIG ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
APP_URL = os.getenv("RENDER_EXTERNAL_URL", "https://your-app-name.onrender.com")

app = Flask(__name__)

# --- DATA STORAGE ---
users = {}       # user_id: profile info
waiting = {"male": set(), "female": set(), "any": set()}
chats = {}       # user_id: partner_id

# --- FLASK ---
@app.route("/")
def home():
    return "✅ Anonymous Telegram Bot is Alive!"

# --- KEEP ALIVE (for uptimebot ping) ---
@app.route("/ping")
def ping():
    return "pong"

# --- COMMANDS ---

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    users[uid] = {"step": "gender"}
    await update.message.reply_text(
        "👋 Welcome to **Anonymous Chat!**\n\nLet's set up your profile.\n\n"
        "👉 What’s your gender? (male/female)",
        parse_mode="Markdown"
    )

async def process_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text

    if uid not in users:
        await update.message.reply_text("Please use /start first.")
        return

    step = users[uid].get("step")

    # --- SETUP PROCESS ---
    if step == "gender":
        users[uid]["gender"] = text.lower()
        users[uid]["step"] = "age"
        await update.message.reply_text("🎂 How old are you?")
    elif step == "age":
        users[uid]["age"] = text
        users[uid]["step"] = "location"
        await update.message.reply_text("📍 Where are you from?")
    elif step == "location":
        users[uid]["location"] = text
        users[uid]["step"] = "interest"
        await update.message.reply_text("💫 What are your interests?")
    elif step == "interest":
        users[uid]["interest"] = text
        users[uid]["step"] = "done"
        await update.message.reply_text(
            "✅ Profile saved! Use /find to start chatting.\n"
            "You can edit anytime with /edit."
        )
    else:
        # --- RELAY CHAT MESSAGES ---
        if uid in chats:
            partner = chats[uid]
            await ctx.bot.copy_message(partner, update.effective_chat.id, update.message.message_id)
        else:
            await update.message.reply_text("❗ You’re not in a chat. Use /find to start.")

async def find(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = users.get(uid)
    if not user or user.get("step") != "done":
        await update.message.reply_text("⚠️ Complete your profile first with /start.")
        return

    gender = user.get("gender", "any")
    opposite = "female" if gender == "male" else "male"
    found = None

    # Try to find opposite gender first
    if waiting[opposite]:
        found = waiting[opposite].pop()
    elif waiting["any"]:
        found = waiting["any"].pop()
    elif waiting[gender]:
        found = waiting[gender].pop()

    if found:
        chats[uid] = found
        chats[found] = uid

        p1 = users[uid]
        p2 = users[found]

        info1 = f"👤 {p1['gender'].title()}, {p1['age']} yrs\n📍 {p1['location']}\n💫 {p1['interest']}"
        info2 = f"👤 {p2['gender'].title()}, {p2['age']} yrs\n📍 {p2['location']}\n💫 {p2['interest']}"

        await ctx.bot.send_message(found, f"🎉 You’re connected!\n\nYour partner:\n{info1}")
        await update.message.reply_text(f"🎉 You’re connected!\n\nYour partner:\n{info2}")
    else:
        waiting["any"].add(uid)
        await update.message.reply_text("🔍 Searching for a partner... Please wait!")

async def stop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in chats:
        await update.message.reply_text("❗ You are not in a chat.")
        return
    partner = chats.pop(uid)
    chats.pop(partner, None)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔎 Search Female", callback_data="find_female")],
        [InlineKeyboardButton("🔎 Search Male", callback_data="find_male")],
    ])

    await ctx.bot.send_message(partner, "⚠️ Your partner left the chat.", reply_markup=keyboard)
    await update.message.reply_text("✅ Chat ended.", reply_markup=keyboard)

async def button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id

    if query.data == "find_female":
        waiting["female"].add(uid)
        await query.edit_message_text("🔍 Searching for a female partner...")
    elif query.data == "find_male":
        waiting["male"].add(uid)
        await query.edit_message_text("🔍 Searching for a male partner...")

async def edit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    users[uid] = {"step": "gender"}
    await update.message.reply_text("🛠️ Let’s update your profile!\nWhat’s your gender?")

async def help_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 **Bot Commands:**\n\n"
        "✅ /start – Register or restart your profile\n"
        "🔍 /find – Find a partner\n"
        "🚫 /stop – End current chat\n"
        "➡️ /next – Stop and find a new partner\n"
        "✏️ /edit – Edit profile (gender, age, etc.)\n"
        "ℹ️ /help – Show all commands\n\n"
        "You can send 🖼️ photos, 🎥 videos, 🎙️ voice, 🎧 stickers, or 💬 text.",
        parse_mode="Markdown"
    )

async def next_chat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await stop(update, ctx)
    await find(update, ctx)

# --- BOT RUNNER ---
def run_bot():
    app_tg = ApplicationBuilder().token(BOT_TOKEN).build()
    app_tg.add_handler(CommandHandler("start", start))
    app_tg.add_handler(CommandHandler("find", find))
    app_tg.add_handler(CommandHandler("stop", stop))
    app_tg.add_handler(CommandHandler("next", next_chat))
    app_tg.add_handler(CommandHandler("edit", edit))
    app_tg.add_handler(CommandHandler("help", help_command))
    app_tg.add_handler(CallbackQueryHandler(button))
    app_tg.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, process_message))
    app_tg.run_polling(drop_pending_updates=True)

# --- MAIN ---
if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
        
