# AnonChatPlush — Anonymous Telegram Chat Bot

## What it is
AnonChatPlush is an anonymous matching Telegram bot (in-memory profiles).  
Commands: `/start`, `/profile`, `/edit`, `/find [gender]`, `/next`, `/stop`, `/help`.

## Files
- `main.py` — Flask + Telegram bot launcher
- `requirements.txt` — dependencies
- `Procfile` — tells Render to run Gunicorn

## Deploy on Render
1. Create a new Web Service on Render and connect the repo.
2. Add environment variable:
   - `BOT_TOKEN` = `<your bot token from BotFather>`
3. Deploy. Render will install packages and run Gunicorn.
4. Optionally set up UptimeRobot to ping `https://<your-app>.onrender.com/` every 5 minutes to reduce sleep.

## Notes
- Data is stored in-memory only (no persistent DB).
- `--workers 1` in Procfile is required to prevent multiple bot instances.
- If you want persistence (JSON or Firebase), I can add that later.
- 
