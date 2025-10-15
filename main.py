# anon_match_bot.py
"""
Anonymous Telegram matching bot
Features:
- /start: register profile (gender, age, location, interest)
- /find: join queue and get matched with next available user
- /search <gender>: join queue but only match users with given gender
- /next: end current chat and search again
- /stop: end current chat (notifies partner)
- /edit: edit profile anytime
- /help: show commands
- Inline buttons for Next and Stop while chatting
- Persist to data.json
- Read BOT_TOKEN from environment (suitable for Render)
"""

import asyncio
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Dict, Optional

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputFile,
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

# ---------- Configuration ----------
BOT_TOKEN = os.getenv("BOT_TOKEN")  # set this on Render or local env
DATA_FILE = Path("data.json")
LOG_FILE = "anon_bot.log"

if not BOT_TOKEN:
    raise SystemExit("Please set BOT_TOKEN environment variable before running.")

# ---------- Logging ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# ---------- Persistence ----------
def load_data():
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.exception("Error loading data.json, starting fresh: %s", e)
    # Structure:
    # users: { str(user_id): {"gender":str,"age":str,"location":str,"interest":str} }
    # queue: [ {"user_id":str, "filter_gender": Optional[str]} , ... ]
    # sessions: { session_id: {"a": user_id, "b": user_id} } where user_id is str
    # user_session: { user_id: session_id } reverse map
    return {"users": {}, "queue": [], "sessions": {}, "user_session": {}}

def save_data(data):
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

DATA = load_data()

# ---------- Utilities ----------
def user_profile_text(uid: str) -> str:
    u = DATA["users"].get(str(uid), {})
    gender = u.get("gender", "—")
    age = u.get("age", "—")
    location = u.get("location", "—")
    interest = u.get("interest", "—")
    return (
        f"👤 Gender: {gender}\n"
        f"🎂 Age: {age}\n"
        f"📍 Location: {location}\n"
        f"✨ Interest: {interest}"
    )

def in_queue(uid: str) -> bool:
    return any(item["user_id"] == str(uid) for item in DATA["queue"])

def remove_from_queue(uid: str):
    DATA["queue"] = [item for item in DATA["queue"] if item["user_id"] != str(uid)]

def get_partner(user_id: str) -> Optional[str]:
    sid = DATA["user_session"].get(str(user_id))
    if not sid:
        return None
    s = DATA["sessions"].get(sid)
    if not s:
        return None
    if s["a"] == str(user_id):
        return s["b"]
    return s["a"]

def end_session_for(user_id: str):
    sid = DATA["user_session"].get(str(user_id))
    if not sid:
        return None
    s = DATA["sessions"].pop(sid, None)
    if not s:
        DATA["user_session"].pop(str(user_id), None)
        return None
    # remove both from user_session
    DATA["user_session"].pop(str(s["a"]), None)
    DATA["user_session"].pop(str(s["b"]), None)
    return s

def make_session(a: str, b: str):
    sid = str(uuid.uuid4())
    DATA["sessions"][sid] = {"a": str(a), "b": str(b)}
    DATA["user_session"][str(a)] = sid
    DATA["user_session"][str(b)] = sid
    return sid

def chat_buttons():
    kb = [
        [InlineKeyboardButton("➡️ Next", callback_data="next") , InlineKeyboardButton("⛔ Stop", callback_data="stop")],
    ]
    return InlineKeyboardMarkup(kb)

# ---------- Conversation flow for /start and /edit ----------
# We'll do a simple sequential state machine saved in memory per user
TEMP_STATE: Dict[str, dict] = {}  # { user_id: {"step": "gender"/"age"/..., "profile": {...}} }

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    await update.message.reply_text(
        "👋 Welcome! This bot connects you anonymously with other users.\n\n"
        "To begin, I'll ask 4 short questions. You can put anything for location/interest.\n"
        "Type /stop anytime to leave a chat.\n\n"
        "Let's start.\n\n"
        "💁 Please tell me your gender (e.g., Male / Female / Other / prefer not to say):"
    )
    TEMP_STATE[uid] = {"step": "gender", "profile": {}}

