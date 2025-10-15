import os
import asyncio
from flask import Flask
from telethon import TelegramClient, events, Button

# === ENVIRONMENT ===
API_ID = int(os.getenv("API_ID", "28560028"))
API_HASH = os.getenv("API_HASH", "efc9a353e1d044c3ebf0f143a7782df8")
BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.environ.get("PORT", "10000"))

# === WEB SERVER (to stay alive) ===
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Anonymous Telegram Bot is alive and running."

# === TELEGRAM CLIENT ===
bot = TelegramClient("anonbot", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# === DATA ===
users = {}        # user_id: {"step": ..., "gender": ..., "age": ..., "location": ..., "interest": ...}
waiting = {"male": set(), "female": set(), "any": set()}
active_chats = {} # user_id: partner_id


# === HELPERS ===
async def safe_send(user_id, text=None, buttons=None):
    try:
        await bot.send_message(user_id, text, buttons=buttons)
    except Exception:
        pass


# === COMMANDS ===

@bot.on(events.NewMessage(pattern="/start"))
async def start(event):
    uid = event.sender_id
    users[uid] = {"step": "gender"}
    buttons = [
        [Button.inline("👨 Male", data=b"gender_male"), Button.inline("👩 Female", data=b"gender_female")]
    ]
    await event.respond("👋 Welcome to *Anonymous Chat!*\nLet's create your profile.\n\nSelect your gender:", buttons=buttons, parse_mode="Markdown")


@bot.on(events.CallbackQuery)
async def callback(event):
    uid = event.sender_id
    data = event.data.decode()

    if data.startswith("gender_"):
        gender = data.split("_")[1]
        users[uid]["gender"] = gender
        users[uid]["step"] = "age"
        await event.edit("🎂 Please enter your age:")

    elif data == "find_male":
        waiting["male"].add(uid)
        await event.edit("🔎 Searching for a male partner...")

    elif data == "find_female":
        waiting["female"].add(uid)
        await event.edit("🔎 Searching for a female partner...")


@bot.on(events.NewMessage(pattern="/find"))
async def find(event):
    uid = event.sender_id
    user = users.get(uid)

    if not user or user.get("step") != "done":
        await event.respond("⚠️ Complete your profile first using /start.")
        return

    gender = user["gender"]
    opposite = "female" if gender == "male" else "male"
    found = None

    for g in [opposite, "any", gender]:
        if waiting[g]:
            found = waiting[g].pop()
            break

    if found:
        active_chats[uid] = found
        active_chats[found] = uid

        u1, u2 = users[uid], users[found]
        info1 = f"👤 {u1['gender'].title()}, {u1['age']}\n📍 {u1['location']}\n💫 {u1['interest']}"
        info2 = f"👤 {u2['gender'].title()}, {u2['age']}\n📍 {u2['location']}\n💫 {u2['interest']}"

        await safe_send(found, f"🎉 Match found!\n\nYour partner:\n{info1}")
        await event.respond(f"🎉 Match found!\n\nYour partner:\n{info2}")
    else:
        waiting["any"].add(uid)
        await event.respond("🔍 Searching for a partner...")


@bot.on(events.NewMessage(pattern="/stop"))
async def stop(event):
    uid = event.sender_id
    if uid not in active_chats:
        await event.respond("❗ You're not chatting with anyone.")
        return

    partner = active_chats.pop(uid)
    active_chats.pop(partner, None)

    buttons = [
        [Button.inline("🔍 Search Female", data=b"find_female")],
        [Button.inline("🔍 Search Male", data=b"find_male")]
    ]

    await safe_send(partner, "⚠️ Your partner left the chat.", buttons=buttons)
    await event.respond("✅ Chat ended.", buttons=buttons)


@bot.on(events.NewMessage(pattern="/next"))
async def next_chat(event):
    await stop(event)
    await find(event)


@bot.on(events.NewMessage(pattern="/edit"))
async def edit(event):
    uid = event.sender_id
    users[uid] = {"step": "gender"}
    buttons = [
        [Button.inline("👨 Male", data=b"gender_male"), Button.inline("👩 Female", data=b"gender_female")]
    ]
    await event.respond("✏️ Let's edit your profile.\nChoose your gender:", buttons=buttons)


@bot.on(events.NewMessage(pattern="/help"))
async def help_cmd(event):
    await event.respond(
        "📘 *Commands:*\n"
        "• /start — Create profile\n"
        "• /find — Find partner\n"
        "• /stop — End chat\n"
        "• /next — Find another\n"
        "• /edit — Edit your profile\n"
        "• /help — Show help\n\n"
        "💬 You can send text, photos, videos, stickers, voice messages safely.",
        parse_mode="Markdown"
    )


# === HANDLE USER MESSAGES ===
@bot.on(events.NewMessage)
async def message_handler(event):
    uid = event.sender_id
    if event.raw_text.startswith("/"):
        return  # ignore commands here

    user = users.get(uid, {})
    step = user.get("step")

    # Collect profile info
    if step == "age":
        user["age"] = event.raw_text
        user["step"] = "location"
        await event.respond("📍 Where are you from?")
    elif step == "location":
        user["location"] = event.raw_text
        user["step"] = "interest"
        await event.respond("💫 What are your interests?")
    elif step == "interest":
        user["interest"] = event.raw_text
        user["step"] = "done"
        await event.respond("✅ Profile complete! Use /find to start chatting.")
    else:
        if uid in active_chats:
            partner = active_chats[uid]
            try:
                # Send message anonymously (no username shown)
                if event.message.media:
                    await bot.send_file(partner, file=event.message.media, caption=event.message.text or "")
                else:
                    await bot.send_message(partner, event.message.text or "")
            except Exception:
                await event.respond("⚠️ Couldn't deliver your message.")
        else:
            await event.respond("❗ You're not in a chat. Use /find to start.")


# === RUN BOTH FLASK + TELETHON ===
async def run_all():
    loop = asyncio.get_event_loop()
    loop.create_task(bot.run_until_disconnected())
    app.run(host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    asyncio.run(run_all())
    
