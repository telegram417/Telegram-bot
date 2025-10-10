#!/usr/bin/env python3
"""
AnonChatPlush - Elegant & Minimal anonymous chat Telegram bot (memory-only)

Features:
- /start -> interactive profile (gender, age, location, interest)
- /find [gender] [min-max] [interest] -> optional quick filters
  Example: /find female 18-25 music
- /stop -> end chat
- /next -> end current chat and find next
- /edit -> re-run profile setup
- /ref -> produce referral link; 3 joins -> 3 days premium (memory)
- /help -> help message
- Supports text, photo, sticker, voice, video via copy_message
"""

import os
import asyncio
import logging
from datetime import datetime, timedelta

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

# --------- CONFIG ----------
BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME", "MeetAnonymousBOT")  # used for referral links
REF_REQUIRED = 3
REF_DAYS = 3

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable not set")

# --------- LOGGING ----------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AnonChatPlush")

# --------- IN-MEMORY STORAGE ----------
# user_profiles[user_id] = {
#   'gender','age','location','interest',
#   'partner' -> user_id or None,
#   'awaiting' -> None or one of 'gender','age','location','interest','edit_*',
#   'search_pref' -> dict like {'gender':..., 'min_age':..., 'max_age':..., 'interest':...}
#   'invites' -> int, 'premium_until' -> iso str or None
# }
user_profiles = {}
# waiting queue holds tuples (user_id)
waiting = []
# active chats: user_id -> partner_id
active = {}

# --------- HELPERS ----------
def now_iso():
    return datetime.utcnow().isoformat()

def is_premium(u):
    until = u.get("premium_until")
    if not until:
        return False
    try:
        return datetime.fromisoformat(until) > datetime.utcnow()
    except Exception:
        return False

def grant_premium(u, days=REF_DAYS):
    until = datetime.utcnow() + timedelta(days=days)
    u["premium_until"] = until.isoformat()

def profile_complete(u):
    return all(u.get(k) for k in ("gender", "age", "location", "interest"))

def format_profile(u):
    return (
        f"👤 Gender: {u.get('gender','—')}\n"
        f"🎂 Age: {u.get('age','—')}\n"
        f"📍 Location: {u.get('location','—')}\n"
        f"💬 Interest: {u.get('interest','—')}"
    )

def parse_find_args(args_list):
    # returns dict: {'gender':..., 'min_age':..., 'max_age':..., 'interest':...}
    pref = {"gender": None, "min_age": None, "max_age": None, "interest": None}
    if not args_list:
        return pref
    # first arg maybe gender
    idx = 0
    a0 = args_list[0].lower()
    if a0 in ("male", "female", "other", "any"):
        pref["gender"] = None if a0 == "any" else a0.capitalize()
        idx = 1
    # next could be age range like 18-25
    if idx < len(args_list):
        if "-" in args_list[idx]:
            r = args_list[idx].split("-", 1)
            if r[0].isdigit() and r[1].isdigit():
                pref["min_age"] = int(r[0])
                pref["max_age"] = int(r[1])
                idx += 1
    # remaining joined as interest
    if idx < len(args_list):
        pref["interest"] = " ".join(args_list[idx:]).strip().lower()
    return pref

def matches_pref(u, pref):
    # u is profile dict
    if not u:
        return False
    if pref.get("gender") and u.get("gender") != pref.get("gender"):
        return False
    if pref.get("min_age"):
        try:
            age = int(u.get("age", 0))
            if age < pref["min_age"]:
                return False
        except:
            return False
    if pref.get("max_age"):
        try:
            age = int(u.get("age", 0))
            if age > pref["max_age"]:
                return False
        except:
            return False
    if pref.get("interest"):
        user_interest = (u.get("interest") or "").lower()
        if pref["interest"] not in user_interest:
            return False
    return True

# --------- UI helpers (elegant minimal) ----------
def title(txt):
    return f"✨ {txt} ✨"

def divider():
    return "――――――――――――――――"

