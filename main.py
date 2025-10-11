#!/usr/bin/env python3
# main.py — AnonChatPlush (Render web service friendly)
import os
import threading
import time
import logging
from flask import Flask
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ---------- Config ----------
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN missing. Set BOT_TOKEN in environment variables.")

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AnonChatPlush")

# ---------- Flask app (for Render port binding) ----------
flask_app = Flask(__name__)

@flask_app.route("/")
def index():
    return "AnonChatPlush is alive ✨"

@flask_app.route("/health")
def health():
    return "OK", 200

# ---------- In-memory data ----------
# users[user_id] = {
#   "gender","age","location","interest","awaiting"(None or step),"partner"(id or None)
# }
users = {}
waiting = []   # FIFO list of user_ids searching
active = {}    # user_id -> partner_id mapping

# ---------- Helpers ----------
def ensure_user(uid: int):
    if uid not in users:
        users[uid] = {
            "gender": None,
            "age": None,
            "location": None,
            "interest": None,
            "awaiting": None,
            "partner": None,
        }
    return users[uid]

def profile_text(uid: int):
    p = users.get(uid, {})
    return (
        f"👤 Gender: {p.get('gender') or '—'}\n"
        f"🎂 Age: {p.get('age') or '—'}\n"
        f"📍 Location: {p.get('location') or '—'}\n"
        f"💭 Interest: {p.get('interest') or '—'}"
    )

def find_match_for(uid: int, pref_gender: str = None):
    """Return partner_id if found (and remove from waiting)."""
    # try candidates in waiting (FIFO)
    for idx, cand in enumerate(waiting):
        if cand == uid:
            continue
        cand_profile = users.get(cand)
        if not cand_profile:
            continue
        # skip if already partnered
        if cand_profile.get("partner"):
            continue
        # if pref_gender specified, require candidate gender match
        if pref_gender:
            if (cand_profile.get("gender") or "").lower() != pref_gender.lower():
                continue
        # candidate eligible -> remove and return
        waiting.pop(idx)
        return cand
    return None

# ---------- Commands ----------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ensure_user(uid)
    users[uid]["awaiting"] = "gender"
    kb = ReplyKeyboardMarkup([["Male", "Female", "Other"]], resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(
        "🌸 *Welcome to AnonChatPlush!* 🌸\n\nLet's set up your profile — quick & private.\n\nChoose your gender:",
        parse_mode="Markdown",
        reply_markup=kb,
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📘 *AnonChatPlush — Commands*\n\n"
        "/start - Setup profile\n"
        "/profile - View & edit profile\n"
        "/edit - Edit profile step-by-step\n"
        "/find [gender] - Find a partner (optional gender filter)\n"
        "/stop - Leave current chat\n"
        "/next - Skip current partner and find another\n"
        "/help - Show this message\n\n"
        "You can send text, photos, stickers, voice & video in chat.",
        parse_mode="Markdown",
    )

async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    p = ensure_user(uid)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Edit Gender", callback_data="edit_gender"),
         InlineKeyboardButton("✏️ Edit Age", callback_data="edit_age")],
        [InlineKeyboardButton("✏️ Edit Location", callback_data="edit_location"),
         InlineKeyboardButton("✏️ Edit Interest", callback_data="edit_interest")],
    ])
    await update.message.reply_text(f"🧾 *Your Profile*\n\n{profile_text(uid)}", parse_mode="Markdown", reply_markup=kb)

async def cmd_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ensure_user(uid)
    users[uid]["awaiting"] = "gender"
    kb = ReplyKeyboardMarkup([["Male", "Female", "Other"]], resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text("✏️ Edit profile — choose your gender:", reply_markup=kb)

async def cmd_find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ensure_user(uid)
    # optional gender arg
    args = context.args or []
    pref = None
    if args:
        pref = args[0].lower()
        if pref not in ("male", "female", "other"):
            pref = None
    # prevent matching while already chatting
    if users[uid].get("partner"):
        await update.message.reply_text("⚠️ You're already in a chat. Use /stop or /next.")
        return
    # try immediate match
    partner = find_match_for(uid, pref_gender=pref)
    if partner:
        # create pairing
        users[uid]["partner"] = partner
        users[partner]["partner"] = uid
        active[uid] = partner
        active[partner] = uid
        # send both sides profile preview
        await context.bot.send_message(partner, f"💫 Matched! Say hi 👋\n\nPartner info:\n{profile_text(uid)}", parse_mode="Markdown")
        await update.message.reply_text(f"💫 Matched! Say hi 👋\n\nPartner info:\n{profile_text(partner)}", parse_mode="Markdown")
        return
    # else join waiting queue if not already
    if uid not in waiting:
        waiting.append(uid)
    await update.message.reply_text("🔎 Searching for a match... (you can /stop anytime)")

async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if users.get(uid, {}).get("partner"):
        partner = users[uid]["partner"]
        # clear both
        users[uid]["partner"] = None
        users[partner]["partner"] = None
        active.pop(uid, None)
        active.pop(partner, None)
        # notify partner
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 Find another", callback_data="find")],
            [InlineKeyboardButton("🎯 Search by gender", callback_data="search_gender")]
        ])
        try:
            await context.bot.send_message(partner, "❌ Your partner left the chat.", reply_markup=kb)
        except Exception:
            logger.exception("notify partner failed")
        await update.message.reply_text("✅ You left the chat. Use /find to search again.")
        return
    # if waiting, remove
    if uid in waiting:
        try:
            waiting.remove(uid)
        except ValueError:
            pass
        await update.message.reply_text("Stopped searching. Use /find to start again.")
        return
    await update.message.reply_text("You are not in a chat or queue.")

