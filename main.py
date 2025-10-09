import os
import time
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")

users = {}
waiting_users = {"any": [], "male": [], "female": []}
premium_users = {"@tandoori123"}
referrals = {}
premium_duration = 3 * 24 * 60 * 60  # 3 days in seconds


def is_premium(username):
    if username in premium_users:
        return True
    if username in referrals and time.time() < referrals[username]:
        return True
    return False


# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    users[user_id] = {"gender": None, "partner": None, "age": None, "location": None, "interest": None, "match_pref": None}

    keyboard = [["👨 Male", "👩 Female"]]
    await update.message.reply_text(
        "🌈 *Welcome to MeetAnonymousBot!* 💬\n\n"
        "Chat anonymously with people worldwide 🌍\n\n"
        "But first, choose your gender 👇",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )


# Gender selection
async def gender_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    gender = None
    if text == "👨 Male":
        gender = "Male"
    elif text == "👩 Female":
        gender = "Female"

    if gender:
        users[user_id]["gender"] = gender
        await update.message.reply_text(f"✅ Gender set as *{gender}*.\nNow send your age like this → /age 20", parse_mode="Markdown")
    else:
        partner_id = users.get(user_id, {}).get("partner")
        if partner_id:
            await context.bot.copy_message(chat_id=partner_id, from_chat_id=user_id, message_id=update.message.message_id)
        else:
            await update.message.reply_text("⚠️ Please choose your gender first using /start.")


# /age
async def set_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if len(context.args) == 1 and context.args[0].isdigit():
        users[user_id]["age"] = int(context.args[0])
        await update.message.reply_text("📍 Great! Now tell me — where are you from?")
        users[user_id]["next_step"] = "location"
    else:
        await update.message.reply_text("⚠️ Use like this → /age 20")


# Handle location & interest
async def extra_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if "next_step" not in users[user_id]:
        partner_id = users.get(user_id, {}).get("partner")
        if partner_id:
            await context.bot.copy_message(chat_id=partner_id, from_chat_id=user_id, message_id=update.message.message_id)
        else:
            await update.message.reply_text("⚠️ You’re not chatting yet. Use /find to start.")
        return

    step = users[user_id]["next_step"]

    if step == "location":
        users[user_id]["location"] = text
        users[user_id]["next_step"] = "interest"
        await update.message.reply_text("💬 Awesome! Now tell me your *interest* or reason for chatting.\nExample: `Just bored`, `Want to make friends`, etc.", parse_mode="Markdown")

    elif step == "interest":
        users[user_id]["interest"] = text
        del users[user_id]["next_step"]
        await update.message.reply_text(
            "✅ Profile completed!\nNow choose who you want to chat with 👇",
            reply_markup=ReplyKeyboardMarkup(
                [["🔍 Search Male", "🔍 Search Female"], ["🎯 Search Anyone"]],
                resize_keyboard=True
            )
        )


