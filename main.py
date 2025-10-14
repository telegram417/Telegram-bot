# main.py
import logging
import threading
import os
from typing import Optional

from flask import Flask
from telethon import TelegramClient

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, Message
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

# ------------------ Config & Keepalive Flask ------------------
server = Flask(__name__)


@server.route("/")
def home():
    return "✅ Anonymous Chat Bot is running!"


def run_flask():
    # Port Render provides via $PORT; default 10000 for local
    server.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))


# ------------------ Logging ------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------ Conversation states ------------------
(
    GENDER,
    AGE,
    LOCATION,
    INTEREST,
    EDIT_CHOICE,
    EDIT_VALUE,
) = range(6)

# ------------------ In-memory stores ------------------
# users: chat_id -> {gender, age, location, interest}
users: dict[int, dict] = {}
# waiting queue: list of chat_ids waiting to be paired
waiting_users: list[int] = []
# active pairs: chat_id -> partner_chat_id
active_chats: dict[int, int] = {}

# ------------------ Environment vars ------------------
TOKEN = os.getenv("BOT_TOKEN")
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")

if not TOKEN:
    raise SystemExit("❌ BOT_TOKEN environment variable is required.")

# Try to start Telethon client if API_ID/API_HASH provided (optional)
tg_client: Optional[TelegramClient] = None
try:
    if API_ID and API_HASH:
        tg_client = TelegramClient("anon_session", int(API_ID), API_HASH)
        tg_client.start(bot_token=TOKEN)
        logger.info("Telethon client started (optional).")
    else:
        logger.info("API_ID/API_HASH not provided — skipping Telethon client.")
except Exception:
    logger.exception("Telethon client failed to start (continuing without it).")
    tg_client = None


# ------------------ Helper functions ------------------


def is_profile_complete(chat_id: int) -> bool:
    data = users.get(chat_id)
    return bool(data) and all(k in data for k in ("gender", "age", "location", "interest"))


def format_profile(data: dict) -> str:
    # Nice emoji-rich multi-line profile
    return (
        f"👤 *Partner Info:*\n"
        f"• Gender: {data.get('gender','—')}\n"
        f"• Age: {data.get('age','—')}\n"
        f"• Location: {data.get('location','—')}\n"
        f"• Interest: {data.get('interest','—')}\n"
    )


def safe_enqueue(user_id: int):
    # avoid duplicates in waiting queue
    if user_id in waiting_users:
        return
    waiting_users.append(user_id)


def safe_dequeue(user_id: int):
    try:
        while user_id in waiting_users:
            waiting_users.remove(user_id)
    except ValueError:
        pass


def pair_users(a: int, b: int):
    active_chats[a] = b
    active_chats[b] = a


def unpair_user(chat_id: int) -> Optional[int]:
    """Remove pair for chat_id and return partner id if any."""
    partner = active_chats.pop(chat_id, None)
    if partner:
        active_chats.pop(partner, None)
    return partner


# ------------------ Start / Setup Flow ------------------


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    # reset any previous state
    users.pop(chat_id, None)
    safe_dequeue(chat_id)
    unpair_user(chat_id)

    await update.message.reply_text(
        "👋 *Welcome to Anonymous Chat Bot!* 🤫\n\n"
        "Before we start, create a small anonymous profile.\n\n"
        "What’s your gender? 🚻",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup([["👦 Male", "👧 Female", "🤖 Other"]], one_time_keyboard=True, resize_keyboard=True),
    )
    return GENDER


