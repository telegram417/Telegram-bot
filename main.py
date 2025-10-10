# main.py
import os
import asyncio
from datetime import datetime, timedelta
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

# ---------- CONFIG ----------
TOKEN = os.getenv("BOT_TOKEN")  # set this in environment
BOT_USERNAME = "MeetAnonymousBOT"  # used in /ref link text
PREMIUM_INVITES_REQUIRED = 5
PREMIUM_DAYS = 3

if not TOKEN:
    raise RuntimeError("❌ BOT_TOKEN environment variable is not set. Add it and restart.")

# ---------- IN-MEMORY STORAGE ----------
# users[user_id] = {
#   "gender": "Male"/"Female"/None,
#   "age": "18"/None,
#   "location": "City"/None,
#   "interest": "text"/None,
#   "partner": partner_id_or_None,
#   "awaiting": None or "gender"/"age"/"location"/"interest"/"edit_gender"/...,
#   "invites": 0,
#   "premium_until": ISO string or None,
#   "search_pref": None or "Male"/"Female"/"Any"
# }
users = {}
# waiting queue (simple FIFO list of user_ids)
waiting_users = []

# ---------- HELPERS ----------
def ensure_user(uid: int):
    u = users.get(uid)
    if not u:
        u = {
            "gender": None,
            "age": None,
            "location": None,
            "interest": None,
            "partner": None,
            "awaiting": None,
            "invites": 0,
            "premium_until": None,
            "search_pref": None,
        }
        users[uid] = u
    return u

def is_profile_complete(u: dict) -> bool:
    return bool(u.get("gender") and u.get("age") and u.get("location") and u.get("interest"))

def is_premium(uid: int) -> bool:
    u = users.get(uid)
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
        f"👤 *Gender:* {u.get('gender','Unknown')}\n"
        f"🎂 *Age:* {u.get('age','Unknown')}\n"
        f"📍 *Location:* {u.get('location','Unknown')}\n"
        f"💭 *Interest:* {u.get('interest','Unknown')}"
    )

def show_end_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Find Another", callback_data="find_any")],
        [InlineKeyboardButton("🔎 Search by Gender (Premium)", callback_data="search_gender")],
    ])

def show_main_menu_keyboard(user_id: int):
    premium_flag = "💎" if is_premium(user_id) else ""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Find Chat", callback_data="find_any"),
         InlineKeyboardButton("⚙️ Profile", callback_data="profile")],
        [InlineKeyboardButton(f"🎁 Invite (Get Premium) {premium_flag}", callback_data="ref")]
    ])