# /find
async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text if update.message else ""
    username = f"@{update.effective_user.username}" if update.effective_user.username else "Unknown"

    if user_id not in users or not users[user_id].get("gender"):
        await update.message.reply_text("⚠️ Please select your gender using /start first.")
        return

    user_data = users[user_id]
    if not user_data.get("age") or not user_data.get("location") or not user_data.get("interest"):
        await update.message.reply_text("⚠️ Please complete your profile first using /age command.")
        return

    # Search preference
    if "Male" in text:
        pref = "male"
    elif "Female" in text:
        pref = "female"
    else:
        pref = "any"

    users[user_id]["match_pref"] = pref

    if pref != "any" and not is_premium(username):
        await update.message.reply_text(
            "💎 *Premium Feature*\n\n"
            "You can only search specific genders if you have Premium.\n\n"
            "✨ Invite 5 friends to get 3 days free premium!\nUse /ref to get your link.",
            parse_mode="Markdown"
        )
        return

    msg = await update.message.reply_text("🔍 Searching for your match")
    for i in range(3):
        await msg.edit_text("🔍 Searching" + " ." * (i + 1))
        time.sleep(0.7)

    # Match system
    opposite_list = waiting_users[pref]
    if opposite_list and opposite_list[0] != user_id:
        partner_id = opposite_list.pop(0)
        users[user_id]["partner"] = partner_id
        users[partner_id]["partner"] = user_id

        p1 = users[user_id]
        p2 = users[partner_id]

        profile1 = f"👤 *{p1['gender']}*, {p1['age']}\n📍 {p1['location']}\n💬 {p1['interest']}"
        profile2 = f"👤 *{p2['gender']}*, {p2['age']}\n📍 {p2['location']}\n💬 {p2['interest']}"

        await context.bot.send_message(partner_id, f"🎉 You’re connected!\n\nYour partner:\n{profile1}", parse_mode="Markdown")
        await update.message.reply_text(f"🎉 You’re connected!\n\nYour partner:\n{profile2}", parse_mode="Markdown")
    else:
        waiting_users[pref].append(user_id)
        await update.message.reply_text("⌛ No one found right now, please wait...")


# /stop
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users or not users[user_id].get("partner"):
        await update.message.reply_text("⚠️ You are not in a chat.")
        return

    partner_id = users[user_id]["partner"]
    users[user_id]["partner"] = None
    users[partner_id]["partner"] = None

    await context.bot.send_message(partner_id, "❌ Your partner left the chat.")
    await update.message.reply_text(
        "✅ You left the chat.\n\nChoose your next search 👇",
        reply_markup=ReplyKeyboardMarkup(
            [["🔍 Search Male", "🔍 Search Female"], ["🎯 Search Anyone"]],
            resize_keyboard=True
        )
    )


# /ref
async def ref(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.effective_user.username
    if not username:
        await update.message.reply_text("⚠️ You need a Telegram username to use referrals.")
        return
    link = f"https://t.me/MeetAnonymousBOT?start={username}"
    await update.message.reply_text(
        f"💎 *Invite Friends & Get Premium!*\n\n"
        f"Invite 5 people using your link to unlock *3 days of Premium!* 💖\n\n"
        f"🔗 Your link: {link}",
        parse_mode="Markdown"
    )


# /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *MeetAnonymousBot Help*\n\n"
        "Here’s what you can do:\n"
        "• /start — Setup your profile\n"
        "• /age <age> — Set your age\n"
        "• /find — Find a random chat partner\n"
        "• /stop — End current chat\n"
        "• /ref — Invite friends for Premium\n"
        "• /help — Show this help menu\n\n"
        "💡 You can send text, photos, videos, stickers, voice & files freely.",
        parse_mode="Markdown"
    )


# Forward all other messages
async def forward_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    partner_id = users.get(user_id, {}).get("partner")
    if partner_id:
        await context.bot.copy_message(chat_id=partner_id, from_chat_id=user_id, message_id=update.message.message_id)
    else:
        await update.message.reply_text("⚠️ You’re not chatting yet. Use /find to start!")


def build_app(token):
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("age", set_age))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("ref", ref))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.Regex("^(👨 Male|👩 Female)$"), gender_select))
    app.add_handler(MessageHandler(filters.Regex("^(🔍 Search Male|🔍 Search Female|🎯 Search Anyone)$"), find))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, extra_info))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, forward_message))
    return app


if __name__ == "__main__":
    if not TOKEN:
        print("❌ BOT_TOKEN missing!")
    else:
        print("🚀 MeetAnonymousBot v3 running...")
        app = build_app(TOKEN)
        app.run_webhook(
            listen="0.0.0.0",
            port=int(os.environ.get("PORT", "10000")),
            url_path=TOKEN,
            webhook_url=f"https://telegram-bot-99.onrender.com/{TOKEN}"
        )
        
