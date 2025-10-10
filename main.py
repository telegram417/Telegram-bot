# main.py
import os
import json
import asyncio
from datetime import datetime, timedelta
from flask import Flask, request
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# ---------- CONFIG ----------
TOKEN = os.getenv("BOT_TOKEN")                     # set in Render env
BASE_URL = os.getenv("https://telegram-bot-99.onrender.com")                   # e.g. https://telegram-bot-99.onrender.com
BOT_USERNAME = os.getenv("BOT_USERNAME", "MeetAnonymousBOT")
PREMIUM_INVITES_REQUIRED = 5
PREMIUM_DAYS = 3

if not TOKEN or not BASE_URL:
    raise RuntimeError("❌ Set BOT_TOKEN and BASE_URL environment variables in Render settings.")

WEBHOOK_PATH = f"/{TOKEN}"                         # endpoint Telegram will POST to
WEBHOOK_URL = f"{BASE_URL}{WEBHOOK_PATH}"

# ---------- FLASK APP (Render uses this) ----------
app = Flask(__name__)

# ---------- IN-MEMORY STORAGE ----------
# Structure for users (keys are strings to simplify JSON if used later)
users = {}   # users[str(uid)] = {...}
waiting_users = []  # FIFO queue of ints

# ---------- HELPERS ----------
def ensure_user(uid: int):
    k = str(uid)
    if k not in users:
        users[k] = {
            "gender": None,
            "age": None,
            "location": None,
            "interest": None,
            "partner": None,
            "awaiting": None,     # "gender"/"age"/"location"/"interest"/"edit_*"
            "invites": 0,
            "premium_until": None,
            "search_pref": None,  # holds preferred gender during queued search
        }
    return users[k]

def is_profile_complete(u: dict) -> bool:
    return bool(u.get("gender") and u.get("age") and u.get("location") and u.get("interest"))

def is_premium(uid: int) -> bool:
    u = users.get(str(uid))
    if not u or not u.get("premium_until"):
        return False
    try:
        return datetime.fromisoformat(u["premium_until"]) > datetime.utcnow()
    except Exception:
        return False

def grant_premium(uid: int, days=PREMIUM_DAYS):
    u = ensure_user(uid)
    until = datetime.utcnow() + timedelta(days=days)
    u["premium_until"] = until.isoformat()

def format_profile(u: dict) -> str:
    return (
        f"👤 Gender: {u.get('gender','—')}\n"
        f"🎂 Age: {u.get('age','—')}\n"
        f"📍 Location: {u.get('location','—')}\n"
        f"💭 Interest: {u.get('interest','—')}"
    )

def show_end_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Find Another", callback_data="find_any")],
        [InlineKeyboardButton("🔎 Search by Gender", callback_data="search_gender")]
    ])

def show_main_menu_keyboard(uid: int):
    premium_flag = " 💎" if is_premium(uid) else ""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Find Chat", callback_data="find_any"),
         InlineKeyboardButton("⚙️ Profile", callback_data="profile")],
        [InlineKeyboardButton(f"🎁 Invite (Get Premium){premium_flag}", callback_data="ref")]
    ])

# ---------- TELEGRAM BOT SETUP ----------
application = Application.builder().token(TOKEN).build()

# ---------- HANDLERS ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start flow. Accepts optional referral argument like: /start ref12345"""
    uid = update.effective_user.id
    ensure_user(uid)
    args = context.args or []
    if args:
        raw = args[0]
        if raw.startswith("ref"):
            try:
                inviter = int(raw[3:])
                inv_k = str(inviter)
                if inv_k in users:
                    users[inv_k]["invites"] = users[inv_k].get("invites", 0) + 1
                    if users[inv_k]["invites"] >= PREMIUM_INVITES_REQUIRED:
                        grant_premium(inviter, PREMIUM_DAYS)
                        users[inv_k]["invites"] = 0
                        try:
                            await context.bot.send_message(inviter, f"🎉 You earned {PREMIUM_DAYS} days Premium for inviting {PREMIUM_INVITES_REQUIRED} users!")
                        except Exception:
                            pass
            except Exception:
                pass

    u = ensure_user(uid)
    # start profile step if incomplete
    if not is_profile_complete(u):
        u["awaiting"] = "gender"
        kb = ReplyKeyboardMarkup([["Male ♂","Female ♀"]], one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text(
            "🌸 *Welcome to MeetAnonymousBOT!* Let's set your profile quickly.\n\nChoose your gender:",
            parse_mode="Markdown", reply_markup=kb
        )
        return

    # if complete
    await update.message.reply_text("✨ You're ready! Use the menu to find chats or edit your profile.")
    await update.message.reply_text("Choose an action:", reply_markup=show_main_menu_keyboard(uid))

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📘 *Commands*\n"
        "/start — Setup profile\n"
        "/find — Find a partner\n"
        "/next — Leave and find next\n"
        "/stop — Leave current chat\n"
        "/profile — View & edit profile\n"
        "/ref — Invite friends\n"
        "/help — This help\n",
        parse_mode="Markdown"
    )

