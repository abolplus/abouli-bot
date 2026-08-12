import asyncio
import os
import random
import sqlite3
import time
from contextlib import closing
from decimal import Decimal, InvalidOperation

from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.dispatcher.middlewares.base import BaseMiddleware

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 1873527787
CHANNEL_USERNAME = "@abolsniper"
CHANNEL_URL = "https://t.me/abolsniper"
DB = "abouli.db"

CAP = Decimal("30000")
RATE = {
    1: Decimal(".1"), 2: Decimal(".2"), 3: Decimal(".5"), 4: Decimal("1"),
    5: Decimal("1.5"), 6: Decimal("2"), 7: Decimal("3"), 8: Decimal("4"),
    9: Decimal("5"), 10: Decimal("6"),
}
ABOULI_REWARD = {1: 1, 2: 2, 3: 3, 4: 5, 5: 7, 6: 10, 7: 13, 8: 17, 9: 22, 10: 30}
ABOULI_COST = {1: 100, 2: 200, 3: 400, 4: 500, 5: 600, 6: 700, 7: 800, 8: 900, 9: 1000, 10: 1100}
SPOON_COST = {2: 100, 3: 250, 4: 500, 5: 800, 6: 1200, 7: 1800, 8: 2500, 9: 3500, 10: 5000}
FOODS = [("لوبیا", .4, 1), ("قورمه‌سبزی", .3, 2), ("کباب", .2, 3), ("جوجه", .1, 4)]

PROFILE_ALIASES = {"پروف ابولی", "پروفایل ابولی", "پروفای ابولی", "پروف ابولی ری"}

# user_id -> {kind, chat_id, message_id, amount?}
PENDING_BANK = {}

dp = Dispatcher()


def d(value):
    return Decimal(str(value))


def fmt_num(value):
    n = d(value)
    if n == n.to_integral():
        return f"{int(n):,}"
    return f"{n:.8f}".rstrip("0").rstrip(".")


