FROM python:3.11-slim

WORKDIR /app
COPY anon_bot.py .
RUN pip install --no-cache-dir python-telegram-bot

ENV TELEGRAM_TOKEN=""
CMD ["python", "anon_bot.py"]