async def search_animation_send(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    # send and edit a single message for animation
    messages = [
        "🔍 Searching the cosmos for your vibe...",
        "💫 Twinkling through profiles...",
        "✨ Aligning stars...",
        "❤️ Connecting you now..."
    ]
    msg = await context.bot.send_message(chat_id, messages[0])
    for i in range(1, len(messages)):
        await asyncio.sleep(1.0)
        try:
            await context.bot.edit_message_text(messages[i], chat_id=chat_id, message_id=msg.message_id)
        except Exception:
            # if edit fails (rare), just send a new message
            msg = await context.bot.send_message(chat_id, messages[i])
    await asyncio.sleep(0.8)
    # final small pause
    try:
        await context.bot.edit_message_text("✨ Almost there...", chat_id=chat_id, message_id=msg.message_id)
    except Exception:
        await context.bot.send_message(chat_id, "✨ Almost there...")

# ---------- COMMANDS ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start / restart. Also handles referral param: /start ref<inviter_id>"""
    uid = update.effective_user.id
    args = context.args or []
    inviter_id = None

    # preserve existing profile; only set awaiting if profile incomplete
    u = ensure_user(uid)

    # Handle referral if present: expects start=ref<digits>
    if args:
        raw = args[0]
        if raw.startswith("ref"):
            ref_token = raw[3:]
            try:
                inviter_id = int(ref_token)
                inviter = users.get(inviter_id)
                if inviter:
                    inviter["invites"] = inviter.get("invites", 0) + 1
                    # award premium if reached threshold
                    if inviter["invites"] >= PREMIUM_INVITES_REQUIRED:
                        grant_premium(inviter_id, PREMIUM_DAYS)
                        inviter["invites"] = 0
                        # notify inviter if possible won't work if they are offline - but we try
                        try:
                            await context.bot.send_message(inviter_id,
                                f"🎉 Congrats — you got {PREMIUM_DAYS} days of Premium for inviting {PREMIUM_INVITES_REQUIRED} people! 🎁")
                        except Exception:
                            pass
                # else: inviter not known (maybe invite link used before inviter created)
            except Exception:
                pass

    # If profile incomplete — start step-by-step
    if not is_profile_complete(u):
        u["awaiting"] = "gender"
        keyboard = ReplyKeyboardMarkup([["Male ♂", "Female ♀"]], one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text(
            "👋 *Welcome to MeetAnonymousBot!* 🌸\n\nLet's set up your profile in a few easy steps.\n\n👉 First, select your *gender:*",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        return

    # profile exists -> show main menu
    await update.message.reply_text(
        "✨ You're all set! Use the menu below to start matching or edit profile.",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )
    await update.message.reply_text("Choose an action:", reply_markup=show_main_menu_keyboard(uid))

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Commands*\n\n"
        "/start — Setup or edit your profile 🌸\n"
        "/find — Find someone to chat 💬\n"
        "/next — Leave current chat and find next 🔁\n"
        "/stop — Leave current chat ❌\n"
        "/profile — View & edit profile ⚙️\n"
        "/ref — Invite friends / get Premium 🎁\n"
        "/help — Show this help 📘",
        parse_mode="Markdown"
    )

async def profile_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = ensure_user(uid)
    premium_text = ""
    if is_premium(uid):
        premium_text = f"\n💎 *Premium active until:* {u['premium_until']}"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Edit Gender", callback_data="edit_gender"),
         InlineKeyboardButton("✏️ Edit Age", callback_data="edit_age")],
        [InlineKeyboardButton("✏️ Edit Location", callback_data="edit_location"),
         InlineKeyboardButton("✏️ Edit Interest", callback_data="edit_interest")],
        [InlineKeyboardButton("🔙 Back", callback_data="menu")]
    ])
    await update.message.reply_text(
        "🧾 *Your Profile*\n\n" + format_profile(u) + premium_text,
        parse_mode="Markdown",
        reply_markup=kb
    )

async def ref_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    username = update.effective_user.username
    if username:
        link = f"https://t.me/{BOT_USERNAME}?start=ref{uid}"
    else:
        link = f"https://t.me/{BOT_USERNAME}?start=ref{uid}"
    u = ensure_user(uid)
    prem = "🟢 Active" if is_premium(uid) else "🔴 Expired"
    await update.message.reply_text(
        f"🎁 *Invite Friends and Earn Premium*\n\n"
        f"Share this link:\n👉 `{link}`\n\n"
        f"Invites: *{u.get('invites',0)}* / {PREMIUM_INVITES_REQUIRED}\n"
        f"Premium: *{prem}*\n\n"
        f"When someone starts the bot with your link, you get +1 invite. Reach {PREMIUM_INVITES_REQUIRED} to unlock {PREMIUM_DAYS} days of Premium.",
        parse_mode="Markdown"
    )