def fmt_time(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def q(sql, args=(), one=False):
    with closing(sqlite3.connect(DB)) as conn:
        result = conn.execute(sql, args).fetchone() if one else conn.execute(sql, args).fetchall()
        conn.commit()
        return result


def init():
    with closing(sqlite3.connect(DB)) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users(
                user_id INTEGER PRIMARY KEY,
                name TEXT,
                ap TEXT DEFAULT '0',
                mined TEXT DEFAULT '0',
                level INTEGER DEFAULT 1,
                spoon INTEGER DEFAULT 1,
                hunger INTEGER DEFAULT 0,
                last_mine REAL,
                last_food REAL DEFAULT 0,
                last_aboul REAL DEFAULT 0,
                bank TEXT DEFAULT '0',
                account TEXT UNIQUE,
                created REAL
            );
            CREATE TABLE IF NOT EXISTS tx(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                kind TEXT,
                amount TEXT,
                note TEXT,
                ts REAL
            );
            """
        )
        # Existing databases from the old version start at 10 hunger.
        conn.execute("UPDATE users SET hunger=0 WHERE hunger IS NULL")
        conn.commit()


def user(uid, name=""):
    row = q("SELECT * FROM users WHERE user_id=?", (uid,), True)
    if row:
        if name and row[1] != name:
            q("UPDATE users SET name=? WHERE user_id=?", (name, uid))
            row = q("SELECT * FROM users WHERE user_id=?", (uid,), True)
        return row

    while True:
        account = str(random.randint(1000000000, 9999999999))
        if not q("SELECT 1 FROM users WHERE account=?", (account,), True):
            break

    now = time.time()
    q(
        "INSERT INTO users(user_id,name,account,created,last_mine,hunger) VALUES(?,?,?,?,?,0)",
        (uid, name or str(uid), account, now, now),
    )
    return q("SELECT * FROM users WHERE user_id=?", (uid,), True)


def cd(spoon):
    return (60 - (spoon - 1) * 5) * 60


def mine(uid):
    row = user(uid)
    now = time.time()
    hunger = int(row[6])
    elapsed = max(0, now - float(row[7] or now))

    # Hunger naturally drops while time passes.
    loss = int(elapsed / 3600 * 2)
    new_hunger = max(0, hunger - loss)

    mined = d(row[3])
    if hunger > 0 and mined < CAP:
        mined = min(CAP, mined + RATE[int(row[4])] * d(elapsed))

    q(
        "UPDATE users SET mined=?,hunger=?,last_mine=? WHERE user_id=?",
        (str(mined), new_hunger, now, uid),
    )
    return user(uid)


def join_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 عضویت در کانال", url=CHANNEL_URL)]
        ]
    )


async def is_member(bot: Bot, uid: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_USERNAME, uid)
        if member.status in {"creator", "administrator", "member"}:
            return True
        if member.status == "restricted":
            return bool(getattr(member, "is_member", False))
    except Exception:
        return False
    return False


async def require_membership(message: Message) -> bool:
    if await is_member(message.bot, message.from_user.id):
        return True
    await message.answer("برای بازی کردن در کانال عضو شوید", reply_markup=join_keyboard())
    return False


class MembershipMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if isinstance(event, Message):
            # /start is allowed to show the join prompt.
            if not (isinstance(event.text, str) and event.text.startswith("/start")):
                if not await require_membership(event):
                    return
        return await handler(event, data)


dp.message.outer_middleware(MembershipMiddleware())


def profile_keyboard(uid):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬆️ ارتقای ابولی", callback_data=f"p:{uid}:upab"),
                InlineKeyboardButton(text="🥄 ارتقای قاشق", callback_data=f"p:{uid}:upsp"),
            ],
            [InlineKeyboardButton(text="💰 برداشت پوینت‌های ماین‌شده", callback_data=f"p:{uid}:claim")],
        ]
    )


def abouli_upgrade_keyboard(uid):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬆️ ارتقای ابولی", callback_data=f"p:{uid}:buyab")],
            [InlineKeyboardButton(text="🔙 پروف ابولی", callback_data=f"p:{uid}:profile")],
        ]
    )


def spoon_upgrade_keyboard(uid):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬆️ ارتقای قاشق", callback_data=f"p:{uid}:buysp")],
            [InlineKeyboardButton(text="🔙 پروف ابولی", callback_data=f"p:{uid}:profile")],
        ]
    )


def bank_keyboard(uid):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💰 واریز", callback_data=f"p:{uid}:deposit"),
                InlineKeyboardButton(text="💸 برداشت", callback_data=f"p:{uid}:withdraw"),
            ],
            [InlineKeyboardButton(text="🔁 انتقال", callback_data=f"p:{uid}:transfer")],
        ]
    )


def confirm_keyboard(uid):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ بله", callback_data=f"p:{uid}:yes"),
                InlineKeyboardButton(text="❌ نه", callback_data=f"p:{uid}:no"),
            ]
        ]
    )


def bank_text(uid):
    row = user(uid)
    return (
        "🏦 بانک ابولی 🏦\n\n"
        f"💳 شماره حساب : {row[11]}\n"
        f"👤 به نام : {row[1]}\n\n"
        f"💰 موجودی بانک : {fmt_num(row[10])} ابولی"
    )


def profile_text(uid):
    row = mine(uid)
    mined = d(row[3])
    status = "⛏️ فعال" if int(row[6]) > 0 and mined < CAP else "⛔ متوقف"
    return (
        "🐮 پروف ابولی\n\n"
        f"👤 {row[1]}\n"
        f"⭐️ سطح ابولی : {row[4]}/10\n"
        f"🥄 سطح قاشق : {row[5]}/10\n"
        f"🥣 شکم : {row[6]}/10\n\n"
        f"{status}\n"
        f"⚡ سرعت ماین : {fmt_num(RATE[int(row[4])])} ابولی/s\n"
        f"🪙 ماین‌شده : {fmt_num(mined)}\n"
        f"💰 موجودی ابولی : {fmt_num(row[2])}\n"
        f"🎁 پاداش هر ابول : {fmt_num(ABOULI_REWARD[int(row[4])])}"
    )


@dp.message(CommandStart())
async def start(message: Message):
    user(message.from_user.id, message.from_user.full_name)
    if not await is_member(message.bot, message.from_user.id):
        await message.answer("برای بازی کردن در کانال عضو شوید", reply_markup=join_keyboard())
        return
    await message.answer("🐮 به ابولی خوش اومدی!\n\nابول\nپروف ابولی\nغذا\nارتقای قاشق\nبانک ابولی")


@dp.message(F.text == "ابول")
async def aboul(message: Message):
    row = user(message.from_user.id, message.from_user.full_name)
    left = 300 - (time.time() - float(row[9] or 0))
    if left > 0:
        await message.answer(f"⏳ بعد از {fmt_time(left)} می‌تونی دوباره ابول بگیری.")
        return

    level = int(row[4])
    reward = ABOULI_REWARD[level]
    now = time.time()
    new_balance = d(row[2]) + d(reward)
    q("UPDATE users SET ap=?,last_aboul=? WHERE user_id=?", (str(new_balance), now, message.from_user.id))
    q(
        "INSERT INTO tx(user_id,kind,amount,note,ts) VALUES(?,?,?,?,?)",
        (message.from_user.id, "aboul", str(reward), "دستور ابول", now),
    )
    await message.answer(
        f"🐮 شما یک ابول گرفتید!\n\n"
        f"⭐️ سطح ابولی : {level}/10\n"
        f"🪙 مقدار دریافت‌شده : {fmt_num(reward)} ابولی\n"
        f"💰 ابولی‌هات : {fmt_num(new_balance)}\n"
        f"⏳ بعد از 5 دقیقه می‌تونی دوباره ابول بگیری"
    )


@dp.message(F.text.in_(PROFILE_ALIASES))
async def profile(message: Message):
    await message.answer(profile_text(message.from_user.id), reply_markup=profile_keyboard(message.from_user.id))


@dp.message(F.text == "غذا")
async def food(message: Message):
    mine(message.from_user.id)
    row = user(message.from_user.id, message.from_user.full_name)
    left = cd(row[5]) - (time.time() - float(row[8] or 0))
    if left > 0:
        await message.answer(f"🍽️ بعد از {fmt_time(left)} می‌تونی دوباره غذا بدی.")
        return

    food_name, _, amount = random.choices(FOODS, weights=[x[1] for x in FOODS])[0]
    new_hunger = min(10, int(row[6]) + amount)
    now = time.time()
    q("UPDATE users SET hunger=?,last_food=? WHERE user_id=?", (new_hunger, now, message.from_user.id))
    await message.answer(
        f"🍖 ابولی غذا گرفت!\n\n"
        f"🍽️ غذا : {food_name}\n"
        f"❤️ سیری : +{amount}\n"
        f"🥣 شکم : {row[6]}/10 → {new_hunger}/10"
    )


@dp.message(F.text == "ارتقای قاشق")
async def spoon_upgrade(message: Message):
    row = user(message.from_user.id, message.from_user.full_name)
    level = int(row[5])
    if level >= 10:
        await message.answer("🥄 قاشق ابولی به حداکثر سطح ۱۰ رسیده.")
        return
    nxt = level + 1
    await message.answer(
        f"🥄 ارتقای قاشق\n\nسطح فعلی : {level}/10\nسطح بعدی : {nxt}/10\n"
        f"💰 هزینه : {fmt_num(SPOON_COST[nxt])} ابولی",
        reply_markup=spoon_upgrade_keyboard(message.from_user.id),
    )


@dp.message(F.text.startswith("ارتقای قاشق "))
async def spoon_buy_text(message: Message):
    row = user(message.from_user.id, message.from_user.full_name)
    parts = message.text.split()
    if len(parts) != 3 or not parts[2].isdigit():
        await message.answer("فرمت: ارتقای قاشق 2")
        return
    nxt = int(parts[2])
    if nxt != int(row[5]) + 1 or nxt > 10:
        await message.answer("❌ فقط لول بعدی مجاز است.")
        return
    cost = d(SPOON_COST[nxt])
    if d(row[2]) < cost:
        await message.answer("❌ موجودی کافی نیست.")
        return
    q("UPDATE users SET ap=?,spoon=? WHERE user_id=?", (str(d(row[2]) - cost), nxt, message.from_user.id))
    await message.answer(f"🎉 قاشق به سطح {nxt} ارتقا پیدا کرد!")


@dp.message(F.text == "بانک ابولی")
async def bank(message: Message):
    await message.answer(bank_text(message.from_user.id), reply_markup=bank_keyboard(message.from_user.id))


@dp.message(F.text.startswith("انتقال "))
async def transfer(message: Message):
    parts = message.text.split()
    if len(parts) != 3 or not parts[1].isdigit():
        await message.answer("فرمت: انتقال [شماره حساب] [مقدار]")
        return
    try:
        amount = d(parts[2])
    except InvalidOperation:
        await message.answer("❌ مقدار نامعتبر.")
        return
    if amount <= 0:
        await message.answer("❌ مقدار نامعتبر.")
        return
    sender = user(message.from_user.id, message.from_user.full_name)
    receiver = q("SELECT * FROM users WHERE account=?", (parts[1],), True)
    if not receiver:
        await message.answer("❌ شماره حساب پیدا نشد.")
        return
    if d(sender[10]) < amount:
        await message.answer("❌ موجودی بانک کافی نیست.")
        return
    q("UPDATE users SET bank=? WHERE user_id=?", (str(d(sender[10]) - amount), sender[0]))
    q("UPDATE users SET bank=? WHERE user_id=?", (str(d(receiver[10]) + amount), receiver[0]))
    await message.answer(f"✅ {fmt_num(amount)} ابولی به حساب {parts[1]} منتقل شد.")


@dp.message(F.text == "تراکنش‌ها")
async def transactions(message: Message):
    rows = q("SELECT kind,amount,note FROM tx WHERE user_id=? ORDER BY id DESC LIMIT 10", (message.from_user.id,))
    body = "\n".join(f"• {kind}: {fmt_num(amount)} ابولی — {note}" for kind, amount, note in rows) if rows else "تراکنشی نیست."
    await message.answer("🧾 تراکنش‌ها\n\n" + body)


async def begin_bank_amount(callback: CallbackQuery, kind: str):
    uid = callback.from_user.id
    PENDING_BANK[uid] = {
        "kind": kind,
        "chat_id": callback.message.chat.id,
        "message_id": callback.message.message_id,
    }
    title = "واریز" if kind == "deposit" else "برداشت"
    row = user(uid)
    await callback.message.edit_text(
        f"🏦 بانک ابولی 🏦\n\n"
        f"💳 شماره حساب : {row[11]}\n"
        f"👤 به نام : {row[1]}\n\n"
        f"🔢 چقدر می‌خوای {title} کنی؟\n"
        f"عدد موردنظر رو بفرست.",
    )
    await callback.answer()


@dp.message(F.text.regexp(r"^\s*\d+(?:[.,]\d+)?\s*$"))
async def bank_amount(message: Message):
    pending = PENDING_BANK.get(message.from_user.id)
    if not pending:
        return
    try:
        amount = d(message.text.strip().replace(",", "."))
    except InvalidOperation:
        return
    if amount <= 0:
        return

    pending["amount"] = amount
    row = user(message.from_user.id, message.from_user.full_name)
    title = "واریز" if pending["kind"] == "deposit" else "برداشت"
    text = (
        "🏦 بانک ابولی 🏦\n\n"
        f"💳 شماره حساب : {row[11]}\n"
        f"👤 به نام : {row[1]}\n\n"
        f"❓ آیا از {title} {fmt_num(amount)} ابولی به حساب بانکی خود اطمینان دارید ؟"
    )
    try:
        await message.bot.edit_message_text(
            chat_id=pending["chat_id"],
            message_id=pending["message_id"],
            text=text,
            reply_markup=confirm_keyboard(message.from_user.id),
        )
    except Exception:
        PENDING_BANK.pop(message.from_user.id, None)


async def finish_bank(callback: CallbackQuery, confirmed: bool):
    uid = callback.from_user.id
    pending = PENDING_BANK.get(uid)
    if not pending or "amount" not in pending:
        await callback.answer("این درخواست منقضی شده.", show_alert=True)
        return

    if not confirmed:
        PENDING_BANK.pop(uid, None)
        await callback.message.edit_text(bank_text(uid), reply_markup=bank_keyboard(uid))
        await callback.answer()
        return

    amount = d(pending["amount"])
    row = user(uid, callback.from_user.full_name)

    if pending["kind"] == "deposit":
        if d(row[2]) < amount:
            text = (
                "🏦 بانک ابولی 🏦\n\n"
                "❌ موجودی ابولی کافی نیست.\n"
                f"💰 موجودی : {fmt_num(row[2])}\n"
                f"💳 مبلغ درخواستی : {fmt_num(amount)}"
            )
            await callback.message.edit_text(text, reply_markup=bank_keyboard(uid))
            PENDING_BANK.pop(uid, None)
            await callback.answer()
            return
        q(
            "UPDATE users SET ap=?,bank=? WHERE user_id=?",
            (str(d(row[2]) - amount), str(d(row[10]) + amount), uid),
        )
        note = "واریز به بانک"
    else:
        if d(row[10]) < amount:
            text = (
                "🏦 بانک ابولی 🏦\n\n"
                "❌ موجودی بانک کافی نیست.\n"
                f"🏦 موجودی بانک : {fmt_num(row[10])}\n"
                f"💳 مبلغ درخواستی : {fmt_num(amount)}"
            )
            await callback.message.edit_text(text, reply_markup=bank_keyboard(uid))
            PENDING_BANK.pop(uid, None)
            await callback.answer()
            return
        q(
            "UPDATE users SET ap=?,bank=? WHERE user_id=?",
            (str(d(row[2]) + amount), str(d(row[10]) - amount), uid),
        )
        note = "برداشت از بانک"

    q(
        "INSERT INTO tx(user_id,kind,amount,note,ts) VALUES(?,?,?,?,?)",
        (uid, pending["kind"], str(amount), note, time.time()),
    )
    PENDING_BANK.pop(uid, None)
    await callback.message.edit_text(bank_text(uid), reply_markup=bank_keyboard(uid))
    await callback.answer("انجام شد ✅")


async def callback_owner(callback: CallbackQuery):
    parts = (callback.data or "").split(":")
    if len(parts) != 3 or parts[0] != "p":
        await callback.answer("دکمه نامعتبر است.", show_alert=True)
        return None
    try:
        owner_id = int(parts[1])
    except ValueError:
        await callback.answer("دکمه نامعتبر است.", show_alert=True)
        return None
    if owner_id != callback.from_user.id:
        await callback.answer("❌ این دکمه برای شما نیست.", show_alert=True)
        return None
    if not await is_member(callback.bot, callback.from_user.id):
        await callback.answer("🔒 ابتدا در کانال عضو شوید.", show_alert=True)
        return None
    return parts[2]


@dp.callback_query(F.data.startswith("p:"))
async def callbacks(callback: CallbackQuery):
    action = await callback_owner(callback)
    if action is None:
        return
    uid = callback.from_user.id

    if action == "profile":
        await callback.message.edit_text(profile_text(uid), reply_markup=profile_keyboard(uid))
        await callback.answer()
        return

    if action == "upab":
        row = user(uid)
        level = int(row[4])
        if level >= 10:
            text = "⭐️ ابولی به حداکثر سطح ۱۰ رسیده."
        else:
            nxt = level + 1
            text = (
                "⭐️ ارتقای ابولی\n\n"
                f"سطح فعلی : {level}/10\n"
                f"سطح بعدی : {nxt}/10\n"
                f"💰 هزینه : {fmt_num(ABOULI_COST[nxt])} ابولی\n"
                f"🎁 پاداش فعلی : {fmt_num(ABOULI_REWARD[level])}\n"
                f"🎁 پاداش بعدی : {fmt_num(ABOULI_REWARD[nxt])}"
            )
        await callback.message.edit_text(text, reply_markup=abouli_upgrade_keyboard(uid))
        await callback.answer()
        return

    if action == "buyab":
        row = user(uid)
        level = int(row[4])
        if level >= 10:
            text = "⭐️ ابولی از قبل در بالاترین سطحه."
        else:
            nxt = level + 1
            cost = d(ABOULI_COST[nxt])
            balance = d(row[2])
            if balance < cost:
                text = (
                    "❌ ابولی پوینت کافی نداری.\n\n"
                    f"💰 موجودی : {fmt_num(balance)}\n"
                    f"💳 هزینه : {fmt_num(cost)}\n"
                    f"📉 کمبود : {fmt_num(cost - balance)}"
                )
            else:
                q("UPDATE users SET ap=?,level=? WHERE user_id=?", (str(balance - cost), nxt, uid))
                text = (
                    f"🎉 ابولی به سطح {nxt} ارتقا پیدا کرد!\n\n"
                    f"💰 هزینه : {fmt_num(cost)} ابولی\n"
                    f"🎁 پاداش هر ابول : {fmt_num(ABOULI_REWARD[nxt])}\n"
                    f"⚡ سرعت ماین : {fmt_num(RATE[nxt])} ابولی/s"
                )
        await callback.message.edit_text(text, reply_markup=abouli_upgrade_keyboard(uid))
        await callback.answer()
        return

    if action == "upsp":
        row = user(uid)
        level = int(row[5])
        if level >= 10:
            text = "🥄 قاشق ابولی به حداکثر سطح ۱۰ رسیده."
        else:
            nxt = level + 1
            text = (
                "🥄 ارتقای قاشق\n\n"
                f"سطح فعلی : {level}/10\n"
                f"سطح بعدی : {nxt}/10\n"
                f"💰 هزینه : {fmt_num(SPOON_COST[nxt])} ابولی"
            )
        await callback.message.edit_text(text, reply_markup=spoon_upgrade_keyboard(uid))
        await callback.answer()
        return

    if action == "buysp":
        row = user(uid)
        level = int(row[5])
        if level >= 10:
            text = "🥄 قاشق ابولی از قبل در بالاترین سطحه."
        else:
            nxt = level + 1
            cost = d(SPOON_COST[nxt])
            balance = d(row[2])
            if balance < cost:
                text = (
                    "❌ ابولی پوینت کافی نداری.\n\n"
                    f"💰 موجودی : {fmt_num(balance)}\n"
                    f"💳 هزینه : {fmt_num(cost)}\n"
                    f"📉 کمبود : {fmt_num(cost - balance)}"
                )
            else:
                q("UPDATE users SET ap=?,spoon=? WHERE user_id=?", (str(balance - cost), nxt, uid))
                text = f"🎉 قاشق به سطح {nxt} ارتقا پیدا کرد!"
        await callback.message.edit_text(text, reply_markup=spoon_upgrade_keyboard(uid))
        await callback.answer()
        return

    if action == "claim":
        row = mine(uid)
        mined = d(row[3])
        if mined <= 0:
            text = "⛏️ فعلاً پوینت ماین‌شده‌ای برای برداشت نداری.\n\n🪙 ماین‌شده : 0"
        else:
            new_balance = d(row[2]) + mined
            q("UPDATE users SET ap=?,mined='0',last_mine=? WHERE user_id=?", (str(new_balance), time.time(), uid))
            text = (
                f"✅ {fmt_num(mined)} ابولی ماین‌شده به موجودی منتقل شد.\n\n"
                "🪙 ماین‌شده : 0"
            )
        await callback.message.edit_text(text, reply_markup=profile_keyboard(uid))
        await callback.answer()
        return

    if action == "deposit":
        await begin_bank_amount(callback, "deposit")
        return
    if action == "withdraw":
        await begin_bank_amount(callback, "withdraw")
        return
    if action == "transfer":
        await callback.answer("برای انتقال، دستور انتقال را با شماره حساب و مقدار بفرستید.", show_alert=True)
        return
    if action == "yes":
        await finish_bank(callback, True)
        return
    if action == "no":
        await finish_bank(callback, False)
        return

    await callback.answer("دکمه نامعتبر است.", show_alert=True)


async def admin_reply_points(message: Message, increase: bool):
    if message.from_user.id != ADMIN_ID:
        return
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.answer("❌ باید روی پیام کاربر ریپلای کنی.")
        return

    parts = message.text.split()
    if len(parts) != 4:
        await message.answer(
            "فرمت:\n"
            "افزایش ابول پوینت [مقدار]\n"
            "کاهش ابول پوینت [مقدار]"
        )
        return

    try:
        amount = d(parts[3])
    except InvalidOperation:
        await message.answer("❌ مقدار نامعتبر.")
        return
    if amount <= 0:
        await message.answer("❌ مقدار باید بیشتر از صفر باشد.")
        return

    target = message.reply_to_message.from_user
    row = user(target.id, target.full_name)
    balance = d(row[2])

    if not increase and balance < amount:
        await message.answer(f"❌ موجودی ابولی کاربر کافی نیست. موجودی: {fmt_num(balance)}")
        return

    new_balance = balance + amount if increase else balance - amount
    q("UPDATE users SET ap=? WHERE user_id=?", (str(new_balance), target.id))
    await message.answer(
        f"✅ {fmt_num(amount)} ابولی {'اضافه شد' if increase else 'کم شد'}.\n"
        f"💰 موجودی جدید: {fmt_num(new_balance)}"
    )


@dp.message(F.text.startswith("افزایش ابول پوینت "))
async def admin_add_reply(message: Message):
    await admin_reply_points(message, True)


@dp.message(F.text.startswith("کاهش ابول پوینت "))
async def admin_remove_reply(message: Message):
    await admin_reply_points(message, False)


@dp.message(F.text.startswith("حذف پوینت "))
async def remove_old(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) != 3 or not parts[1].isdigit():
        await message.answer("فرمت: حذف پوینت [ID] [مقدار]")
        return
    try:
        amount = d(parts[2])
    except InvalidOperation:
        await message.answer("❌ مقدار نامعتبر.")
        return
    row = user(int(parts[1]))
    if amount <= 0 or d(row[2]) < amount:
        await message.answer("❌ مقدار نامعتبر یا موجودی ناکافی.")
        return
    q("UPDATE users SET ap=? WHERE user_id=?", (str(d(row[2]) - amount), row[0]))
    await message.answer(f"✅ {fmt_num(amount)} ابولی حذف شد.")


@dp.message(F.text.startswith("اضافه پوینت "))
async def add_old(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) != 3 or not parts[1].isdigit():
        await message.answer("فرمت: اضافه پوینت [ID] [مقدار]")
        return
    try:
        amount = d(parts[2])
    except InvalidOperation:
        await message.answer("❌ مقدار نامعتبر.")
        return
    if amount <= 0:
        await message.answer("❌ مقدار نامعتبر.")
        return
    row = user(int(parts[1]))
    new_balance = d(row[2]) + amount
    q("UPDATE users SET ap=? WHERE user_id=?", (str(new_balance), row[0]))
    await message.answer(f"✅ {fmt_num(amount)} ابولی اضافه شد.")


async def interest():
    done = None
    while True:
        local = time.localtime()
        key = time.strftime("%Y-%m-%d", local)
        if local.tm_hour == 7 and local.tm_min == 0 and done != key:
            for uid, bank_balance in q("SELECT user_id,bank FROM users WHERE CAST(bank AS REAL)>0"):
                current = d(bank_balance)
                q("UPDATE users SET bank=? WHERE user_id=?", (str(current + current * d(".03")), uid))
            done = key
        await asyncio.sleep(20)


async def health(request):
    return web.Response(text="OK")


async def run_web_server():
    port = int(os.getenv("PORT", "10000"))
    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()


async def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN is required")
    init()
    asyncio.create_task(interest())
    bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    await run_web_server()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
