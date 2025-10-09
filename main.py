import os
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")

users = {}
waiting_users = {"Male": [], "Female": []}
premium_users = {"@tandoori123"}  # permanent premium user


# ------------------------- /START -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    users[user_id] = {"gender": None, "age": None, "partner": None, "pref": None, "invites": 0}

    keyboard = [["Male", "Female"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text(
        "👋 Welcome to *MeetAnonymousBot!*\n\nSelect your gender:",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )


# ------------------------- GENDER SELECT -------------------------
async def gender_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    if user_id not in users:
        users[user_id] = {"gender": None, "age": None, "partner": None, "pref": None, "invites": 0}

    if text in ["Male", "Female"]:
        users[user_id]["gender"] = text
        await update.message.reply_text("✅ Gender saved! Now set your age using /age <number>")
        return

    # During chat
    if users[user_id].get("partner"):
        partner_id = users[user_id]["partner"]
        await context.bot.send_message(partner_id, text)
    else:
        await update.message.reply_text("⚠️ Please use /find to start chatting.")


# ------------------------- SET AGE -------------------------
async def set_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if len(context.args) == 1 and context.args[0].isdigit():
        users[user_id]["age"] = int(context.args[0])
        await update.message.reply_text("✅ Age saved! Now use /find to start chatting.")
    else:
        await update.message.reply_text("⚠️ Use like: /age 20")


# ------------------------- /FIND -------------------------
async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or f"user{user_id}"

    if user_id not in users or not users[user_id].get("gender"):
        await update.message.reply_text("⚠️ Please select your gender using /start first.")
        return

    # Ask for preferred gender
    keyboard = [["Male", "Female", "Any"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("💞 Who do you want to chat with?", reply_markup=reply_markup)

    users[user_id]["pref"] = None


async def set_preference(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if text not in ["Male", "Female", "Any"]:
        return

    users[user_id]["pref"] = text
    await update.message.reply_text("🔍 Searching for a match...")

    gender = users[user_id]["gender"]
    pref = users[user_id]["pref"]

    target_gender = "Male" if pref == "Male" else "Female" if pref == "Female" else None

    if target_gender and waiting_users[target_gender]:
        partner_id = waiting_users[target_gender].pop(0)
    elif not target_gender and any(waiting_users.values()):
        partner_id = (waiting_users["Male"] or waiting_users["Female"]).pop(0)
    else:
        waiting_users[gender].append(user_id)
        await update.message.reply_text("⌛ Waiting for someone to match...")
        return

    users[user_id]["partner"] = partner_id
    users[partner_id]["partner"] = user_id

    # Premium badge
    u_name = f"@{update.effective_user.username}" if update.effective_user.username else "User"
    partner = await context.bot.get_chat(partner_id)
    p_name = f"@{partner.username}" if partner.username else "User"

    if u_name in premium_users:
        u_name += " 💎"
    if p_name in premium_users:
        p_name += " 💎"

    await update.message.reply_text(f"🎉 Connected with {p_name}! Say hi 👋")
    await context.bot.send_message(partner_id, f"🎉 Connected with {u_name}! Say hi 👋")

    # Show age if premium
    if u_name.replace(" 💎", "") in premium_users or p_name.replace(" 💎", "") in premium_users:
        age1 = users[user_id].get("age")
        age2 = users[partner_id].get("age")
        if age1 and age2:
            await update.message.reply_text(f"👀 Partner's age: {age2}")
            await context.bot.send_message(partner_id, f"👀 Partner's age: {age1}")


# ------------------------- /STOP -------------------------
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users or not users[user_id].get("partner"):
        await update.message.reply_text("⚠️ You are not in a chat.")
        return

    partner_id = users[user_id]["partner"]
    users[user_id]["partner"] = None
    users[partner_id]["partner"] = None

    await context.bot.send_message(partner_id, "❌ Your partner left the chat.")
    await context.bot.send_message(user_id, "✅ You left the chat.")

    # Offer to find again
    keyboard = [["Find Partner"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("💬 Want to find another partner?", reply_markup=reply_markup)


# ------------------------- /REF -------------------------
async def ref(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ref_link = f"https://t.me/MeetAnonymousBot?start={user.id}"
    users[user.id]["invites"] += 0  # safe initialization

    await update.message.reply_text(
        f"👥 *Invite Friends!*\n\n"
        f"Share this link with your friends:\n{ref_link}\n\n"
        "🎁 Invite *5 friends* to unlock *Premium for 7 days!*",
        parse_mode="Markdown"
    )


# ------------------------- STICKERS -------------------------
async def sticker_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in users and users[user_id].get("partner"):
        partner_id = users[user_id]["partner"]
        await context.bot.send_sticker(partner_id, update.message.sticker.file_id)
    else:
        await update.message.reply_text("⚠️ You are not in a chat.")


# ------------------------- HELP & ABOUT -------------------------
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Commands:*\n"
        "/start - Restart setup\n"
        "/find - Find someone to talk\n"
        "/stop - Leave chat\n"
        "/age - Set your age\n"
        "/ref - Get your invite link\n"
        "/about - Learn about bot",
        parse_mode="Markdown"
    )


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💘 *About MeetAnonymousBot*\n\n"
        "Anonymous random chat with strangers 🌍\n"
        "Invite 5 people to unlock *Premium for 7 days* 💝\n"
        "Premium users can see partner's age 👀 and have a 💎 badge.\n\n"
        "🔒 Stay safe & respectful 💬",
        parse_mode="Markdown"
    )


# ------------------------- BUILD APP -------------------------
def build_app(token):
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("about", about))
    app.add_handler(CommandHandler("age", set_age))
    app.add_handler(CommandHandler("find", find))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("ref", ref))
    app.add_handler(MessageHandler(filters.Sticker.ALL, sticker_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, set_preference))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, gender_select))

    return app


# ------------------------- RUN BOT -------------------------
if __name__ == "__main__":
    if not TOKEN:
        print("❌ Missing BOT_TOKEN environment variable!")
    else:
        print("🤖 MeetAnonymousBot is running...")
        app = build_app(TOKEN)
        app.run_polling()
    