# ---------- MATCHING & BUTTONS ----------
async def begin_find_flow(uid: int, context: ContextTypes.DEFAULT_TYPE, gender_pref: str = None, from_callback=False, source_update=None):
    """
    gender_pref = "Male"/"Female"/None
    source_update: Update object if we need to reply via update instead of context
    """
    u = ensure_user(uid)
    if not is_profile_complete(u):
        if from_callback and source_update:
            await source_update.callback_query.message.reply_text("⚠️ Please complete your profile first with /start.")
        else:
            await context.bot.send_message(uid, "⚠️ Please complete your profile first with /start.")
        return

    if u.get("partner"):
        if from_callback and source_update:
            await source_update.callback_query.message.reply_text("⚠️ You are already chatting. Use /stop or /next.")
        else:
            await context.bot.send_message(uid, "⚠️ You are already chatting. Use /stop or /next.")
        return

    # do animation
    try:
        if from_callback and source_update:
            await search_animation_send(source_update.callback_query.message.chat_id, context)
        else:
            await search_animation_send(uid, context)
    except Exception:
        pass  # animation failing shouldn't break the flow

    # Find candidate from waiting queue
    partner_id = None
    found_index = None
    for idx, candidate in enumerate(waiting_users):
        if candidate == uid:
            continue
        cand = users.get(candidate)
        if not cand:
            continue
        if cand.get("partner"):
            continue
        # if gender_pref specified, require candidate gender to match
        if gender_pref and cand.get("gender") != gender_pref:
            continue
        # otherwise match
        partner_id = candidate
        found_index = idx
        break

    if partner_id is not None:
        # remove candidate from queue
        waiting_users.pop(found_index)
        # create pairing
        users[uid]["partner"] = partner_id
        users[partner_id]["partner"] = uid
        # clear search_pref
        users[uid]["search_pref"] = None
        users[partner_id]["search_pref"] = None

        # send profile info and connected messages
        partner = users[partner_id]
        my_profile = format_profile(users[uid])
        partner_profile = format_profile(partner)
        await context.bot.send_message(uid, f"💬 *You’re now connected!* Say hi 👋\n\n{partner_profile}", parse_mode="Markdown")
        await context.bot.send_message(partner_id, f"💬 *You’re now connected!* Say hi 👋\n\n{my_profile}", parse_mode="Markdown")
        return

    # no partner found -> add to queue
    if uid not in waiting_users:
        waiting_users.append(uid)
    if from_callback and source_update:
        await source_update.callback_query.message.reply_text("🔍 Searching for a match... you're in queue 💫")
    else:
        await context.bot.send_message(uid, "🔍 Searching for a match... you're in queue 💫")


# Command wrapper
async def find_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    # show quick options: find any / search by gender (premium)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Find Any", callback_data="find_any")],
        [InlineKeyboardButton("🔎 Search by Gender", callback_data="search_gender")],
    ])
    await update.message.reply_text("Choose how you want to search:", reply_markup=kb)

# /next = leave current chat and find new
async def next_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    # if in chat, notify partner and clear
    if users.get(uid, {}).get("partner"):
        partner_id = users[uid]["partner"]
        users[uid]["partner"] = None
        if partner_id in users:
            users[partner_id]["partner"] = None
            await context.bot.send_message(partner_id, "💔 Your partner left the chat.")
            # show partner end menu
            await context.bot.send_message(partner_id, "What would you like to do next?", reply_markup=show_end_menu_keyboard())
    # remove from waiting list if present
    if uid in waiting_users:
        waiting_users.remove(uid)
    # now start search for any
    await begin_find_flow(uid, context, gender_pref=None, from_callback=False)

# /stop = leave chat and show menu
async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not users.get(uid) or not users[uid].get("partner"):
        await update.message.reply_text("⚠️ You’re not in a chat right now.")
        return
    partner_id = users[uid]["partner"]
    users[uid]["partner"] = None
    if partner_id in users:
        users[partner_id]["partner"] = None
        await context.bot.send_message(partner_id, "💔 Your partner has left the chat.")
        await context.bot.send_message(partner_id, "What would you like to do next?", reply_markup=show_end_menu_keyboard())
    await update.message.reply_text("✅ You left the chat. What next?", reply_markup=show_end_menu_keyboard())

# ---------- CALLBACK (inline buttons) ----------
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    data = query.data

    # find actions
    if data == "find_any":
        await begin_find_flow(uid, context, gender_pref=None, from_callback=True, source_update=update)
        return
    if data == "search_gender":
        if is_premium(uid):
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("♀️ Female", callback_data="pref_female"),
                 InlineKeyboardButton("♂️ Male", callback_data="pref_male")],
                [InlineKeyboardButton("🔁 Any", callback_data="pref_any")]
            ])
            await query.message.reply_text("Choose preferred gender to search for:", reply_markup=kb)
        else:
            await query.message.reply_text(
                "🔒 *Gender Search is Premium*\nInvite friends with /ref to unlock Premium for 3 days.",
                parse_mode="Markdown"
            )
        return
    if data in ("pref_female", "pref_male", "pref_any"):
        pref = None
        if data == "pref_female":
            pref = "Female"
        elif data == "pref_male":
            pref = "Male"
        else:
            pref = None
        users[uid]["search_pref"] = pref
        await begin_find_flow(uid, context, gender_pref=pref, from_callback=True, source_update=update)
        return

    # profile/menu/edit actions
    if data == "profile" or data == "menu":
        await profile_cmd(update, context)
        return
    if data == "ref":
        await ref_cmd(update, context)
        return

    if data.startswith("edit_"):
        # set awaiting state
        field = data.split("_", 1)[1]  # gender, age, location, interest
        users[uid]["awaiting"] = f"edit_{field}"
        # prompt accordingly
        if field == "gender":
            kb = ReplyKeyboardMarkup([["Male ♂", "Female ♀"]], resize_keyboard=True, one_time_keyboard=True)
            await query.message.reply_text("Choose new gender:", reply_markup=kb)
        else:
            await query.message.reply_text(f"Send new {field} (just the value):", reply_markup=ReplyKeyboardRemove())
        return

    # end-menu actions
    await query.message.reply_text("Unknown action.")

