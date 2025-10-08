#!/usr/bin/env python3
# MeetAnonymousBOT - anonymous dating bot with referrals & premium
# Safe: reads token from BOT_TOKEN env var
import os
import sqlite3
import logging
from datetime import datetime, timedelta
from functools import wraps
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

DB = "bot_data.db"
ADMIN_USERNAME = "tandoori123"  # permanent premium
REF_LINK_BASE = "https://t.me/MeetAnonymousBOT?start="

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def init_db():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        gender TEXT,
        age INTEGER,
        pref_gender TEXT DEFAULT 'any',
        premium_until TEXT,
        ref_code TEXT,
        invited_by INTEGER,
        invites INTEGER DEFAULT 0
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS queue (
        user_id INTEGER PRIMARY KEY,
        ts DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    con.commit()
    con.close()

def db_exec(query, params=(), fetch=False):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute(query, params)
    data = None
    if fetch:
        data = cur.fetchall()
    con.commit()
    con.close()
    return data

def ensure_user(user):
    if not user:
        return
    db_exec("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user.id, user.username))
    db_exec("UPDATE users SET username = ? WHERE user_id = ?", (user.username, user.id))
    row = db_exec("SELECT ref_code FROM users WHERE user_id = ?", (user.id,), fetch=True)
    if row and not row[0][0]:
        code = f"r{user.id}"
        db_exec("UPDATE users SET ref_code = ? WHERE user_id = ?", (code, user.id))

def is_premium_by_row(row):
    if not row:
        return False
    username = row[1] or ""
    if username.lstrip("@").lower() == ADMIN_USERNAME.lower():
        return True
    p_until = row[5]
    if p_until:
        try:
            t = datetime.fromisoformat(p_until)
            return t > datetime.utcnow()
        except:
            return False
    return False

def is_premium(user_id):
    row = db_exec("SELECT * FROM users WHERE user_id = ?", (user_id,), fetch=True)
    if not row:
        return False
    return is_premium_by_row(row[0])

def add_invite_count(ref_owner_id):
    db_exec("UPDATE users SET invites = invites + 1 WHERE user_id = ?", (ref_owner_id,))
    row = db_exec("SELECT invites, premium_until FROM users WHERE user_id = ?", (ref_owner_id,), fetch=True)
    if row:
        invites = row[0][0]
        if invites >= 5:
            until = datetime.utcnow() + timedelta(days=7)
            db_exec("UPDATE users SET premium_until = ?, invites = 0 WHERE user_id = ?", (until.isoformat(), ref_owner_id))
            return True
    return False

def user_in_queue(user_id):
    res = db_exec("SELECT 1 FROM queue WHERE user_id = ?", (user_id,), fetch=True)
    return len(res) > 0

def add_to_queue(user_id):
    db_exec("INSERT OR IGNORE INTO queue (user_id) VALUES (?)", (user_id,))
    return True

def remove_from_queue(user_id):
    db_exec("DELETE FROM queue WHERE user_id = ?", (user_id,))

def find_match_for(user_id):
    rows = db_exec("SELECT user_id FROM queue ORDER BY ts ASC", fetch=True)
    for (candidate_id,) in rows:
        if candidate_id == user_id:
            continue
        return candidate_id
    return None

def start_match(u1, u2):
    partners[u1] = u2
    partners[u2] = u1
    remove_from_queue(u1)
    remove_from_queue(u2)

def end_match(user_id):
    partner = partners.get(user_id)
    if partner:
        partners.pop(user_id, None)
        partners.pop(partner, None)
        return partner
    return None

def get_partner(user_id):
    return partners.get(user_id)

def require_user(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        ensure_user(user)
        return await func(update, context, *args, **kwargs)
    return wrapper

@require_user
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    ensure_user(user)
    if args:
        payload = args[0]
        if payload.startswith("r"):
            owner = db_exec("SELECT user_id FROM users WHERE ref_code = ?", (payload,), fetch=True)
            if owner:
                owner_id = owner[0][0]
                cur = db_exec("SELECT invited_by FROM users WHERE user_id = ?", (user.id,), fetch=True)
                if cur and cur[0][0] is None:
                    db_exec("UPDATE users SET invited_by = ? WHERE user_id = ?", (owner_id, user.id))
                    gained = add_invite_count(owner_id)
                    if gained:
                        try:
                            await context.bot.send_message(chat_id=owner_id, text="🎉 You got 5 invites — Premium activated for 7 days!")
                        except:
                            pass
    keyboard = [["Male", "Female", "Other"]]
    reply = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Welcome to MeetAnonymousBOT! Please select your gender:", reply_markup=reply)
    await update.message.reply_text("Now type your age as a number (e.g., 21). It will be shown to premium partners only.")

@require_user
async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📘 *MeetAnonymousBOT Help*\n\n"
        "/start - Set gender and age (use referral links to invite)\n"
        "/find - Search for a partner\n"
        "/stop - End the current chat\n"
        "/help - Show this help\n"
        "/about - About the bot\n"
        "/refer - Show your referral link & invite progress\n"
        "\nPremium: Invite 5 people to get 7 days premium. Admin @tandoori123 has permanent premium."
    )
    await update.message.reply_text(text, parse_mode="Markdown")

@require_user
async def about_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("MeetAnonymousBOT — anonymous chatting. Premium users can see partner's gender & age and match faster. Invite 5 friends to get 7 days premium!")

@require_user
async def refer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    row = db_exec("SELECT ref_code, invites FROM users WHERE user_id = ?", (user.id,), fetch=True)
    if row:
        code, invites = row[0]
        link = REF_LINK_BASE + (code or f"r{user.id}")
        await update.message.reply_text(f"Share this link: {link}\nInvites progress: {invites}/5\nInvite 5 people to get 7 days Premium!")
    else:
        await update.message.reply_text("Could not find your referral info. Try /start first.")

@require_user
async def setpref_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_premium(user.id):
        await update.message.reply_text("This is a premium feature. Invite friends to unlock it.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /setpref male|female|any")
        return
    val = args[0].lower()
    if val not in ("male", "female", "any", "other"):
        await update.message.reply_text("Choose male, female, other, or any")
        return
    db_exec("UPDATE users SET pref_gender = ? WHERE user_id = ?", (val, user.id))
    await update.message.reply_text(f"Preference set to: {val}")

@require_user
async def find_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user)
    row = db_exec("SELECT gender, age FROM users WHERE user_id = ?", (user.id,), fetch=True)
    if not row or not row[0][0] or not row[0][1]:
        await update.message.reply_text("Please set your gender and age first using /start and then typing your age.")
        return
    if is_premium(user.id):
        partner = find_match_for(user.id)
        if partner:
            start_match(user.id, partner)
            p_row = db_exec("SELECT username, gender, age FROM users WHERE user_id = ?", (partner,), fetch=True)
            await context.bot.send_message(chat_id=user.id, text="🎉 Matched! You can see partner info below because you're premium.")
            await context.bot.send_message(chat_id=partner, text="🎉 Matched!")
            try:
                await context.bot.send_message(chat_id=user.id, text=f"Partner — Gender: {p_row[0][1] or 'Unknown'}, Age: {p_row[0][2] or 'Unknown'}")
            except:
                pass
            return
    if user_in_queue(user.id):
        await update.message.reply_text("You're already in the queue. Please wait.")
        return
    add_to_queue(user.id)
    await update.message.reply_text("⌛ You're in the queue. We'll notify you when matched.")

@require_user
async def stop_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    partner = get_partner(user.id)
    if partner:
        end_match(user.id)
        await context.bot.send_message(chat_id=partner, text="❌ Your partner left the chat.")
        await update.message.reply_text("You left the chat.")
    else:
        if user_in_queue(user.id):
            remove_from_queue(user.id)
            await update.message.reply_text("Removed from queue.")
        else:
            await update.message.reply_text("You're not in a chat or queue.")

@require_user
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip() if update.message.text else ""
    if text.isdigit() and (not db_exec("SELECT age FROM users WHERE user_id = ?", (user.id,), fetch=True)[0][0]):
        age = int(text)
        db_exec("UPDATE users SET age = ? WHERE user_id = ?", (age, user.id))
        await update.message.reply_text(f"Age set to {age}. Now use /find to search for partners.")
        return
    if text.lower() in ("male", "female", "other"):
        db_exec("UPDATE users SET gender = ? WHERE user_id = ?", (text.capitalize(), user.id))
        await update.message.reply_text("Gender saved. Now send your age as a number (e.g., 22).")
        return
    partner = get_partner(user.id)
    if not partner:
        await update.message.reply_text("You're not matched. Use /find to search.")
        return
    if update.message.text:
        await context.bot.send_message(chat_id=partner, text=update.message.text)
        return

@require_user
async def sticker_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    partner = get_partner(user.id)
    if not partner:
        await update.message.reply_text("You're not matched. Use /find to search.")
        return
    if not is_premium(user.id):
        await update.message.reply_text("Stickers and media are premium features. Invite friends to unlock.")
        return
    try:
        await context.bot.send_sticker(chat_id=partner, sticker=update.message.sticker.file_id)
    except Exception as e:
        logger.exception("Failed to forward sticker: %s", e)
        await update.message.reply_text("Couldn't forward sticker.")

@require_user
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    partner = get_partner(user.id)
    if not partner:
        await update.message.reply_text("You're not matched. Use /find to search.")
        return
    if not is_premium(user.id):
        await update.message.reply_text("Sending photos is premium. Invite friends to unlock.")
        return
    photo = update.message.photo[-1]
    f = await photo.get_file()
    path = f"tmp_{user.id}.jpg"
    await f.download_to_drive(path)
    try:
        await context.bot.send_photo(chat_id=partner, photo=open(path, "rb"))
    finally:
        try:
            os.remove(path)
        except:
            pass

def build_app(token):
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("about", about_handler))
    app.add_handler(CommandHandler("refer", refer_handler))
    app.add_handler(CommandHandler("find", find_handler))
    app.add_handler(CommandHandler("stop", stop_handler))
    app.add_handler(CommandHandler("setpref", setpref_handler))
    app.add_handler(MessageHandler(filters.STICKER, sticker_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    return app

if __name__ == "__main__":
    init_db()
    partners = {}
    TOKEN = os.getenv("BOT_TOKEN")
    if not TOKEN:
        print("ERROR: BOT_TOKEN not set in environment variables. Please add it and restart.")
        exit(1)
    app = build_app(TOKEN)
    print("🤖 MeetAnonymousBOT starting...")
    app.run_polling()
                      
