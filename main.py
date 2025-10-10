import os
import logging
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN is missing from environment variables!")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Hello! I'm AnonChatPlush — ready to connect you!")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *AnonChatPlush Commands:*\n"
        "/start - Begin\n"
        "/find - Find a chat partner\n"
        "/stop - Stop chatting\n"
        "/ref - Invite & earn Premium\n"
        "/edit - Edit profile\n"
        "/help - Show this help message",
        parse_mode="Markdown"
    )

def main():
    logger.info("🚀 Starting bot...")

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.COMMAND, help_cmd))

    logger.info("✅ Bot started successfully and polling.")
    app.run_polling(close_loop=False)  # 🔥 key fix here

if __name__ == "__main__":
    main()
    
