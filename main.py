import os
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")

users = {}
waiting_users = []
premium_users = {"@tandoori123"}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    users[user.id] = {"gender": None, "age": None, "partner": None, "invites": 0}
    keyboard = [["Male", "Female"]]
    markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("👋 Welcome! Please select your gender:", reply_markup=markup)

async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💘 *About MeetAnonymousBot*
"
        "Chat anonymously and meet new people.

"
        "Commands:
"
        "/start - Restart setup
"
        "/find - Find someone to talk with
"
        "/stop - Leave current chat
"
        "/help - Show all commands
"
        "/age - Set your age

"
        "Invite 5 people to get *Premium* for 1 week!
"
        "Premium users can view partner’s age and access exclusive chats.
",
        parse_mode="Markdown"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 Available Commands:
"
        "/start - Restart setup
"
        "/find - Match with someone
"
        "/stop - Leave chat
"
        "/about - Learn about the bot
"
        "/age - Set your age"
    )

async def set_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if len(context.args) == 1 and context.args[0].isdigit():
        users[user_id]["age"] = int(context.args[0])
        await update.message.reply_text(f"✅ Age set to {context.args[0]}")
    else:
        await update.message.reply_text("⚠️ Use like: /age 20")

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

async def sticker_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in users and users[user_id].get("partner"):
        partner_id = users[user_id]["partner"]
        await context.bot.send_sticker(partner_id, update.message.sticker.file_id)
    else:
        await update.message.reply_text("⚠️ You are not in a chat.")

async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users or not users[user_id]["gender"]:
        await update.message.reply_text("⚠️ Please set your gender first using /start.")
        return
    if waiting_users and waiting_users[0] != user_id:
        partner_id = waiting_users.pop(0)
        users[user_id]["partner"] = partner_id
        users[partner_id]["partner"] = user_id
        u_name = update.effective_user.username or "User"
        partner_name = context.bot.get_chat(partner_id).username or "User"
        await context.bot.send_message(partner_id, f"🎉 Connected! Say hi 👋")
        await update.message.reply_text("🎉 Connected! Say hi 👋")
        if u_name in premium_users or partner_name in premium_users:
            age_info1 = users[user_id].get("age")
            age_info2 = users[partner_id].get("age")
            if age_info1 and age_info2:
                await update.message.reply_text(f"👀 Your partner's age: {age_info2}")
                await context.bot.send_message(partner_id, f"👀 Your partner's age: {age_info1}")
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
    await context.bot.send_message(partner_id, "❌ Your partner left the chat.")
    await context.bot.send_message(user_id, "✅ You left the chat.")

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

if __name__ == "__main__":
    if not TOKEN:
        print("❌ Missing BOT_TOKEN environment variable!")
    else:
        print("🤖 Bot running...")
        app = build_app(TOKEN)
        app.run_polling()
        
