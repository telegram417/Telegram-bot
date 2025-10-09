# main.py
import os
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
TOKEN = os.getenv("BOT_TOKEN")  # set this in environment (required)
BOT_USERNAME = "MeetAnonymousBOT"  # used in referral / messages

# ---------- IN-MEMORY STORAGE ----------
# users[uid] = {
#   "gender", "age", "location", "interest", "partner", "next_step", "invites", "premium_until"
# }
users = {}
# queue holds user_ids waiting to be matched (FIFO)
waiting_users = []

# ---------- HELPERS ----------
def ensure_user(uid: int):
    if uid not in users:
        users[uid] = {
            "gender": None,
            "age": None,
            "location": None,
            "interest": None,
            "partner": None,
            "next_step": None,
            "invites": 0,
            "premium_until": None,
        }
    return users[uid]

def format_profile(u: dict) -> str:
    return (
        f"👤 *Gender:* {u.get('gender','Unknown')}\n"
        f"🎂 *Age:* {u.get('age','Unknown')}\n"
        f"📍 *Location:* {u.get('location','Unknown')}\n"
        f"💭 *Interest:* {u.get('interest','Unknown')}"
    )

def show_end_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Find Another", callback_data="find")],
        [InlineKeyboardButton("🔎 Search by Gender (Premium)", callback_data="search_gender")],
    ])

def show_main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Find Chat", callback_data="find"),
         InlineKeyboardButton("⚙️ Profile", callback_data="profile")],
        [InlineKeyboardButton("🎁 Invite (Get Premium)", callback_data="premium")]
    ])

def is_complete_profile(u: dict) -> bool:
    return all([u.get("gender"), u.get("age"), u.get("location"), u.get("interest")])

# ---------- COMMANDS ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ensure_user(uid)
    keyboard = ReplyKeyboardMarkup([["Male ♂", "Female ♀"]], resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(
        "🌸 *Welcome to MeetAnonymousBot!* 🌸\n\n"
        "Let's set up your profile in a few quick steps — no long forms 😉\n\n"
        "👉 First: choose your gender",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌌 *About MeetAnonymousBot* 🌌\n\n"
        "✨ Where strangers meet, stories start, and boredom ends.\n"
        "💬 Chat anonymously — no names, just vibes.\n\n"
        "🎯 Profile: Gender → Age → Location → Interest\n"
        "🔗 Invite friends with /ref to unlock Premium (gender search)\n\n"
        "Use /find to begin your next conversation 💫",
        parse_mode="Markdown"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📘 *Commands*\n"
        "/start — Setup or restart profile\n"
        "/find — Find a chat partner\n"
        "/next — Leave current chat and find next\n"
        "/stop — Leave current chat\n"
        "/profile — View & edit profile\n"
        "/about — About the bot\n"
        "/ref — Invite friends for Premium\n"
        "/help — Show this help message",
        parse_mode="Markdown"
    )

# /profile shows profile and edit buttons
async def profile_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = ensure_user(uid)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Gender", callback_data="edit_gender"),
         InlineKeyboardButton("✏️ Age", callback_data="edit_age")],
        [InlineKeyboardButton("✏️ Location", callback_data="edit_location"),
         InlineKeyboardButton("✏️ Interest", callback_data="edit_interest")],
        [InlineKeyboardButton("🔙 Back", callback_data="menu")]
    ])
    await update.message.reply_text(
        "🧾 *Your Profile*:\n\n" + format_profile(user),
        parse_mode="Markdown",
        reply_markup=kb
    )

# /ref returns an invite link (simple, no persistent invite counting in-memory)
async def ref_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = ensure_user(uid)
    username = update.effective_user.username
    if username:
        link = f"https://t.me/{BOT_USERNAME}?start={username}"
    else:
        link = f"https://t.me/{BOT_USERNAME}?start=ref{uid}"
    await update.message.reply_text(
        "🎁 *Invite & Earn Premium*\n\n"
        f"Share this link with friends:\n{link}\n\n"
        "When you invite friends (they start the bot with your link) you'll unlock Premium features like gender-based search.\n\n"
        "Note: invite counting is stored in memory (server restart will clear invites).",
        parse_mode="Markdown"
    )

