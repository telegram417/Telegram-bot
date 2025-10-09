# main.py
import os
import time
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
BOT_USERNAME = "MeetAnonymousBOT"  # for messages/links

# ---------- IN-MEMORY STORAGE ----------
# users[user_id] = {
#   "gender": "Male"/"Female"/None,
#   "age": "18",
#   "location": "City",
#   "interest": "Just bored",
#   "partner": partner_id_or_None,
#   "next_step": None or "age"/"location"/"interest"/"edit_age"/...
# }
users = {}
# queue holds user_ids waiting to be matched (simple FIFO)
waiting_users = []

# ---------- HELPERS ----------
def ensure_user(uid):
    if uid not in users:
        users[uid] = {
            "gender": None,
            "age": None,
            "location": None,
            "interest": None,
            "partner": None,
            "next_step": None,
            "invites": 0,
        }
    return users[uid]

def format_profile(u):
    return (
        f"👤 *Gender:* {u.get('gender','Unknown')}\n"
        f"🎂 *Age:* {u.get('age','Unknown')}\n"
        f"📍 *Location:* {u.get('location','Unknown')}\n"
        f"💭 *Interest:* {u.get('interest','Unknown')}"
    )

def show_end_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Find New Chat", callback_data="find")],
        [InlineKeyboardButton("⚙️ Edit Profile", callback_data="edit")],
        [InlineKeyboardButton("🎁 Get Premium", callback_data="premium")],
    ])

def show_main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Find Chat", callback_data="find"),
         InlineKeyboardButton("⚙️ Profile", callback_data="profile")],
        [InlineKeyboardButton("🎁 Invite (Premium)", callback_data="premium")]
    ])

# ---------- COMMANDS ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ensure_user(uid)
    keyboard = ReplyKeyboardMarkup([["Male ♂", "Female ♀"]], resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(
        "🌸 *Welcome to MeetAnonymousBot!* 🌸\n\n"
        "Let's get your profile set up — quick and easy.\n\n"
        "👉 First: choose your gender",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💘 *About MeetAnonymousBot*\n\n"
        "Anonymous matching — meet new people safely.\n"
        "Set up your profile and use /find to start chatting.\n\n"
        "You can edit profile anytime with /profile.",
        parse_mode="Markdown"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📘 *Commands*\n"
        "/start — Setup profile\n"
        "/find — Search for a chat partner\n"
        "/stop — Leave current chat\n"
        "/profile — Edit your profile\n"
        "/about — About the bot\n"
        "/help — This help message",
        parse_mode="Markdown"
    )

# /profile opens edit menu
async def profile_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = ensure_user(uid)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Edit Gender", callback_data="edit_gender"),
         InlineKeyboardButton("✏️ Edit Age", callback_data="edit_age")],
        [InlineKeyboardButton("✏️ Edit Location", callback_data="edit_location"),
         InlineKeyboardButton("✏️ Edit Interest", callback_data="edit_interest")],
        [InlineKeyboardButton("🔙 Back", callback_data="menu")]
    ])
    await update.message.reply_text(
        "🧾 *Your Profile*:\n\n" + format_profile(user),
        parse_mode="Markdown",
        reply_markup=kb
    )

# ---------- CALLBACK (buttons) ----------
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    user = ensure_user(uid)
    data = query.data

    if data == "find":
        # call find flow
        await begin_find_flow(query, context)
    elif data == "profile" or data == "menu":
        await profile_cmd(update, context)
    elif data == "edit":
        # open profile menu (same as /profile)
        await profile_cmd(update, context)
    elif data == "premium":
        await query.message.reply_text(
            "🎁 *Premium coming soon*\nInvite friends to unlock features.\n(Feature will be added later)",
            parse_mode="Markdown"
        )
    elif data == "edit_gender":
        user["next_step"] = "edit_gender"
        kb = ReplyKeyboardMarkup([["Male ♂", "Female ♀"]], resize_keyboard=True, one_time_keyboard=True)
        await query.message.reply_text("Choose your new gender:", reply_markup=kb)
    elif data == "edit_age":
        user["next_step"] = "edit_age"
        await query.message.reply_text("Enter your new age (just type the number):", reply_markup=ReplyKeyboardRemove())
    elif data == "edit_location":
        user["next_step"] = "edit_location"
        await query.message.reply_text("Enter your new location (city, country):", reply_markup=ReplyKeyboardRemove())
    elif data == "edit_interest":
        user["next_step"] = "edit_interest"
        await query.message.reply_text("Enter your new interest (one line):", reply_markup=ReplyKeyboardRemove())
    else:
        await query.message.reply_text("Unknown action.")

