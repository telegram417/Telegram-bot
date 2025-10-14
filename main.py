import os
import logging
import asyncio
from flask import Flask
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, Message
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler
)

# ------------------ Flask for Render keep-alive ------------------
server = Flask(__name__)

@server.route("/")
def home():
    return "✅ Anonymous Chat Bot is running!"

async def run_flask():
    import uvicorn
    config = uvicorn.Config(app=server, host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
    server_instance = uvicorn.Server(config)
    await server_instance.serve()

# ------------------ Logging ------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------ Bot states ------------------
GENDER, AGE, LOCATION, INTEREST, EDIT_CHOICE, EDIT_VALUE = range(6)

# ------------------ In-memory storage ------------------
users = {}          # chat_id -> profile dict
waiting_users = []  # list of chat_ids waiting to match
active_chats = {}   # chat_id -> partner_chat_id

# ------------------ Environment ------------------
from dotenv import load_dotenv
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise SystemExit("❌ BOT_TOKEN is required in environment variables")

# ------------------ Helper Functions ------------------
def is_profile_complete(chat_id: int) -> bool:
    data = users.get(chat_id, {})
    return all(k in data for k in ["gender","age","location","interest"])

def format_profile(data: dict) -> str:
    return (
        f"👤 *Partner Info:*\n"
        f"• Gender: {data.get('gender','—')}\n"
        f"• Age: {data.get('age','—')}\n"
        f"• Location: {data.get('location','—')}\n"
        f"• Interest: {data.get('interest','—')}\n"
    )

def safe_enqueue(user_id: int):
    if user_id not in waiting_users:
        waiting_users.append(user_id)

def safe_dequeue(user_id: int):
    if user_id in waiting_users:
        waiting_users.remove(user_id)

def pair_users(a:int,b:int):
    active_chats[a]=b
    active_chats[b]=a

def unpair_user(chat_id:int):
    partner = active_chats.pop(chat_id,None)
    if partner:
        active_chats.pop(partner,None)
    return partner

# ------------------ Start / Profile Flow ------------------
async def start_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    chat_id=update.effective_chat.id
    users.pop(chat_id,None)
    safe_dequeue(chat_id)
    unpair_user(chat_id)
    await update.message.reply_text(
        "👋 *Welcome to Anonymous Chat Bot!* 🤫\n\n"
        "Let's set up your profile.\n\nWhat’s your gender? 🚻",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup([["👦 Male","👧 Female","🤖 Other"]],one_time_keyboard=True,resize_keyboard=True)
    )
    return GENDER

async def start_gender(update:Update,context:ContextTypes.DEFAULT_TYPE):
    chat_id=update.effective_user.id
    users[chat_id]={"gender":update.message.text}
    await update.message.reply_text("🎂 Nice! Now tell me your *age*.",parse_mode="Markdown",reply_markup=ReplyKeyboardRemove())
    return AGE

async def start_age(update:Update,context:ContextTypes.DEFAULT_TYPE):
    chat_id=update.effective_user.id
    users.setdefault(chat_id,{})["age"]=update.message.text
    await update.message.reply_text("📍 Where are you from?")
    return LOCATION

async def start_location(update:Update,context:ContextTypes.DEFAULT_TYPE):
    chat_id=update.effective_user.id
    users.setdefault(chat_id,{})["location"]=update.message.text
    await update.message.reply_text("🎯 What are your interests?")
    return INTEREST

async def start_interest(update:Update,context:ContextTypes.DEFAULT_TYPE):
    chat_id=update.effective_user.id
    users.setdefault(chat_id,{})["interest"]=update.message.text
    await update.message.reply_text(
        "✅ Profile complete!\nUse /find to meet someone 🔍\nTip: /find male or /find female to filter.",
    )
    return ConversationHandler.END

# ------------------ Edit Flow ------------------
async def edit_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    chat_id=update.effective_user.id
    if chat_id not in users:
        await update.message.reply_text("⚠️ You need a profile first (/start).")
        return ConversationHandler.END
    cur=users.get(chat_id,{})
    msg="✏️ *Edit Profile*\n\nCurrent profile:\n"+format_profile(cur)+"\nWhat do you want to edit?"
    await update.message.reply_text(
        msg,
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup([["👦 Gender","🎂 Age"],["📍 Location","🎯 Interest"]],one_time_keyboard=True,resize_keyboard=True)
    )
    return EDIT_CHOICE

async def edit_choice(update:Update,context:ContextTypes.DEFAULT_TYPE):
    text=update.message.text.lower()
    field=None
    if "gender" in text:
        field="gender"
        await update.message.reply_text("Select new gender:",reply_markup=ReplyKeyboardMarkup([["👦 Male","👧 Female","🤖 Other"]],one_time_keyboard=True))
    elif "age" in text:
        field="age"
        await update.message.reply_text("Enter new age:",reply_markup=ReplyKeyboardRemove())
    elif "location" in text:
        field="location"
        await update.message.reply_text("Enter new location:",reply_markup=ReplyKeyboardRemove())
    elif "interest" in text:
        field="interest"
        await update.message.reply_text("Enter new interest:",reply_markup=ReplyKeyboardRemove())
    else:
        await update.message.reply_text("❌ Invalid choice. Use /edit again.")
        return ConversationHandler.END
    context.user_data["edit_field"]=field
    return EDIT_VALUE

async def edit_value(update:Update,context:ContextTypes.DEFAULT_TYPE):
    chat_id=update.effective_user.id
    field=context.user_data.get("edit_field")
    if field:
        users.setdefault(chat_id,{})[field]=update.message.text
        await update.message.reply_text(f"✅ *{field.capitalize()}* updated!",parse_mode="Markdown",reply_markup=ReplyKeyboardRemove())
    context.user_data.pop("edit_field",None)
    return ConversationHandler.END

# ------------------ Match & Chat ------------------
async def find_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    chat_id=update.effective_user.id
    if not is_profile_complete(chat_id):
        await update.message.reply_text("⚠️ Complete your profile first (/start).")
        return
    raw=(update.message.text or "").lower()
    gender_filter=None
    if "female" in raw: gender_filter="👧 Female"
    elif "male" in raw: gender_filter="👦 Male"
    if chat_id in active_chats:
        await update.message.reply_text("💬 Already chatting. /leave or /next.")
        return
    match_id=None
    for uid in waiting_users:
        if uid==chat_id: continue
        if not is_profile_complete(uid): continue
        if gender_filter and users.get(uid,{}).get("gender")!=gender_filter: continue
        match_id=uid; break
    if match_id:
        safe_dequeue(match_id)
        pair_users(chat_id,match_id)
        await update.message.reply_text("💞 *Connected!* Say hi 👋\n\n"+format_profile(users.get(match_id,{})),parse_mode="Markdown")
        try:
            await context.bot.send_message(match_id,"💞 *Connected!* Say hi 👋\n\n"+format_profile(users.get(chat_id,{})),parse_mode="Markdown")
        except Exception:
            logger.exception("Failed to notify partner")
            unpair_user(chat_id)
            await update.message.reply_text("⚠️ Partner unavailable. Try /find again.")
    else:
        safe_enqueue(chat_id)
        await update.message.reply_text("🔎 Searching for a partner... /leave to cancel.")

async def leave_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    chat_id=update.effective_user.id
    partner=active_chats.get(chat_id)
    if partner:
        try:
            await context.bot.send_message(partner,"⚠️ Your partner left the chat. /find to meet new 🔍")
        except: pass
        unpair_user(chat_id)
        await update.message.reply_text("👋 You left the chat.")
    else:
        safe_dequeue(chat_id)
        await update.message.reply_text("❌ Not in a chat.")

async def next_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    chat_id=update.effective_user.id
    partner=active_chats.get(chat_id)
    if partner:
        try: await context.bot.send_message(partner,"⚠️ Your partner skipped you 🔁")
        except: pass
        unpair_user(chat_id)
    await find_cmd(update,context)

async def help_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📘 *Commands*\n"
        "/start – Create/reset profile 🧩\n"
        "/find – Find someone 🔍\n"
        "/find male – Filter male 👦\n"
        "/find female – Filter female 👧\n"
        "/next – Skip 🔁\n"
        "/leave – Leave chat 🚪\n"
        "/edit – Edit profile ✏️\n"
        "/help – This guide ℹ️\n\n"
        "✨ Supports *text, sticker, photo, video, voice*.",
        parse_mode="Markdown"
    )