# ---------- CALLBACK (buttons) ----------
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    user = ensure_user(uid)
    data = query.data

    if data == "find":
        await begin_find_flow(update, context, from_callback=True)
        return
    if data in ("profile", "menu"):
        # show profile
        await profile_cmd(update, context)
        return
    if data == "premium":
        await query.message.reply_text(
            "🎁 *Premium (Soon)*\n\n"
            "Premium allows you to search by gender and gives priority matching.\n"
            "Use /ref to invite friends and earn Premium.",
            parse_mode="Markdown"
        )
        return
    if data == "search_gender":
        await query.message.reply_text(
            "🔒 *Gender Search (Premium only)*\n\n"
            "Gender-based search is a Premium feature.\n"
            "Invite friends with /ref to unlock Premium for a few days.",
            parse_mode="Markdown"
        )
        return

    # profile edit buttons
    if data == "edit_gender":
        user["next_step"] = "edit_gender"
        kb = ReplyKeyboardMarkup([["Male ♂", "Female ♀"]], resize_keyboard=True, one_time_keyboard=True)
        await query.message.reply_text("Choose your new gender:", reply_markup=kb)
        return
    if data == "edit_age":
        user["next_step"] = "edit_age"
        await query.message.reply_text("Enter your new age (just type the number):", reply_markup=ReplyKeyboardRemove())
        return
    if data == "edit_location":
        user["next_step"] = "edit_location"
        await query.message.reply_text("Enter your new location (city, country):", reply_markup=ReplyKeyboardRemove())
        return
    if data == "edit_interest":
        user["next_step"] = "edit_interest"
        await query.message.reply_text("Enter your new interest (one line):", reply_markup=ReplyKeyboardRemove())
        return

    await query.message.reply_text("Unknown action.")

# ---------- MATCHING FLOW ----------
async def begin_find_flow(update_or_message, context: ContextTypes.DEFAULT_TYPE, from_callback=False):
    """
    If from_callback == True, update_or_message is a CallbackQuery
    else it's an Update (with message)
    """
    if from_callback:
        query = update_or_message.callback_query
        uid = query.from_user.id
        async def reply(text, **k): await query.message.reply_text(text, **k)
    else:
        uid = update_or_message.effective_user.id
        async def reply(text, **k): await update_or_message.message.reply_text(text, **k)

    user = ensure_user(uid)

    if not is_complete_profile(user):
        await reply("⚠️ Please complete your profile first using /start or /profile.", parse_mode="Markdown")
        return

    if user.get("partner"):
        await reply("⚠️ You are already chatting. Use /stop or /next to change partner.")
        return

    # Attempt match: pick first waiting user who is free
    partner_id = None
    while waiting_users:
        candidate = waiting_users.pop(0)
        # skip self or already partnered or missing user
        if candidate == uid:
            continue
        cand = users.get(candidate)
        if not cand:
            continue
        if cand.get("partner") is None:
            partner_id = candidate
            break

    if partner_id:
        # create match
        users[uid]["partner"] = partner_id
        users[partner_id]["partner"] = uid

        partner = users[partner_id]
        my_profile = format_profile(user)
        partner_profile = format_profile(partner)

        # send matched messages
        await context.bot.send_message(uid, "💫 *You’re now connected!* Say hi 👋\n\n" + partner_profile, parse_mode="Markdown")
        await context.bot.send_message(partner_id, "💫 *You’re now connected!* Say hi 👋\n\n" + my_profile, parse_mode="Markdown")
    else:
        # add to queue if not already waiting
        if uid not in waiting_users:
            waiting_users.append(uid)
        await reply("🔍 Searching for someone to chat with... Please wait 💫")

# command wrapper
async def find_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await begin_find_flow(update, context, from_callback=False)