async def edit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    existing = DATA["users"].get(uid)
    if not existing:
        await update.message.reply_text("ℹ️ You don't have a profile yet. Use /start to create one.")
        return await start_cmd(update, context)
    # start editing by showing current and asking which field
    await update.message.reply_text(
        "✏️ You can edit your profile fields.\n"
        "Reply with the field name you want to edit: gender / age / location / interest\n\n"
        f"Current profile:\n{user_profile_text(uid)}"
    )
    TEMP_STATE[uid] = {"step": "choose_field", "profile": existing.copy()}

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❓ Help — Commands:\n"
        "/start - create your anonymous profile\n"
        "/find - search for next available user (no extra matching)\n"
        "/search <gender> - search but only match users with that gender (e.g. /search female)\n"
        "/next - leave current chat and find another\n"
        "/stop - stop current chat (other user is notified)\n"
        "/edit - edit your profile anytime\n"
        "/help - show this message\n\n"
        "While chatting you'll see buttons: ➡️ Next and ⛔ Stop.\n"
        "Profiles are shown exactly as users wrote them (gender, age, location, interest).\n"
        "Be kind and don't share personal contact info if you want to stay anonymous. 🤝"
    )

# ---------- Message handler for building profile / editing ----------
async def profile_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    text = (update.message.text or "").strip()
    if uid not in TEMP_STATE:
        await update.message.reply_text("I didn't expect that. Use /start to create a profile or /help for commands.")
        return

    state = TEMP_STATE[uid]
    step = state["step"]

    # sequential entry
    if step == "gender":
        state["profile"]["gender"] = text or "—"
        state["step"] = "age"
        await update.message.reply_text("🎂 Now tell me your age (you may type anything):")
        return
    if step == "age":
        state["profile"]["age"] = text or "—"
        state["step"] = "location"
        await update.message.reply_text("📍 Now tell me your location (can be anything):")
        return
    if step == "location":
        state["profile"]["location"] = text or "—"
        state["step"] = "interest"
        await update.message.reply_text("✨ Finally, tell me your interest (one line):")
        return
    if step == "interest":
        state["profile"]["interest"] = text or "—"
        # save profile
        DATA["users"][uid] = state["profile"]
        save_data(DATA)
        TEMP_STATE.pop(uid, None)
        await update.message.reply_text(
            "✅ Profile saved! Here is how it looks:\n\n" + user_profile_text(uid) + "\n\n"
            "Now use /find to search for someone or /search <gender> to restrict by gender."
        )
        return

    # editing flow
    if step == "choose_field":
        fld = text.lower()
        if fld not in ("gender", "age", "location", "interest"):
            await update.message.reply_text("Please reply with one of: gender / age / location / interest")
            return
        state["edit_field"] = fld
        state["step"] = "editing_field"
        await update.message.reply_text(f"Type the new value for *{fld}*:", parse_mode="Markdown")
        return
    if step == "editing_field":
        fld = state.get("edit_field")
        if not fld:
            TEMP_STATE.pop(uid, None)
            await update.message.reply_text("Something went wrong. Try /edit again.")
            return
        state["profile"][fld] = text or "—"
        # commit to DATA
        DATA["users"][uid] = state["profile"]
        save_data(DATA)
        TEMP_STATE.pop(uid, None)
        await update.message.reply_text("✅ Profile updated:\n\n" + user_profile_text(uid))
        return

# ---------- Queue & Matching ----------
async def find_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    args = context.args
    filter_gender = None
    if args:
        filter_gender = " ".join(args).strip().lower()

    # must have profile
    if uid not in DATA["users"]:
        await update.message.reply_text("Please create a profile first with /start.")
        return

    # if already in a session, tell them
    if DATA["user_session"].get(uid):
        await update.message.reply_text("⚠️ You're already in a chat. Use /next to find another or /stop to leave.")
        return

    # Add to queue
    remove_from_queue(uid)  # ensure not duplicate
    DATA["queue"].append({"user_id": uid, "filter_gender": filter_gender})
    save_data(DATA)
    if filter_gender:
        await update.message.reply_text(f"🔎 Searching for users with gender «{filter_gender}»... ⏳")
    else:
        await update.message.reply_text("🔎 Searching for a user... ⏳")

    # try to immediately match
    await try_match(uid)

