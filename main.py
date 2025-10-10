import os
from flask import Flask
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# === ENVIRONMENT VARIABLES ===
TOKEN = os.getenv("BOT_TOKEN")
BASE_URL = os.getenv("BASE_URL")

if not TOKEN or not BASE_URL:
    raise RuntimeError("❌ Set BOT_TOKEN and BASE_URL environment variables in Render settings.")

# === GLOBAL STORAGE ===
users = {}
waiting_users = []

# === FLASK SERVER TO KEEP RENDER ALIVE ===
server = Flask(__name__)

@server.route('/')
def home():
    return "✅ MeetAnonymousBot is running happily on Render! 💫"

# === /START COMMAND ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    users[user_id] = {
        "gender": None,
        "age": None,
        "location": None,
        "interest": None,
        "partner": None,
    }

    keyboard = [["Male ♂", "Female ♀"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

    await update.message.reply_text(
        "👋 *Welcome to MeetAnonymousBot!*\n\n"
        "✨ Let's build your profile!\n"
        "Please select your *gender:*",
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )

# === HANDLE PROFILE CREATION ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    user = users.get(user_id)

    if not user:
        await start(update, context)
        return

    if not user["gender"]:
        if text in ["Male ♂", "Female ♀"]:
            user["gender"] = "Male" if "Male" in text else "Female"
            await update.message.reply_text("🎂 Great! How old are you?")
        else:
            await update.message.reply_text("⚠️ Please select a gender from the options above.")
        return

    if not user["age"]:
        if text.isdigit():
            user["age"] = text
            await update.message.reply_text("📍 Cool! Where are you from? (e.g. Delhi, India)")
        else:
            await update.message.reply_text("⚠️ Please enter a valid number for your age.")
        return

    if not user["location"]:
        user["location"] = text
        await update.message.reply_text("💭 Awesome! What are your interests? (e.g. Music, Gaming, Talking 💬)")
        return

    if not user["interest"]:
        user["interest"] = text
        await update.message.reply_text(
            "✅ *Profile Complete!*\n\n"
            f"👤 *Gender:* {user['gender']}\n"
            f"🎂 *Age:* {user['age']}\n"
            f"📍 *Location:* {user['location']}\n"
            f"💭 *Interest:* {user['interest']}\n\n"
            "Type /find to meet someone new 💌",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    # If user already chatting
    if user.get("partner"):
        partner_id = user["partner"]
        await forward_message(update, context, partner_id)
    else:
        await update.message.reply_text("⚠️ You’re not chatting. Type /find to start chatting 💫")

# === FORWARD MEDIA OR TEXT ===
async def forward_message(update: Update, context: ContextTypes.DEFAULT_TYPE, partner_id):
    msg = update.message
    if msg.text:
        await context.bot.send_message(partner_id, f"{msg.text}")
    elif msg.photo:
        await msg.forward(partner_id)
    elif msg.sticker:
        await msg.forward(partner_id)
    elif msg.voice:
        await msg.forward(partner_id)
    elif msg.video:
        await msg.forward(partner_id)
    elif msg.animation:
        await msg.forward(partner_id)

# === /FIND COMMAND ===
async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = users.get(user_id)

    if not user or not all([user["gender"], user["age"], user["location"], user["interest"]]):
        await update.message.reply_text("⚠️ Please complete your profile first using /start.")
        return

    if user.get("partner"):
        await update.message.reply_text("💬 You’re already chatting! Use /stop to end the chat.")
        return

    if waiting_users and waiting_users[0] != user_id:
        partner_id = waiting_users.pop(0)
        partner = users.get(partner_id)

        if partner and not partner.get("partner"):
            user["partner"] = partner_id
            partner["partner"] = user_id

            await update.message.reply_text("💞 Matched! Say hello 👋")
            await context.bot.send_message(partner_id, "💞 Matched! Say hello 👋")

            await show_partner_info(update, context, partner_id, user_id)
        else:
            await update.message.reply_text("⚠️ No one available right now. Try again in a few minutes!")
    else:
        waiting_users.append(user_id)
        await update.message.reply_text("🔎 Searching for your match... Please wait ⏳")

# === SHOW PARTNER INFO ===
async def show_partner_info(update, context, partner_id, user_id):
    partner = users[partner_id]
    user = users[user_id]

    info_partner = (
        f"✨ *Your partner's profile:*\n"
        f"👤 *Gender:* {partner['gender']}\n"
        f"🎂 *Age:* {partner['age']}\n"
        f"📍 *Location:* {partner['location']}\n"
        f"💭 *Interest:* {partner['interest']}"
    )

    info_user = (
        f"✨ *Your partner's profile:*\n"
        f"👤 *Gender:* {user['gender']}\n"
        f"🎂 *Age:* {user['age']}\n"
        f"📍 *Location:* {user['location']}\n"
        f"💭 *Interest:* {user['interest']}"
    )

    await update.message.reply_text(info_partner, parse_mode="Markdown")
    await context.bot.send_message(partner_id, info_user, parse_mode="Markdown")

# === /STOP COMMAND ===
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = users.get(user_id)

    if not user or not user.get("partner"):
        await update.message.reply_text("⚠️ You’re not chatting currently.")
        return

    partner_id = user["partner"]
    partner = users.get(partner_id)

    if partner:
        partner["partner"] = None
        await context.bot.send_message(partner_id, "❌ Your partner left the chat 💔\nType /find to meet someone new 💫")

    user["partner"] = None
    await update.message.reply_text("✅ You left the chat. Type /find to search again 💞")

# === /EDIT COMMAND ===
async def edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users:
        await update.message.reply_text("⚠️ Please start with /start first!")
        return

    users[user_id] = {
        "gender": None,
        "age": None,
        "location": None,
        "interest": None,
        "partner": None,
    }

    await update.message.reply_text("📝 Let’s edit your profile! Type /start again to rebuild it 💫")

# === /HELP COMMAND ===
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Available Commands:*\n\n"
        "/start - Setup your profile 🌸\n"
        "/find - Find someone to chat 💌\n"
        "/stop - Leave current chat ❌\n"
        "/edit - Edit your profile 📝\n"
        "/help - Show this help menu 📘",
        parse_mode="Markdown",
    )

# === BUILD APP ===
def build_app(token):
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("find", find))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("edit", edit))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    return app

# === MAIN RUN ===
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print("🚀 MeetAnonymousBot is running on Render... 🌍")

    from threading import Thread
    Thread(target=lambda: server.run(host="0.0.0.0", port=port)).start()

    app = build_app(TOKEN)
    app.run_polling()
                          