async def profile_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = ensure_user(uid)
    premium_text = f"\n💎 Premium: active until {u['premium_until']}" if is_premium(uid) else ""
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Edit Gender", callback_data="edit_gender"),
         InlineKeyboardButton("✏️ Edit Age", callback_data="edit_age")],
        [InlineKeyboardButton("✏️ Edit Location", callback_data="edit_location"),
         InlineKeyboardButton("✏️ Edit Interest", callback_data="edit_interest")],
        [InlineKeyboardButton("🔙 Back", callback_data="menu")]
    ])
    await update.message.reply_text("🧾 *Your Profile*\n\n" + format_profile(u) + premium_text, parse_mode="Markdown", reply_markup=kb)

async def ref_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    link = f"https://t.me/{BOT_USERNAME}?start=ref{uid}"
    u = ensure_user(uid)
    prem = "🟢 Active" if is_premium(uid) else "🔴 Expired"
    await update.message.reply_text(
        f"🎁 Invite friends with this link:\n{link}\n\nInvites: *{u.get('invites',0)}* / {PREMIUM_INVITES_REQUIRED}\nPremium: *{prem}*",
        parse_mode="Markdown"
    )

# Search animation (simple, send then edit where possible)
async def play_search_animation(chat_id:int, context:ContextTypes.DEFAULT_TYPE):
    msgs = [
        "🔍 Searching the universe for your vibe...",
        "💫 Scanning nearby souls...",
        "✨ Matching interests...",
        "❤️ Almost connected..."
    ]
    msg = await context.bot.send_message(chat_id, msgs[0])
    for text in msgs[1:]:
        await asyncio.sleep(1.2)
        try:
            await context.bot.edit_message_text(text, chat_id=chat_id, message_id=msg.message_id)
        except Exception:
            # fallback: send a new message if edit fails
            msg = await context.bot.send_message(chat_id, text)
    await asyncio.sleep(0.6)
    try:
        await context.bot.edit_message_text("🔎 Finalizing match...", chat_id=chat_id, message_id=msg.message_id)
    except Exception:
        await context.bot.send_message(chat_id, "🔎 Finalizing match...")

async def begin_find_flow(uid:int, context:ContextTypes.DEFAULT_TYPE, gender_pref=None, source_update:Update=None):
    u = ensure_user(uid)
    if not is_profile_complete(u):
        if source_update:
            await source_update.message.reply_text("⚠️ Complete profile first with /start.")
        else:
            await context.bot.send_message(uid, "⚠️ Complete profile first with /start.")
        return
    if u.get("partner"):
        if source_update:
            await source_update.message.reply_text("⚠️ You're already in a chat. Use /stop or /next.")
        else:
            await context.bot.send_message(uid, "⚠️ You're already in a chat. Use /stop or /next.")
        return

    # animation
    try:
        chat_for_anim = source_update.message.chat_id if source_update else uid
        await play_search_animation(chat_for_anim, context)
    except Exception:
        pass

    # match loop: find first waiting candidate that matches gender_pref and is free
    partner_id = None
    found_idx = None
    for idx, cand in enumerate(waiting_users):
        if cand == uid:
            continue
        cand_u = users.get(str(cand))
        if not cand_u or cand_u.get("partner"):
            continue
        if gender_pref and cand_u.get("gender") != gender_pref:
            continue
        partner_id = cand
        found_idx = idx
        break

    if partner_id is not None:
        # remove from queue and pair
        waiting_users.pop(found_idx)
        users[str(uid)]["partner"] = partner_id
        users[str(partner_id)]["partner"] = uid

        me_profile = format_profile(users[str(uid)])
        partner_profile = format_profile(users[str(partner_id)])
        # notify both
        await context.bot.send_message(uid, f"💬 *Connected!* Say hi 👋\n\n{partner_profile}", parse_mode="Markdown")
        await context.bot.send_message(partner_id, f"💬 *Connected!* Say hi 👋\n\n{me_profile}", parse_mode="Markdown")
        return

    # no partner -> enqueue
    if uid not in waiting_users:
        waiting_users.append(uid)
    if source_update:
        await source_update.message.reply_text("🔎 You're in queue. Waiting for a partner...")
    else:
        await context.bot.send_message(uid, "🔎 You're in queue. Waiting for a partner...")