# ---------- MESSAGE HANDLER (profile setup / edits / relaying) ----------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text if update.message and update.message.text else None
    u = ensure_user(uid)

    # 1) If awaiting edit or initial setup
    awaiting = u.get("awaiting")
    if awaiting:
        if awaiting in ("gender", "edit_gender"):
            if text and any(x in text.lower() for x in ("male","female")):
                u["gender"] = "Male" if "male" in text.lower() else "Female"
                u["awaiting"] = None
                await update.message.reply_text("✅ Gender saved. Now enter /find to search or /profile to edit more.", reply_markup=ReplyKeyboardRemove())
            else:
                keyboard = ReplyKeyboardMarkup([["Male ♂", "Female ♀"]], resize_keyboard=True, one_time_keyboard=True)
                await update.message.reply_text("👉 Please choose Male ♂ or Female ♀", reply_markup=keyboard)
            return

        if awaiting in ("age", "edit_age"):
            if text and text.isdigit() and 10 <= int(text) <= 120:
                u["age"] = text
                u["awaiting"] = None
                await update.message.reply_text("✅ Age saved. Now enter /find to search or /profile to edit more.")
            else:
                await update.message.reply_text("🔢 Please enter a valid age number (10-120).")
            return

        if awaiting in ("location", "edit_location"):
            if text:
                u["location"] = text.strip()
                u["awaiting"] = None
                await update.message.reply_text("✅ Location saved. Now enter /find to search or /profile to edit more.")
            else:
                await update.message.reply_text("📍 Please type your location (city, country).")
            return

        if awaiting in ("interest", "edit_interest"):
            if text:
                u["interest"] = text.strip()
                u["awaiting"] = None
                await update.message.reply_text("✅ Interest saved. Profile is updated.", parse_mode="Markdown")
            else:
                await update.message.reply_text("💭 Please type a one-line interest.")
            return

    # 2) If profile incomplete but no awaiting set, start the next step automatically
    if not is_profile_complete(u):
        if not u.get("gender"):
            u["awaiting"] = "gender"
            kb = ReplyKeyboardMarkup([["Male ♂", "Female ♀"]], one_time_keyboard=True, resize_keyboard=True)
            await update.message.reply_text("👉 Please choose your gender:", reply_markup=kb)
            return
        if not u.get("age"):
            u["awaiting"] = "age"
            await update.message.reply_text("🎂 Please send your age (just number):", reply_markup=ReplyKeyboardRemove())
            return
        if not u.get("location"):
            u["awaiting"] = "location"
            await update.message.reply_text("📍 Send your location (city, country):")
            return
        if not u.get("interest"):
            u["awaiting"] = "interest"
            await update.message.reply_text("💭 Finally, tell us your interest or mood (one line):")
            return

    # 3) If user is in chat, relay other message types & text
    partner_id = u.get("partner")
    if partner_id:
        try:
            # preserve media where possible
            await context.bot.copy_message(chat_id=partner_id,
                                           from_chat_id=update.effective_chat.id,
                                           message_id=update.message.message_id)
        except Exception:
            # fallback: send plain text only
            if text:
                await context.bot.send_message(partner_id, text)
        return

    # 4) Not chatting & not editing -> guide the user
    if text and text.lower() in ("profile", "/profile"):
