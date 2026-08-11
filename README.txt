ABOULI BOT - RENDER

Render:
Build Command:
pip install -r requirements.txt

Start Command:
python bot.py

Environment Variable:
BOT_TOKEN = token from BotFather

The bot is Telegram polling based and also opens an HTTP health endpoint
on 0.0.0.0:$PORT so it can run as a Render Web Service.

IMPORTANT:
Do not put BOT_TOKEN inside bot.py or upload it to GitHub.
SQLite is fine for testing, but for a serious public bot with balances,
use persistent storage/PostgreSQL.
