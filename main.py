import os
import asyncio
from flask import Flask
from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
import logging

# ---------------- CONFIG ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.environ.get("PORT", "10000"))

logging.basicConfig(level=logging.INFO)

# ---------------- FLASK APP ----------------
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Anonymous Chat Bot is alive and ready!"

# ---------------- DATA STORAGE ----------------
users = {}
waiting = {"male": set(), "female": set(), "any": set()}
chats = {}

# ---------------- BOT LOGIC ----------------

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    users[uid] = {"step": "gender"}

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👨 Male", callback_data="gender_male"),
            InlineKeyboardButton("👩 Female", callback_data="gender_female"),
        ]
    ])
    await update.message.reply_text(
        "👋 **Welcome to Anonymous Chat Bot!**\n\n"
        "Let’s build your profile.\n\n"
        "Please select your gender:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

async def button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id

    data = query.data

    # --- GENDER SELECT ---
    if data.startswith("gender_"):
        gender = data.split("_")[1]
        users[uid]["gender"] = gender
        users[uid]["step"] = "age"
        await query.edit_message_text("🎂 Great! Now enter your age:")

    # --- SEARCH PREFERENCE BUTTONS ---
    elif data == "find_female":
        waiting["female"].add(uid)
        await query.edit_message_text("🔍 Searching for a female partner...")
    elif data == "find_male":
        waiting["male"].add(uid)
        await query.edit_message_text("🔍 Searching for a male partner...")

async def process_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text or ""
    user = users.get(uid, {})

    if user.get("step") == "age":
        users[uid]["age"] = text
        users[uid]["step"] = "location"
        await update.message.reply_text("📍 Nice! Where are you from?")
    elif user.get("step") == "location":
        users[uid]["location"] = text
        users[uid]["step"] = "interest"
        await update.message.reply_text("💫 Awesome! What are your interests?")
    elif user.get("step") == "interest":
        users[uid]["interest"] = text
        users[uid]["step"] = "done"
        await update.message.reply_text(
            "✅ Profile saved!\n\nUse /find to start chatting!"
        )
    else:
        if uid in chats:
            partner = chats[uid]
            await ctx.bot.copy_message(
                chat_id=partner,
                from_chat_id=update.message.chat_id,
                message_id=update.message.message_id
            )
        else:
            await update.message.reply_text("❗ You are not in a chat. Use /find to start.")

async def find(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = users.get(uid)
    if not user or user.get("step") != "done":
        await update.message.reply_text("⚠️ Please complete your profile first using /start.")
        return

    gender = user["gender"]
    opposite = "female" if gender == "male" else "male"
    found = None

    if waiting[opposite]:
        found = waiting[opposite].pop()
    elif waiting["any"]:
        found = waiting["any"].pop()
    elif waiting[gender]:
        found = waiting[gender].pop()

    if found:
        chats[uid] = found
        chats[found] = uid

        p1 = users[uid]
        p2 = users[found]

        info1 = f"👤 {p1['gender'].title()}, {p1['age']} yrs\n📍 {p1['location']}\n💫 {p1['interest']}"
        info2 = f"👤 {p2['gender'].title()}, {p2['age']} yrs\n📍 {p2['location']}\n💫 {p2['interest']}"

        await ctx.bot.send_message(found, f"🎉 Matched!\n\nYour partner:\n{info1}")
        await update.message.reply_text(f"🎉 Matched!\n\nYour partner:\n{info2}")
    else:
        waiting["any"].add(uid)
        await update.message.reply_text("🔎 Searching for a partner... Please wait!")

async def stop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in chats:
        await update.message.reply_text("❗ You are not in a chat.")
        return

    partner = chats.pop(uid)
    chats.pop(partner, None)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔎 Search Female", callback_data="find_female")],
        [InlineKeyboardButton("🔎 Search Male", callback_data="find_male")]
    ])

    await ctx.bot.send_message(partner, "⚠️ Your partner left.", reply_markup=keyboard)
    await update.message.reply_text("✅ Chat ended.", reply_markup=keyboard)

async def next_chat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await stop(update, ctx)
    await find(update, ctx)

async def edit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    users[update.effective_user.id] = {"step": "gender"}
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👨 Male", callback_data="gender_male"),
            InlineKeyboardButton("👩 Female", callback_data="gender_female"),
        ]
    ])
    await update.message.reply_text(
        "✏️ Let’s edit your profile.\nPlease select your gender:",
        reply_markup=keyboard
    )

async def help_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📘 **Command List:**\n\n"
        "• /start — Setup your profile\n"
        "• /find — Find a random partner\n"
        "• /stop — End chat\n"
        "• /next — End & find a new chat\n"
        "• /edit — Edit profile\n"
        "• /help — Show this help\n\n"
        "💬 You can send messages, photos, videos, voices, and stickers.",
        parse_mode="Markdown"
    )

# ---------------- RUN FLASK + BOT TOGETHER ----------------
async def main():
    bot_app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .build()
    )

    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("find", find))
    bot_app.add_handler(CommandHandler("stop", stop))
    bot_app.add_handler(CommandHandler("next", next_chat))
    bot_app.add_handler(CommandHandler("edit", edit))
    bot_app.add_handler(CommandHandler("help", help_command))
    bot_app.add_handler(CallbackQueryHandler(button))
    bot_app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, process_message))

    await asyncio.gather(
        bot_app.run_polling(drop_pending_updates=True),
        asyncio.to_thread(app.run, host="0.0.0.0", port=PORT)
    )

if __name__ == "__main__":
    asyncio.run(main())
    
