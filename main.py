import os
import time
import threading
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
    users[user_id] = {"gender": None, "partner": None, "age": None, "match_pref": None}

    keyboard = [["👨 Male", "👩 Female"]]
    await update.message.reply_text(
        "🌈 *Welcome to MeetAnonymousBot!* 💬\n\n"
        "Chat anonymously with people around the world 🌍\n"
        "But first, tell me your gender 👇",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )


# Gender selection
async def gender_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if text == "👨 Male":
        gender = "Male"
    elif text == "👩 Female":
        gender = "Female"
    else:
        gender = None

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
        await update.message.reply_text(
            "✅ Age saved!\nNow choose who you want to chat with 👇",
            reply_markup=ReplyKeyboardMarkup(
                [["🔍 Search Male", "🔍 Search Female"], ["🎯 Search Anyone"]],
                resize_keyboard=True
            )
        )
    else:
        await update.message.reply_text("⚠️ Use like this → /age 20")


# /find
async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text if update.message else ""
    username = f"@{update.effective_user.username}" if update.effective_user.username else "Unknown"

    # Validate profile
    if user_id not in users or not users[user_id].get("gender"):
        await update.message.reply_text("⚠️ Please select your gender using /start first.")
        return

    gender = users[user_id]["gender"]
    age = users[user_id].get("age")

    # Determine preference
    if "Male" in text:
        pref = "male"
    elif "Female" in text:
        pref = "female"
    else:
        pref = "any"

    users[user_id]["match_pref"] = pref

    # If non-premium, restrict gender-specific search
    if pref != "any" and not is_premium(username):
        await update.message.reply_text(
            "💎 *Premium Feature*\n\n"
            "You can only search specific genders if you have Premium.\n\n"
            "✨ Invite 5 friends to get 3 days free premium!\nUse /ref to get your link.",
            parse_mode="Markdown"
        )
        return

    # Search animation
    msg = await update.message.reply_text("🔍 Searching for your match")
    for dot_count in range(3):
        await msg.edit_text("🔍 Searching" + " ." * (dot_count + 1))
        time.sleep(0.7)

    # Match
    opposite_list = waiting_users[pref]
    if opposite_list and opposite_list[0] != user_id:
        partner_id = opposite_list.pop(0)
        users[user_id]["partner"] = partner_id
        users[partner_id]["partner"] = user_id

        gender_p1, gender_p2 = users[user_id]["gender"], users[partner_id]["gender"]
        age_p1, age_p2 = users[user_id].get("age"), users[partner_id].get("age")

        await context.bot.send_message(partner_id, f"🎉 You’re connected!\n👤 Partner: *{gender_p1}, {age_p1 or 'Unknown'}*", parse_mode="Markdown")
        await update.message.reply_text(f"🎉 You’re connected!\n👤 Partner: *{gender_p2}, {age_p2 or 'Unknown'}*", parse_mode="Markdown")
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


# Forward messages (text, photo, video, audio, etc.)
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
    app.add_handler(MessageHandler(filters.Regex("^(👨 Male|👩 Female)$"), gender_select))
    app.add_handler(MessageHandler(filters.Regex("^(🔍 Search Male|🔍 Search Female|🎯 Search Anyone)$"), find))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, forward_message))
    return app


if __name__ == "__main__":
    if not TOKEN:
        print("❌ BOT_TOKEN missing!")
    else:
        print("🚀 MeetAnonymousBot v2 running 24/7...")
        app = build_app(TOKEN)
        app.run_webhook(
            listen="0.0.0.0",
            port=int(os.environ.get("PORT", "10000")),
            url_path=TOKEN,
            webhook_url=f"https://telegram-bot-99.onrender.com/{TOKEN}"
        )
        