async def start_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_user.id
    users[chat_id] = {"gender": update.message.text}
    await update.message.reply_text("🎂 Nice! Now tell me your *age*.", parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    return AGE


async def start_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_user.id
    users.setdefault(chat_id, {})["age"] = update.message.text
    await update.message.reply_text("📍 Great. Where are you from? (You can write anything)")
    return LOCATION


async def start_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_user.id
    users.setdefault(chat_id, {})["location"] = update.message.text
    await update.message.reply_text("🎯 Cool — what are your interests? (e.g., music, games, travel)")
    return INTEREST


async def start_interest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_user.id
    users.setdefault(chat_id, {})["interest"] = update.message.text
    await update.message.reply_text(
        "✅ Profile complete!\n\n"
        "You can now use /find to meet someone anonymously 🔍\n"
        "Tip: try `/find female` or `/find male` to filter by gender.",
    )
    return ConversationHandler.END


# ------------------ Edit Flow ------------------


async def edit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_user.id
    if chat_id not in users:
        await update.message.reply_text("⚠️ You don't have a profile yet. Use /start to create one.")
        return ConversationHandler.END

    # show current profile before editing
    cur = users.get(chat_id, {})
    msg = (
        "✏️ *Edit profile*\n\n"
        f"Your current profile:\n{format_profile(cur)}\n"
        "What do you want to edit?"
    )
    await update.message.reply_text(
        msg,
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup([["👦 Gender", "🎂 Age"], ["📍 Location", "🎯 Interest"]], one_time_keyboard=True, resize_keyboard=True),
    )
    return EDIT_CHOICE


async def edit_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    field = None
    if "gender" in text:
        field = "gender"
        await update.message.reply_text("Select new gender:", reply_markup=ReplyKeyboardMarkup([["👦 Male", "👧 Female", "🤖 Other"]], one_time_keyboard=True))
    elif "age" in text:
        field = "age"
        await update.message.reply_text("Enter your new age:", reply_markup=ReplyKeyboardRemove())
    elif "location" in text:
        field = "location"
        await update.message.reply_text("Enter your new location:", reply_markup=ReplyKeyboardRemove())
    elif "interest" in text:
        field = "interest"
        await update.message.reply_text("Enter your new interest:", reply_markup=ReplyKeyboardRemove())
    else:
        await update.message.reply_text("❌ Invalid choice. Use /edit again.")
        return ConversationHandler.END

    context.user_data["edit_field"] = field
    return EDIT_VALUE


async def edit_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_user.id
    field = context.user_data.get("edit_field")
    if not field:
        await update.message.reply_text("⚠️ No field selected. Use /edit again.")
        return ConversationHandler.END

    users.setdefault(chat_id, {})[field] = update.message.text
    await update.message.reply_text(f"✅ *{field.capitalize()}* updated!", parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    context.user_data.pop("edit_field", None)
    return ConversationHandler.END


# ------------------ Matching & Chat Commands ------------------


async def find_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_user.id
    # guard: profile must be complete
    if not is_profile_complete(chat_id):
        await update.message.reply_text("⚠️ Please finish profile first with /start (gender, age, location, interest).")
        return

    # parse gender filter from command text if provided, e.g., "/find female"
    raw = update.message.text or ""
    gender_filter = None
    if "female" in raw.lower():
        gender_filter = "👧 Female"
    elif "male" in raw.lower():
        gender_filter = "👦 Male"

    if chat_id in active_chats:
        await update.message.reply_text("💬 You're already in a chat. Use /leave or /next.")
        return

    # look for match in waiting_users
    match_id = None
    for uid in waiting_users:
        if uid == chat_id:
            continue
        # ensure profile exists & complete
        if not is_profile_complete(uid):
            continue
        if gender_filter:
            if users.get(uid, {}).get("gender") == gender_filter:
                match_id = uid
                break
        else:
            match_id = uid
            break

    if match_id:
        safe_dequeue(match_id)
        pair_users(chat_id, match_id)

        # send both users partner profile details
        partner_profile = users.get(match_id, {})
        my_profile = users.get(chat_id, {})

        # to the caller
        await update.message.reply_text("💞 *Connected!* Say hi 👋\n\n" + format_profile(partner_profile), parse_mode="Markdown")
        # to the partner
        try:
            await context.bot.send_message(match_id, "💞 *Connected!* Say hi 👋\n\n" + format_profile(my_profile), parse_mode="Markdown")
        except Exception:
            # partner may have blocked bot or left; unpair and notify caller
            logger.exception("Failed to notify partner on connect. Unpairing.")
            unpair_user(chat_id)
            await update.message.reply_text("⚠️ Failed to connect (partner unavailable). Try /find again.")
    else:
        safe_enqueue(chat_id)
        await update.message.reply_text("🔎 Searching for a partner... please wait. Use /leave to cancel.")


async def leave_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_user.id
    partner = active_chats.get(chat_id)
    if partner:
        # notify partner
        try:
            await context.bot.send_message(partner, "⚠️ Your partner has left the chat. Use /find to meet someone new 🔍")
        except Exception:
            logger.exception("Failed notifying partner on leave.")
        unpair_user(chat_id)
        await update.message.reply_text("👋 You left the chat. Use /find to search again.")
    else:
        # if in waiting queue, remove
        safe_dequeue(chat_id)
        await update.message.reply_text("❌ You were not in a chat (or your search was cancelled).")


async def next_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_user.id
    partner = active_chats.get(chat_id)
    if partner:
        try:
            await context.bot.send_message(partner, "⚠️ Your partner skipped you and searched for someone new 🔁")
        except Exception:
            logger.exception("Failed notifying partner on next.")
        unpair_user(chat_id)
        # after unpairing, start new find
        await find_cmd(update, context)
    else:
        await update.message.reply_text("⚠️ You're not in a chat. Use /find to connect.")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📘 *Commands Guide*\n\n"
        "/start – Create or reset your profile 🧩\n"
        "/find – Find someone to chat 🔍\n"
        "/find male – Find a male 👦\n"
        "/find female – Find a female 👧\n"
        "/next – Skip current and find someone new 🔁\n"
        "/leave – Leave current chat 🚪\n"
        "/edit – Edit your profile ✏️\n"
        "/help – Show this message ℹ️\n\n"
        "✨ You can send *text, stickers, photos, videos, voice messages,* and *documents*.",
        parse_mode="Markdown",
    )


# ------------------ Relay messages to partner ------------------


async def relay_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg: Message = update.effective_message
    from_id = update.effective_chat.id

    # if not in active chat, ignore or prompt
    if from_id not in active_chats:
        # ignore non-command message if not chatting; optionally prompt
        # await update.message.reply_text("⚠️ You're not in a chat. Use /find to connect.")
        return

    to_id = active_chats.get(from_id)
    if not to_id:
        # cleanup just in case
        unpair_user(from_id)
        await update.message.reply_text("⚠️ Partner disconnected. Use /find to search again.")
        return

    try:
        # Prefer copy methods to preserve files and speed
        # python-telegram-bot v20.7: Message.copy(target_chat_id) exists on Message
        if msg.text and not (msg.sticker or msg.photo or msg.video or msg.voice or msg.document or msg.animation):
            # plain text
            await context.bot.send_message(chat_id=to_id, text=msg.text)
        else:
            # for media and non-text, use copy_message where available
            await context.bot.copy_message(chat_id=to_id, from_chat_id=from_id, message_id=msg.message_id)
    except Exception:
        logger.exception("Failed to forward message, unpairing.")
        # attempt to unpair silently
        partner = unpair_user(from_id)
        try:
            await context.bot.send_message(from_id, "⚠️ Failed to deliver message. Partner may have left. Use /find to search again.")
        except Exception:
            pass


# ------------------ Main: build app and handlers ------------------


def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # start/setup conversation
    start_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start_cmd)],
        states={
            GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, start_gender)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, start_age)],
            LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, start_location)],
            INTEREST: [MessageHandler(filters.TEXT & ~filters.COMMAND, start_interest)],
        },
        fallbacks=[],
    )

    # edit conversation
    edit_conv = ConversationHandler(
        entry_points=[CommandHandler("edit", edit_cmd)],
        states={
            EDIT_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_choice)],
            EDIT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_value)],
        },
        fallbacks=[],
    )

    app.add_handler(start_conv)
    app.add_handler(edit_conv)

    # commands
    app.add_handler(CommandHandler("find", find_cmd))
    app.add_handler(CommandHandler("leave", leave_cmd))
    app.add_handler(CommandHandler("next", next_cmd))
    app.add_handler(CommandHandler("help", help_cmd))

    # forward all non-command messages to partner (text/media)
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, relay_message))

    # run Flask (keepalive) + bot
    threading.Thread(target=run_flask).start()
    logger.info("Starting bot polling...")
    app.run_polling()


if __name__ == "__main__":
    main()
    
