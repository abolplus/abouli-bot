ABOULI BOT - RENDER

Build Command:
pip install -r requirements.txt

Start Command:
python bot.py

Environment Variable:
BOT_TOKEN = token from BotFather

The bot also opens an HTTP health endpoint on 0.0.0.0:$PORT for Render Web Service.

Important:
- Add the bot as an administrator of @abolsniper so membership checks work.
- Do not put BOT_TOKEN inside bot.py or upload it to GitHub.
- SQLite is suitable for testing; for a serious public bot with balances, use persistent storage/PostgreSQL.
