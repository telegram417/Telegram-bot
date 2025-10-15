import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, CallbackQueryHandler
)

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Store user data
users = {}
waiting = set()
chats = {}

# 🌟 Helper functions
def get_user_summary(user_id):
    user = users[user_id]
    return (
        f"👤 Gender: {user['gender']}\n"
        f"🎂 Age: {user['age']}\n"
        f"📍 Location: {user['location']}\n"
        f"🎯 Interest: {user['interest']}"
    )

async def send_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔍 Search", callback_data="find")],
        [InlineKeyboardButton("📝 Edit Info", callback_data="edit")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")]
    ]
    await update.message.reply_text(
        "Choose an option 👇",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# 🟢 /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    users[user_id] = {"stage": "gender"}
    await update.message.reply_text("👋 Welcome to Anonymous Chat!\n\nPlease enter your gender (Male/Female/Other):")

# 🧍 Collect user info
async def collect_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users:
        await update.message.reply_text("Use /start first!")
        return

    user = users[user_id]
    text = update.message.text

    if user["stage"] == "gender":
        user["gender"] = text
        user["stage"] = "age"
        await update.message.reply_text("🎂 Enter your age:")
    elif user["stage"] == "age":
        user["age"] = text
        user["stage"] = "location"
        await update.message.reply_text("📍 Enter your location:")
    elif user["stage"] == "location":
        user["location"] = text
        user["stage"] = "interest"
        await update.message.reply_text("🎯 What are your interests?")
    elif user["stage"] == "interest":
        user["interest"] = text
        user["stage"] = "done"
        await update.message.reply_text("✅ Profile saved!\n\nUse /find to start chatting 🔍")
    else:
        # If chatting
        if user_id in chats:
            partner_id = chats[user_id]
            await context.bot.send_message(partner_id, f"💬 Stranger: {text}")
        else:
            await update.message.reply_text("❗ You're not in a chat. Use /find to start.")

# 🔍 /find command
async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in chats:
        await update.message.reply_text("❗ You're already chatting. Use /next or /stop.")
        return

    if user_id not in users or users[user_id].get("stage") != "done":
        await update.message.reply_text("⚙️ Please complete your profile with /start first.")
        return

    if waiting:
        partner_id = waiting.pop()
        chats[user_id] = partner_id
        chats[partner_id] = user_id

        await context.bot.send_message(
            user_id, f"🎉 Found a match!\n\n{get_user_summary(partner_id)}\n\nSay hi! 👋"
        )
        await context.bot.send_message(
            partner_id, f"🎉 Found a match!\n\n{get_user_summary(user_id)}\n\nSay hi! 👋"
        )
    else:
        waiting.add(user_id)
        await update.message.reply_text("🔎 Searching for someone... please wait!")

# ⏹️ /stop command
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in chats:
        await update.message.reply_text("❗ You're not in a chat.")
        return

    partner_id = chats.pop(user_id)
    chats.pop(partner_id, None)

    await context.bot.send_message(partner_id, "⚠️ The other user has left the chat.")
    await update.message.reply_text("✅ You have left the chat. Use /find to chat again.")

# 🔄 /next command
async def next_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await stop(update, context)
    await find(update, context)

# 📝 /edit command
async def edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    users[user_id]["stage"] = "gender"
    await update.message.reply_text("📝 Let's update your info!\nEnter your gender:")

# ℹ️ /help command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🤖 *Anonymous Chat Bot Commands*\n\n"
        "/start - Register your info 👤\n"
        "/find - Search for a partner 🔍\n"
        "/next - Find someone new 🔄\n"
        "/stop - Leave the current chat ⏹️\n"
        "/edit - Edit your info 📝\n"
        "/help - Show this help message ℹ️"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

# 🔘 Handle buttons
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "find":
        await find(update, context)
    elif data == "edit":
        await edit(update, context)
    elif data == "help":
        await help_command(update, context)

# 🚀 Main
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("find", find))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("next", next_chat))
    app.add_handler(CommandHandler("edit", edit))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, collect_info))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
    
