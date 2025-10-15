# main.py
# Telethon anonymous matching bot + Flask keep-alive
# Requires env vars: BOT_TOKEN, API_ID, API_HASH, PORT (optional, default 10000)

import os
import json
import asyncio
import threading
from pathlib import Path
from typing import Optional, Dict, Any

from flask import Flask
from telethon import TelegramClient, events, Button
from telethon.tl.types import InputPeerUser

# --------- Config (from environment) ----------
BOT_TOKEN = os.getenv("BOT_TOKEN")          # set this in Render
API_ID = int(os.getenv("API_ID", "0"))     # set this in Render
API_HASH = os.getenv("API_HASH")           # set this in Render
PORT = int(os.getenv("PORT", "10000"))

DATA_FILE = Path("data.json")

# --------- Simple persistent storage ----------
def load_data() -> Dict[str, Any]:
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {"users": {}, "queue": [], "sessions": {}, "user_session": {}}
    return {"users": {}, "queue": [], "sessions": {}, "user_session": {}}

def save_data(data: Dict[str, Any]):
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

DATA = load_data()

# Structure:
# DATA["users"][str(user_id)] = {"gender":..., "age":..., "location":..., "interest":...}
# DATA["queue"] = [ {"user_id":str, "filter_gender":Optional[str]} , ... ]
# DATA["sessions"][session_id] = {"a": str, "b": str}
# DATA["user_session"][str(user_id)] = session_id

# --------- Utilities ----------
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

def make_session(a: int, b: int):
    import uuid
    sid = str(uuid.uuid4())
    DATA["sessions"][sid] = {"a": str(a), "b": str(b)}
    DATA["user_session"][str(a)] = sid
    DATA["user_session"][str(b)] = sid
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
    save_data(DATA)
    return s

# ---------- Flask server (for Render + UptimeRobot) ----------
flask_app = Flask("anon_bot")

@flask_app.route("/")
def index():
    return "✅ Anonymous Telethon Bot running!"

@flask_app.route("/ping")
def ping():
    return "pong"

def run_flask():
    # development server is fine for keep-alive; Render will detect port
    flask_app.run(host="0.0.0.0", port=PORT)

