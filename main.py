import os
import threading
from telegram import Update, ChatAction
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from flask import Flask

# Flask keep-alive for Render
app_server = Flask("web")

@app_server.route("/")
def home():
    return "Bot is running! 🚀"

def run_flask():
    app_server.run(host="0.0.0.0", port=10000)

threading.Thread(target=run_flask).start()

# Get Telegram bot token
TOKEN = os.getenv("BOT_TOKEN")

# User data store (in-memory)
users = {}         # user_id -> profile
chats = {}         # user_id -> chatting with

# ---- Handlers ---- #

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    users[user_id] = {}
    await update.message.reply_text(
        "👋 Hello! Welcome to Anonymous Chat Bot!\n"
        "Let's start by knowing you better.\n\n"
        "❓ What is your gender? (Male/Female/Other)"
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    profile = users.get(user_id, {})

    # Step-based input
    if "gender" not in profile:
        profile["gender"] = text
        await update.message.reply_text("🎂 Great! How old are you?")
    elif "age" not in profile:
        profile["age"] = text
        await update.message.reply_text("📍 Your location?")
    elif "location" not in profile:
        profile["location"] = text
        await update.message.reply_text("💖 Your interest?")
    elif "interest" not in profile:
        profile["interest"] = text
        await update.message.reply_text(
            "✅ Profile completed!\nUse /find to start chatting anonymously.\n"
            "You can also edit your profile anytime with /edit"
        )
    else:
        # If chatting, send message to matched user
        if user_id in chats:
            other_id = chats[user_id]
            await context.bot.send_chat_action(chat_id=other_id, action=ChatAction.TYPING)
            await context.bot.send_message(chat_id=other_id, text=f"💬 Stranger: {text}")
        else:
            await update.message.reply_text("❗ Use /find to start chatting.")

    users[user_id] = profile

async def edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users:
        users[user_id] = {}
    await update.message.reply_text(
        "✏️ What do you want to edit?\nOptions: gender, age, location, interest"
    )

async def edit_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    field = update.message.text.lower()
    if user_id not in users:
        await update.message.reply_text("❗ You have no profile yet. Use /start first.")
        return
    if field in ["gender", "age", "location", "interest"]:
        await update.message.reply_text(f"🔹 Enter new value for {field}:")
        context.user_data["edit_field"] = field
    elif "edit_field" in context.user_data:
        field = context.user_data.pop("edit_field")
        users[user_id][field] = update.message.text
        await update.message.reply_text(f"✅ {field} updated successfully!")
    else:
        await update.message.reply_text("❗ Invalid option.")

async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users or len(users[user_id]) < 4:
        await update.message.reply_text("❗ Complete your profile first using /start.")
        return

    # Simple match: find first available user not chatting with anyone
    for uid, profile in users.items():
        if uid != user_id and uid not in chats:
            chats[user_id] = uid
            chats[uid] = user_id
            await update.message.reply_text(
                f"💬 You are now connected anonymously!\n"
                f"👤 Gender: {profile.get('gender')}\n"
                f"🎂 Age: {profile.get('age')}\n"
                f"📍 Location: {profile.get('location')}\n"
                f"💖 Interest: {profile.get('interest')}\n\n"
                "Type messages, send stickers, photos, voice, or video to chat."
            )
            await context.bot.send_message(
                chat_id=uid,
                text=f"💬 You are connected with a stranger!\n"
                f"👤 Gender: {users[user_id].get('gender')}\n"
                f"🎂 Age: {users[user_id].get('age')}\n"
                f"📍 Location: {users[user_id].get('location')}\n"
                f"💖 Interest: {users[user_id].get('interest')}"
            )
            return

    await update.message.reply_text("❗ No users available right now. Try again later.")

async def leave(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in chats:
        other_id = chats.pop(user_id)
        chats.pop(other_id, None)
        await update.message.reply_text("🚪 You left the chat.")
        await context.bot.send_message(chat_id=other_id, text="❌ Stranger left the chat.")
    else:
        await update.message.reply_text("❗ You are not in a chat.")

async def next_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await leave(update, context)
    await find(update, context)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 Commands:\n"
        "/start - Begin profile setup\n"
        "/find - Find a stranger to chat\n"
        "/edit - Edit your profile\n"
        "/leave - Leave current chat\n"
        "/next - Find next stranger\n"
        "/help - Show this message"
    )

# ---- Main ---- #
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("find", find))
    app.add_handler(CommandHandler("leave", leave))
    app.add_handler(CommandHandler("next", next_chat))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("edit", edit))

    # Message handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, edit_field))
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.VOICE | filters.STICKER, handle_text))

    print("🤖 Bot started. Running polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
    
