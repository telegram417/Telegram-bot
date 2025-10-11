#!/usr/bin/env python3
"""
AnonChatPlush - Elegant & Minimal anonymous chat bot (memory-only)
Drop this file in repo root. Make sure BOT_TOKEN (and optional BOT_USERNAME) env vars are set.
"""

import os
import logging
import asyncio
from datetime import datetime, timedelta

from telegram import (
    Update, ReplyKeyboardMarkup, ReplyKeyboardRemove,
    InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# ---------- CONFIG ----------
BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME", "MeetAnonymousBOT")  # used for referral link
REF_REQUIRED = 3
REF_DAYS = 3

if not BOT_TOKEN:
    raise RuntimeError("Missing BOT_TOKEN environment variable. Set it in Render/hosting platform.")

# ---------- LOGGING ----------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AnonChatPlush")

# ---------- IN-MEMORY STORAGE ----------
# user_profiles[user_id] = {
#   gender, age, location, interest,
#   awaiting -> None or 'gender'/'age'/'location'/'interest'/'edit_*'
#   search_pref -> dict,
#   invites -> int,
#   premium_until -> iso str or None
# }
user_profiles = {}
waiting = []    # list of user_ids in queue
active = {}     # map user_id -> partner_id

# ---------- HELPERS ----------
def title(txt: str) -> str:
    return f"✨ {txt} ✨"

def divider() -> str:
    return "――――――――――――――――"

def is_premium(profile: dict) -> bool:
    until = profile.get("premium_until")
    if not until:
        return False
    try:
        return datetime.fromisoformat(until) > datetime.utcnow()
    except Exception:
        return False

def grant_premium(profile: dict, days: int = REF_DAYS):
    profile["premium_until"] = (datetime.utcnow() + timedelta(days=days)).isoformat()

def profile_complete(p: dict) -> bool:
    return bool(p.get("gender") and p.get("age") and p.get("location") and p.get("interest"))

def format_profile(p: dict) -> str:
    return (
        f"👤 Gender: {p.get('gender','—')}\n"
        f"🎂 Age: {p.get('age','—')}\n"
        f"📍 Location: {p.get('location','—')}\n"
        f"💬 Interest: {p.get('interest','—')}"
    )

def parse_find_args(args_list):
    # returns dict {gender, min_age, max_age, interest}
    pref = {"gender": None, "min_age": None, "max_age": None, "interest": None}
    if not args_list:
        return pref
    idx = 0
    a0 = args_list[0].lower()
    if a0 in ("male", "female", "other", "any"):
        pref["gender"] = None if a0 == "any" else a0.capitalize()
        idx = 1
    if idx < len(args_list) and "-" in args_list[idx]:
        r = args_list[idx].split("-", 1)
        if r[0].isdigit() and r[1].isdigit():
            pref["min_age"] = int(r[0]); pref["max_age"] = int(r[1])
            idx += 1
    if idx < len(args_list):
        pref["interest"] = " ".join(args_list[idx:]).strip().lower()
    return pref

def matches_pref(profile: dict, pref: dict) -> bool:
    if not profile:
        return False
    if pref.get("gender") and profile.get("gender") != pref.get("gender"):
        return False
    if pref.get("min_age"):
        try:
            if int(profile.get("age", 0)) < pref["min_age"]:
                return False
        except:
            return False
    if pref.get("max_age"):
        try:
            if int(profile.get("age", 0)) > pref["max_age"]:
                return False
        except:
            return False
    if pref.get("interest"):
        user_interest = (profile.get("interest") or "").lower()
        if pref["interest"] not in user_interest:
            return False
    return True

# ---------- PROFILE FLOW ----------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    args = context.args or []

    # Referral handling: /start ref<inviter_id>
    if args:
        raw = args[0]
        if raw.startswith("ref"):
            try:
                inviter = int(raw[3:])
                invp = user_profiles.setdefault(inviter, {})
                invp["invites"] = invp.get("invites", 0) + 1
                if invp["invites"] >= REF_REQUIRED:
                    grant_premium(invp, REF_DAYS)
                    invp["invites"] = 0
                    # notify inviter
                    try:
                        await context.bot.send_message(inviter, f"🎉 You've earned {REF_DAYS} days Premium on AnonChatPlush — enjoy!")
                    except Exception:
                        pass
            except Exception:
                pass

    p = user_profiles.setdefault(uid, {})
    p.setdefault("invites", 0)
    p.setdefault("premium_until", None)
    p["partner"] = p.get("partner")  # keep partner if any
    # start profile flow
    p["awaiting"] = "gender"
    kb = ReplyKeyboardMarkup([["Male", "Female", "Other"]], resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(
        f"{title('Welcome to AnonChatPlush')}\n\nA quiet, elegant place to meet strangers anonymously.\n\nPlease choose your gender:",
        reply_markup=kb
    )

async def _continue_profile_from_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    p = user_profiles.get(uid)
    if not p:
        await cmd_start(update, context)
        return
    waiting_for = p.get("awaiting")
    text = (update.message.text or "").strip()

    if waiting_for == "gender":
        if text.lower() not in ("male", "female", "other"):
            await update.message.reply_text("Please choose Male, Female or Other (use the buttons).")
            return
        p["gender"] = text.capitalize()
        p["awaiting"] = "age"
        await update.message.reply_text("🎂 Now send your age (just the number):", reply_markup=ReplyKeyboardRemove())
        return

    if waiting_for == "age":
        if not text.isdigit() or not (10 <= int(text) <= 120):
            await update.message.reply_text("Please send a valid age number (10–120).")
            return
        p["age"] = text
        p["awaiting"] = "location"
        await update.message.reply_text("📍 Where are you from? (city or city, country)")
        return

    if waiting_for == "location":
        p["location"] = text
        p["awaiting"] = "interest"
        await update.message.reply_text("💬 One-line: what are your interests? (e.g., music, travel)")
        return

    if waiting_for == "interest":
        p["interest"] = text
        p["awaiting"] = None
        await update.message.reply_text(
            f"{divider()}\nProfile saved ✔️\n\n{format_profile(p)}\n{divider()}\nUse /find to meet someone, or /edit to change your profile."
        )
        return

    # if not awaiting and user is chatting, relay occurs elsewhere
    await update.message.reply_text("Use /find to search for a partner or /profile to view your profile.")

async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    p = user_profiles.get(uid)
    if not p:
        await update.message.reply_text("You don't have a profile yet. Use /start to create one.")
        return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Edit Gender", callback_data="edit_gender"),
         InlineKeyboardButton("✏️ Edit Age", callback_data="edit_age")],
        [InlineKeyboardButton("✏️ Edit Location", callback_data="edit_location"),
         InlineKeyboardButton("✏️ Edit Interest", callback_data="edit_interest")]
    ])
    await update.message.reply_text(f"{title('Your Profile')}\n\n{format_profile(p)}", reply_markup=kb)

