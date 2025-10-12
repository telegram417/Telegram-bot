#!/usr/bin/env python3
"""
AnonChatPlush - main launcher for Render.

Structure:
- Flask `app` exported for Gunicorn (Procfile uses `gunicorn main:app`).
- Starts a separate multiprocessing.Process that runs the Telegram bot loop
  (this avoids asyncio / signal issues that happen when running polling inside threads).
"""

import os
import time
import asyncio
import logging
from multiprocessing import Process
from flask import Flask
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
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ------------ CONFIG ------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN environment variable missing. Set it in Render settings.")

# ------------ Logging ------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)8s | %(name)s | %(message)s",
)
logger = logging.getLogger("AnonChatPlush")

# ------------ Flask for Render ------------
app = Flask(__name__)


@app.route("/")
def home():
    return "✅ AnonChatPlush (Flask) — service running"


@app.route("/health")
def health():
    return "OK", 200


# ------------ In-memory storage (lightweight) ------------
# users[user_id] = {
#   gender, age, location, interest, awaiting (setup step or None), partner (id or None)
# }
users = {}
waiting = []  # FIFO queue (list) of user_ids waiting for match

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

def format_profile(uid: int) -> str:
    p = users.get(uid, {})
    return (
        f"👤 Gender: {p.get('gender') or '—'}\n"
        f"🎂 Age: {p.get('age') or '—'}\n"
        f"📍 Location: {p.get('location') or '—'}\n"
        f"💭 Interest: {p.get('interest') or '—'}"
    )

def find_partner_for(uid: int, pref_gender: str | None = None):
    """Return matched partner id or None. Removes matched partner from waiting."""
    for i, cand in enumerate(waiting):
        if cand == uid:
            continue
        cand_prof = users.get(cand)
        if not cand_prof:
            continue
        if cand_prof.get("partner") is not None:
            continue
        if pref_gender:
            if (cand_prof.get("gender") or "").lower() != pref_gender.lower():
                continue
        # eligible
        waiting.pop(i)
        return cand
    return None

# ------------ Telegram bot code (run inside separate process) ------------
async def _build_and_run_bot():
    """Builds the Application and runs polling (async)."""
    app_tg = ApplicationBuilder().token(BOT_TOKEN).build()

    # ---- Commands ----
    app_tg.add_handler(CommandHandler("start", cmd_start))
    app_tg.add_handler(CommandHandler("help", cmd_help))
    app_tg.add_handler(CommandHandler("profile", cmd_profile))
    app_tg.add_handler(CommandHandler("edit", cmd_edit))
    app_tg.add_handler(CommandHandler("find", cmd_find))
    app_tg.add_handler(CommandHandler("stop", cmd_stop))
    app_tg.add_handler(CommandHandler("next", cmd_next))

    # Callbacks for inline buttons
    app_tg.add_handler(CallbackQueryHandler(callback_query))

    # Generic messages (setup steps & relay)
    app_tg.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, generic_message))

    logger.info("🤖 Telegram bot: starting polling ...")
    await app_tg.run_polling()


def run_bot_process():
    """Entry point for child process. Runs an asyncio loop and runs the bot."""
    # Child process: safe to use asyncio.run (main thread of child)
    try:
        asyncio.run(_build_and_run_bot())
    except Exception as e:
        logger.exception("Bot process crashed: %s", e)
        # Child process exits; the master (gunicorn worker) won't respawn it automatically.
        # Render will restart whole service on crash. Sleep a bit before exit to avoid tight crash loops.
        time.sleep(5)

# --------------- Bot handlers (async) ---------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ensure_user(uid)
    users[uid]["awaiting"] = "gender"
    kb = ReplyKeyboardMarkup([["Male", "Female", "Other"]], one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text(
        "🌸 *Welcome to AnonChatPlush!* 🌸\n\nLet's set up your profile — quick & private.\n\nChoose your gender:",
        parse_mode="Markdown",
        reply_markup=kb,
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📘 *AnonChatPlush — Commands*\n\n"
        "/start — Setup profile\n"
        "/profile — View & edit profile\n"
        "/edit — Edit profile step-by-step\n"
        "/find [gender] — Find a partner (optional: male/female/other)\n"
        "/stop — Leave chat\n"
        "/next — Skip to next partner\n"
        "/help — This help message\n\n"
        "Send text, photos, stickers, voice & video while chatting.",
        parse_mode="Markdown",
    )

async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ensure_user(uid)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Edit Gender", callback_data="edit_gender"),
         InlineKeyboardButton("✏️ Edit Age", callback_data="edit_age")],
        [InlineKeyboardButton("✏️ Edit Location", callback_data="edit_location"),
         InlineKeyboardButton("✏️ Edit Interest", callback_data="edit_interest")],
    ])
    await update.message.reply_text(f"🧾 *Your Profile*\n\n{format_profile(uid)}", parse_mode="Markdown", reply_markup=kb)