# /find command: present options
async def find_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Find Any", callback_data="find_any")],
        [InlineKeyboardButton("🔎 Search by Gender", callback_data="search_gender")]
    ])
    await update.message.reply_text("How would you like to search?", reply_markup=kb)

# /next - leave current and find new
async def next_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if users.get(str(uid), {}).get("partner"):
        partner = users[str(uid)]["partner"]
        users[str(uid)]["partner"] = None
        if str(partner) in users:
            users[str(partner)]["partner"] = None
            await context.bot.send_message(partner, "💔 Your partner left the chat.")
            await context.bot.send_message(partner, "What next?", reply_markup=show_end_menu_keyboard())
    if uid in waiting_users:
        waiting_users.remove(uid)
    await begin_find_flow(uid, context, gender_pref=None)

# /stop
async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not users.get(str(uid)) or not users[str(uid)].get("partner"):
        await update.message.reply_text("⚠️ You are not in a chat.")
        return
    partner = users[str(uid)]["partner"]
    users[str(uid)]["partner"] = None
    if str(partner) in users:
        users[str(partner)]["partner"] = None
        await context.bot.send_message(partner, "💔 Your partner left the chat.")
        await context.bot.send_message(partner, "What next?", reply_markup=show_end_menu_keyboard())
    await update.message.reply_text("✅ You left the chat.", reply_markup=show_end_menu_keyboard())

# Callback (inline button) handler
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    data = query.data

    if data == "find_any":
        await begin_find_flow(uid, context, gender_pref=None, source_update=update)
        return
    if data == "search_gender":
        if is_premium(uid):
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("♀️ Female", callback_data="pref_female"),
                 InlineKeyboardButton("♂️ Male", callback_data="pref_male")],
                [InlineKeyboardButton("🔁 Any", callback_data="pref_any")]
            ])
            await query.message.reply_text("Choose preferred gender:", reply_markup=kb)
        else:
            await query.message.reply_text("🔒 Gender search is Premium. Get Premium via /ref.")
        return
    if data in ("pref_female","pref_male","pref_any"):
        pref = None
        if data == "pref_female":
            pref = "Female"
        elif data == "pref_male":
            pref = "Male"
        else:
            pref = None
        users[str(uid)]["search_pref"] = pref
        await begin_find_flow(uid, context, gender_pref=pref, source_update=update)
        return

    # profile editing buttons
    if data == "profile" or data == "menu":
        await profile_cmd(update, context)
        return
    if data == "ref":
        await ref_cmd(update, context)
        return
    if data.startswith("edit_"):
        field = data.split("_",1)[1]
        users[str(uid)]["awaiting"] = f"edit_{field}"
        if field == "gender":
            kb = ReplyKeyboardMarkup([["Male ♂","Female ♀"]], one_time_keyboard=True, resize_keyboard=True)
            await query.message.reply_text("Choose new gender:", reply_markup=kb)
        else:
            await query.message.reply_text(f"Send new {field} value:", reply_markup=ReplyKeyboardRemove())
        return

    await query.message.reply_text("Unknown action.")