async def cmd_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in user_profiles:
        await cmd_start(update, context)
        return
    user_profiles[uid]["awaiting"] = "gender"
    kb = ReplyKeyboardMarkup([["Male", "Female", "Other"]], resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text("Edit Profile — choose new gender:", reply_markup=kb)

# ---------- REF / HELP ----------
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"{title('AnonChatPlush — Help')}\n\n"
        "• /start — create or edit profile\n"
        "• /profile — view & edit your profile\n"
        "• /find [gender] [min-max] [interest] — find a partner (optional filters)\n"
        "  e.g.: /find, /find female, /find 18-24 music\n"
        "• /next — skip current chat and find another\n"
        "• /stop — end current chat\n"
        "• /edit — step-by-step edit profile\n"
        "• /ref — get your referral link (3 invites -> 3 days premium)\n\n"
        "Media supported: photos, videos, voice, stickers. Data is memory-only (resets on restart)."
    )

async def cmd_ref(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    link = f"https://t.me/{BOT_USERNAME}?start=ref{uid}"
    p = user_profiles.get(uid, {})
    invites = p.get("invites", 0) if p else 0
    prem = "Active" if p and is_premium(p) else "None"
    await update.message.reply_text(
        f"Share your referral link:\n{link}\n\nInvites: {invites}/{REF_REQUIRED}\nPremium: {prem}\n\n"
        f"Get {REF_REQUIRED} invites to earn {REF_DAYS} days Premium (memory-only)."
    )

# ---------- MATCHING ----------
async def find_for_user(uid: int, context: ContextTypes.DEFAULT_TYPE, via_update: Update = None, pref: dict = None):
    # Ensure user profile exists and complete
    p = user_profiles.get(uid)
    if not p or not profile_complete(p):
        if via_update:
            await context.bot.send_message(uid, "Complete profile first with /start.")
        return

    if uid in active:
        if via_update:
            await context.bot.send_message(uid, "You're already in a chat. Use /stop or /next.")
        return

    if pref is None:
        pref = p.get("search_pref") or {}

    # scan waiting queue
    for idx, cand in enumerate(waiting):
        if cand == uid:
            continue
        cand_prof = user_profiles.get(cand)
        if not cand_prof or cand_prof.get("partner"):
            continue
        cand_pref = cand_prof.get("search_pref") or {}
        # check mutual match
        if not matches_pref(cand_prof, pref):
            continue
        if cand_pref and any(cand_pref.values()):
            if not matches_pref(p, cand_pref):
                continue
        # OK match
        waiting.pop(idx)
        active[uid] = cand
        active[cand] = uid
        # show partner info (if premium or always — both see)
        try:
            await context.bot.send_message(cand, f"💫 You are now connected anonymously.\n\n{format_profile(p)}\n\nSay hi 👋")
            await context.bot.send_message(uid, f"💫 You are now connected anonymously.\n\n{format_profile(cand_prof)}\n\nSay hi 👋")
        except Exception:
            pass
        return

    # not found — add to waiting
    if uid not in waiting:
        waiting.append(uid)
    # send queue message (animated)
    if via_update:
        msg = await via_update.message.reply_text("🔎 Searching for a refined connection...")
    else:
        msg = await context.bot.send_message(uid, "🔎 Searching for a refined connection...")
    try:
        steps = ["🔎 Searching for a refined connection...", "✨ Scanning compatible profiles...", "🌙 Almost there..."]
        for s in steps:
            await asyncio.sleep(1.0)
            await msg.edit_text(s)
    except Exception:
        pass
    await msg.edit_text("⌛ You are in queue. We'll notify you when matched.")

async def cmd_find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    args = context.args or []
    pref = parse_find_args(args)
    user_profiles.setdefault(uid, {})
    user_profiles[uid]["search_pref"] = pref
    await find_for_user(uid, context, via_update=update, pref=pref)

# ---------- END / NEXT ----------
async def end_chat_for_user(uid: int, context: ContextTypes.DEFAULT_TYPE):
    partner = active.pop(uid, None)
    if partner:
        active.pop(partner, None)
        # notify partner that their partner left and provide quick actions
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 Find another", callback_data="find")],
            [InlineKeyboardButton("🎯 Search by gender", callback_data="search_gender")]
        ])
        try:
            await context.bot.send_message(partner, "❌ Your partner left the chat.", reply_markup=kb)
        except Exception:
            pass

