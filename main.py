from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import os
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")




# Store user data
users = {}
waiting_users = []

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    users[user_id] = {"gender": None, "partner": None}

    keyboard = [["Male", "Female"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

    await update.message.reply_text(
        "👋 Welcome! Please select your gender:",
        reply_markup=reply_markup
    )

async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ *About This Bot*\n\n"
        "This is an anonymous dating chat bot 💌\n\n"
        "Commands:\n"
        "👉 /start - Set your gender\n"
        "👉 /find - Find a random partner\n"
        "👉 /stop - Leave the chat\n"
        "👉 /about - Show this help\n\n"
        "✨ Stay safe & have fun!",
        parse_mode="Markdown"
    )

async def gender_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if text in ["Male", "Female"]:
        users[user_id]["gender"] = text
        await update.message.reply_text("✅ Gender set! Type /find to match with someone.")
    else:
        if user_id in users and users[user_id].get("partner"):
            partner_id = users[user_id]["partner"]
            await context.bot.send_message(partner_id, text)
        else:
            await update.message.reply_text("⚠️ Please select Male or Female first.")

async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users or not users[user_id]["gender"]:
        await update.message.reply_text("⚠️ Please set your gender first using /start.")
        return

    if waiting_users and waiting_users[0] != user_id:
        partner_id = waiting_users.pop(0)
        users[user_id]["partner"] = partner_id
        users[partner_id]["partner"] = user_id

        await context.bot.send_message(partner_id, "🎉 You are now connected! Say hi 👋")
        await context.bot.send_message(user_id, "🎉 You are now connected! Say hi 👋")
    else:
        waiting_users.append(user_id)
        await update.message.reply_text("⌛ Waiting for a match...")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users or not users[user_id].get("partner"):
        await update.message.reply_text("⚠️ You are not in a chat.")
        return

    partner_id = users[user_id]["partner"]

    users[user_id]["partner"] = None
    users[partner_id]["partner"] = None

    await context.bot.send_message(partner_id, "❌ Your partner has left the chat. Type /find to search again.")
    await context.bot.send_message(user_id, "✅ You left the chat. Type /find to meet someone new.")

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("find", find))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("about", about))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, gender_select))

    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
