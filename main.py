# main.py
# Anonymous Telethon bot with typing indicator, /block, /report, /clear, /menu, auto-clean, safe resend (no forwards)
# Env vars required: BOT_TOKEN, API_ID, API_HASH. Optional: PORT, ADMIN_USERNAME

import os, time, json, threading, asyncio, logging
from pathlib import Path
from typing import Optional, Dict, Any
from flask import Flask
from telethon import TelegramClient, events, Button
from telethon.tl.types import InputPeerUser

# --------- Config ----------
API_ID = int(os.getenv("API_ID", "28560028"))
API_HASH = os.getenv("API_HASH", "efc9a353e1d044c3ebf0f143a7782df8")
BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", "10000"))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "tandoori123")  # admin to receive /report

if not BOT_TOKEN or not API_ID or not API_HASH:
    raise SystemExit("Set BOT_TOKEN, API_ID, API_HASH environment variables.")

DATA_FILE = Path("data.json")
CLEANUP_INTERVAL = 60  # seconds
INACTIVE_TIMEOUT = 15 * 60  # 15 minutes inactivity -> end session

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("anonbot")

# --------- Persistent storage helpers ----------
def load_data() -> Dict[str, Any]:
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    # structure: users, queue, sessions, user_session, blocks, last_active
    return {
        "users": {},          # user_id -> profile dict
        "queue": [],          # list of {"user_id": str, "filter_gender": Optional[str]}
        "sessions": {},       # session_id -> {"a": str, "b": str}
        "user_session": {},   # user_id -> session_id
        "blocks": {},         # blocker_id -> [blocked_user_ids]
        "last_active": {}     # user_id -> unix timestamp
    }

def save_data(data: Dict[str,Any]):
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

DATA = load_data()

# --------- Flask (keep-alive) ----------
flask_app = Flask("anon_anon")
@flask_app.route("/")
def index():
    return "✅ Anonymous Bot (with typing & admin tools) running"
@flask_app.route("/ping")
def ping():
    return "pong"

def run_flask():
    # run dev server for keep-alive (Render detects port)
    flask_app.run(host="0.0.0.0", port=PORT)