# --------- COMMANDS & HANDLERS ----------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start or resume profile setup. Accept referral args like: /start ref<inviter_id>"""
    uid = update.effective_user.id
    args = context.args or []
    # handle referral if present
    if args:
        raw = args[0]
        if raw.startswith("ref"):
            try:
                inviter = int(raw[3:])
                invp = user_profiles.get(inviter)
                if invp is not None:
                    invp["invites"] = invp.get("invites", 0) + 1
                    if invp["invites"] >= REF_REQUIRED:
                        grant_premium(invp, REF_DAYS)
                        invp["invites"] = 0
                        try:
                            await context.bot.send_message(inviter, f"🎉 Congratulations — you earned {REF_DAYS} days Premium on AnonChatPlush!")
                        except Exception:
                            pass
            except Exception:
                pass

    # initialize profile
    user_profiles[uid] = user_profiles.get(uid, {})
    u = user_profiles[uid]
    u.setdefault("partner", None)
    u.setdefault("invites", 0)
    u.setdefault("premium_until", None)
    # start flow
    u["awaiting"] = "gender"
    kb = ReplyKeyboardMarkup([["Male", "Female", "Other"]], resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(
        f"{title('Welcome to AnonChatPlush')}\n\nA simple anonymous space to meet new people.\n\nPlease select your gender:",
        reply_markup=kb
    )

async def _continue_profile_from_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = user_profiles.get(uid)
    if not u:
        await cmd_start(update, context)
        return
    waiting_for = u.get("awaiting")
    text = (update.message.text or "").strip()
    if waiting_for == "gender":
        if text.lower() not in ("male", "female", "other"):
            await update.message.reply_text("Please choose Male, Female, or Other (use the buttons).")
            return
        u["gender"] = text.capitalize()
        u["awaiting"] = "age"
        await update.message.reply_text("🎂 Now send your age (number):", reply_markup=ReplyKeyboardRemove())
        return
    if waiting_for == "age":
        if not text.isdigit() or not (10 <= int(text) <= 120):
            await update.message.reply_text("Please send a valid age number (10-120).")
            return
        u["age"] = text
        u["awaiting"] = "location"
        await update.message.reply_text("📍 Where are you from? (city or city, country)")
        return
    if waiting_for == "location":
        u["location"] = text
        u["awaiting"] = "interest"
        await update.message.reply_text("💬 Lastly — one-line about your interests (e.g. music, travel):")
        return
    if waiting_for == "interest":
        u["interest"] = text
        u["awaiting"] = None
        # confirm
        await update.message.reply_text(
            f"{divider()}\nProfile saved ✔️\n\n{format_profile(u)}\n{divider()}\nUse /find to meet someone.\nUse /edit to change profile anytime."
        )
        return
    # not awaiting anything: treat as normal chat message or command
    # if in active chat, handled separately
    if uid in active:
        # should be handled by separate message handler; but we put safeguard
        partner = active.get(uid)
        if partner:
            try:
                await context.bot.copy_message(chat_id=partner, from_chat_id=update.effective_chat.id, message_id=update.message.message_id)
            except Exception:
                await update.message.reply_text("Could not forward message to partner.")
            return
    # else suggest /find
    await update.message.reply_text("Use /find to search for a chat partner, or /start to update profile.")

async def cmd_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset awaiting to allow re-editing fields step-by-step"""
    uid = update.effective_user.id
    if uid not in user_profiles:
        await cmd_start(update, context)
        return
    user_profiles[uid]["awaiting"] = "gender"
    kb = ReplyKeyboardMarkup([["Male", "Female", "Other"]], resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text("Edit profile — choose new gender:", reply_markup=kb)

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"{title('AnonChatPlush — Help')}\n\n"
        "• /start — create or edit profile\n"
        "• /find [gender] [min-max] [interest] — find partner (optional filters)\n"
        "   examples: /find  /find female 18-25  /find male 20-30 music\n"
        "• /next — end current chat and find another\n"
        "• /stop — end current chat\n"
        "• /edit — edit profile step-by-step\n"
        "• /ref — get referral link (3 joins → 3 days premium)\n"
        "• /help — this message\n\n"
        "You may send text, photos, videos, voice, or stickers while chatting.\n"
        "All data is stored in memory (resets on restart).",
    )

async def cmd_ref(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    link = f"https://t.me/{BOT_USERNAME}?start=ref{uid}"
    u = user_profiles.get(uid, {})
    invites = u.get("invites", 0)
    prem = "Active" if is_premium(u) else "None"
    await update.message.reply_text(
        f"Share this referral link:\n{link}\n\nInvites: {invites}/{REF_REQUIRED}\nPremium: {prem}\n\nGet {REF_REQUIRED} invites to earn {REF_DAYS} days Premium."
    )

# matching / find logic
async def cmd_find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    args = context.args or []
    # parse quick filters
    pref = parse_find_args(args)
    user_profiles.setdefault(uid, {})
    u = user_profiles[uid]
    # ensure profile complete
    if not profile_complete(u):
        await update.message.reply_text("Complete your profile first with /start (quick and elegant).")
        return
    # If already chatting
    if uid in active:
        await update.message.reply_text("You are already in a chat. Use /stop or /next.")
        return
    # set user's search_pref
    u["search_pref"] = pref
    # Try find candidate in waiting respecting their search_pref and this user's pref too
    # Search queue from oldest to newest
    for idx, cand in enumerate(waiting):
        if cand == uid:
            continue
        cand_prof = user_profiles.get(cand)
        if not cand_prof or cand_prof.get("partner"):
            continue
        # candidate's own search preference: if set, check mutual
        cand_pref = cand_prof.get("search_pref") or {}
        # match checks: candidate must match uid's pref, and uid must match candidate's pref (if candidate specified)
        if not matches_pref(cand_prof, pref):
            continue
        # if candidate has pref - ensure uid matches
        if cand_pref and any(cand_pref.values()):
            if not matches_pref(u, cand_pref):
                continue
        # found match
        waiting.pop(idx)
        active[uid] = cand
        active[cand] = uid
        # notify both
        await context.bot.send_message(cand, f"💫 You are connected anonymously.\n\n{format_profile(u)}\n\nSay hi.")
        await context.bot.send_message(uid, f"💫 You are connected anonymously.\n\n{format_profile(cand_prof)}\n\nSay hi.")
        return
    # no candidate found -> add to waiting if not present
    if uid not in waiting:
        waiting.append(uid)
    # show searching animation (edit message)
    msg = await update.message.reply_text("🔎 Searching for a refined connection...")
    # animate a few edits
    try:
        steps = ["🔎 Searching for a refined connection...", "✨ Scanning compatible profiles...", "🌙 Almost there..."]
        for s in steps:
            await asyncio.sleep(1.2)
            await msg.edit_text(s)
    except Exception:
        pass
    await msg.edit_text("⌛ You are in queue. We'll notify you when matched.")

async def end_chat_for_user(uid, context):
    partner = active.pop(uid, None)
    if partner:
        active.pop(partner, None)
        try:
            await context.bot.send_message(partner, "❌ Your partner left the chat. Use /find to meet another.")
        except Exception:
            pass

async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid in active:
        partner = active.get(uid)
        await end_chat_for_user(uid, context)
        await update.message.reply_text("✅ You left the chat. Use /find to meet someone new.")
    elif uid in waiting:
        waiting.remove(uid)
        await update.message.reply_text("Stopped searching. Use /find when ready.")
    else:
        await update.message.reply_text("You are not in a chat or queue.")

async def cmd_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    # remember current search_pref
    pref = user_profiles.get(uid, {}).get("search_pref")
    # stop current
    if uid in active:
        await end_chat_for_user(uid, context)
    if uid in waiting:
        try:
            waiting.remove(uid)
        except:
            pass
    # call find again with same pref
    # emulate args building
    args = []
    if pref:
        if pref.get("gender"):
            args.append(pref["gender"])
        if pref.get("min_age") and pref.get("max_age"):
            args.append(f"{pref['min_age']}-{pref['max_age']}")
        if pref.get("interest"):
            args.append(pref["interest"])
    context.args = args
    await cmd_find(update, context)

# message relay (forward/copy) for active chats (media + text)
async def relay_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    # handle profile steps if awaiting
    u = user_profiles.get(uid)
    if u and u.get("awaiting"):
        await _continue_profile_from_text(update, context)
        return
    # if user in active chat -> copy message
    if uid in active:
        partner = active.get(uid)
        try:
            # copy_message preserves media, captions, stickers, etc.
            await context.bot.copy_message(chat_id=partner, from_chat_id=update.effective_chat.id, message_id=update.message.message_id)
        except Exception:
            # fallback for text
            if update.message.text:
                await context.bot.send_message(partner, update.message.text)
        return
    # else not in chat
    # friendly hint
    await update.message.reply_text("Use /find to search for someone to chat with. Use /start to set up your profile.")

# callback buttons (none used heavily now but placeholder)
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("Action received.")

# --------- BOOTSTRAP & RUN ----------
async def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # commands
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("find", cmd_find))
    application.add_handler(CommandHandler("stop", cmd_stop))
    application.add_handler(CommandHandler("next", cmd_next))
    application.add_handler(CommandHandler("edit", cmd_edit))
    application.add_handler(CommandHandler("ref", cmd_ref))
    application.add_handler(CommandHandler("help", cmd_help))

    # callback queries
    application.add_handler(CallbackQueryHandler(callback_handler))

    # message relay & profile input
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, relay_message))

    logger.info("AnonChatPlush starting (long polling)...")
    await application.run_polling()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down AnonChatPlush.")
    