async def cmd_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ensure_user(uid)
    users[uid]["awaiting"] = "gender"
    kb = ReplyKeyboardMarkup([["Male", "Female", "Other"]], one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("✏️ Edit profile — choose your gender:", reply_markup=kb)

async def cmd_find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ensure_user(uid)

    # optional gender argument
    pref = None
    if context.args:
        arg = context.args[0].lower()
        if arg in ("male", "female", "other"):
            pref = arg

    # if already in a chat
    if users[uid].get("partner"):
        await update.message.reply_text("⚠️ You're already chatting. Use /stop or /next.")
        return

    # try to match immediately
    partner = find_partner_for(uid, pref_gender=pref)
    if partner:
        users[uid]["partner"] = partner
        users[partner]["partner"] = uid

        # send partner info to both
        await context.bot.send_message(
            partner,
            f"💫 Matched! Say hi 👋\n\nPartner info:\n{format_profile(uid)}",
            parse_mode="Markdown",
        )
        await update.message.reply_text(f"💫 Matched! Say hi 👋\n\nPartner info:\n{format_profile(partner)}", parse_mode="Markdown")
        return

    # else add to waiting queue (if not already)
    if uid not in waiting:
        waiting.append(uid)
    await update.message.reply_text("🔎 Searching for a partner... (use /stop anytime)")

async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if users.get(uid, {}).get("partner"):
        partner = users[uid]["partner"]
        # clear both
        users[uid]["partner"] = None
        if partner in users:
            users[partner]["partner"] = None

        # notify partner and show options
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 Find another", callback_data="find")],
            [InlineKeyboardButton("🎯 Search by gender", callback_data="search_gender")],
        ])
        try:
            await context.bot.send_message(partner, "❌ Your partner left the chat.", reply_markup=kb)
        except Exception:
            logger.exception("Failed to notify partner on /stop")

        await update.message.reply_text("✅ You left the chat. Use /find to search again.")
        return

    # if not in chat but searching -> remove from waiting
    if uid in waiting:
        try:
            waiting.remove(uid)
        except ValueError:
            pass
        await update.message.reply_text("Stopped searching. Use /find to begin again.")
        return

    await update.message.reply_text("You are not in a chat or search queue.")

async def cmd_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # leave current chat (if any) then search again with previous pref (none in this design)
    uid = update.effective_user.id
    # stop if in chat
    if users.get(uid, {}).get("partner"):
        await cmd_stop(update, context)
    # ensure removed from waiting
    if uid in waiting:
        try:
            waiting.remove(uid)
        except ValueError:
            pass
    # start find
    await cmd_find(update, context)

# CallbackQuery handler (inline buttons)
async def callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    data = q.data

    if data == "find":
        await q.message.reply_text("🔎 Searching for another connection...")
        # simulate user message /find
        await cmd_find(q, context)
        return
    if data == "search_gender":
        await q.message.reply_text("To search by gender, use `/find female` or `/find male`.", parse_mode="Markdown")
        return

    if data.startswith("edit_"):
        field = data.split("_", 1)[1]
        ensure_user(uid)
        users[uid]["awaiting"] = field
        if field == "gender":
            kb = ReplyKeyboardMarkup([["Male", "Female", "Other"]], one_time_keyboard=True, resize_keyboard=True)
            await q.message.reply_text("Choose your new gender:", reply_markup=kb)
        else:
            await q.message.reply_text(f"Send new {field} value (text).", reply_markup=ReplyKeyboardRemove())
        return

    await q.message.reply_text("Action received.")

# Generic message handler: handles profile setup steps and relays messages when in chat
async def generic_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    uid = update.effective_user.id
    ensure_user(uid)
    user = users[uid]
    text = update.message.text if update.message.text else None

    # Setup/edit flow
    step = user.get("awaiting")
    if step:
        if step == "gender":
            if text and text.lower() in ("male", "female", "other"):
                user["gender"] = text.capitalize()
                user["awaiting"] = "age"
                await update.message.reply_text("🎂 Got it. Now send your *age* (just the number).", parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
            else:
                await update.message.reply_text("Please choose Male / Female / Other (use the buttons).")
            return

        if step == "age":
            if text and text.isdigit():
                user["age"] = text
                user["awaiting"] = "location"
                await update.message.reply_text("📍 Now send your location (city or city, country).")
            else:
                await update.message.reply_text("Please send a numeric age (e.g., 20).")
            return

        if step == "location":
            if text:
                user["location"] = text.strip()
                user["awaiting"] = "interest"
                await update.message.reply_text("💭 One-line: what are your interests? (e.g., music, travel)")
            else:
                await update.message.reply_text("Please type your location (city/country).")
            return

        if step == "interest":
            if text:
                user["interest"] = text.strip()
                user["awaiting"] = None
                await update.message.reply_text("✅ Profile saved!\n\n" + format_profile(uid), parse_mode="Markdown")
            else:
                await update.message.reply_text("Please type one-line interest.")
            return

    # If currently in an active chat, relay any media or text
    partner = user.get("partner")
    if partner:
        try:
            # copy_message preserves media (photo, sticker, voice, video)
            await context.bot.copy_message(chat_id=partner, from_chat_id=update.message.chat_id, message_id=update.message.message_id)
        except Exception:
            # fallback for text only
            if text:
                await context.bot.send_message(partner, text)
        return

    # not setting up profile and not in chat
    await update.message.reply_text("ℹ️ You are not in a chat. Use /find to search or /start to set up your profile.")

# ------------ Process launcher ------------
def start_bot_background_process():
    """Start the Telegram bot in a separate process."""
    p = Process(target=run_bot_process, daemon=True)
    p.start()
    logger.info("Started Telegram bot in child process (pid=%s).", p.pid)

# Start bot process when module is imported (Gunicorn worker will import main)
start_bot_background_process()

# ------------ If run directly (local dev) ------------
if __name__ == "__main__":
    # When running locally via `python main.py`, still start child process and run Flask dev server
    logger.info("Running main directly — starting Flask (dev) and child bot process.")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "10000")))