async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid in active:
        await end_chat_for_user(uid, context)
        await update.message.reply_text("✅ You left the chat. Use /find to meet someone new.")
    elif uid in waiting:
        try:
            waiting.remove(uid)
        except ValueError:
            pass
        await update.message.reply_text("Stopped searching. Use /find when you're ready.")
    else:
        await update.message.reply_text("You are not in a chat or queue.")

async def cmd_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    # keep user's existing search_pref
    pref = user_profiles.get(uid, {}).get("search_pref")
    if uid in active:
        await end_chat_for_user(uid, context)
    if uid in waiting:
        try:
            waiting.remove(uid)
        except Exception:
            pass
    # call find_for_user using same pref
    await find_for_user(uid, context, via_update=update, pref=pref)

# ---------- MESSAGE RELAY ----------
async def relay_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    p = user_profiles.get(uid)
    # priority: if user in profile flow, handle it
    if p and p.get("awaiting"):
        await _continue_profile_from_text(update, context)
        return
    # if in chat -> copy message to partner
    if uid in active:
        partner = active.get(uid)
        try:
            await context.bot.copy_message(chat_id=partner, from_chat_id=update.effective_chat.id, message_id=update.message.message_id)
        except Exception:
            # fallback text only
            if update.message.text:
                await context.bot.send_message(partner, update.message.text)
        return
    # otherwise, friendly hint
    await update.message.reply_text("Use /find to search for a partner, or /start to set up your profile.")

# ---------- CALLBACK HANDLER (inline buttons) ----------
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = query.from_user.id

    if data.startswith("edit_"):
        field = data.split("_", 1)[1]
        user_profiles.setdefault(uid, {})
        user_profiles[uid]["awaiting"] = field
        if field == "gender":
            kb = ReplyKeyboardMarkup([["Male", "Female", "Other"]], resize_keyboard=True, one_time_keyboard=True)
            await query.message.reply_text("Choose new gender:", reply_markup=kb)
        else:
            await query.message.reply_text(f"Send new {field} value:", reply_markup=ReplyKeyboardRemove())
        return

    if data == "find":
        # user clicked "Find another"
        await query.message.reply_text("🔎 Searching for another connection...")
        await find_for_user(uid, context, via_update=None)
        return

    if data == "search_gender":
        # explain /ref and options
        await query.message.reply_text("To refine matches by gender, use:\n/find female\n/find male\n\nOr use /ref to see referral/premium details.")
        return

    await query.message.reply_text("Action received.")

# ---------- STARTUP ----------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # command handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("profile", cmd_profile))
    app.add_handler(CommandHandler("edit", cmd_edit))
    app.add_handler(CommandHandler("find", cmd_find))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("next", cmd_next))
    app.add_handler(CommandHandler("ref", cmd_ref))
    app.add_handler(CommandHandler("help", cmd_help))

    # callbacks and generic messages
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, relay_message))

    logger.info("AnonChatPlush starting (long polling)...")
    # Run polling. close_loop=False avoids closing outer loop (fixes "event loop already running")
    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
    
