# AnonChatPlush

AnonChatPlush is an elegant anonymous matchmaking Telegram bot (memory-only).

## Deploy
1. Create a new **Worker** (not web service) on Render or similar.
2. Set environment variables:
   - `BOT_TOKEN` = your bot token (from @BotFather)
   - `BOT_USERNAME` = (optional) e.g. MeetAnonymousBOT
3. Add files: `main.py`, `requirements.txt`, `Procfile`.
4. Start the worker (Render will run `python main.py`).
5. Keep the worker alive with UptimeRobot if needed.

## Notes
- Data is stored only in memory and resets on restart.
- Referral link: https://t.me/<BOT_USERNAME>?start=ref<your_id>
