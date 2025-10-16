import os
import json
import asyncio
import random
from flask import Flask
from telegram import (
    Update, ChatAction, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

TOKEN = os.getenv("BOT_TOKEN")  # add this in Render Environment

app = Flask(__name__)
chats = {}          # user_id -> partner_id
gender = {}         # user_id -> "male" or "female"
profiles = {}       # user_id -> {"gender":..., "age":..., "location":..., "interests":...}

@app.route('/')
def home():
    return "Bot is alive ✅"

# ---------- Helper ----------
async def typing(context, chat_id):
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    await asyncio.sleep(random.uniform(0.7, 1.5))

def get_main_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Next 👥", callback_data="next"),
         InlineKeyboardButton("Stop 🚫", callback_data="stop")],
        [InlineKeyboardButton("Edit Profile 📝", callback_data="edit_profile")]
    ])

# ---------- Commands ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    profiles.setdefault(uid, {"gender": None, "age": None, "location": None, "interests": None})
    await typing(context, uid)
    await update.message.reply_text(
        "👋 Welcome to **Anonymous Meet Bot!**\n\n"
        "Meet new people and chat privately.\n\n"
        "Please select your gender:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👨 Male", callback_data="male"),
             InlineKeyboardButton("👩 Female", callback_data="female")]
        ])
    )

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    p = profiles.get(uid, {})
    text = (
        f"👤 **Your Profile**\n\n"
        f"Gender: {p.get('gender') or 'Not set'}\n"
        f"Age: {p.get('age') or 'Not set'}\n"
        f"Location: {p.get('location') or 'Not set'}\n"
        f"Interests: {p.get('interests') or 'Not set'}"
    )
    await typing(context, uid)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_main_buttons())

# ---------- Inline button actions ----------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id

    if query.data == "male" or query.data == "female":
        gender[uid] = query.data
        profiles.setdefault(uid, {})["gender"] = query.data
        await query.edit_message_text("✅ Gender saved. Searching for a match...")
        await search_partner(uid, context)

    elif query.data == "next":
        await next_chat(uid, context)

    elif query.data == "stop":
        await stop_chat(uid, context)

    elif query.data == "edit_profile":
        await query.edit_message_text(
            "📝 Edit your profile:\n\nSend in this format:\n"
            "`age; location; interests`\n\nExample:\n`20; Delhi; gaming, music, travel`",
            parse_mode="Markdown"
        )
        context.user_data["editing"] = True

# ---------- Edit Profile ----------
async def handle_profile_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if context.user_data.get("editing"):
        try:
            age, location, interests = [x.strip() for x in update.message.text.split(";", 2)]
            profiles.setdefault(uid, {}).update({
                "age": age,
                "location": location,
                "interests": interests
            })
            context.user_data["editing"] = False
            await update.message.reply_text("✅ Profile updated!", reply_markup=get_main_buttons())
        except:
            await update.message.reply_text("❌ Invalid format. Please use `age; location; interests`")

# ---------- Matchmaking ----------
async def search_partner(uid, context):
    for user, g in gender.items():
        if user != uid and user not in chats and g != gender[uid]:
            chats[user] = uid
            chats[uid] = user
            await context.bot.send_message(chat_id=uid, text="💬 Connected! Say hi!", reply_markup=get_main_buttons())
            await context.bot.send_message(chat_id=user, text="💬 Connected! Say hi!", reply_markup=get_main_buttons())
            return
    await context.bot.send_message(chat_id=uid, text="🔍 Searching for a partner...")

async def next_chat(uid, context):
    if uid in chats:
        partner = chats.pop(uid)
        chats.pop(partner, None)
        await context.bot.send_message(chat_id=partner, text="⚠️ Partner left. Searching new one...")
        await search_partner(partner, context)
    await search_partner(uid, context)

async def stop_chat(uid, context):
    if uid in chats:
        partner = chats.pop(uid)
        chats.pop(partner, None)
        await context.bot.send_message(chat_id=partner, text="🚫 Partner ended the chat.")
        await context.bot.send_message(chat_id=uid, text="❌ Chat stopped.", reply_markup=get_main_buttons())
    else:
        await context.bot.send_message(chat_id=uid, text="⚠️ You’re not chatting with anyone.", reply_markup=get_main_buttons())

# ---------- Messaging ----------
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    # Profile editing mode
    if context.user_data.get("editing"):
        await handle_profile_edit(update, context)
        return

    if uid not in chats:
        await update.message.reply_text("⚠️ Not chatting. Use /male or /female to start.")
        return

    partner = chats.get(uid)
    if not partner:
        return

    await typing(context, partner)

    if update.message.text:
        await context.bot.send_message(chat_id=partner, text=update.message.text)
    elif update.message.photo:
        await context.bot.send_photo(chat_id=partner, photo=update.message.photo[-1].file_id, caption=update.message.caption or "")
    elif update.message.video:
        await context.bot.send_video(chat_id=partner, video=update.message.video.file_id, caption=update.message.caption or "")
    elif update.message.voice:
        await context.bot.send_voice(chat_id=partner, voice=update.message.voice.file_id)
    elif update.message.sticker:
        await context.bot.send_sticker(chat_id=partner, sticker=update.message.sticker.file_id)

# ---------- Keep Alive ----------
async def keep_alive():
    while True:
        await asyncio.sleep(300)
        print("✅ Alive ping...")

# ---------- Main ----------
async def main():
    app_telegram = ApplicationBuilder().token(TOKEN).build()

    app_telegram.add_handler(CommandHandler("start", start))
    app_telegram.add_handler(CommandHandler("profile", profile))
    app_telegram.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, message_handler))
    app_telegram.add_handler(CallbackQueryHandler(button_handler))

    await asyncio.gather(app_telegram.run_polling(), keep_alive())

if __name__ == "__main__":
    asyncio.run(main())
    