async def try_match(uid: str):
    """
    Try to pair uid with the earliest queued user that is not themselves and meets filter.
    """
    # If already matched or not in queue, do nothing
    if DATA["user_session"].get(uid):
        return
    # find this user's queue entry (it should exist)
    caller_entry = None
    for e in DATA["queue"]:
        if e["user_id"] == str(uid):
            caller_entry = e
            break
    if not caller_entry:
        return

    # search for partner (first queued that is not self and satisfies filters both ways)
    for e in DATA["queue"]:
        if e["user_id"] == str(uid):
            continue
        # partner filter: if caller requested gender filter, partner must match
        partner_profile = DATA["users"].get(str(e["user_id"]), {})
        caller_req = caller_entry.get("filter_gender")
        partner_req = e.get("filter_gender")
        # evaluate if partner meets caller's requested gender (if any)
        if caller_req:
            if partner_profile.get("gender", "").lower() != caller_req.lower():
                continue
        # also, if partner set a filter, ensure caller meets that
        caller_profile = DATA["users"].get(str(uid), {})
        if partner_req:
            if caller_profile.get("gender", "").lower() != (partner_req.lower()):
                continue
        # we've found a partner
        a = str(uid)
        b = str(e["user_id"])
        # remove both from queue entries
        remove_from_queue(a)
        remove_from_queue(b)
        sid = make_session(a, b)
        save_data(DATA)
        # notify both users (we can't await send here because we don't have context — we'll schedule)
        # We'll use application to send messages
        app = ApplicationBuilder().token(BOT_TOKEN).build()
        # Instead of rebuilding application, we will use the global running app via asyncio tasks.
        # To send messages we will use an async callback scheduled from the running loop.
        async def notify():
            # fetch bot instance from running application
            bot = context_bot()
            # send profiles to each
            try:
                await bot.send_message(int(a), "🎉 Match found! You are now connected anonymously. Say hi! 👋", reply_markup=chat_buttons())
                await bot.send_message(int(a), "––– Partner profile –––\n" + user_profile_text(b))
                await bot.send_message(int(b), "🎉 Match found! You are now connected anonymously. Say hi! 👋", reply_markup=chat_buttons())
                await bot.send_message(int(b), "––– Partner profile –––\n" + user_profile_text(a))
            except Exception as e:
                logger.exception("Failed to notify matched users: %s", e)
        # schedule notify on event loop
        asyncio.get_event_loop().create_task(notify())
        break

def context_bot():
    """
    Helper to get the running application's bot instance.
    We rely on Application.current (set by python-telegram-bot when running).
    """
    # Application.current returns the running Application instance
    from telegram.ext import Application
    app = Application.current()
    if app is None:
        raise RuntimeError("No running Application found")
    return app.bot

# ---------- Relay messages while in a session ----------
async def relay_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    sid = DATA["user_session"].get(uid)
    if not sid:
        await update.message.reply_text("You're not in a chat. Use /find to search someone.")
        return
    sess = DATA["sessions"].get(sid)
    if not sess:
        await update.message.reply_text("Session error. Use /stop to clear.")
        return
    partner = get_partner(uid)
    if not partner:
        await update.message.reply_text("Partner not found. Use /stop to clear.")
        return

    bot = context.bot
    # relay text or media while not revealing sender identity.
    # For different message types: text, sticker, photo, voice, video, document — forward or re-send.
    msg = update.message

    # If the user pressed inline buttons, those are handled elsewhere via callback queries.
    # Relay basic types:
    try:
        if msg.text:
            await bot.send_message(int(partner), msg.text)  # plain text relay
        elif msg.sticker:
            await bot.send_sticker(int(partner), msg.sticker.file_id)
        elif msg.photo:
            # pick largest
            largest = msg.photo[-1]
            f = await context.bot.get_file(largest.file_id)
            # download and re-send (or send by file_id)
            await bot.send_photo(int(partner), largest.file_id)
        elif msg.video:
            await bot.send_video(int(partner), msg.video.file_id)
        elif msg.voice:
            await bot.send_voice(int(partner), msg.voice.file_id)
        elif msg.document:
            await bot.send_document(int(partner), msg.document.file_id, filename=msg.document.file_name)
        elif msg.audio:
            await bot.send_audio(int(partner), msg.audio.file_id)
        else:
            await bot.send_message(int(partner), "📩 [Unsupported message type received]")
    except Exception as e:
        logger.exception("Failed to relay message: %s", e)
        await update.message.reply_text("⚠️ Failed to send to partner. They might have blocked the bot or left. Use /stop to end chat.")