# ---------- FIND FLOW ----------
async def begin_find_flow(source, context: ContextTypes.DEFAULT_TYPE):
    # source may be a CallbackQuery or a Message
    if hasattr(source, "from_user"):  # CallbackQuery
        uid = source.from_user.id
        reply = source.message.reply_text
        send = context.bot.send_message
    else:
        uid = source.effective_user.id
        reply = source.message.reply_text
        send = context.bot.send_message

    user = ensure_user(uid)
    # profile completion check
    if not all([user.get("gender"), user.get("age"), user.get("location"), user.get("interest")]):
        await reply("⚠️ Please complete your profile first. Use /start or /profile.",)
        return

    if user.get("partner"):
        await reply("⚠️ You're already chatting. Use /stop to end current chat.")
        return

    # Attempt match: skip users who are already partnered
    partner_id = None
    while waiting_users:
        candidate = waiting_users.pop(0)
        cand_user = users.get(candidate)
        if not cand_user:
            continue
        if cand_user.get("partner") is None and candidate != uid:
            partner_id = candidate
            break
    if partner_id:
        # create match
        users[uid]["partner"] = partner_id
        users[partner_id]["partner"] = uid

        # prepare and send profiles
        partner = users[partner_id]
        my_profile = format_profile(user)
        partner_profile = format_profile(partner)

        await send(uid, "💫 You’re now connected! Say hi 👋\n\n" + partner_profile, parse_mode="Markdown")
        await send(partner_id, "💫 You’re now connected! Say hi 👋\n\n" + my_profile, parse_mode="Markdown")
    else:
        # no partner -> add to queue if not already in
        if uid not in waiting_users:
            waiting_users.append(uid)
        await reply("🔍 Searching for someone to chat with... Please wait 💫")

# wrapper so both callback and command can call find
async def find_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await begin_find_flow(update, context)

# ---------- STOP ----------
async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = users.get(uid)
    if not user or not user.get("partner"):
        await update.message.reply_text("⚠️ You are not in a chat right now.")
        return

    partner_id = user["partner"]
    # clear both sides safely
    user["partner"] = None
    if partner_id in users:
        users[partner_id]["partner"] = None
        # notify the partner
        await context.bot.send_message(partner_id, "💔 Your partner has left the chat.")
        # show partner end menu
        await context.bot.send_message(partner_id, "What would you like to do next?", reply_markup=show_end_menu_keyboard())

    await update.message.reply_text("✅ You left the chat.")
    await update.message.reply_text("What would you like to do next?", reply_markup=show_end_menu_keyboard())

# ---------- MESSAGE HANDLER (profile steps & relay) ----------
async def generic_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text if update.message and update.message.text else None
    user = ensure_user(uid)

    # If in a profile step (next_step), handle that first
    ns = user.get("next_step")
    if ns:
        # profile edit flows and initial setup flows
        if ns == "edit_gender" or (user["gender"] is None and text in ["Male ♂", "Female ♀"]):
            # accept button gender either way
            if text in ["Male ♂", "Female ♀"]:
                user["gender"] = "Male" if "Male" in text else "Female"
            else:
                # typed plain 'Male' or 'Female'
                if text and text.lower() in ["male", "female"]:
                    user["gender"] = "Male" if text.lower() == "male" else "Female"
                else:
                    await update.message.reply_text("⚠️ Please choose Male or Female.")
                    return
            user["next_step"] = None
            await update.message.reply_text("✅ Gender saved. Now continue with /profile to edit other fields or /find to search.")
            return

        if ns == "edit_age" or user["age"] is None:
            if text and text.isdigit():
                user["age"] = text
                user["next_step"] = None
                await update.message.reply_text("✅ Age saved. Now send your location (e.g. Delhi, India).")
            else:
                await update.message.reply_text("⚠️ Please enter a numeric age (e.g., 20).")
            return

        if ns == "edit_location" or user["location"] is None:
            if text:
                user["location"] = text.strip()
                user["next_step"] = None
                await update.message.reply_text("✅ Location saved. Now type one-line interest (e.g., Just bored).")
            else:
                await update.message.reply_text("⚠️ Please type your location (city, country).")
            return

        if ns == "edit_interest" or user["interest"] is None:
            if text:
                user["interest"] = text.strip()
                user["next_step"] = None
                # profile complete -> show main menu
                await update.message.reply_text("✅ Profile updated!", parse_mode="Markdown")
                await update.message.reply_text(format_profile(user), parse_mode="Markdown")
                await update.message.reply_text("Choose an action:", reply_markup=show_main_menu_keyboard())
            else:
                await update.message.reply_text("⚠️ Please type one-line interest.")
            return

    # If not in profile input mode:
    # If user is in chat, forward (copy_message preserves media)
    partner_id = user.get("partner")
    if partner_id:
        try:
            await context.bot.copy_message(chat_id=partner_id,
                                           from_chat_id=update.message.chat_id,
                                           message_id=update.message.message_id)
        except Exception:
            # fallback for text
            if text:
                await context.bot.send_message(partner_id, text)
        return

    # If not in chat and message looks like a quick edit request:
    if text and text.lower() in ["edit", "profile", "/profile"]:
        await profile_cmd(update, context)
        return

    # Otherwise guide user
    await update.message.reply_text("ℹ️ Not in a chat. Use /find to search or /start to setup your profile.")

# ---------- START-UP / BUILD ----------
def build_app(token):
    app = Application.builder().token(token).build()

    # commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("about", about))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("find", find_cmd))
    app.add_handler(CommandHandler("stop", stop_cmd))
    app.add_handler(CommandHandler("profile", profile_cmd))

    # buttons
    app.add_handler(CallbackQueryHandler(callback_handler))

    # generic messages (profile setup, edits, relays)
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, generic_message))

    return app

# ---------- RUN ----------
if __name__ == "__main__":
    if not TOKEN:
        print("❌ BOT_TOKEN missing in environment. Set BOT_TOKEN and restart.")
    else:
        print("🚀 MeetAnonymousBot running (in-memory mode).")
        app = build_app(TOKEN)
        # Using polling for simplicity — change to run_webhook if you prefer webhooks.
        app.run_polling()
    
