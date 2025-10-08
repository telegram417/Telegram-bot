
MeetAnonymousBOT - Anonymous Dating Telegram Bot

Features:
- /start - set gender and age (age shown to premium only)
- /find - find a partner (premium users match faster and see partner info)
- /stop - end chat
- /help - list commands
- /refer - give referral link; 5 invites -> 7 days premium
- Sticker & photo forwarding for premium users only
- Admin @tandoori123 has permanent premium

Deployment (Render.com):
1. Create a new service on Render. Choose a Worker/Background option or a Web service but ensure it does not require a bound port.
2. Add environment variable BOT_TOKEN with your Telegram token.
3. Build command: pip install -r requirements.txt
4. Start command: python main.py

Security:
- Do NOT put your BOT TOKEN in code or in GitHub. Use environment variables.

