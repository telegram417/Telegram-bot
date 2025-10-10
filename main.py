import asyncio
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

# In-memory data
users = {}
chat_pairs = {}
referrals = {}
premium_users = {}

# --- Helper functions ---
def get_profile(user_id):
    return users.get(user_id, {"gender": "N/A", "age": "N/A", "location": "N/A", "interest": "N/A"})

async def send_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "✨ **AnonChatPlush Help** ✨\n\n"
        "/start - Begin your anonymous journey\n"
        "/find - Search for a chat partner\n"
        "/stop - Leave the chat\n"
        "/next - Find another user\n"
        "/edit - Edit your profile\n"
        "/ref - Invite friends for premium\n"
        "/help - Show this message again\n\n"
        "🎧 You can send text, photos, voice, videos & stickers."
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# --- Commands ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    users[user_id] = {"gender": None, "age": None, "location": None, "interest": None}
    await update.message.reply_text(
        "👋 Welcome to *AnonChatPlush*!\nLet’s set up your profile.\n\n"
        "What's your gender? (Male/Female/Other)", parse_mode="Markdown"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_help(update, context)

async def ref(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    link = f"https://t.me/MeetAnonymousBOT?start={user_id}"
    referrals.setdefault(user_id, [])
    await update.message.reply_text(
        f"🎁 Share this link with friends:\n{link}\n\n"
        "Get *3 friends* to start the bot & earn *3 days premium!*",
        parse_mode="Markdown"
    )

async def edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    users[user_id] = {"gender": None, "age": None, "location": None, "interest": None}
    await update.message.reply_text("🪞 Profile reset! Please send your gender again.")

async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in chat_pairs:
        await update.message.reply_text("🔹 You’re already in a chat.")
        return

    for uid, partner in chat_pairs.items():
        if partner is None and uid != user_id:
            chat_pairs[uid] = user_id
            chat_pairs[user_id] = uid
            await context.bot.send_message(uid, "💫 You’re now connected! Say hi 👋")
            await context.bot.send_message(user_id, "💫 You’re now connected! Say hi 👋")
            return

    chat_pairs[user_id] = None
    await update.message.reply_text("🔍 Searching for a partner...")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    partner = chat_pairs.pop(user_id, None)
    if partner and partner in chat_pairs:
        chat_pairs.pop(partner, None)
        await context.bot.send_message(partner, "⚠️ Your partner left the chat.")
    await update.message.reply_text("🚪 You left the chat.")

async def next_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await stop(update, context)
    await find(update, context)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    partner = chat_pairs.get(user_id)
    if not partner:
        await update.message.reply_text("❗ You’re not chatting with anyone. Use /find.")
        return
    msg = update.message
    if msg.text:
        await context.bot.send_message(partner, msg.text)
    elif msg.photo:
        await context.bot.send_photo(partner, msg.photo[-1].file_id)
    elif msg.sticker:
        await context.bot.send_sticker(partner, msg.sticker.file_id)
    elif msg.voice:
        await context.bot.send_voice(partner, msg.voice.file_id)
    elif msg.video:
        await context.bot.send_video(partner, msg.video.file_id)

# --- Run bot ---
async def main():
    app = (
        ApplicationBuilder()
        .token("YOUR_TELEGRAM_BOT_TOKEN")
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("ref", ref))
    app.add_handler(CommandHandler("edit", edit))
    app.add_handler(CommandHandler("find", find))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("next", next_cmd))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, message_handler))

    print("🤖 Bot started successfully.")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
  
