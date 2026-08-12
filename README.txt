ABOULI BOT

Render:
Build Command: pip install -r requirements.txt
Start Command: python bot.py
Environment Variable: BOT_TOKEN

Important:
1. Add the bot as an administrator in @abolsniper so membership checks work.
2. Keep BOT_TOKEN in Render Environment Variables; do not put it in bot.py.
3. The bot exposes /health on the Render PORT.

Implemented changes:
- Required membership in @abolsniper before game commands.
- Inline buttons are locked to the user who opened the menu.
- Profile aliases: پروف ابولی / پروفایل ابولی / پروفای ابولی.
- Profile no longer has Food or Bank buttons.
- Mining claim button transfers mined points to balance and resets mined points to 0.
- Profile shows only current mined amount, not a fixed cap expression.
- Initial hunger is 0/10.
- Bank deposit/withdraw uses amount entry and confirmation by editing the same bank message.
- Bank text uses "ابولی" instead of "میو پوینت".
- Admin can reply to a user's message with:
  افزایش ابول پوینت 500
  کاهش ابول پوینت 500
- Old ID-based add/remove commands remain for compatibility.
