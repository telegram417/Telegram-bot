import json
import random
import asyncio
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes,
    filters, ConversationHandler
)

TOKEN = "YOUR_TELEGRAM_BOT_TOKEN_HERE"

# --- Storage file
DATA_FILE = "users.json"

def load_data():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

users = load_data()
searching = set()
active_chats = {}

# --- Helper Functions ---
def get_user(uid):
    if str(uid) not in users:
        users[str(uid)] = {
            "gender": None,
            "age": None,
            "location": None,
            "interest": None,
            "premium_until": None,
            "referrals": 0
        }
    return users[str(uid)]

def is_premium(uid):
    user = get_user(uid)
    if user["premium_until"]:
        return datetime.now() < datetime.fromisoformat(user["premium_until"])
    return False

def add_premium(uid, days=3):
    user = get_user(uid)
    until = datetime.now() + timedelta(days=days)
    user["premium_until"] = until.isoformat()
    save_data(users)

# --- Commands ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)

    text = (
        "🌸 *Welcome to MeetAnonymousBot!* 🌸\n\n"
        "✨ Meet new people, chat freely, and share your thoughts.\n"
        "💬 Everything is private — no usernames, no stress.\n\n"
        "Let's set up your profile!\n"
        "👇 Please select your gender:"
    )

    keyboard = [["👦 Male", "👧 Female"], ["⚧ Other"]]
    await update.message.reply_text(text, parse_mode="Markdown",
                                    reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))

async def handle_profile_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    msg = update.message.text.strip()
    user = get_user(uid)

    # Gender selection
    if user["gender"] is None:
        if msg not in ["👦 Male", "👧 Female", "⚧ Other"]:
            await update.message.reply_text("⚠️ Please choose one from options above.")
            return
        user["gender"] = msg
        await update.message.reply_text("🎂 Great! Now send your *age* (just number, e.g., 18)", parse_mode="Markdown")
        save_data(users)
        return

    # Age input
    if user["age"] is None:
        if not msg.isdigit():
            await update.message.reply_text("⚠️ Please send your age as a number.")
            return
        user["age"] = msg
        await update.message.reply_text("📍 Send your *location* (any text):", parse_mode="Markdown")
        save_data(users)
        return

    # Location input
    if user["location"] is None:
        user["location"] = msg
        await update.message.reply_text("🎯 Finally, share your *interest* or mood today!", parse_mode="Markdown")
        save_data(users)
        return

    # Interest input
    if user["interest"] is None:
        user["interest"] = msg
        await update.message.reply_text("✅ Profile setup complete!\nUse /find to start chatting 💬")
        save_data(users)
        return

    # Normal chat flow (if profile complete)
    if uid in active_chats:
        partner_id = active_chats[uid]
        await context.bot.send_message(partner_id, msg)
    else:
        await update.message.reply_text("💭 You're not in a chat. Use /find to start matching!")

async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)

    if not all([user["gender"], user["age"], user["location"], user["interest"]]):
        await update.message.reply_text("⚠️ Please complete your profile first using /start.")
        return

    if uid in active_chats:
        await update.message.reply_text("💬 You're already chatting! Use /stop to leave.")
        return

    if uid in searching:
        await update.message.reply_text("⏳ You're already searching...")
        return

    searching.add(uid)
    await update.message.reply_text("🔎 Searching for someone to chat with...")

    await asyncio.sleep(1)
    for other_id in list(searching):
        if other_id != uid:
            searching.remove(uid)
            searching.remove(other_id)
            active_chats[uid] = other_id
            active_chats[other_id] = uid

            user1 = get_user(uid)
            user2 = get_user(other_id)

            await context.bot.send_message(
                uid,
                f"🌟 *You’re now connected!* 🌟\n\n"
                f"👤 *Gender:* {user2['gender']}\n🎂 *Age:* {user2['age']}\n"
                f"📍 *Location:* {user2['location']}\n💭 *Interest:* {user2['interest']}\n\n"
                f"✨ Say hi!"
                , parse_mode="Markdown"
            )
            await context.bot.send_message(
                other_id,
                f"🌟 *You’re now connected!* 🌟\n\n"
                f"👤 *Gender:* {user1['gender']}\n🎂 *Age:* {user1['age']}\n"
                f"📍 *Location:* {user1['location']}\n💭 *Interest:* {user1['interest']}\n\n"
                f"✨ Say hi!"
                , parse_mode="Markdown"
            )
            return

    await update.message.reply_text("👀 No one found yet... waiting for someone new 💫")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in active_chats:
        await update.message.reply_text("⚠️ You’re not chatting with anyone.")
        return

    partner_id = active_chats[uid]
    del active_chats[uid]
    del active_chats[partner_id]

    await context.bot.send_message(uid, "❌ You ended the chat.")
    await context.bot.send_message(partner_id, "⚠️ Your partner left the chat.")

async def ref(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)

    ref_link = f"https://t.me/MeetAnonymousBOT?start=ref{uid}"
    premium_status = "🟢 Active" if is_premium(uid) else "🔴 Expired"

    await update.message.reply_text(
        f"🎁 *Referral Program* 🎁\n\n"
        f"Invite friends using your link below:\n"
        f"{ref_link}\n\n"
        f"👥 Each new user gives you +3 days of Premium 💎\n\n"
        f"💠 *Premium Status:* {premium_status}",
        parse_mode="Markdown"
    )

async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌌 *About MeetAnonymousBot* 🌌\n\n"
        "✨ Where strangers meet, stories start, and boredom ends.\n"
        "💬 Chat freely — no names, no pressure.\n\n"
        "🎯 Customize your profile, meet new people, and earn Premium by inviting friends.\n\n"
        "⚙️ Use /find to start your next chat 🌸",
        parse_mode='Markdown'
    )

# --- Main ---
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("find", find))
app.add_handler(CommandHandler("stop", stop))
app.add_handler(CommandHandler("ref", ref))
app.add_handler(CommandHandler("about", about))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_profile_setup))

print("🚀 MeetAnonymousBot is running...")
app.run_polling()
    