# --------- Telethon bot client ----------
client = TelegramClient('anon_bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# Temporary state while collecting profile info
# { user_id: {"step": "gender"/"age"/"location"/"interest", "profile": {...}} }
TEMP = {}

# Keyboard helpers
def search_keyboard():
    return [
        [Button.inline("🔎 Search Female", b"search_female"), Button.inline("🔎 Search Male", b"search_male")],
        [Button.inline("🔁 Search Anyone", b"search_any")]
    ]

def chat_buttons():
    return [Button.inline("➡️ Next", b"next"), Button.inline("⛔ Stop", b"stop")]

# --------- Handlers ----------

@client.on(events.NewMessage(pattern="/start"))
async def cmd_start(event):
    uid = event.sender_id
    # start profile collection with gender buttons
    TEMP[str(uid)] = {"step": "gender", "profile": {}}
    await event.respond(
        "👋 Welcome! Let's create your anonymous profile.\nChoose your gender:",
        buttons=[
            [Button.inline("👨 Male", b"gender_male"), Button.inline("👩 Female", b"gender_female"), Button.inline("⚧ Other", b"gender_other")]
        ]
    )

@client.on(events.CallbackQuery)
async def callback_handler(event):
    uid = event.sender_id
    data = event.data.decode() if isinstance(event.data, bytes) else str(event.data)

    # gender selection during setup
    if data.startswith("gender_") and str(uid) in TEMP and TEMP[str(uid)]["step"] == "gender":
        g = data.split("_",1)[1]
        TEMP[str(uid)]["profile"]["gender"] = g
        TEMP[str(uid)]["step"] = "age"
        await event.answer("Gender saved ✅", alert=False)
        await event.edit("🎂 Now please type your age (you can write anything):")
        return

    # search buttons after stop / quick actions
    if data in ("search_female", "search_male", "search_any"):
        # add to queue with filter
        remove_from_queue(uid)
        filt = None
        if data == "search_female": filt = "female"
        elif data == "search_male": filt = "male"
        DATA["queue"].append({"user_id": str(uid), "filter_gender": filt})
        save_data(DATA)
        await event.answer("Searching...", alert=False)
        await event.edit("🔎 Searching. I'll notify you when matched.")
        # attempt immediate match
        await try_match(uid)
        return

    # in-chat inline buttons: next / stop
    if data in ("next", "stop"):
        if data == "stop":
            s = end_session_for(uid)
            if s:
                other = int(s["b"]) if s["a"] == str(uid) else int(s["a"])
                try:
                    await client.send_message(other, "⛔ The other user left the chat. Chat ended.", buttons=search_keyboard())
                except Exception:
                    pass
            await event.answer("Chat ended", alert=False)
            await event.edit("⛔ Chat ended. Use /find to search again.", buttons=search_keyboard())
            return
        else:  # next
            s = end_session_for(uid)
            if s:
                other = int(s["b"]) if s["a"] == str(uid) else int(s["a"])
                try:
                    await client.send_message(other, "➡️ The other user moved to the next. Chat ended.", buttons=search_keyboard())
                except Exception:
                    pass
            # requeue requester
            remove_from_queue(uid)
            DATA["queue"].append({"user_id": str(uid), "filter_gender": None})
            save_data(DATA)
            await event.answer("Finding next...", alert=False)
            await event.edit("➡️ Searching for next user...", buttons=None)
            await try_match(uid)
            return

@client.on(events.NewMessage(func=lambda e: e.raw_text and e.raw_text.startswith("/find")))
async def cmd_find(event):
    uid = event.sender_id
    # must have profile set in DATA or TEMP
    # if in TEMP and finished, commit
    if str(uid) in TEMP and TEMP[str(uid)]["step"] == "done":
        DATA["users"][str(uid)] = TEMP[str(uid)]["profile"]
        TEMP.pop(str(uid), None)
        save_data(DATA)

    if str(uid) not in DATA["users"]:
        await event.respond("⚠️ You must complete /start setup first.")
        return

    # if in a session already
    if DATA["user_session"].get(str(uid)):
        await event.respond("⚠️ You're already in a chat. Use /next or /stop.")
        return

    # add to queue and try match
    DATA["queue"].append({"user_id": str(uid), "filter_gender": None})
    save_data(DATA)
    await event.respond("🔎 Searching for someone... ⏳", buttons=search_keyboard())
    await try_match(uid)

@client.on(events.NewMessage(pattern="/male"))
async def cmd_male(event):
    uid = event.sender_id
    if str(uid) in TEMP and TEMP[str(uid)]["step"] == "done":
        DATA["users"][str(uid)] = TEMP[str(uid)]["profile"]
        TEMP.pop(str(uid), None)
        save_data(DATA)
    if str(uid) not in DATA["users"]:
        await event.respond("⚠️ Complete setup with /start first.")
        return
    if DATA["user_session"].get(str(uid)):
        await event.respond("⚠️ You're already in a chat.")
        return
    DATA["queue"].append({"user_id": str(uid), "filter_gender": "male"})
    save_data(DATA)
    await event.respond("🔎 Searching for male users... ⏳", buttons=search_keyboard())
    await try_match(uid)

@client.on(events.NewMessage(pattern="/female"))
async def cmd_female(event):
    uid = event.sender_id
    if str(uid) in TEMP and TEMP[str(uid)]["step"] == "done":
        DATA["users"][str(uid)] = TEMP[str(uid)]["profile"]
        TEMP.pop(str(uid), None)
        save_data(DATA)
    if str(uid) not in DATA["users"]:
        await event.respond("⚠️ Complete setup with /start first.")
        return
    if DATA["user_session"].get(str(uid)):
        await event.respond("⚠️ You're already in a chat.")
        return
    DATA["queue"].append({"user_id": str(uid), "filter_gender": "female"})
    save_data(DATA)
    await event.respond("🔎 Searching for female users... ⏳", buttons=search_keyboard())
    await try_match(uid)

@client.on(events.NewMessage(pattern="/anyone"))
async def cmd_anyone(event):
    uid = event.sender_id
    if str(uid) in TEMP and TEMP[str(uid)]["step"] == "done":
        DATA["users"][str(uid)] = TEMP[str(uid)]["profile"]
        TEMP.pop(str(uid), None)
        save_data(DATA)
    if str(uid) not in DATA["users"]:
        await event.respond("⚠️ Complete setup with /start first.")
        return
    if DATA["user_session"].get(str(uid)):
        await event.respond("⚠️ You're already in a chat.")
        return
    DATA["queue"].append({"user_id": str(uid), "filter_gender": None})
    save_data(DATA)
    await event.respond("🔎 Searching for anyone... ⏳", buttons=search_keyboard())
    await try_match(uid)

@client.on(events.NewMessage(pattern="/stop"))
async def cmd_stop(event):
    uid = event.sender_id
    s = end_session_for(uid)
    if not s:
        # if in queue, remove
        if in_queue(uid):
            remove_from_queue(uid)
            await event.respond("You left the search queue.")
            return
        await event.respond("You were not in a chat or in queue.")
        return
    other = int(s["b"]) if s["a"] == str(uid) else int(s["a"])
    try:
        await client.send_message(other, "⛔ The other user left the chat.", buttons=search_keyboard())
    except Exception:
        pass
    await event.respond("⛔ Chat ended.", buttons=search_keyboard())

@client.on(events.NewMessage(pattern="/next"))
async def cmd_next(event):
    uid = event.sender_id
    s = end_session_for(uid)
    if s:
        other = int(s["b"]) if s["a"] == str(uid) else int(s["a"])
        try:
            await client.send_message(other, "➡️ The other user moved to the next. Chat ended.", buttons=search_keyboard())
        except Exception:
            pass
    remove_from_queue(uid)
    DATA["queue"].append({"user_id": str(uid), "filter_gender": None})
    save_data(DATA)
    await event.respond("➡️ Finding next user...", buttons=search_keyboard())
    await try_match(uid)

@client.on(events.NewMessage(pattern="/edit"))
async def cmd_edit(event):
    uid = event.sender_id
    TEMP[str(uid)] = {"step": "gender", "profile": {}}
    await event.respond(
        "✏️ Edit profile — choose gender:",
        buttons=[[Button.inline("👨 Male", b"gender_male"), Button.inline("👩 Female", b"gender_female"), Button.inline("⚧ Other", b"gender_other")]]
    )

@client.on(events.NewMessage(pattern="/help"))
async def cmd_help(event):
    txt = (
        "🤖 *Commands*\n"
        "/start - Setup profile\n"
        "/find - Search anyone\n"
        "/male - Search male only\n"
        "/female - Search female only\n"
        "/anyone - Search anyone\n"
        "/next - Next partner\n"
        "/stop - Stop chat\n"
        "/edit - Edit profile\n"
        "/help - Show this help\n\n"
        "You can send text, photos, stickers, voice, video or documents while matched — they will be forwarded anonymously."
    )
    await event.respond(txt)

# Collect profile steps and also relay media/text when in session
@client.on(events.NewMessage)
async def general_handler(event):
    uid = event.sender_id
    text = (event.raw_text or "").strip()

    # If user is in TEMP setup, progress steps:
    if str(uid) in TEMP:
        state = TEMP[str(uid)]
        step = state["step"]

        if step == "age":
            state["profile"]["age"] = text or "—"
            state["step"] = "location"
            await event.respond("📍 Now tell me your location (can be anything):")
            return
        if step == "location":
            state["profile"]["location"] = text or "—"
            state["step"] = "interest"
            await event.respond("✨ Now tell me your interest (one line):")
            return
        if step == "interest":
            state["profile"]["interest"] = text or "—"
            # commit to DATA
            DATA["users"][str(uid)] = state["profile"]
            TEMP.pop(str(uid), None)
            save_data(DATA)
            await event.respond("✅ Profile saved! Use /find to search for someone.")
            return

    # If user is in a chat, forward the message/media to partner
    partner = get_partner(uid)
    if partner:
        # Use forward_messages if possible to preserve media; else send content
        try:
            await client.forward_messages(entity=partner, messages=event.message, from_peer=event.message.peer_id)
        except Exception:
            # Send message anonymously (no "forwarded from" tag)
        if event.message.media:
            try:
                await client.send_file(partner, file=event.message.media, caption=event.message.text or "")
            except Exception:
                await client.send_message(partner, event.message.text or "[Media delivery failed]")
        else:
            try:
                await client.send_message(partner, event.message.text or "")
            except Exception:
                pass
            
        return

    # if not in a chat and not in TEMP, ignore or prompt
    if not in_queue(uid):
        # do not spam the user; only suggest commands if they typed something
        if text:
            await event.respond("Not in a chat. Use /start to setup and /find to search.")
    # if in queue, optionally acknowledge
    else:
        # user is waiting
        await event.respond("🔎 Still searching... please wait or use /stop to cancel.")

# ---------- Matching algorithm ----------
async def try_match(uid: int):
    # only try if user still queued and not in session
    if DATA["user_session"].get(str(uid)):
        return
    caller_entry = None
    for e in DATA["queue"]:
        if e["user_id"] == str(uid):
            caller_entry = e
            break
    if not caller_entry:
        return

    # look for partner
    for e in list(DATA["queue"]):
        if e["user_id"] == str(uid):
            continue
        partner_profile = DATA["users"].get(e["user_id"], {})
        caller_req = caller_entry.get("filter_gender")
        partner_req = e.get("filter_gender")
        caller_profile = DATA["users"].get(str(uid), {})

        # check caller's filter
        if caller_req and partner_profile.get("gender","").lower() != caller_req.lower():
            continue
        # check partner's filter
        if partner_req and caller_profile.get("gender","").lower() != partner_req.lower():
            continue

        # match them
        a = int(uid)
        b = int(e["user_id"])
        # remove both entries
        remove_from_queue(a)
        remove_from_queue(b)
        sid = make_session(a,b)
        # notify
        try:
            await client.send_message(a, "🎉 Match found! You are now connected anonymously. Say hi! 👋", buttons=chat_buttons())
            await client.send_message(a, "––– Partner profile –––\n" + profile_text(b))
            await client.send_message(b, "🎉 Match found! You are now connected anonymously. Say hi! 👋", buttons=chat_buttons())
            await client.send_message(b, "––– Partner profile –––\n" + profile_text(a))
        except Exception:
            pass
        break

# --------- Start everything ----------
def main():
    print("Starting Flask (background) and Telethon bot (main)...")
    # start flask in background thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # start Telethon loop (main thread)
    client.run_until_disconnected()

if __name__ == "__main__":
    if not BOT_TOKEN or not API_ID or not API_HASH:
        raise SystemExit("Please set BOT_TOKEN, API_ID and API_HASH environment variables.")
    main()
        
