import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)

# Enable logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Conversation states
GENDER, AGE, LOCATION, INTEREST = range(4)

# In-memory user data (not saved permanently)
users = {}
waiting_users = []
active_chats = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(
        "👋 Hey there! Welcome to *Anonymous Chat Bot* 🤫\n\n"
        "Let’s set up your profile.\n\n"
        "What’s your gender? 🚻",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            [["👦 Male", "👧 Female", "🤖 Other"]],
            one_time_keyboard=True
        )
    )
    return GENDER

async def gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users[update.effective_user.id] = {"gender": update.message.text}
    await update.message.reply_text("🎂 Great! Now tell me your age:", reply_markup=ReplyKeyboardRemove())
    return AGE

async def age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users[update.effective_user.id]["age"] = update.message.text
    await update.message.reply_text("📍 Where are you from? (Type anything)")
    return LOCATION

async def location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users[update.effective_user.id]["location"] = update.message.text
    await update.message.reply_text("🎯 What are your interests?")
    return INTEREST

async def interest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users[update.effective_user.id]["interest"] = update.message.text
    await update.message.reply_text(
        "✅ All set! You can now start chatting anonymously.\n\n"
        "Use /find to match with someone 🔍\n"
        "Use /help to see all commands ℹ️"
    )
    return ConversationHandler.END

async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip().lower() if update.message else ""
    gender_filter = None
    if "female" in text:
        gender_filter = "👧 Female"
    elif "male" in text:
        gender_filter = "👦 Male"

    if user_id in active_chats:
        await update.message.reply_text("💬 You’re already chatting. Use /leave to end it first.")
        return

    # Try to find a match
    match = None
    for uid in waiting_users:
        if uid != user_id:
            if gender_filter:
                if users.get(uid, {}).get("gender") == gender_filter:
                    match = uid
                    break
            else:
                match = uid
                break

    if match:
        waiting_users.remove(match)
        active_chats[user_id] = match
        active_chats[match] = user_id
        await update.message.reply_text("💞 Connected! Say hi 👋")
        await context.bot.send_message(match, "💞 Connected! Say hi 👋")
    else:
        waiting_users.append(user_id)
        await update.message.reply_text("🔍 Searching for a partner... Please wait ⏳")

async def leave(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in active_chats:
        partner_id = active_chats[user_id]
        await context.bot.send_message(partner_id, "⚠️ Your partner has left the chat.")
        del active_chats[partner_id]
        del active_chats[user_id]
        await update.message.reply_text("👋 You left the chat. Use /find to search again 🔎")
    else:
        await update.message.reply_text("❌ You’re not in a chat right now.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Available Commands:*\n\n"
        "/start – Set up your profile 🧩\n"
        "/find – Find a chat partner 🔍\n"
        "/find male – Find a male 👦\n"
        "/find female – Find a female 👧\n"
        "/leave – Leave current chat 🚪\n"
        "/help – Show this help message ℹ️",
        parse_mode="Markdown"
    )

async def forward_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in active_chats:
        partner_id = active_chats[user_id]
        await update.message.copy(partner_id)
    else:
        await update.message.reply_text("⚠️ You’re not in a chat. Use /find to connect!")

def main():
    TOKEN = "YOUR_BOT_TOKEN_HERE"
    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, gender)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, age)],
            LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, location)],
            INTEREST: [MessageHandler(filters.TEXT & ~filters.COMMAND, interest)],
        },
        fallbacks=[],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("find", find))
    app.add_handler(CommandHandler("leave", leave))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, forward_message))

    app.run_polling()

if __name__ == "__main__":
    main()
        