# /next command - leave current and find new
async def next_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = ensure_user(uid)

    # if in chat, notify partner and clear
    if user.get("partner"):
        partner_id = user["partner"]
        user["partner"] = None
        if partner_id in users:
            users[partner_id]["partner"] = None
            await context.bot.send_message(partner_id, "💔 Your partner has left the chat.")
            # show partner end menu
            await context.bot.send_message(partner_id, "What would you like to do next?", reply_markup=show_end_menu_keyboard())

    # remove from waiting list if present
    if uid in waiting_users:
        waiting_users.remove(uid)

    # now start find again
    await begin_find_flow(update, context, from_callback=False)

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
        await context.bot.send_message(partner_id, "💔 Your partner has left the chat.", parse_mode="Markdown")
        # show partner end menu
        await context.bot.send_message(partner_id, "What would you like to do next?", reply_markup=show_end_menu_keyboard())

    await update.message.reply_text("✅ You left the chat.")
    await update.message.reply_text("What would you like to do next?", reply_markup=show_end_menu_keyboard())

# ---------- MESSAGE HANDLER (profile steps & relay) ----------
async def generic_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = ensure_user(uid)
    text = update.message.text if update.message and update.message.text else None

    # If user is mid profile step (next_step) OR profile incomplete, guide them
    ns = user.get("next_step")

    # 1) Gender
    if user.get("gender") is None or ns == "edit_gender":
        # accept either button or plain text
        if text in ["Male ♂", "Female ♀", "Male", "Female"]:
            user["gender"] = "Male" if "Male" in text else "Female"
            user["next_step"] = None
            await update.message.reply_text("✅ Gender saved. Now enter your *age* (just the number).", parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
            return
        else:
            # if they typed during normal flow without pressing buttons, prompt for buttons
            await update.message.reply_text("👉 Please choose your gender: Male ♂ or Female ♀", reply_markup=ReplyKeyboardMarkup([["Male ♂","Female ♀"]], one_time_keyboard=True, resize_keyboard=True))
            return

    # 2) Age
    if user.get("age") is None or ns == "edit_age":
        if text and text.isdigit():
            user["age"] = text
            user["next_step"] = None
            await update.message.reply_text("✅ Age saved. Now send your *location* (city, country).", parse_mode="Markdown")
            return
        else:
            await update.message.reply_text("🔢 Please enter your age as a number (e.g., 20).")
            return

    # 3) Location
    if user.get("location") is None or ns == "edit_location":
        if text:
            user["location"] = text.strip()
            user["next_step"] = None
            await update.message.reply_text("✅ Location saved. Now type one-line *interest* (e.g., 'Just bored').", parse_mode="Markdown")
            return
        else:
            await update.message.reply_text("📍 Please type your location (city or country).")
            return

    # 4) Interest
    if user.get("interest") is None or ns == "edit_interest":
        if text:
            user["interest"] = text.strip()
            user["next_step"] = None
            # profile complete -> show main menu
            await update.message.reply_text("✅ Profile saved!", parse_mode="Markdown")
            await update.message.reply_text(format_profile(user), parse_mode="Markdown")
            await update.message.reply_text("Choose an action:", reply_markup=show_main_menu_keyboard())
            return
        else:
            await update.message.reply_text("💭 Please type a one-line interest (why you're here).")
            return

    # If not in profile input mode:
    # If user is in chat, forward (copy_message preserves media)
    partner_id = user.get("partner")
    if partner_id:
        try:
            # copy_message preserves all media types + captions
            await context.bot.copy_message(chat_id=partner_id,
                                           from_chat_id=update.effective_chat.id,
                                           message_id=update.message.message_id)
        except Exception:
            # fallback to sending text
            if text:
                await context.bot.send_message(partner_id, text)
        return

    # If not in chat and typed "profile" quickly
    if text and text.lower() in ["profile", "/profile", "edit"]:
        await profile_cmd(update, context)
        return

    # Otherwise guide user
    await update.message.reply_text("ℹ️ You are not in a chat. Use /find to search or /start to setup your profile.")

# ---------- BUILD APP ----------
def build_app(token: str):
    app = Application.builder().token(token).build()

    # commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("about", about))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("find", find_cmd))
    app.add_handler(CommandHandler("next", next_cmd))
    app.add_handler(CommandHandler("stop", stop_cmd))
    app.add_handler(CommandHandler("profile", profile_cmd))
    app.add_handler(CommandHandler("ref", ref_cmd))

    # callback buttons
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
        # Using polling for simplicity
        app.run_polling()
    
