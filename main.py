import os
import json
import asyncio
from flask import Flask, request
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
)
from threading import Thread

# ====== Web Server ======
app = Flask(__name__)

@app.route('/')
def home():
    return "💘 MeetAnonymousBOT is alive and glowing 🌸"

@app.route('/webhook', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    asyncio.run(application.process_update(update))
    return "ok"

# ====== In-memory data ======
users = {}
active_chats = {}
DATA_FILE = "users.json"

def load_data():
    global users
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            users = json.load(f)

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(users, f)

def get_user(user_id):
    return users.get(str(user_id))

def set_user(user_id, data):
    users[str(user_id)] = data
    save_data()

# ====== Bot Functions ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user:
        keyboard = [["♂️ Male", "♀️ Female", "⚧️ Other"]]
        await update.message.reply_text(
            "🌸 **Welcome to MeetAnonymousBot!** 🌸\n\n"
            "Let's create your anonymous profile 💫",
            parse_mode="Markdown"
        )
        await update.message.reply_text(
            "💬 Choose your gender:",
            reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
        )
        return 1
    else:
        await update.message.reply_text(
            "🌼 You already have a profile! Use /profile to view or /update to change it."
        )
        return ConversationHandler.END

async def gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gender = update.message.text
    user_id = update.effective_user.id
    set_user(user_id, {"gender": gender})
    await update.message.reply_text("🎂 Please send your age (just number):")
    return 2

async def age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    age = update.message.text.strip()
    user_id = update.effective_user.id
    user = get_user(user_id)
    user["age"] = age
    set_user(user_id, user)
    await update.message.reply_text("📍 Please share your location (e.g. Delhi, India):")
    return 3

async def location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    loc = update.message.text
    user_id = update.effective_user.id
    user = get_user(user_id)
    user["location"] = loc
    set_user(user_id, user)
    await update.message.reply_text("💭 Now tell your interests or mood (anything you want):")
    return 4

async def interest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    interest = update.message.text
    user_id = update.effective_user.id
    user = get_user(user_id)
    user["interest"] = interest
    set_user(user_id, user)
    await update.message.reply_text(
        "✨ Profile setup complete!\n\n"
        "Use /find to meet someone new 💞\n"
        "Use /profile to view your info 🌸"
    )
    return ConversationHandler.END

# ====== Profile ======
async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if not user:
        await update.message.reply_text("❌ You don’t have a profile yet! Use /start first.")
        return
    msg = (
        f"👤 **Your Profile:**\n"
        f"💫 Gender: {user.get('gender','❔')}\n"
        f"🎂 Age: {user.get('age','❔')}\n"
        f"📍 Location: {user.get('location','❔')}\n"
        f"💭 Interest: {user.get('interest','❔')}\n"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

# ====== Search Animation ======
async def search_animation(update, context):
    messages = [
        "🌍 Searching across the galaxy...",
        "💫 Matching souls...",
        "✨ Reading vibes...",
        "❤️ Almost connected..."
    ]
    for msg in messages:
        await update.message.reply_text(msg)
        await asyncio.sleep(1.2)

# ====== Find Command ======
async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in active_chats:
        await update.message.reply_text("⚠️ You’re already in a chat!")
        return
    user = get_user(user_id)
    if not user:
        await update.message.reply_text("❌ Use /start to set up your profile first!")
        return
    await search_animation(update, context)
    for uid, udata in users.items():
        if int(uid) != user_id and uid not in active_chats and udata.get("gender") != user.get("gender"):
            partner_id = int(uid)
            active_chats[user_id] = partner_id
            active_chats[partner_id] = user_id
            p_text = (
                f"💞 You’ve been matched! 💞\n\n"
                f"👤 Gender: {udata.get('gender')}\n"
                f"🎂 Age: {udata.get('age')}\n"
                f"📍 Location: {udata.get('location')}\n"
                f"💭 Interest: {udata.get('interest')}\n"
                f"💌 Say hi!"
            )
            await update.message.reply_text(p_text)
            await context.bot.send_message(
                partner_id,
                f"💞 You’ve been matched!\n\n"
                f"👤 Gender: {user.get('gender')}\n"
                f"🎂 Age: {user.get('age')}\n"
                f"📍 Location: {user.get('location')}\n"
                f"💭 Interest: {user.get('interest')}\n"
                f"💌 Say hi!"
            )
            return
    await update.message.reply_text("😔 No match found yet. Try again later 💭")

# ====== Relay Messages ======
async def message_relay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender = update.effective_user.id
    if sender not in active_chats:
        await update.message.reply_text("⚠️ Not chatting yet. Use /find 💬")
        return
    receiver = active_chats[sender]
    try:
        await context.bot.copy_message(chat_id=receiver, from_chat_id=sender, message_id=update.message.message_id)
    except:
        await update.message.reply_text("⚠️ Failed to deliver message!")

# ====== Stop Chat ======
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in active_chats:
        await update.message.reply_text("❌ You’re not in a chat.")
        return
    partner_id = active_chats[user_id]
    del active_chats[user_id]
    if partner_id in active_chats:
        del active_chats[partner_id]
        await context.bot.send_message(partner_id, "💔 Your partner left the chat.")
    await update.message.reply_text("👋 You left the chat.")

# ====== Help ======
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💫 **MeetAnonymousBOT Commands** 💫\n\n"
        "🌸 /start – Create your profile\n"
        "🔍 /find – Find someone new\n"
        "👤 /profile – View your profile\n"
        "💔 /stop – End chat\n"
        "🌷 /help – Show this message again\n\n"
        "✨ Meet anonymously, connect genuinely 💘",
        parse_mode="Markdown"
    )

# ====== Telegram Application ======
BOT_TOKEN = "BOT_TOKEN"
WEBHOOK_URL = "https://telegram-bot-99.onrender.com"

application = Application.builder().token(TOKEN).build()

conv = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        1: [MessageHandler(filters.TEXT & ~filters.COMMAND, gender)],
        2: [MessageHandler(filters.TEXT & ~filters.COMMAND, age)],
        3: [MessageHandler(filters.TEXT & ~filters.COMMAND, location)],
        4: [MessageHandler(filters.TEXT & ~filters.COMMAND, interest)],
    },
    fallbacks=[]
)

application.add_handler(conv)
application.add_handler(CommandHandler("find", find))
application.add_handler(CommandHandler("profile", profile))
application.add_handler(CommandHandler("stop", stop))
application.add_handler(CommandHandler("help", help_cmd))
application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, message_relay))

# ====== Run Bot ======
async def run_bot():
    load_data()
    await application.bot.set_webhook(WEBHOOK_URL)
    print("🚀 Webhook set and MeetAnonymousBOT is live 🌸")

Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))).start()
asyncio.run(run_bot())
        