async def cmd_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    # store pref if had one
    pref = users[uid].get("search_pref") if users.get(uid) else None
    # stop if in chat
    if users.get(uid, {}).get("partner"):
        # reuse cmd_stop logic
        await cmd_stop(update, context)
    # remove from waiting if present
    if uid in waiting:
        try:
            waiting.remove(uid)
        except Exception:
            pass
    # call find
    if pref:
        context.args = [pref]
    else:
        context.args = []
    await cmd_find(update, context)

# ---------- Message handler (profile steps & relay) ----------
async def generic_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ensure_user(uid)
    text = update.message.text if update.message and update.message.text else None
    p = users[uid]
    # profile setup steps
    if p.get("awaiting"):
        step = p["awaiting"]
        if step == "gender":
            if text and text.lower() in ("male", "female", "other"):
                p["gender"] = text.capitalize()
                p["awaiting"] = "age"
                await update.message.reply_text("🎂 Got it. Now send your age (number).", reply_markup=ReplyKeyboardRemove())
            else:
                await update.message.reply_text("Please choose Male, Female or Other (use the buttons).")
            return
        if step == "age":
            if text and text.isdigit():
                p["age"] = text
                p["awaiting"] = "location"
                await update.message.reply_text("📍 Now send your location (city or city, country).")
            else:
                await update.message.reply_text("Please send a numeric age (e.g., 20).")
            return
        if step == "location":
            if text:
                p["location"] = text
                p["awaiting"] = "interest"
                await update.message.reply_text("💭 One-line: what are your interests? (e.g., music, travel)")
            else:
                await update.message.reply_text("Please send your location (city, country).")
            return
        if step == "interest":
            if text:
                p["interest"] = text
                p["awaiting"] = None
                await update.message.reply_text("✅ Profile saved!\n\n" + profile_text(uid), parse_mode="Markdown")
            else:
                await update.message.reply_text("Please type one-line interest.")
            return
    # if in chat => relay message (preserve media)
    partner = p.get("partner")
    if partner:
        try:
            await context.bot.copy_message(chat_id=partner, from_chat_id=update.message.chat_id, message_id=update.message.message_id)
        except Exception:
            # fallback text only
            if text:
                await context.bot.send_message(partner, text)
        return
    # not in chat and not setting profile => hint
    await update.message.reply_text("ℹ️ Not in a chat. Use /find to search or /start to set up your profile.")

# ---------- Callback Query Handler (buttons) ----------
async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    data = q.data
    if data == "find":
        # user clicked 'Find another'
        await q.message.reply_text("🔎 Searching for another connection...")
        await cmd_find(q, context)  # q acts similarly to Update
        return
    if data == "search_gender":
        await q.message.reply_text("Use `/find female` or `/find male` to search by gender.")
        return
    if data.startswith("edit_"):
        field = data.split("_", 1)[1]
        ensure_user(uid)
        users[uid]["awaiting"] = field
        if field == "gender":
            kb = ReplyKeyboardMarkup([["Male", "Female", "Other"]], resize_keyboard=True, one_time_keyboard=True)
            await q.message.reply_text("Choose new gender:", reply_markup=kb)
        else:
            await q.message.reply_text(f"Send new {field}:", reply_markup=ReplyKeyboardRemove())
        return
    await q.message.reply_text("Action received.")

# ---------- Bot runner (in background thread) ----------
def run_tg_bot():
    async def _runner():
        app = ApplicationBuilder().token(BOT_TOKEN).build()
        # Commands
        app.add_handler(CommandHandler("start", cmd_start))
        app.add_handler(CommandHandler("help", cmd_help))
        app.add_handler(CommandHandler("profile", cmd_profile))
        app.add_handler(CommandHandler("edit", cmd_edit))
        app.add_handler(CommandHandler("find", cmd_find))
        app.add_handler(CommandHandler("stop", cmd_stop))
        app.add_handler(CommandHandler("next", cmd_next))
        # Callbacks
        app.add_handler(CallbackQueryHandler(callback_query_handler))
        # Generic messages
        app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, generic_message))
        logger.info("🤖 Starting Telegram polling (bot)...")
        # run_polling blocks; close_loop=False avoids closing outer loop
        app.run_polling(close_loop=False)

    # run the async runner in this thread (synchronously)
    try:
        _runner()
    except Exception:
        logger.exception("Telegram bot runner crashed")

# Start the bot thread when module is imported (Gunicorn will import main)
_bot_thread = threading.Thread(target=run_tg_bot, daemon=True)
_bot_thread.start()
logger.info("Started bot thread; Flask will handle web requests.")

# ---------- If run directly (for local dev) ----------
if __name__ == "__main__":
    # When running locally without Gunicorn: start Flask dev server + bot thread already started
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "10000")))