# ---------- Callback buttons (Next / Stop) ----------
async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    uid = str(user.id)
    data = query.data

    if data == "stop":
        s = end_session_for(uid)
        save_data(DATA)
        if s:
            # notify partner
            other = s["b"] if s["a"] == uid else s["a"]
            try:
                await context.bot.send_message(int(other), "⛔ The other user left the chat. Chat ended.")
            except Exception:
                pass
        await query.edit_message_text("⛔ Chat ended. Use /find to search again.")
        return

    if data == "next":
        # end current session and immediately place the requester into queue to find next
        s = end_session_for(uid)
        save_data(DATA)
        if s:
            other = s["b"] if s["a"] == uid else s["a"]
            try:
                await context.bot.send_message(int(other), "➡️ The other user moved to the next. Chat ended.")
            except Exception:
                pass
        await query.edit_message_text("➡️ Finding next user for you...")
        # add to queue with no filter
        remove_from_queue(uid)
        DATA["queue"].append({"user_id": uid, "filter_gender": None})
        save_data(DATA)
        await try_match(uid)
        return

# ---------- Commands for stop/next via text ----------
async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    s = end_session_for(uid)
    save_data(DATA)
    if s:
        other = s["b"] if s["a"] == uid else s["a"]
        try:
            await context.bot.send_message(int(other), "⛔ The other user left the chat. Chat ended.")
        except Exception:
            pass
        await update.message.reply_text("⛔ Chat ended.")
    else:
        # if they are in queue remove them
        removed = False
        if in_queue(uid):
            remove_from_queue(uid)
            save_data(DATA)
            removed = True
        if removed:
            await update.message.reply_text("You left the search queue.")
        else:
            await update.message.reply_text("You were not in a chat or in the queue.")

async def next_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    # if in a chat: end it and search again
    if DATA["user_session"].get(uid):
        s = end_session_for(uid)
        save_data(DATA)
        if s:
            other = s["b"] if s["a"] == uid else s["a"]
            try:
                await context.bot.send_message(int(other), "➡️ The other user moved to the next. Chat ended.")
            except Exception:
                pass
        await update.message.reply_text("➡️ Finding next user for you...")
        remove_from_queue(uid)
        DATA["queue"].append({"user_id": uid, "filter_gender": None})
        save_data(DATA)
        await try_match(uid)
        return
    # if not in chat, put in queue
    if in_queue(uid):
        await update.message.reply_text("You're already in the search queue.")
        return
    DATA["queue"].append({"user_id": uid, "filter_gender": None})
    save_data(DATA)
    await update.message.reply_text("➡️ You've been added to the search queue. Searching now...")
    await try_match(uid)

# ---------- Startup/Shutdown ----------
async def on_startup(app):
    logger.info("Bot started")

async def on_shutdown(app):
    save_data(DATA)
    logger.info("Bot shutting down and data saved")

# ---------- Main ----------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("find", find_cmd))
    app.add_handler(CommandHandler("search", find_cmd))  # usage: /search male
    app.add_handler(CommandHandler("stop", stop_cmd))
    app.add_handler(CommandHandler("next", next_cmd))
    app.add_handler(CommandHandler("edit", edit_cmd))
    app.add_handler(CommandHandler("help", help_cmd))

    # Callbacks for inline buttons
    app.add_handler(CallbackQueryHandler(callback_query_handler, pattern="^(next|stop)$"))

    # Text messages for building profile or editing
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, profile_message_handler))

    # Relay all messages (text/media) while in session
    # This should run before the generic text handler — but because the profile handler also catches, we
    # decide to use a b