async def relay_message(update:Update,context:ContextTypes.DEFAULT_TYPE):
    msg:Message=update.effective_message
    from_id=update.effective_chat.id
    if from_id not in active_chats: return
    to_id=active_chats.get(from_id)
    if not to_id: unpair_user(from_id); return
    try:
        if msg.text and not (msg.sticker or msg.photo or msg.video or msg.voice or msg.document or msg.animation):
            await context.bot.send_message(chat_id=to_id,text=msg.text)
        else:
            await context.bot.copy_message(chat_id=to_id,from_chat_id=from_id,message_id=msg.message_id)
    except:
        logger.exception("Failed to forward, unpairing")
        unpair_user(from_id)

async def main():
    app=ApplicationBuilder().token(TOKEN).build()

    start_conv=ConversationHandler(
        entry_points=[CommandHandler("start",start_cmd)],
        states={
            GENDER:[MessageHandler(filters.TEXT & ~filters.COMMAND,start_gender)],
            AGE:[MessageHandler(filters.TEXT & ~filters.COMMAND,start_age)],
            LOCATION:[MessageHandler(filters.TEXT & ~filters.COMMAND,start_location)],
            INTEREST:[MessageHandler(filters.TEXT & ~filters.COMMAND,start_interest)]
        },
        fallbacks=[]
    )

    edit_conv=ConversationHandler(
        entry_points=[CommandHandler("edit",edit_cmd)],
        states={
            EDIT_CHOICE:[MessageHandler(filters.TEXT & ~filters.COMMAND,edit_choice)],
            EDIT_VALUE:[MessageHandler(filters.TEXT & ~filters.COMMAND,edit_value)]
        },
        fallbacks=[]
    )

    app.add_handler(start_conv)
    app.add_handler(edit_conv)
    app.add_handler(CommandHandler("find",find_cmd))
    app.add_handler(CommandHandler("leave",leave_cmd))
    app.add_handler(CommandHandler("next",next_cmd))
    app.add_handler(CommandHandler("help",help_cmd))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND,relay_message))

    # Run Flask keep-alive
    asyncio.create_task(run_flask())
    logger.info("🤖 Bot started. Running polling...")
    await app.run_polling()

if __name__=="__main__":
    asyncio.run(main())
    
