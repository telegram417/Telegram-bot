import os
import asyncio
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")

users = {}
waiting_users = []
premium_users = {"@tandoori123"}


# 🌟 /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    users[user_id] = {
        "gender": None,
        "age": None,
        "location": None,
        "interest": None,
        "partner": None,
        "invites": 0,
    }

    keyboard = [["Male ♂", "Female ♀"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

    await update.message.reply_text(
        "👋 *Welcome to MeetAnonymousBot!*\n\n"
        "Let's set up your profile 💫\n\n"
        "👉 First, select your *gender:*",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )


# 🌈 Handle profile setup
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    user = users.get(user_id)

    if not user:
        await start(update, context)
        return

    if not user["gender"]:
        if text in ["Male ♂", "Female ♀"]:
            user["gender"] = "Male" if "Male" in text else "Female"
            await update.message.reply_text("🎂 Great! Now, tell me your *age:*", parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ Please select your gender using the buttons above.")
        return

    if not user["age"]:
        if text.isdigit():
            user["age"] = text
            await update.message.reply_text("📍 Nice! Now share your *location:* (e.g. Delhi, India)", parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ Please enter a valid age number.")
        return

    if not user["location"]:
        user["location"] = text
        await update.message.reply_text("💭 Cool! What’s your *interest*? (e.g. Just here to talk 😄)", parse_mode="Markdown")
        return

    if not user["interest"]:
        user["interest"] = text
        await update.message.reply_text(
            "✅ *Profile setup complete!*\n\n"
            f"👤 *Gender:* {user['gender']}\n"
            f"🎂 *Age:* {user['age']}\n"
            f"📍 *Location:* {user['location']}\n"
            f"💭 *Interest:* {user['interest']}\n\n"
            "Now type /find to meet someone 💌",
            parse_mode="Markdown"
        )
        return

    if user.get("partner"):
        partner_id = user["partner"]
        await context.bot.send_message(partner_id, text)
    else:
        await update.message.reply_text("⚠️ You’re not in a chat. Type /find to start chatting.")


# ✨ Animated searching
async def searching_animation(message, context):
    animations = [
        "🔍 Searching for your next connection...",
        "💫 Looking around the world...",
        "🌎 Finding someone who matches your vibe...",
        "❤️ Almost there...",
    ]
    for step in animations:
        await message.edit_text(step)
        await asyncio.sleep(2)


# 🔎 Find partner
async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = users.get(user_id)

    if not user or not all([user["gender"], user["age"], user["location"], user["interest"]]):
        await update.message.reply_text("⚠️ Please complete your profile first using /start.")
        return

    if user.get("partner"):
        await update.message.reply_text("⚠️ You’re already chatting! Use /stop to end it.")
        return

    if waiting_users and waiting_users[0] != user_id:
        partner_id = waiting_users.pop(0)
        partner = users.get(partner_id)

        if partner and not partner.get("partner"):
            user["partner"] = partner_id
            partner["partner"] = user_id

            await context.bot.send_message(partner_id, "💬 You’re now connected! Say hi 👋")
            await update.message.reply_text("💬 You’re now connected! Say hi 👋")

            # Show each other's info
            info_user = (
                f"👤 *Gender:* {partner['gender']}\n"
                f"🎂 *Age:* {partner['age']}\n"
                f"📍 *Location:* {partner['location']}\n"
                f"💭 *Interest:* {partner['interest']}"
            )
            await update.message.reply_text(f"✨ *Your partner’s info:*\n{info_user}", parse_mode="Markdown")

            info_partner = (
                f"👤 *Gender:* {user['gender']}\n"
                f"🎂 *Age:* {user['age']}\n"
                f"📍 *Location:* {user['location']}\n"
                f"💭 *Interest:* {user['interest']}"
            )
            await context.bot.send_message(partner_id, f"✨ *Your partner’s info:*\n{info_partner}", parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ Partner got busy. Try /find again.")
    else:
        waiting_users.append(user_id)
        msg = await update.message.reply_text("🔍 Searching for your next connection...")
        await searching_animation(msg, context)
        await msg.edit_text("⏳ Still searching... Please wait 💫")


# 🛑 Stop chat
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = users.get(user_id)

    if not user or not user.get("partner"):
        await update.message.reply_text("⚠️ You’re not chatting right now.")
        return

    partner_id = user["partner"]
    partner = users.get(partner_id)

    if partner:
        partner["partner"] = None
        await context.bot.send_message(partner_id, "❌ Your partner left the chat.")
        await context.bot.send_message(partner_id, "💔 Want to meet someone new? Type /find 💫")

    user["partner"] = None
    await update.message.reply_text("✅ You left the chat. Type /find to meet new people 💌")


# 🆘 Help
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Available Commands:*\n\n"
        "/start - Setup or edit your profile 🌸\n"
        "/find - Find someone to chat 💬\n"
        "/stop - Leave chat ❌\n"
        "/ref - Invite friends for Premium 🎁\n"
        "/help - Show all commands 📘",
        parse_mode="Markdown"
    )


# 🎁 Referral
async def ref(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.effective_user.username
    if username:
        await update.message.reply_text(
            f"🎁 *Invite Friends to Unlock Premium!*\n\n"
            f"Share this link:\n👉 `https://t.me/MeetAnonymousBOT?start={username}`\n\n"
            "Invite 5 people to get *Premium for 3 days!* 💖",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("⚠️ You need a Telegram username to use referrals.")


# 🚀 Build App
def build_app(token):
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("find", find))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("ref", ref))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    return app


if __name__ == "__main__":
    if not TOKEN:
        print("❌ BOT_TOKEN missing!")
    else:
        print("🚀 MeetAnonymousBot is running...")
        app = build_app(TOKEN)
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    
