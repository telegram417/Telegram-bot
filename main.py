import os
import threading
from flask import Flask
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# 🌸 Load your bot token from Render environment variables
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("⚠️ BOT_TOKEN environment variable not set! Go to Render → Environment → Add Variable → Key: BOT_TOKEN, Value: your bot token.")

# Flask app (Render pings this to keep bot alive)
app = Flask(__name__)

@app.route('/')
def home():
    return "🌐 MeetAnonymousBOT is running smoothly!"

# In-memory data
users = {}
waiting_users = []

# --- Helper functions ---
def get_profile_text(user):
    return (
        f"🌸 *Profile*\n"
        f"👤 Gender: {user.get('gender', 'Not set')}\n"
        f"🎂 Age: {user.get('age', 'Not set')}\n"
        f"📍 Location: {user.get('location', 'Not set')}\n"
        f"🎯 Interest: {user.get('interest', 'Not set')}"
    )

# --- Commands ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    users[user_id] = users.get(user_id, {"chatting": None})
    gender_keyboard = [["👨 Male", "👩 Female"]]
    await update.message.reply_text(
        "👋 Welcome to *MeetAnonymousBOT*!\n\nLet's set up your profile 💫\nChoose your gender:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(gender_keyboard, one_time_keyboard=True, resize_keyboard=True)
    )

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if user_id not in users:
        await update.message.reply_text("⚠️ Please type /start to set up your profile first.")
        return

    user = users[user_id]

    # Setting gender
    if "gender" not in user:
        if "male" in text.lower():
            user["gender"] = "Male"
        elif "female" in text.lower():
            user["gender"] = "Female"
        else:
            await update.message.reply_text("⚠️ Please select 'Male' or 'Female' using the buttons.")
            return
        await update.message.reply_text("🎂 Great! Now send your *age* (just type a number):", parse_mode="Markdown")
        return

    # Setting age
    if "age" not in user:
        if text.isdigit():
            user["age"] = int(text)
            await update.message.reply_text("📍 Nice! Now send your *location*:", parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ Please enter a valid age (just a number).")
        return

    # Setting location
    if "location" not in user:
        user["location"] = text
        await update.message.reply_text("🎯 Cool! Lastly, type your *interest* (anything you like):", parse_mode="Markdown")
        return

    # Setting interest
    if "interest" not in user:
        user["interest"] = text
        await update.message.reply_text(
            f"✨ Profile complete!\n{get_profile_text(user)}\n\nType /find to meet someone new 👀",
            parse_mode="Markdown"
        )
        return

    # Chat relay
    partner_id = user.get("chatting")
    if partner_id:
        await context.bot.send_message(partner_id, f"{update.message.text}")
    else:
        await update.message.reply_text("⚠️ You’re not chatting with anyone. Type /find to start chatting 💬")

async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = users.get(user_id)
    if not user:
        await update.message.reply_text("⚠️ Please set up your profile with /start first.")
        return

    if user.get("chatting"):
        await update.message.reply_text("💬 You’re already chatting with someone!")
        return

    if user_id in waiting_users:
        await update.message.reply_text("⏳ You’re already searching for someone…")
        return

    if waiting_users:
        partner_id = waiting_users.pop(0)
        partner = users[partner_id]
        user["chatting"] = partner_id
        partner["chatting"] = user_id

        text_self = f"🌟 You’re now connected!\n\n{get_profile_text(partner)}\n\nStart chatting 💬"
        text_partner = f"🌟 You’re now connected!\n\n{get_profile_text(user)}\n\nSay hi 👋"

        await update.message.reply_text(text_self, parse_mode="Markdown")
        await context.bot.send_message(partner_id, text_partner, parse_mode="Markdown")
    else:
        waiting_users.append(user_id)
        await update.message.reply_text("🔍 Searching for someone... please wait a moment 🌙")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = users.get(user_id)
    if not user or not user.get("chatting"):
        await update.message.reply_text("⚠️ You’re not chatting right now.")
        return

    partner_id = user["chatting"]
    user["chatting"] = None
    if partner_id and partner_id in users:
        partner = users[partner_id]
        partner["chatting"] = None
        await context.bot.send_message(partner_id, "💔 Your partner left the chat.")
    await update.message.reply_text("❌ Chat ended. Type /find to search again 🔎")

# --- Run Telegram bot ---
def run_bot():
    app_bot = Application.builder().token(TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("find", find))
    app_bot.add_handler(CommandHandler("stop", stop))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    print("🤖 MeetAnonymousBOT is now running...")
    app_bot.run_polling()

# --- Start both Flask & Telegram threads ---
if __name__ == "__main__":
    threading.Thread(target=run_bot).start()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
    
