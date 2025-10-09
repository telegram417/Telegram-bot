import os
import json
import asyncio
from flask import Flask
from threading import Thread
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
)

# ====== Web server for Render ======
app = Flask(__name__)

@app.route('/')
def home():
    return "💘 MeetAnonymousBOT is alive and glowing 🌸"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

Thread(target=run_web).start()

# ====== Global Variables ======
DATA_FILE = "users.json"
users = {}
active_chats = {}

# ====== Helper Functions ======
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

# ====== Start Command ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)

    if not user:
        await update.message.reply_text(
            "🌸 **Welcome to MeetAnonymousBot!** 🌸\n\n"
            "Let's create your anonymous profile 💫",
            parse_mode="Markdown"
        )
        keyboard = [["♂️ Male", "♀️ Female", "⚧️ Other"]]
        await update.message.reply_text(
            "💬 Choose your gender:",
            reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
        )
        return 1
    else:
        await update.message.reply_text(
            "🌼 You’re already registered! Use /profile to view or /update to change your info."
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
    await update.message.reply_text("📍 Please share your location (just text, e.g., Delhi, India):")
    return 3

async def location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    loc = update.message.text
    user_id = update.effective_user.id
    user = get_user(user_id)
    user["location"] = loc
    set_user(user_id, user)
    await update.message.reply_text("💭 Now tell us your interests or mood (anything you want to share):")
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

# ====== Profile Command ======
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

# ====== Update Command ======
async def update_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔄 What do you want to update?\nChoose one:",
        reply_markup=ReplyKeyboardMarkup(
            [["Gender", "Age"], ["Location", "Interest"]], one_time_keyboard=True
        )
    )
    return 5

async def update_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text.lower()
    user_id = update.effective_user.id
    context.user_data["update_choice"] = choice
    await update.message.reply_text(f"✏️ Send new {choice}:")
    return 6

async def update_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = update.message.text
    user_id = update.effective_user.id
    choice = context.user_data["update_choice"]
    user = get_user(user_id)
    user[choice] = val
    set_user(user_id, user)
    await update.message.reply_text("✅ Updated successfully! Use /profile to view changes 🌷")
    return ConversationHandler.END

# ====== Search Animation ======
async def search_animation(update, context):
    animations = [
        "🌍 Searching across the universe...",
        "💫 Matching souls...",
        "✨ Finding your vibe...",
        "❤️ Almost connected..."
    ]
    for msg in animations:
        await update.message.reply_text(msg)
        await asyncio.sleep(1.5)

# ====== Find Command ======
async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in active_chats:
        await update.message.reply_text("⚠️ You're already in a chat!")
        return

    user = get_user(user_id)
    if not user:
        await update.message.reply_text("❌ Please set up your profile using /start first.")
        return

    await search_animation(update, context)

    for uid, udata in users.items():
        if int(uid) != user_id and uid not in active_chats and udata.get("gender") != user.get("gender"):
            # match found
            partner_id = int(uid)
            active_chats[user_id] = partner_id
            active_chats[partner_id] = user_id

            profile_text = (
                f"💞 You’ve been matched! 💞\n\n"
                f"👤 Gender: {udata.get('gender')}\n"
                f"🎂 Age: {udata.get('age')}\n"
                f"📍 Location: {udata.get('location')}\n"
                f"💭 Interest: {udata.get('interest')}\n\n"
                f"💌 Say hi!"
            )
            await update.message.reply_text(profile_text)
            await context.bot.send_message(partner_id, 
                f"💞 You’ve been matched!\n\n"
                f"👤 Gender: {user.get('gender')}\n"
                f"🎂 Age: {user.get('age')}\n"
                f"📍 Location: {user.get('location')}\n"
                f"💭 Interest: {user.get('interest')}\n\n"
                f"💌 Say hi!"
            )
            return
    await update.message.reply_text("😔 No one is available right now. Try again later 💭")

# ====== Message Relay ======
async def message_relay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender = update.effective_user.id
    if sender not in active_chats:
        await update.message.reply_text("⚠️ You’re not chatting. Use /find to meet someone 💬")
        return
    receiver = active_chats[sender]
    try:
        await context.bot.copy_message(chat_id=receiver, from_chat_id=sender, message_id=update.message.message_id)
    except:
        await update.message.reply_text("⚠️ Failed to deliver message!")

# ====== Stop Command ======
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in active_chats:
        await update.message.reply_text("❌ You’re not in a chat right now.")
        return
    partner_id = active_chats[user_id]
    del active_chats[user_id]
    if partner_id in active_chats:
        del active_chats[partner_id]
        await context.bot.send_message(partner_id, "💔 Your partner left the chat.")
    await update.message.reply_text("👋 You left the chat.")

# ====== Help Command ======
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💫 **MeetAnonymousBOT Commands** 💫\n\n"
        "🌸 /start – Create your profile\n"
        "🔍 /find – Find someone new\n"
        "👤 /profile – View your profile\n"
        "✏️ /update – Change your info\n"
        "💔 /stop – End chat\n"
        "🌷 /help – Show this message again\n\n"
        "✨ Meet anonymously, connect genuinely 💘",
        parse_mode="Markdown"
    )

# ====== Main App ======
def main():
    load_data()
    TOKEN = "YOUR_TELEGRAM_BOT_TOKEN_HERE"  # replace with your real bot token
    app_ = Application.builder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            1: [MessageHandler(filters.TEXT & ~filters.COMMAND, gender)],
            2: [MessageHandler(filters.TEXT & ~filters.COMMAND, age)],
            3: [MessageHandler(filters.TEXT & ~filters.COMMAND, location)],
            4: [MessageHandler(filters.TEXT & ~filters.COMMAND, interest)],
            5: [MessageHandler(filters.TEXT & ~filters.COMMAND, update_profile)],
            6: [MessageHandler(filters.TEXT & ~filters.COMMAND, update_value)],
        },
        fallbacks=[]
    )

    app_.add_handler(conv)
    app_.add_handler(CommandHandler("find", find))
    app_.add_handler(CommandHandler("profile", profile))
    app_.add_handler(CommandHandler("update", update_profile))
    app_.add_handler(CommandHandler("stop", stop))
    app_.add_handler(CommandHandler("help", help_command))
    app_.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, message_relay))

    print("🚀 MeetAnonymousBOT is running...")
    app_.run_polling()

if __name__ == "__main__":
    main()
    
