import os
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# ==========================
# 🤖 CONFIG
# ==========================
TOKEN = os.environ.get("TELEGRAM_TOKEN")

# store users and pairs
user_data = {}      # chat_id → {"gender": str, "age": str, "location": str, "interest": str}
waiting = []        # users waiting
partners = {}       # chat_id → partner_chat_id


# ==========================
# 🚀 COMMANDS
# ==========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_data.pop(chat_id, None)  # reset
    partners.pop(chat_id, None)
    if chat_id in waiting:
        waiting.remove(chat_id)

    await update.message.reply_text(
        "👋 *Welcome to Anonymous Chat Bot!*\n\n"
        "Let’s create your anonymous profile 🕵️‍♂️\n"
        "First, tell me your **gender** 👇",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup([["👨 Male", "👩 Female"]], one_time_keyboard=True, resize_keyboard=True)
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (
        "🤖 *Anonymous Chat Bot Help*\n\n"
        "Here’s what you can do:\n"
        "• /start – restart bot and setup again\n"
        "• /find – find a random partner\n"
        "• /stop – leave current chat\n"
        "• /next – leave and find next partner\n"
        "• /help – show this help message\n\n"
        "You can send 💬 text, 🎧 voice, 🎥 video, 🖼️ photo, or 🤡 stickers!"
    )
    await update.message.reply_text(txt, parse_mode="Markdown")


# ==========================
# 🧍 USER SETUP FLOW
# ==========================

async def handle_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    msg = update.message.text

    # create entry if not exists
    if chat_id not in user_data:
        user_data[chat_id] = {}

    data = user_data[chat_id]

    # gender
    if "gender" not in data:
        data["gender"] = msg.replace("👨", "Male").replace("👩", "Female")
        await update.message.reply_text("🎂 Great! Now send me your *age* 👇", parse_mode="Markdown")
        return

    # age
    if "age" not in data:
        data["age"] = msg
        await update.message.reply_text("📍 Cool! Where are you from? (you can type anything)")
        return

    # location
    if "location" not in data:
        data["location"] = msg
        await update.message.reply_text("💭 Nice! What are your *interests*? (like music, games, travel...)", parse_mode="Markdown")
        return

    # interest
    if "interest" not in data:
        data["interest"] = msg
        await update.message.reply_text(
            f"✅ Profile created!\n\n"
            f"👤 *Gender:* {data['gender']}\n"
            f"🎂 *Age:* {data['age']}\n"
            f"📍 *Location:* {data['location']}\n"
            f"💭 *Interests:* {data['interest']}\n\n"
            "Now type /find to start chatting anonymously 🔎",
            parse_mode="Markdown"
        )
        return


# ==========================
# 💬 CHAT SYSTEM
# ==========================

async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    app = context.application

    # make sure user completed setup
    if chat_id not in user_data or "interest" not in user_data[chat_id]:
        await app.bot.send_message(chat_id, "⚠️ Please finish your setup first using /start.")
        return

    # already chatting
    if chat_id in partners:
        await app.bot.send_message(chat_id, "💬 You’re already chatting! Use /stop to end.")
        return

    # try to match
    if waiting:
        partner = waiting.pop(0)
        partners[chat_id] = partner
        partners[partner] = chat_id
        await app.bot.send_message(chat_id, "✅ You’re now connected! Say hi 👋")
        await app.bot.send_message(partner, "✅ You’re now connected! Say hi 👋")
    else:
        waiting.append(chat_id)
        await app.bot.send_message(chat_id, "🔎 Searching for a partner... Please wait ⏳")


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    app = context.application

    # cancel search
    if chat_id in waiting:
        waiting.remove(chat_id)
        await app.bot.send_message(chat_id, "❌ Search canceled.")
        return

    # end chat
    if chat_id in partners:
        partner = partners.pop(chat_id)
        partners.pop(partner, None)
        await app.bot.send_message(chat_id, "👋 You left the chat.")
        await app.bot.send_message(partner, "⚠️ Your partner left the chat.")
    else:
        await app.bot.send_message(chat_id, "⚠️ You are not in a chat.")


async def next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await stop(update, context)
    await find(update, context)


# ==========================
# 🔁 RELAY MESSAGES
# ==========================

async def relay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    chat_id = msg.chat_id
    app = context.application

    if chat_id not in partners:
        return

    partner = partners[chat_id]
    await app.bot.copy_message(partner, chat_id, msg.message_id)


# ==========================
# 🚀 MAIN
# ==========================

def main():
    if not TOKEN:
        raise SystemExit("Please set TELEGRAM_TOKEN env variable!")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("find", find))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("next", next))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_setup))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, relay))

    app.run_polling()


if __name__ == "__main__":
    main()
