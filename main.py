import asyncio
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
)
import logging
import os
import aiohttp

# ================= LOGGING ====================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================= BOT TOKEN ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN_HERE")

# ================= GLOBAL DATA ====================
user_profiles = {}
waiting_users = []
active_chats = {}
user_states = {}
ping_interval = 600  # seconds (10 minutes uptime ping)

# ================== AESTHETIC TEXT ==================
def divider():
    return "━━━━━━━━━━━━━━━━━━━━━━━"

def sparkle(text):
    return f"✨ {text} ✨"

# ================== PROFILE CREATION ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_profiles[user_id] = {}
    user_states[user_id] = "gender"

    keyboard = [
        [InlineKeyboardButton("♂️ Male", callback_data="Male"),
         InlineKeyboardButton("♀️ Female", callback_data="Female")],
        [InlineKeyboardButton("🌈 Other", callback_data="Other")]
    ]
    await update.message.reply_text(
        f"{sparkle('Welcome to MeetAnonymous!')}\n\nLet's set up your profile 💫\n\nChoose your gender:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    state = user_states.get(user_id)

    await query.answer()

    if state == "gender":
        user_profiles[user_id]["gender"] = query.data
        user_states[user_id] = "age"
        await query.message.reply_text("🎂 Great! Now tell me your age (just send a number):", reply_markup=ReplyKeyboardRemove())

    elif state == "ref_gender":
        await search_user(update, context, gender_filter=query.data)
        await query.message.delete()

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = user_states.get(user_id)

    if state == "age":
        age = update.message.text.strip()
        if not age.isdigit():
            await update.message.reply_text("❗Please enter a valid number for your age.")
            return
        user_profiles[user_id]["age"] = age
        user_states[user_id] = "location"
        await update.message.reply_text("📍 Awesome! Where are you from? 🌏")

    elif state == "location":
        user_profiles[user_id]["location"] = update.message.text.strip()
        user_states[user_id] = "interest"
        await update.message.reply_text("🎯 Cool! What are your interests? (e.g., music, gaming, travel)")

    elif state == "interest":
        user_profiles[user_id]["interest"] = update.message.text.strip()
        user_states[user_id] = None
        await update.message.reply_text(
            f"✅ Profile created successfully!\n\n{divider()}\n👤 Gender: {user_profiles[user_id]['gender']}\n🎂 Age: {user_profiles[user_id]['age']}\n📍 Location: {user_profiles[user_id]['location']}\n🎯 Interest: {user_profiles[user_id]['interest']}\n{divider()}\n\nUse /find to start chatting 💌",
        )

    elif user_id in active_chats:
        partner_id = active_chats[user_id]
        try:
            await update.message.copy(chat_id=partner_id)
        except:
            await update.message.reply_text("⚠️ Could not deliver message to your partner.")
    else:
        await update.message.reply_text("💡 Use /find to start chatting!")

# ================= MATCHING =================
async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id in active_chats:
        await update.message.reply_text("⚠️ You're already chatting! Use /stop to end current chat.")
        return

    for waiting_id in waiting_users:
        if waiting_id != user_id and waiting_id not in active_chats:
            active_chats[user_id] = waiting_id
            active_chats[waiting_id] = user_id
            waiting_users.remove(waiting_id)

            await context.bot.send_message(waiting_id, "💫 Matched! You’re now chatting. Send any message to begin 💬")
            await update.message.reply_text("🎉 You’re now connected! Use /stop to end chat.")
            return

    waiting_users.append(user_id)
    await update.message.reply_text("🔍 Looking for someone to chat with... please wait 💫")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    partner_id = active_chats.pop(user_id, None)

    if partner_id:
        active_chats.pop(partner_id, None)
        await context.bot.send_message(partner_id, "❌ Your partner has left the chat.")
        await context.bot.send_message(user_id, "✅ You left the chat. Use /find to meet new people 💫")
    elif user_id in waiting_users:
        waiting_users.remove(user_id)
        await update.message.reply_text("🛑 You stopped searching.")
    else:
        await update.message.reply_text("ℹ️ You’re not chatting currently.")

async def next_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await stop(update, context)
    await find(update, context)

# ================= PROFILE COMMANDS =================
async def edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def ref(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("♂️ Male", callback_data="Male"),
         InlineKeyboardButton("♀️ Female", callback_data="Female"),
         InlineKeyboardButton("🌈 Other", callback_data="Other")]
    ]
    await update.message.reply_text("🔍 Choose a gender to search for:", reply_markup=InlineKeyboardMarkup(keyboard))
    user_states[update.effective_user.id] = "ref_gender"

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"{sparkle('MeetAnonymous Help Menu')}\n{divider()}\n"
        "💬 /start - Create or edit your profile\n"
        "🔎 /find - Find a random chat partner\n"
        "⏭️ /next - Skip current chat\n"
        "❌ /stop - End current chat\n"
        "🧭 /ref - Search by gender\n"
        "⚙️ /edit - Edit profile anytime\n"
        "💡 Send text, photos, stickers, videos or voice freely!\n"
        f"{divider()}\n💖 Made with love by @MeetAnonymousBOT"
    )

# ================= KEEP ALIVE (PING) =================
async def keep_alive():
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                await session.get("https://meetanonymous.onrender.com")  # Change to your uptime URL if needed
        except Exception as e:
            logger.warning(f"Ping failed: {e}")
        await asyncio.sleep(ping_interval)

# ================= MAIN =================
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("find", find))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("next", next_user))
    app.add_handler(CommandHandler("edit", edit))
    app.add_handler(CommandHandler("ref", ref))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.ALL, message_handler))

    asyncio.create_task(keep_alive())

    logger.info("Bot is running... 🚀")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
