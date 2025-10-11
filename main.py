import os
import asyncio
from flask import Flask
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")  # Set your Telegram bot token in Render’s Environment Variables

app = Flask(__name__)

# ------------------ Flask Route (to prevent sleeping) ------------------ #
@app.route('/')
def home():
    return "AnonChatPlush Bot is alive ✨"

# ------------------ Bot Data ------------------ #
users = {}
searching = set()
premium_users = set()

# ------------------ Start Command ------------------ #
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    users[uid] = {"gender": None, "age": None, "location": None, "interest": None, "partner": None}
    await update.message.reply_text(
        "🌟 **Welcome to AnonChatPlush!**\n\n"
        "Let's get you started 👇\n"
        "Type /setprofile to set your Gender, Age, Location & Interest 💬",
        parse_mode="Markdown"
    )

# ------------------ Help Command ------------------ #
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💡 **AnonChatPlush Commands**\n\n"
        "🧩 /start - Start bot\n"
        "🧠 /setprofile - Setup or update profile\n"
        "🎯 /find - Find random user to chat\n"
        "🚫 /stop - Stop current chat\n"
        "🌈 /ref - Invite & get Premium\n"
        "📘 /help - Show this menu",
        parse_mode="Markdown"
    )

# ------------------ Set Profile ------------------ #
async def setprofile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    users.setdefault(uid, {})
    msg = (
        "🧠 **Let’s set your profile!**\n\n"
        "Please reply in this format:\n"
        "`Gender | Age | Location | Interests`\n\n"
        "Example:\n`Male | 18 | Delhi | Anime, Music`"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def profile_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in users:
        return await update.message.reply_text("Please use /setprofile first 💫")

    text = update.message.text
    try:
        gender, age, location, interest = [x.strip() for x in text.split("|")]
        users[uid] = {
            "gender": gender,
            "age": age,
            "location": location,
            "interest": interest,
            "partner": None
        }
        await update.message.reply_text(
            f"✅ Profile Updated!\n\n"
            f"✨ Gender: {gender}\n🎂 Age: {age}\n📍 Location: {location}\n💭 Interest: {interest}\n\n"
            "Use /find to start chatting! 💬",
            parse_mode="Markdown"
        )
    except Exception:
        await update.message.reply_text("⚠️ Please follow the format correctly:\n`Gender | Age | Location | Interests`")

# ------------------ Find Chat Partner ------------------ #
async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in users or not users[uid].get("gender"):
        return await update.message.reply_text("❗ Set your profile first using /setprofile")

    if uid in premium_users or True:  # remove premium restriction for now
        if uid in searching:
            await update.message.reply_text("🔍 Already searching for a partner...")
            return
        if users[uid].get("partner"):
            await update.message.reply_text("💬 You're already chatting!")
            return

        # Try to match
        for user_id in list(searching):
            if user_id != uid and not users[user_id].get("partner"):
                users[user_id]["partner"] = uid
                users[uid]["partner"] = user_id
                searching.remove(user_id)
                await context.bot.send_message(user_id, "💞 Matched! Say Hi 👋")
                await update.message.reply_text("💞 Matched! Say Hi 👋")
                return

        searching.add(uid)
        await update.message.reply_text("🕊 Searching for someone to chat...")
    else:
        await update.message.reply_text(
            "🔒 Only Premium users can search directly.\nUse /ref to invite 3 friends and unlock Premium for 3 days!"
        )

# ------------------ Stop Chat ------------------ #
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    partner = users.get(uid, {}).get("partner")
    if not partner:
        return await update.message.reply_text("You're not chatting right now ❌")

    users[uid]["partner"] = None
    users[partner]["partner"] = None
    await context.bot.send_message(partner, "😢 Partner left the chat.\nUse /find to meet someone new 💫")
    await update.message.reply_text("💬 Chat ended. Use /find to start a new one!")

# ------------------ Refer Command ------------------ #
async def ref(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    link = f"https://t.me/{context.bot.username}?start={uid}"
    await update.message.reply_text(
        f"🌈 **Invite friends!**\n\nShare this link 👇\n{link}\n\n"
        "Invite 3 people to get **3 days Premium Access** 💎",
        parse_mode="Markdown"
    )

# ------------------ Message Forwarding ------------------ #
async def relay_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    partner = users.get(uid, {}).get("partner")
    if not partner:
        return await update.message.reply_text("You’re not chatting yet. Use /find 💬")

    msg = update.message
    if msg.text:
        await context.bot.send_message(partner, msg.text)
    elif msg.photo:
        await context.bot.send_photo(partner, msg.photo[-1].file_id)
    elif msg.sticker:
        await context.bot.send_sticker(partner, msg.sticker.file_id)
    elif msg.voice:
        await context.bot.send_voice(partner, msg.voice.file_id)
    elif msg.video:
        await context.bot.send_video(partner, msg.video.file_id)

# ------------------ Run Bot ------------------ #
async def main():
    app_bot = ApplicationBuilder().token(TOKEN).build()

    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("help", help_command))
    app_bot.add_handler(CommandHandler("setprofile", setprofile))
    app_bot.add_handler(CommandHandler("find", find))
    app_bot.add_handler(CommandHandler("stop", stop))
    app_bot.add_handler(CommandHandler("ref", ref))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, profile_text))
    app_bot.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, relay_message))

    print("Bot started successfully 🚀")
    await app_bot.run_polling()

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(main())
    app.run(host="0.0.0.0", port=10000)
