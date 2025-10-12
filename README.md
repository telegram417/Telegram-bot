# AnonChatPlush — Telegram anonymous chat bot

Lightweight anonymous chat bot (profile + matching), built with python-telegram-bot and Flask.
Designed to run on Render (free web service).

## Files
- `main.py` — launcher (starts Flask + Telegram bot in child process)
- `requirements.txt` — dependencies
- `Procfile` — instructs Render to run Gunicorn

## Commands
- `/start` — Setup profile (gender → age → location → interest)
- `/profile` — View & edit profile
- `/edit` — Edit profile
- `/find [gender]` — Find a partner (optional: `male`, `female`, `other`)
- `/stop` — Leave chat (partner is notified)
- `/next` — Skip and find another
- `/help` — List commands

## Deploy (Render)
1. Push this repo to GitHub.
2. Create a **Web Service** pointing to this repo/branch.
3. Set environment variable: `BOT_TOKEN` = (your @BotFather token).
4. Deploy. Render will run Gunicorn (see `Procfile`).
5. Optionally add an Uptime monitor (UptimeRobot) to ping `https://<your-app>.onrender.com/` every 5 minutes to keep it awake.

## Notes
- Data is stored in-memory (lightweight). Restarting the service clears stored profiles.
- `--workers 1` is required to avoid Telegram `Conflict` errors.
- 
