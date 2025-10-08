import os
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")

users = {}
waiting_users = []
premium_users = {"@tandoori123"}  # You are premium ✅


# ------------------------- ABOUT COMMAND -------------------------
async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💘 *About MeetAnonymousBot*\n\n"
        "Welcome to the safest place to chat anonymously! 💬\n\n"
        "✨ *Features:*\n"
        "• Anonymous random chat with strangers 🌍\n"
        "• Choose your gender to match 🔍\n"
        "• Send stickers and share vibes 🎨\n"
        "• Invite 5 friends to unlock Premium for 7 days 💝\n\n"
        "🔒 Stay respectful and enjoy meeting new people!\n\n"
        "👀 *Commands:*\n"
        "/start - Restart setup\n"
        "/find - Find someone to talk with\n"
        "/stop - Leave current chat\n"
        "/help - Show all commands\n"
        "/age - Set your age\n\n"
        "Invite 5 people to get *Premium* for 1 week!\n"
        "Premium users can view partner’s age and access exclusive chats. 💫",
        parse_mode="Markdown"
    )


# ------------------------- HELP COMMAND -------------------------
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Available Commands:*\n\n"
        "/start - Restart setup\n"
        "/find - Match with someone\n"
        "/stop - Leave chat\n"
        "/about - Learn about the bot\n"
        "/age - Set your age",
        parse_mode="Markdown"
    )


# ------------------------- START COMMAND -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["Male", "Female"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    users[update.effective_user.id] = {"gender": None, "age": None, "partner": None, "invites": 0}
    await update.message.reply_text(
        "👋 Welcome to *MeetAnonymousBot!*\n\nPlease select your gender:",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )


# ------------------------- AGE SETUP -------------------------
async def set_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users:
        users[user_id] = {"gender": None, "age": None, "partner": None, "invites": 0}

    if len(context.args) == 1 and context.args[0].isdigit():
        users[user_id]["age"] = int(context.args[0])
        await update.message.reply_text(f"✅ Age set to {context.args[0]}")
    else:
        await update.message.reply_text("⚠️ Use like: /age 20")


# ------------------------- GENDER SELECT -------------------------
async def gender_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if user_id not in users:
        users[user_id] = {"gender": None, "age": None, "partner": None, "invites": 0}

    if text in ["Male", "Female"]:
        users[user_id]["gender"] = text
        await update.message.reply_text("✅ Gender set! Now type /age <your age>")
    elif users[user_id].get("partner"):
        partner_id = users[user_id]["partner"]
        await context.bot.send_message(partner_id, text)
    else:
        await update.message.reply_text("⚠️ Please select Male or Female first.")


# ------------------------- STICKER HANDLER -------------------------
async def sticker_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in users and users[user_id].get("partner"):
        partner_id = users[user_id]["partner"]
        await context.bot.send_sticker(partner_id, update.message.sticker.file_id)
    else:
        await update.message.reply_text("⚠️ You are not in a chat.")


# ------------------------- FIND COMMAND -------------------------
async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "User"

    if user_id not in users or not users[user_id]["gender"]:
        await update.message.reply_text("⚠️ Please set your gender first using /start.")
        return

    if waiting_users and waiting_users[0] != user_id:
        partner_id = waiting_users.pop(0)
        users[user_id]["partner"] = partner_id
        users[partner_id]["partner"] = user_id

        partner_username = context.bot.get_chat(partner_id).username or "User"

        await context.bot.send_message(partner_id, "🎉 Connected! Say hi 👋")
        await update.message.reply_text("🎉 Connected! Say hi 👋")

        # Premium feature - show age
        if username in premium_users or partner_username in premium_users:
            age1 = users[user_id].get("age")
            age2 = users[partner_id].get("age")
            if age1 and age2:
                await update.message.reply_text(f"👀 Your partner's age: {age2}")
                await context.bot.send_message(partner_id, f"👀 Your partner's age: {age1}")
    else:
        waiting_users.append(user_id)
        await update.message.reply_text("⌛ Waiting for a match...")


# ------------------------- STOP COMMAND -------------------------
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users or not users[user_id].get("partner"):
        await update.message.reply_text("⚠️ You are not in a chat.")
        return

    partner_id = users[user_id]["partner"]
    users[user_id]["partner"] = None
    users[partner_id]["partner"] = None

    await context.bot.send_message(partner_id, "❌ Your partner left the chat.")
    await context.bot.send_message(user_id, "✅ You left the chat.")


# ------------------------- BUILD BOT -------------------------
def build_app(token):
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("about", about))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("find", find))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("age", set_age))
    app.add_handler(MessageHandler(filters.Sticker.ALL, sticker_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, gender_select))

    return app


# ------------------------- RUN BOT -------------------------
if __name__ == "__main__":
    if not TOKEN:
        print("❌ Missing BOT_TOKEN environment variable!")
    else:
        print("🤖 Bot running...")
        app = build_app(TOKEN)
        app.run_polling()