# --------- Telethon client ----------
client = TelegramClient("anonbot_session", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# --------- Helpers ----------
def now_ts() -> int:
    return int(time.time())

def is_blocked(a: int, b: int) -> bool:
    """Return True if a has blocked b or b has blocked a (mutual block check)."""
    a_blocks = set(DATA.get("blocks", {}).get(str(a), []))
    b_blocks = set(DATA.get("blocks", {}).get(str(b), []))
    return str(b) in a_blocks or str(a) in b_blocks

def add_block(blocker: int, blocked: int):
    DATA.setdefault("blocks", {})
    lst = DATA["blocks"].setdefault(str(blocker), [])
    if str(blocked) not in lst:
        lst.append(str(blocked))
    save_data(DATA)

def profile_text(uid: int) -> str:
    u = DATA["users"].get(str(uid), {})
    return (
        f"👤 Gender: {u.get('gender','—')}\n"
        f"🎂 Age: {u.get('age','—')}\n"
        f"📍 Location: {u.get('location','—')}\n"
        f"✨ Interest: {u.get('interest','—')}"
    )

def in_queue(uid: int) -> bool:
    return any(item["user_id"] == str(uid) for item in DATA["queue"])

def remove_from_queue(uid: int):
    DATA["queue"] = [item for item in DATA["queue"] if item["user_id"] != str(uid)]
    save_data(DATA)

def make_session(a: int, b: int) -> str:
    import uuid
    sid = str(uuid.uuid4())
    DATA["sessions"][sid] = {"a": str(a), "b": str(b)}
    DATA["user_session"][str(a)] = sid
    DATA["user_session"][str(b)] = sid
    DATA.setdefault("last_active", {})[str(a)] = now_ts()
    DATA["last_active"][str(b)] = now_ts()
    save_data(DATA)
    return sid

def get_partner(uid: int) -> Optional[int]:
    sid = DATA["user_session"].get(str(uid))
    if not sid: return None
    s = DATA["sessions"].get(sid)
    if not s: return None
    return int(s["b"]) if s["a"] == str(uid) else int(s["a"])

def end_session_for(uid: int) -> Optional[Dict[str,str]]:
    sid = DATA["user_session"].get(str(uid))
    if not sid:
        return None
    s = DATA["sessions"].pop(sid, None)
    if not s:
        DATA["user_session"].pop(str(uid), None)
        save_data(DATA)
        return None
    DATA["user_session"].pop(s["a"], None)
    DATA["user_session"].pop(s["b"], None)
    # clear last_active
    DATA.get("last_active", {}).pop(s["a"], None)
    DATA.get("last_active", {}).pop(s["b"], None)
    save_data(DATA)
    return s

def queue_add(uid: int, filter_gender: Optional[str]):
    remove_from_queue(uid)
    DATA["queue"].append({"user_id": str(uid), "filter_gender": filter_gender})
    save_data(DATA)

# ---------- Buttons ----------
def search_keyboard():
    return [
        [Button.inline("🔎 Search Female", b"search_female"), Button.inline("🔎 Search Male", b"search_male")],
        [Button.inline("🔁 Search Anyone", b"search_any")]
    ]
def chat_buttons():
    return [Button.inline("➡️ Next", b"next"), Button.inline("⛔ Stop", b"stop")]

# --------- Matching algorithm ----------
async def try_match(uid: int):
    # return if already in session
    if DATA["user_session"].get(str(uid)):
        return
    # find caller entry
    caller_entry = None
    for e in DATA["queue"]:
        if e["user_id"] == str(uid):
            caller_entry = e
            break
    if not caller_entry:
        return
    # iterate queue to find partner
    for e in list(DATA["queue"]):
        if e["user_id"] == str(uid):
            continue
        partner_profile = DATA["users"].get(e["user_id"], {})
        caller_req = caller_entry.get("filter_gender")
        partner_req = e.get("filter_gender")
        caller_profile = DATA["users"].get(str(uid), {})
        # filters
        if caller_req and partner_profile.get("gender","").lower() != caller_req.lower():
            continue
        if partner_req and caller_profile.get("gender","").lower() != partner_req.lower():
            continue
        # prevent matching if blocked
        if is_blocked(uid, int(e["user_id"])):
            continue
        # match
        a = int(uid); b = int(e["user_id"])
        remove_from_queue(a); remove_from_queue(b)
        make_session(a,b)
        try:
            await client.send_message(a, "🎉 Match found! You are now connected anonymously. Say hi! 👋", buttons=chat_buttons())
            await client.send_message(a, "––– Partner profile –––\n" + profile_text(b))
            await client.send_message(b, "🎉 Match found! You are now connected anonymously. Say hi! 👋", buttons=chat_buttons())
            await client.send_message(b, "––– Partner profile –––\n" + profile_text(a))
        except Exception as ex:
            log.exception("notify match failed: %s", ex)
        break

# --------- Auto-clean background task ----------
async def cleaner_loop():
    while True:
        try:
            now = now_ts()
            sessions_to_end = []
            for sid, s in list(DATA.get("sessions", {}).items()):
                a,b = s["a"], s["b"]
                last_a = DATA.get("last_active", {}).get(a, 0)
                last_b = DATA.get("last_active", {}).get(b, 0)
                if now - max(last_a, last_b) > INACTIVE_TIMEOUT:
                    sessions_to_end.append((sid, s))
            for sid, s in sessions_to_end:
                a = int(s["a"]); b = int(s["b"])
                # remove session
                DATA["sessions"].pop(sid, None)
                DATA["user_session"].pop(str(a), None)
                DATA["user_session"].pop(str(b), None)
                DATA.get("last_active", {}).pop(str(a), None)
                DATA.get("last_active", {}).pop(str(b), None)
                save_data(DATA)
                # notify both
                try:
                    await client.send_message(a, "⏲️ Chat ended due to inactivity.")
                    await client.send_message(b, "⏲️ Chat ended due to inactivity.")
                except Exception:
                    pass
        except Exception as e:
            log.exception("cleaner loop error: %s", e)
        await asyncio.sleep(CLEANUP_INTERVAL)

# --------- Admin helper ----------
async def send_report_to_admin(reporter: int, reported_partner: Optional[int], reason: str):
    admin = os.getenv("ADMIN_USERNAME", ADMIN_USERNAME)
    try:
        text = f"🚨 *User Report*\nReporter id: `{reporter}`\nReason: {reason}\n"
        if reported_partner:
            text += "\nReported partner profile:\n" + profile_text(reported_partner)
        await client.send_message(admin, text, parse_mode="markdown")
    except Exception:
        log.exception("failed send report to admin")

# --------- Event Handlers ----------
@client.on(events.NewMessage(pattern="/start"))
async def h_start(event):
    uid = event.sender_id
    DATA["users"].pop(str(uid), None)  # reset prior for fresh start optionally
    TEMP = {"step":"gender", "profile":{}}
    # save TEMP in-memory: we store in runtime-only map to avoid accidental persistence
    event.client._temp_profiles = getattr(event.client, "_temp_profiles", {})
    event.client._temp_profiles[str(uid)] = TEMP
    await event.respond("👋 Welcome! Choose gender:", buttons=[
        [Button.inline("👨 Male", b"gender_male"), Button.inline("👩 Female", b"gender_female"), Button.inline("⚧ Other", b"gender_other")]
    ])

@client.on(events.CallbackQuery)
async def h_callback(event):
    uid = event.sender_id
    data = event.data.decode() if isinstance(event.data, bytes) else str(event.data)
    temp_profiles = getattr(client, "_temp_profiles", {})
    tp = temp_profiles.get(str(uid))
    # Gender selection during setup
    if data.startswith("gender_") and tp and tp.get("step")=="gender":
        g = data.split("_",1)[1]
        tp["profile"]["gender"]=g
        tp["step"]="age"
        await event.edit("🎂 Now send your age (text):")
        return
    # search buttons
    if data in ("search_female","search_male","search_any"):
        remove_from_queue(uid)
        filt = None
        if data=="search_female": filt="female"
        elif data=="search_male": filt="male"
        DATA["queue"].append({"user_id":str(uid),"filter_gender":filt})
        save_data(DATA)
        await event.edit("🔎 Searching... I'll notify you.", buttons=search_keyboard())
        await try_match(uid)
        return
    # in-chat buttons next / stop
    if data in ("next","stop"):
        if data=="stop":
            s = end_session_for(uid)
            if s:
                other = int(s["b"]) if s["a']==str(uid) else int(s["a"])
                try:
                    await client.send_message(other, "⛔ The other user left the chat.", buttons=search_keyboard())
                except Exception:
                    pass
            await event.edit("⛔ Chat ended. Use /find to search again.", buttons=search_keyboard())
            await event.answer("Chat ended")
            return
        else:  # next
            s = end_session_for(uid)
            if s:
                other = int(s["b"]) if s["a']==str(uid) else int(s["a"])
                try:
                    await client.send_message(other, "➡️ The other user moved to next.", buttons=search_keyboard())
                except Exception:
                    pass
            remove_from_queue(uid)
            DATA["queue"].append({"user_id":str(uid),"filter_gender":None})
            save_data(DATA)
            await event.edit("➡️ Searching for next user...", buttons=None)
            await try_match(uid)
            await event.answer("Finding next")
            return

@client.on(events.NewMessage(pattern="/find"))
async def h_find(event):
    uid = event.sender_id
    # commit temp profile if exists
    temp_profiles = getattr(client, "_temp_profiles", {})
    tp = temp_profiles.get(str(uid))
    if tp and tp.get("step")=="done":
        DATA["users"][str(uid)] = tp["profile"]
        temp_profiles.pop(str(uid), None)
        save_data(DATA)
    if str(uid) not in DATA["users"]:
        await event.respond("⚠️ Complete setup first with /start.")
        return
    if DATA["user_session"].get(str(uid)):
        await event.respond("⚠️ You're already in chat. Use /next or /stop.")
        return
    DATA["queue"].append({"user_id":str(uid),"filter_gender":None})
    save_data(DATA)
    await event.respond("🔎 Searching for a partner...", buttons=search_keyboard())
    await try_match(uid)

@client.on(events.NewMessage(pattern="/male"))
async def h_male(event):
    uid = event.sender_id
    if str(uid) not in DATA["users"]:
        await event.respond("⚠️ Complete /start first.")
        return
    DATA["queue"].append({"user_id":str(uid),"filter_gender":"male"})
    save_data(DATA)
    await event.respond("🔎 Searching for male...", buttons=search_keyboard())
    await try_match(uid)

@client.on(events.NewMessage(pattern="/female"))
async def h_female(event):
    uid = event.sender_id
    if str(uid) not in DATA["users"]:
        await event.respond("⚠️ Complete /start first.")
        return
    DATA["queue"].append({"user_id":str(uid),"filter_gender":"female"})
    save_data(DATA)
    await event.respond("🔎 Searching for female...", buttons=search_keyboard())
    await try_match(uid)

@client.on(events.NewMessage(pattern="/anyone"))
async def h_anyone(event):
    uid = event.sender_id
    if str(uid) not in DATA["users"]:
        await event.respond("⚠️ Complete /start first.")
        return
    DATA["queue"].append({"user_id":str(uid),"filter_gender":None})
    save_data(DATA)
    await event.respond("🔎 Searching for anyone...", buttons=search_keyboard())
    await try_match(uid)

@client.on(events.NewMessage(pattern="/stop"))
async def h_stop(event):
    uid = event.sender_id
    s = end_session_for(uid)
    if not s:
        if in_queue(uid):
            remove_from_queue(uid)
            await event.respond("You left the queue.")
            return
        await event.respond("You were not in chat or queue.")
        return
    other = int(s["b"]) if s["a"]==str(uid) else int(s["a"])
    try:
        await client.send_message(other, "⛔ The other user left the chat.", buttons=search_keyboard())
    except Exception:
        pass
    await event.respond("⛔ Chat ended.", buttons=search_keyboard())

@client.on(events.NewMessage(pattern="/next"))
async def h_next(event):
    uid = event.sender_id
    s = end_session_for(uid)
    if s:
        other = int(s["b"]) if s["a"]==str(uid) else int(s["a"])
        try:
            await client.send_message(other, "➡️ The other user moved to the next.", buttons=search_keyboard())
        except Exception:
            pass
    remove_from_queue(uid)
    DATA["queue"].append({"user_id":str(uid),"filter_gender":None})
    save_data(DATA)
    await event.respond("➡️ Finding next user...", buttons=search_keyboard())
    await try_match(uid)

@client.on(events.NewMessage(pattern="/edit"))
async def h_edit(event):
    uid = event.sender_id
    event.client._temp_profiles = getattr(client, "_temp_profiles", {})
    event.client._temp_profiles[str(uid)] = {"step":"gender","profile":{}}
    await event.respond("✏️ Edit profile — choose gender:", buttons=[
        [Button.inline("👨 Male", b"gender_male"), Button.inline("👩 Female", b"gender_female")]
    ])

@client.on(events.NewMessage(pattern="/clear"))
async def h_clear(event):
    uid = event.sender_id
    # remove user profile, queue, sessions
    DATA["users"].pop(str(uid), None)
    remove_from_queue(uid)
    s = end_session_for(uid)
    save_data(DATA)
    await event.respond("🧹 Your data has been cleared. Use /start to create profile again.")

@client.on(events.NewMessage(pattern="/block"))
async def h_block(event):
    uid = event.sender_id
    # expects reply to message to block that partner, else error
    if event.is_reply:
        target = event.reply_to_msg_id
        try:
            replied = await event.get_reply_message()
            target_uid = replied.sender_id
            add_block(uid, target_uid)
            # if in session, end it
            end_session_for(uid); end_session_for(target_uid)
            await event.respond("⛔ User blocked and chat removed.")
        except Exception:
            await event.respond("Failed to block.")
    else:
        await event.respond("Reply to a user's message with /block to block them.")

@client.on(events.NewMessage(pattern="/report"))
async def h_report(event):
    uid = event.sender_id
    text = event.message.message.split(" ",1)
    reason = text[1] if len(text)>1 else "No reason provided"
    partner = get_partner(uid)
    await send_report_to_admin(uid, partner, reason)
    await event.respond("✅ Report sent to admin. Thank you.")

@client.on(events.NewMessage(pattern="/menu"))
async def h_menu(event):
    await event.respond(
        "Menu",
        buttons=[
            [Button.inline("🔎 Find", b"search_any"), Button.inline("⛔ Stop", b"stop")],
            [Button.inline("➡️ Next", b"next"), Button.inline("✏️ Edit", b"edit")]
        ]
    )

@client.on(events.NewMessage(pattern="/help"))
async def h_help(event):
    await event.respond(
        "Commands:\n"
        "/start /find /male /female /anyone /next /stop /edit /clear /block (reply) /report <reason> /menu /help\n"
        "Sends text, photos, videos, voice, stickers while matched. All forwarded anonymously."
    )

# General handler: collect profile steps and resend anonymously (no forward)
@client.on(events.NewMessage)
async def h_general(event):
    uid = event.sender_id
    text = (event.raw_text or "").strip()

    # profile temp storage
    temp_profiles = getattr(client, "_temp_profiles", {})
    tp = temp_profiles.get(str(uid))
    if tp:
        step = tp.get("step")
        if step == "age":
            tp["profile"]["age"] = text or "—"
            tp["step"] = "location"
            await event.respond("📍 Now tell me your location:")
            return
        if step == "location":
            tp["profile"]["location"] = text or "—"
            tp["step"] = "interest"
            await event.respond("✨ Now tell me your interest:")
            return
        if step == "interest":
            tp["profile"]["interest"] = text or "—"
            tp["step"] = "done"
            DATA["users"][str(uid)] = tp["profile"]
            temp_profiles.pop(str(uid), None)
            save_data(DATA)
            await event.respond("✅ Profile saved! Use /find to search.")
            return

    # If user is in session, deliver anonymously (no forward)
    partner = get_partner(uid)
    if partner:
        if is_blocked(uid, partner):
            await event.respond("⚠️ Message could not be delivered (blocked).")
            return
        # Update last active
        DATA.setdefault("last_active", {})[str(uid)] = now_ts()
        save_data(DATA)
        # typing indicator for partner (show typing)
        try:
            await client.send_chat_action(partner, 'typing')
        except Exception:
            pass
        # deliver message safely (media or text)
        try:
            if event.message.media:
                await client.send_file(partner, file=event.message.media, caption=event.message.text or "")
            else:
                await client.send_message(partner, event.message.text or "")
            # send delivered ack to sender (one-time, non-spam): ephemeral small message then delete after 5s
            ack = await client.send_message(uid, "✅ Delivered")
            await asyncio.sleep(3)
            try:
                await ack.delete()
            except Exception:
                pass
        except Exception as ex:
            log.exception("deliver failed: %s", ex)
            await event.respond("⚠️ Could not deliver message.")
        return

    # If user is queued, acknowledge softly
