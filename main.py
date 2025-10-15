import os, threading
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, CallbackQueryHandler
)

BOT_TOKEN = os.getenv("BOT_TOKEN")

# --- Simple Flask keep-alive server ---
app = Flask(__name__)

@app.route("/")
def home():
    return "🤖 Anonymous Telegram Bot is alive!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# --- Telegram logic ---
users = {}
waiting = {"male": set(), "female": set(), "any": set()}
chats = {}

def summary(uid):
    u = users[uid]
    return (f"👤 Gender: {u['gender']}\n🎂 Age: {u['age']}\n"
            f"📍 Location: {u['location']}\n🎯 Interest: {u['interest']}")

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    users[uid] = {"stage": "gender"}
    await update.message.reply_text(
        "👋 Welcome to *Anonymous Chat!*\n\nEnter your **gender** (Male/Female/Other):",
        parse_mode="Markdown"
    )

async def collect(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in users:
        await update.message.reply_text("Use /start first ⚙️")
        return
    u, text = users[uid], update.message.text
    if u["stage"] == "gender":
        u["gender"], u["stage"] = text.lower(), "age"
        await update.message.reply_text("🎂 Enter your age:")
    elif u["stage"] == "age":
        u["age"], u["stage"] = text, "location"
        await update.message.reply_text("📍 Enter your location:")
    elif u["stage"] == "location":
        u["location"], u["stage"] = text, "interest"
        await update.message.reply_text("🎯 What are your interests?")
    elif u["stage"] == "interest":
        u["interest"], u["stage"] = text, "done"
        await update.message.reply_text("✅ Profile saved! Use /find to start 🔍")
    elif uid in chats:
        partner = chats[uid]
        await ctx.bot.copy_message(partner, update.effective_chat.id, update.message.message_id)
    else:
        await update.message.reply_text("❗ Not chatting. Use /find.")

async def find_user(update: Update, ctx: ContextTypes.DEFAULT_TYPE, pref="any"):
    uid = update.effective_user.id
    if uid not in users or users[uid].get("stage") != "done":
        await update.message.reply_text("⚙️ Complete profile first with /start")
        return
    if uid in chats:
        await update.message.reply_text("❗ Already chatting. /stop or /next")
        return
    pool = waiting[pref]
    if pool:
        partner = pool.pop()
        chats[uid] = partner
        chats[partner] = uid
        await ctx.bot.send_message(partner, f"🎉 Matched!\n\n{summary(uid)}\n\nSay hi 👋")
        await update.message.reply_text(f"🎉 Found someone!\n\n{summary(partner)}\n\nStart chatting 👋")
    else:
        pool.add(uid)
        await update.message.reply_text("🔎 Searching... Please wait!")

async def find(update, ctx):  await find_user(update, ctx, "any")
async def male(update, ctx):  await find_user(update, ctx, "male")
async def female(update, ctx):await find_user(update, ctx, "female")

async def stop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in chats:
        await update.message.reply_text("❗ Not in a chat.")
        return
    partner = chats.pop(uid)
    chats.pop(partner, None)
    await ctx.bot.send_message(partner, "⚠️ Partner left the chat.")
    kb = [
        [InlineKeyboardButton("👩 Search Female", callback_data="female")],
        [InlineKeyboardButton("👨 Search Male", callback_data="male")],
        [InlineKeyboardButton("🔁 Search Anyone", callback_data="any")],
    ]
    await update.message.reply_text("✅ Chat ended. Find new?", reply_markup=InlineKeyboardMarkup(kb))

async def next_chat(update, ctx):
    await stop(update, ctx)
    await find(update, ctx)

async def edit(update, ctx):
    uid = update.effective_user.id
    users[uid]["stage"] = "gender"
    await update.message.reply_text("📝 Let's edit your info. Enter gender:")

async def help_cmd(update, ctx):
    await update.message.reply_text(
        "🤖 *Commands*\n/start – Register\n/find – Random match\n/male – Find male\n"
        "/female – Find female\n/stop – Leave chat\n/next – New chat\n/edit – Edit profile\n/help – Help\n\n"
        "Send text, stickers, photos, voice, videos 🎥🎤", parse_mode="Markdown")

async def media(update, ctx):
    uid = update.effective_user.id
    if uid in chats:
        partner = chats[uid]
        await ctx.bot.copy_message(partner, update.effective_chat.id, update.message.message_id)
    else:
        await update.message.reply_text("❗ Not chatting. Use /find.")

async def button(update, ctx):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(f"🔍 Searching for {q.data} users...")
    await find_user(update, ctx, q.data)

async def main():
    tg = ApplicationBuilder().token(BOT_TOKEN).build()
    tg.add_handler(CommandHandler("start", start))
    tg.add_handler(CommandHandler("find", find))
    tg.add_handler(CommandHandler("male", male))
    tg.add_handler(CommandHandler("female", female))
    tg.add_handler(CommandHandler("stop", stop))
    tg.add_handler(CommandHandler("next", next_chat))
    tg.add_handler(CommandHandler("edit", edit))
    tg.add_handler(CommandHandler("help", help_cmd))
    tg.add_handler(CallbackQueryHandler(button))
    tg.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, collect))
    tg.add_handler(MessageHandler(filters.ALL & filters.COMMAND, media))
    print("🤖 Bot running...")
    await tg.run_polling()

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    import asyncio
    asyncio.run(main())
    
