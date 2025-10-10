# AnonChatPlush — Elegant & Minimal Anonymous Chat Bot

## What
AnonChatPlush is an elegant, anonymous Telegram chat bot that matches users for 1:1 anonymous chats.
Memory-only (no DB). Referral & premium features are in-memory and reset on restart.

## Features
- /start — create or edit profile (gender, age, location, interest)
- /find [gender] [min-max] [interest] — find partner with optional filters
- /stop — end chat
- /next — skip and find another
- /edit — edit profile step-by-step
- /ref — referral link (3 invites => 3 days premium in memory)
- /help — show commands
- Supports text, photos, videos, voice, stickers via copy_message

## Deploy on Render (recommended)
1. Create a new **Worker** on Render.
2. Add Environment Variable:
   - `BOT_TOKEN` = your Telegram bot token (from @BotFather)
   - `BOT_USERNAME` = (optional) your bot username (e.g. MeetAnonymousBOT)
3. Add files: `main.py`, `requirements.txt`, `Procfile`, `README.md`.
4. Deploy. Render will run `python main.py` as worker.
5. To keep the worker alive, optionally use UptimeRobot (ping any HTTP endpoint you host elsewhere) — polling works even if idle, but Render may stop inactive free workers.

## Notes
- Data is stored only in memory. Restart clears profiles/invites/premium statuses.
- Referral link format: `https://t.me/<BOT_USERNAME>?start=ref<your_user_id>`
- Premium is granted for REF_REQUIRED invites (default 3) and lasts REF_DAYS days (default 3).

## Customize
Edit `main.py` constants:
- `REF_REQUIRED` and `REF_DAYS`.
- `BOT_USERNAME` if you want referral links generated.

## Troubleshooting
- Make sure `BOT_TOKEN` is set correctly in env vars.
- If you see errors on startup, check logs — most issues are due to missing env vars or port conflicts.

Enjoy — and if you want persistent storage later, we can add a simple `users.json` persistence or Firebase.
