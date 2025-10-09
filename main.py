import os
import time
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from urllib.parse import urlencode

TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = "MeetAnonymousBOT"

# Data storage
users = {}
waiting_users = []
referrals = {}
premium_users = {"@tandoori123": float("inf")}  # Owner: permanent premium

# ---------------------------------------------
# Helper functions
# ---------------------------------------------
def is_premium(username: str):
    if username in premium_users:
        exp = premium_users[username]
        if exp == float("inf") or exp > time.time():
            return True
    return False

def add_premium(username: str, days=3):
    premium_users[username] = time.time() + (days * 86400)

def gen_ref_link(user_id):
    return f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"

# ---------------------------------------------
# Commands
# ---------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = f"@{user.username}" if user.username else str(user_id)

    # Initialize user data
    users[user_id] = users.get(user_id, {"gender": None, "age": None, "partner": None, "ref_count": 0})
    args = context.args

    # Handle referral
    if args and args[0].startswith("ref_"):
        ref_user = int(args[0].split("_")[1])
        if ref_user != user_id:
            referrals.setdefault(ref_user, set()).add(user_id)
            if len(referrals[ref_user]) >= 3:
                ref_name = users.get(ref_user, {}).get("username")
                if ref_name:
                    add_premium(ref_name, days=3)
                    await context.bot.send_message(ref_user, "🎉 Congrats! You’ve unlocked *Premium* for 3 days! 💎", parse_mode="Markdown")

    users[user_id]["username"] = username

    gender_keyboard = ReplyKeyboardMarkup(
        [["👨 Male", "👩 Female"]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await update.message.reply_text(
        "🌸 *Welcome to MeetAnonymousBot!* 🌸\n\n"
        "Choose your gender to start meeting amazing people 💫",
        reply_markup=gender_keyboard,
        parse_mode="Markdown"
    )

async def set_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if user_id not in users:
        users[user_id] = {"gender": None, "age": None, "partner": None}

    if text in ["👨 Male", "👩 Female"]:
        users[user_id]["gender"] = text
        await update.message.reply_text(
            f"✅ Gender set as *{text}*\nNow set your age with `/age 18` 🕐",
            parse_mode="Markdown"
        )
    else:
        # Forward messages in chat
        partner_id = users[user_id].get("partner")
        if partner_id:
            await context.bot.send_message(partner_id, text)

async def set_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if len(context.args) == 1 and context.args[0].isdigit():
        users[user_id]["age"] = int(context.args[0])
        await update.message.reply_text("✅ Age saved! Now use /find to start chatting 💬")
    else:
        await update.message.reply_text("⚠️ Use like: `/age 18`", parse_mode="Markdown")

async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = users.get(user_id)

    if not user or not user.get("gender"):
        await update.message.reply_text("⚠️ Please select your gender using /start first.")
        return

    if user_id in waiting_users:
        await update.message.reply_text("⌛ You’re already in the queue!")
        return

    if waiting_users:
        partner_id = waiting_users.pop(0)
        users[user_id]["partner"] = partner_id
        users[partner_id]["partner"] = user_id

        u_name = users[user_id].get("username", "User")
        p_name = users[partner_id].get("username", "User")

        # Notify both
        await update.message.reply_text("🎉 You’ve been connected! Say hi 👋")
        await context.bot.send_message(partner_id, "🎉 You’ve been connected! Say hi 👋")

        # Show ages if premium
        if is_premium(u_name) or is_premium(p_name):
            age1 = users[user_id].get("age")
            age2 = users[partner_id].get("age")
            if age1 and age2:
                await update.message.reply_text(f"👀 Your partner’s age: {age2}")
                await context.bot.send_message(partner_id, f"👀 Your partner’s age: {age1}")
    else:
        waiting_users.append(user_id)
        await update.message.reply_text("⌛ Waiting for someone special to appear 💞")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    partner_id = users.get(user_id, {}).get("partner")

    if not partner_id:
        await update.message.reply_text("⚠️ You’re not chatting with anyone.")
        return

    # Disconnect both users
    users[user_id]["partner"] = None
    users[partner_id]["partner"] = None

    await update.message.reply_text("❌ Chat ended.\nWho would you like to meet next? 💭")
    await context.bot.send_message(partner_id, "❌ Your partner left the chat.")

    gender_keyboard = ReplyKeyboardMarkup(
        [["👨 Male", "👩 Female"]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await update.message.reply_text(
        "Select the gender you’d like to meet next 💌",
        reply_markup=gender_keyboard
    )

async def ref(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = users.get(user_id, {}).get("username", f"User{user_id}")
    link = gen_ref_link(user_id)

    await update.message.reply_text(
        f"💎 *Invite friends & Earn Premium!*\n\n"
        f"Invite 3 friends using your link to unlock 3 days of Premium access.\n\n"
        f"✨ Your link:\n{link}",
        parse_mode="Markdown"
    )

async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💘 *About MeetAnonymousBot*\n\n"
        "Meet new people. Stay anonymous. Make genuine connections. 💫\n\n"
        "✨ Features:\n"
        "• Random chat with strangers 🌍\n"
        "• Choose who you want to meet 💞\n"
        "• Send messages freely 💬\n"
        "• Earn Premium for 3 days by inviting friends 💎\n\n"
        "Be kind, be real — and enjoy your time 💐",
        parse_mode="Markdown"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Available Commands:*\n"
        "/start - Setup gender\n"
        "/age - Set your age\n"
        "/find - Start chatting\n"
        "/stop - Leave chat\n"
        "/ref - Get referral link\n"
        "/about - Learn about the bot",
        parse_mode="Markdown"
    )

# ---------------------------------------------
# App setup
# ---------------------------------------------
def build_app():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("age", set_age))
    app.add_handler(CommandHandler("find", find))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("ref", ref))
    app.add_handler(CommandHandler("about", about))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, set_gender))
    return app

# ---------------------------------------------
# Run bot (Render compatible)
# ---------------------------------------------
if __name__ == "__main__":
    if not TOKEN:
        print("❌ BOT_TOKEN is missing! Set it in environment variables.")
    else:
        print("🚀 MeetAnonymousBot is running...")
        app = build_app()
        port = int(os.environ.get("PORT", "8080"))
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=TOKEN,
            webhook_url=f"https://telegram-bot-99.onrender.com/{TOKEN}"
    )
    