# Generic message handler: profile inputs & relaying media/text
async def generic_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    uid = update.effective_user.id
    u = ensure_user(uid)
    text = update.message.text if update.message.text else None

    # 1) handle awaiting steps
    awaiting = u.get("awaiting")
    if awaiting:
        if awaiting in ("gender","edit_gender"):
            # accept button or typed gender
            if text and ("male" in text.lower() or "female" in text.lower()):
                u["gender"] = "Male" if "male" in text.lower() else "Female"
                u["awaiting"] = None
                await update.message.reply_text("✅ Gender saved.")
            else:
                kb = ReplyKeyboardMarkup([["Male ♂","Female ♀"]], one_time_keyboard=True, resize_keyboard=True)
                await update.message.reply_text("Please choose Male ♂ or Female ♀", reply_markup=kb)
            return
        if awaiting in ("age","edit_age"):
            if text and text.isdigit() and 10 <= int(text) <= 120:
                u["age"] = text
                u["awaiting"] = None
                await update.message.reply_text("✅ Age saved.")
            else:
                await update.message.reply_text("🔢 Please send valid age (10-120).")
            return
        if awaiting in ("location","edit_location"):
            if text:
                u["location"] = text.strip()
                u["awaiting"] = None
                await update.message.reply_text("✅ Location saved.")
            else:
                await update.message.reply_text("📍 Send your location (city, country).")
            return
        if awaiting in ("interest","edit_interest"):
            if text:
                u["interest"] = text.strip()
                u["awaiting"] = None
                await update.message.reply_text("✅ Interest saved.")
            else:
                await update.message.reply_text("💭 Send a one-line interest.")
            return

    # 2) If profile incomplete and not awaiting, kickstart
    if not is_profile_complete(u):
        if not u.get("gender"):
            u["awaiting"] = "gender"
            kb = ReplyKeyboardMarkup([["Male ♂","Female ♀"]], one_time_keyboard=True, resize_keyboard=True)
            await update.message.reply_text("Choose your gender:", reply_markup=kb)
            return
        if not u.get("age"):
            u["awaiting"] = "age"
            await update.message.reply_text("Send your age (number):", reply_markup=ReplyKeyboardRemove())
            return
        if not u.get("location"):
            u["awaiting"] = "location"
            await update.message.reply_text("Send your location (city,country):")
            return
        if not u.get("interest"):
            u["awaiting"] = "interest"
            await update.message.reply_text("Send a one-line interest:")
            return

    # 3) If user is chatting, forward all content to partner using copy_message
    partner = u.get("partner")
    if partner:
        try:
            await context.bot.copy_message(chat_id=partner,
                                           from_chat_id=update.message.chat_id,
                                           message_id=update.message.message_id)
        except Exception:
            # fallback: if text available, send it
            if text:
                await context.bot.send_message(partner, text)
        return

    # 4) Not chatting: help user
    if text and text.lower() in ("/profile","profile"):
        await profile_cmd(update, context)
        return

    await update.message.reply_text("ℹ️ Not in a chat. Use /find to search or /start to set up your profile.")

# ---------- ROUTE: Telegram webhook receiver ----------
@app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    """Telegram will POST updates here."""
    update = Update.de_json(request.get_json(force=True), application.bot)
    # process update in asyncio event loop
    asyncio.run(application.process_update(update))
    return "OK"

# ---------- STARTUP: set webhook and add handlers ----------
def setup_handlers_and_webhook():
    # add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("find", find_cmd))
    application.add_handler(CommandHandler("next", next_cmd))
    application.add_handler(CommandHandler("stop", stop_cmd))
    application.add_handler(CommandHandler("profile", profile_cmd))
    application.add_handler(CommandHandler("ref", ref_cmd))
    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, generic_message))

    # set webhook (sync call to Telegram)
    asyncio.run(application.bot.set_webhook(WEBHOOK_URL))
    print(f"✅ Webhook set to {WEBHOOK_URL}")

# ---------- FLASK root (health) ----------
@app.route("/", methods=["GET"])
def root():
    return "MeetAnonymousBOT is running."

# ---------- ENTRY POINT ----------
if __name__ == "__main__":
    setup_handlers_and_webhook()
    # start Flask (Gunicorn will use 'app' object exported from this file)
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
                
