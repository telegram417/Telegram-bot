import os
import asyncio
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
)

TOKEN = os.getenv("BOT_TOKEN")  # Set in Render Environment Variables
PORT = int(os.getenv("PORT", 10000))

app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Bot is running on Render!"

# ---------------- BOT HANDLERS ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hello! I'm your anonymous chat bot!\nUse /help to see all commands."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📜 *Available Commands:*\n"
        "/start - Start the bot\n"
        "/help - Show this message\n"
        "/search - Find a chat partner\n"
        "/stop - Stop current chat\n"
        "/feedback - Send feedback\n"
        "/report - Report a user\n"
        "/about - Learn about this bot\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *About this Bot:*\n"
        "This is an anonymous chat bot made with ❤️ for fun and connection!\n"
        "Built with Python and hosted on Render.",
        parse_mode="Markdown"
    )

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Searching for a chat partner... (Demo mode)")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Chat stopped. Type /search to find a new partner.")

async def feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💬 Please type your feedback — I’ll forward it to admin!")

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⚠️ Please describe the issue — I’ll send it to admin.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    await update.message.reply_text(f"You said: {text}")

# ---------------- BOT LAUNCHER ----------------

async def run_bot():
    app_builder = ApplicationBuilder().token(TOKEN).build()

    app_builder.add_handler(CommandHandler("start", start))
    app_builder.add_handler(CommandHandler("help", help_command))
    app_builder.add_handler(CommandHandler("about", about))
    app_builder.add_handler(CommandHandler("search", search))
    app_builder.add_handler(CommandHandler("stop", stop))
    app_builder.add_handler(CommandHandler("feedback", feedback))
    app_builder.add_handler(CommandHandler("report", report))
    app_builder.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🚀 Bot connected to Telegram successfully.")
    await app_builder.run_polling()

# ---------------- RUN FLASK + BOT ----------------

if __name__ == "__main__":
    loop = asyncio.get_event_loop()

    # Start Telegram bot in background
    loop.create_task(run_bot())

    # Start Flask server
    app.run(host="0.0.0.0", port=PORT)
    
