#!/usr/bin/env python3
"""
AnonChatPlush - single-file launcher.

Behavior:
- Exposes Flask `app` for Gunicorn (production WSGI).
- Spawns a separate OS process that runs the Telegram bot polling loop.
- Uses in-memory storage only (no permanent save).
- Commands implemented: /start, /find [gender], /next, /stop, /help, /profile, /edit.
- Supports forwarding text + photos + stickers + voice + video while matched.
"""

import os
import time
import logging
from multiprocessing import Process
import asyncio

from flask import Flask
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ------------- Configuration -------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("❌ Set BOT_TOKEN environment variable in Render settings.")

# ------------- Logging -------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)8s | %(name)s | %(message)s",
)
logger = logging.getLogger("AnonChatPlush")

# ------------- Flask (health) -------------
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ AnonChatPlush is running."

@app.route("/health")
def health():
    return "OK", 200

# ------------- In-memory storage -------------
# users: user_id -> { gender, age, location, interest, awaiting (step), partner }
users: dict[int, dict] = {}
waiting: list[int] = []  # simple FIFO queue for matching

def ensure_user(uid: int):
    if uid not in users:
        users[uid] = {
            "gender": None,
            "age": None,
            "location": None,
            "interest": None,
            "awaiting": None,   # step name during profile setup/edit
            "partner": None,
        }
    return users[uid]

def format_profile_by_id(uid: int) -> str:
    p = users.get(uid, {})
    return (
        f"👤 Gender: {p.get('gender') or '—'}\n"
        f"🎂 Age: {p.get('age') or '—'}\n"
        f"📍 Location: {p.get('location') or '—'}\n"
        f"💭 Interest: {p.get('interest') or '—'}"
    )

def find_partner_for(uid: int, pref: str | None = None):
    """Find first eligible waiting user matching optional pref; remove from waiting."""
    for i, cand in enumerate(waiting):
        if cand == uid:
            continue
        cand_prof = users.get(cand)
        if not cand_prof:
            continue
        if cand_prof.get("partner") is not None:
            continue
        if pref:
            if (cand_prof.get("gender") or "").lower() != pref.lower():
                continue
        # match
        waiting.pop(i)
        return cand
    return None

# ------------- Telegram bot logic (async) -------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ensure_user(uid)
    users[uid]["awaiting"] = "gender"
    kb = ReplyKeyboardMarkup([["Male", "Female", "Other"]], one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text(
        "🌸 *Welcome to AnonChatPlush!* 🌸\n\nLet's set up your profile so we can match you.\n\nChoose your gender:",
        parse_mode="Markdown",
        reply_markup=kb,
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📘 *Commands*\n\n"
        "/start — Setup profile\n"
        "/profile — View and edit profile\n"
        "/edit — Edit profile step-by-step\n"
        "/find [gender] — Find partner (optional: male/female/other)\n"
        "/next — Skip current and find a new partner\n"
        "/stop — Leave current chat\n"
        "/help — This message\n\n"
        "You can send text, photos, stickers, voice & video while chatting.",
        parse_mode="Markdown"
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
    await update.message.reply_text(
        f"🧾 *Your Profile*\n\n{format_profile_by_id(uid)}",
        parse_mode="Markdown",
        reply_markup=kb
    )

async def cmd_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ensure_user(uid)
    users[uid]["awaiting"] = "gender"
    kb = ReplyKeyboardMarkup([["Male", "Female", "Other"]], one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("✏️ Edit profile — choose your gender:", reply_markup=kb)

async def cmd_find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ensure_user(uid)
    # optional gender preference
    pref = None
    if context.args:
        a = context.args[0].lower()
        if a in ("male", "female", "other"):
            pref = a

    # if already chatting
    if users[uid].get("partner"):
        await update.message.reply_text("⚠️ You are already chatting. Use /stop or /next.")
        return

    # try match immediately
    partner = find_partner_for(uid, pref)
    if partner:
        users[uid]["partner"] = partner
        users[partner]["partner"] = uid
        # send partner info to both
        try:
            await context.bot.send_message(partner,
                f"💫 Matched! Say hi 👋\n\nPartner info:\n{format_profile_by_id(uid)}",
                parse_mode="Markdown")
        except Exception:
            logger.exception("Failed to send partner info to partner")
        await update.message.reply_text(f"💫 Matched! Say hi 👋\n\nPartner info:\n{format_profile_by_id(partner)}", parse_mode="Markdown")
        return

    # else join waiting
    if uid not in waiting:
        waiting.append(uid)
    await update.message.reply_text("🔎 Searching for a partner... (use /stop to cancel)")

async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = users.get(uid)
    if not user:
        await update.message.reply_text("You have no active profile. Use /start to set up.")
        return

    partner = user.get("partner")
    if partner:
        # clear both
        users[uid]["partner"] = None
        if partner in users:
            users[partner]["partner"] = None
            # show buttons to partner
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("💬 Find another", callback_data="find")],
                [InlineKeyboardButton("🎯 Search by gender", callback_data="search_gender")]
            ])
            try:
                await context.bot.send_message(partner, "❌ Your partner left the chat.", reply_markup=kb)
            except Exception:
                logger.exception("Failed to notify partner on stop")
        await update.message.reply_text("✅ You left the chat. Use /find to search again.")
        return

    # if not chatting but was waiting
    if uid in waiting:
        try:
            waiting.remove(uid)
        except ValueError:
            pass
        await update.message.reply_text("Stopped searching. Use /find to start again.")
        return

    await update.message.reply_text("You are not in chat or searching. Use /find to start.")

async def cmd_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    # leave any chat
    if users.get(uid, {}).get("partner"):
        # reuse cmd_stop to notify partner
        await cmd_stop(update, context)
    # remove from waiting if present
    if uid in waiting:
        try:
            waiting.remove(uid)
        except Exception:
            pass
    # start new find (no pref)
    await cmd_find(update, context)

async def callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    data = q.data

    if data == "find":
        await q.message.reply_text("🔎 Searching for another connection...")
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

async def generic_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    uid = update.effective_user.id
    ensure_user(uid)
    user = users[uid]
    text = update.message.text if update.message.text else None

    # profile setup/edit step
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
                await update.message.reply_text("✅ Profile saved!\n\n" + format_profile_by_id(uid), parse_mode="Markdown")
            else:
                await update.message.reply_text("Please type one-line interest.")
            return

    # if in active chat, relay any media/text
    partner = user.get("partner")
    if partner:
        try:
            # copy_message preserves media (photo, sticker, voice, video)
            await context.bot.copy_message(chat_id=partner, from_chat_id=update.message.chat_id, message_id=update.message.message_id)
        except Exception:
            # fallback: send text
            if text:
                await context.bot.send_message(partner, text)
        return

    # otherwise guide user
    await update.message.reply_text("ℹ️ You are not in a chat. Use /find to search or /start to set up your profile.")

# ------------- Bot runner (in child process) -------------
async def _build_and_run_bot():
    app_tg = ApplicationBuilder().token(BOT_TOKEN).build()

    # register handlers
    app_tg.add_handler(CommandHandler("start", cmd_start))
    app_tg.add_handler(CommandHandler("help", cmd_help))
    app_tg.add_handler(CommandHandler("profile", cmd_profile))
    app_tg.add_handler(CommandHandler("edit", cmd_edit))
    app_tg.add_handler(CommandHandler("find", cmd_find))
    app_tg.add_handler(CommandHandler("stop", cmd_stop))
    app_tg.add_handler(CommandHandler("next", cmd_next))
    app_tg.add_handler(CallbackQueryHandler(callback_query))
    app_tg.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, generic_message))

    logger.info("🤖 Telegram bot: starting polling ...")
    await app_tg.run_polling()

def run_bot_process():
    """Run the bot. This function runs inside the child process."""
    try:
        asyncio.run(_build_and_run_bot())
    except Exception as e:
        logger.exception("Bot process crashed: %s", e)
        # short sleep to avoid hot-loop crash
        time.sleep(5)

# ------------- Launch child process -------------
def start_bot_background_process():
    # spawn a separate process that runs the async bot loop (prevents signal/set_wakeup_fd issues)
    p = Process(target=run_bot_process, daemon=True)
    p.start()
    logger.info("Started Telegram bot in child process (pid=%s).", p.pid)

# Start child process when the module is imported by Gunicorn worker
start_bot_background_process()

# ------------- If run directly (local dev) -------------
if __name__ == "__main__":
    logger.info("Running main.py directly (dev). Flask dev server will run; bot process already started.")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "10000")))
          
