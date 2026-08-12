import asyncio, os, random, sqlite3, time
from aiohttp import web
from decimal import Decimal
from contextlib import closing
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.client.default import DefaultBotProperties

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 1873527787
DB = "abouli.db"
CAP = Decimal("30000")
RATE = {
    1: Decimal(".1"), 2: Decimal(".2"), 3: Decimal(".5"), 4: Decimal("1"),
    5: Decimal("1.5"), 6: Decimal("2"), 7: Decimal("3"), 8: Decimal("4"),
    9: Decimal("5"), 10: Decimal("6")
}
ABOULI_REWARD = {1:1, 2:2, 3:3, 4:5, 5:7, 6:10, 7:13, 8:17, 9:22, 10:30}
ABOULI_COST = {1:100, 2:200, 3:400, 4:500, 5:700, 6:900, 7:1200, 8:1600, 9:2200, 10:3000}
SPOON_COST = {2:100, 3:250, 4:500, 5:800, 6:1200, 7:1800, 8:2500, 9:3500, 10:5000}
FOODS = [("لوبیا", .4, 1), ("قورمه‌سبزی", .3, 2), ("کباب", .2, 3), ("جوجه", .1, 4)]
dp=Dispatcher()

def init():
    with closing(sqlite3.connect(DB)) as c:
        c.executescript("""CREATE TABLE IF NOT EXISTS users(
        user_id INTEGER PRIMARY KEY,name TEXT,ap TEXT DEFAULT '0',mined TEXT DEFAULT '0',
        level INTEGER DEFAULT 1,spoon INTEGER DEFAULT 1,hunger INTEGER DEFAULT 10,
        last_mine REAL,last_food REAL DEFAULT 0,last_aboul REAL DEFAULT 0,
        bank TEXT DEFAULT '0',account TEXT UNIQUE,created REAL);
        CREATE TABLE IF NOT EXISTS tx(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,kind TEXT,amount TEXT,note TEXT,ts REAL);""")
        c.commit()

def q(sql,args=(),one=False):
    with closing(sqlite3.connect(DB)) as c:
        r=c.execute(sql,args).fetchone() if one else c.execute(sql,args).fetchall()
        c.commit(); return r

def user(uid,name=""):
    r=q("SELECT * FROM users WHERE user_id=?",(uid,),True)
    if r:return r
    while True:
        a=str(random.randint(1000000000,9999999999))
        if not q("SELECT 1 FROM users WHERE account=?",(a,),True):break
    now=time.time()
    q("INSERT INTO users(user_id,name,account,created,last_mine) VALUES(?,?,?,?,?)",(uid,name or str(uid),a,now,now))
    return q("SELECT * FROM users WHERE user_id=?",(uid,),True)

def d(x): return Decimal(str(x))
def cd(spoon): return (60-(spoon-1)*5)*60

def mine(uid):
    r=user(uid); now=time.time()
    # columns: uid,name,ap,mined,level,spoon,hunger,last_mine,last_food,last_aboul,bank,account,created
    hunger=int(r[6]); elapsed=max(0,now-float(r[7]))
    loss=int(elapsed/3600*2)
    new_h=max(0,hunger-loss)
    active=elapsed
    if new_h==0 and hunger>0: active=min(active,hunger*1800)
    mined=d(r[3])
    if hunger>0 and mined<CAP:
        mined=min(CAP,mined+RATE[int(r[4])]*d(active))
    q("UPDATE users SET mined=?,hunger=?,last_mine=? WHERE user_id=?",(str(mined),new_h,now,uid))


def fmt_num(x):
    try:
        n = Decimal(str(x))
    except Exception:
        return str(x)
    if n == n.to_integral():
        return f"{int(n):,}"
    return f"{n:.2f}".rstrip("0").rstrip(",")


def fmt_time(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def reply_kwargs(m):
    return {"reply_to_message_id": m.message_id}


def profile_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⬆️ ارتقای ابولی", callback_data="upgrade_abouli"),
            InlineKeyboardButton(text="🥄 ارتقای قاشق", callback_data="upgrade_spoon"),
        ],
        [
            InlineKeyboardButton(text="🏦 بانک ابولی", callback_data="bank"),
            InlineKeyboardButton(text="🍖 غذا", callback_data="food"),
        ],
    ])


def upgrade_abouli_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬆️ ارتقای ابولی", callback_data="buy_abouli")],
        [InlineKeyboardButton(text="🔙 پروف ابولی", callback_data="profile")],
    ])


def upgrade_spoon_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬆️ ارتقای قاشق", callback_data="buy_spoon")],
        [InlineKeyboardButton(text="🔙 پروف ابولی", callback_data="profile")],
    ])


def bank_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💰 واریز", callback_data="bank_deposit"),
            InlineKeyboardButton(text="💸 برداشت", callback_data="bank_withdraw"),
        ],
        [InlineKeyboardButton(text="🔁 انتقال", callback_data="bank_transfer")],
    ])


async def send_profile(m: Message, edit=False):
    mine(m.from_user.id)
    r = user(m.from_user.id, m.from_user.full_name)
    left = max(0, cd(r[5]) - (time.time() - float(r[8])))
    status = "⛏️ فعال" if int(r[6]) > 0 and d(r[3]) < CAP else "⛔ متوقف"

    text = (
        f"🐮 پروف ابولی\n\n"
        f"👤 {r[1]}\n"
        f"⭐ سطح ابولی: {r[4]}/10\n"
        f"🥄 سطح قاشق: {r[5]}/10\n"
        f"🍽️ شکم: {r[6]}/10\n\n"
        f"{status}\n"
        f"⚡ سرعت ماین: {fmt_num(RATE[int(r[4])])} AP/s\n"
        f"🪙 ماین‌شده: {fmt_num(r[3])} / {fmt_num(CAP)}\n"
        f"💰 ابول پوینت: {fmt_num(r[2])}\n"
        f"🎁 پاداش هر «ابول»: {fmt_num(ABOULI_REWARD[int(r[4])])}\n"
        f"⏱️ غذای بعدی: {fmt_time(left)}"
    )

    if edit:
        await m.message.edit_text(text, reply_markup=profile_kb())
    else:
        await m.answer(text, reply_markup=profile_kb(), **reply_kwargs(m))


@dp.message(CommandStart())
async def start(m: Message):
    user(m.from_user.id, m.from_user.full_name)
    await m.answer(
        "🐮 به ابولی خوش اومدی!\n\n"
        "دستورها:\n"
        "ابول\n"
        "پروف ابولی\n"
        "غذا\n"
        "بانک ابولی",
        **reply_kwargs(m)
    )


@dp.message(F.text == "ابول")
async def aboul(m: Message):
    r = user(m.from_user.id, m.from_user.full_name)
    left = 300 - (time.time() - float(r[9]))
    if left > 0:
        await m.answer(f"⏳ هنوز {fmt_time(left)} مونده تا دوباره ابول بگیری.", **reply_kwargs(m))
        return

    level = int(r[4])
    reward = ABOULI_REWARD[level]
    now = time.time()
    q("UPDATE users SET ap=CAST(ap AS REAL)+?, last_aboul=? WHERE user_id=?",
      (reward, now, m.from_user.id))
    q("INSERT INTO tx(user_id,kind,amount,note,ts) VALUES(?,?,?,?,?)",
      (m.from_user.id, "aboul", str(reward), "دستور ابول", now))

    updated = user(m.from_user.id, m.from_user.full_name)
    await m.answer(
        f"🐮 شما یک ابول گرفتید!\n\n"
        f"⭐️ سطح ابولی: {level}/10\n"
        f"🪙 پاداش: {fmt_num(reward)} ابول پوینت\n"
        f"💰 ابول پوینت هات: {fmt_num(updated[2])}\n"
        f"⏳ بعد از ۵ دقیقه میتونی دوباره ابول بگیری",
        **reply_kwargs(m)
    )


@dp.message(F.text == "پروف ابولی")
async def profile(m: Message):
    await send_profile(m)


@dp.message(F.text == "غذا")
async def food(m: Message):
    mine(m.from_user.id)
    r = user(m.from_user.id, m.from_user.full_name)
    left = cd(r[5]) - (time.time() - float(r[8]))

    if left > 0:
        await m.answer(f"🍽️ هنوز {fmt_time(left)} تا غذای بعدی مونده.", **reply_kwargs(m))
        return

    f = random.choices(FOODS, weights=[x[1] for x in FOODS])[0]
    new = min(10, int(r[6]) + f[2])
    now = time.time()
    q("UPDATE users SET hunger=?,last_food=? WHERE user_id=?", (new, now, m.from_user.id))

    await m.answer(
        f"🍖 ابولی غذا گرفت!\n\n"
        f"🍽️ غذا: {f[0]}\n"
        f"❤️ سیری: +{f[2]}\n"
        f"🥣 شکم: {r[6]}/10 → {new}/10\n"
        f"⏱️ غذای بعدی: {int(cd(r[5]) / 60)} دقیقه",
        **reply_kwargs(m)
    )


async def show_abouli_upgrade(target, uid):
    r = user(uid)
    level = int(r[4])
    if level >= 10:
        text = "⭐️ ابولی به حداکثر سطح ۱۰ رسیده."
    else:
        nxt = level + 1
        text = (
            f"⭐️ ارتقای ابولی\n\n"
            f"سطح فعلی: {level}/10\n"
            f"سطح بعدی: {nxt}/10\n"
            f"💰 هزینه: {fmt_num(ABOULI_COST[nxt])} AP\n"
            f"🎁 پاداش فعلی: {fmt_num(ABOULI_REWARD[level])}\n"
            f"🎁 پاداش بعدی: {fmt_num(ABOULI_REWARD[nxt])}"
        )
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=upgrade_abouli_kb())
    else:
        await target.answer(text, reply_markup=upgrade_abouli_kb(), **reply_kwargs(target))


async def buy_abouli(target, uid):
    r = user(uid)
    level = int(r[4])

    if level >= 10:
        text = "⭐️ ابولی از قبل در بالاترین سطحه."
    else:
        nxt = level + 1
        cost = d(ABOULI_COST[nxt])
        balance = d(r[2])

        if balance < cost:
            text = (
                f"❌ ابول پوینت کافی نداری.\n\n"
                f"💰 موجودی: {fmt_num(balance)}\n"
                f"💳 هزینه: {fmt_num(cost)}\n"
                f"📉 کمبود: {fmt_num(cost - balance)}"
            )
        else:
            q("UPDATE users SET ap=?,level=? WHERE user_id=?",
              (str(balance - cost), nxt, uid))
            text = (
                f"🎉 ابولی به سطح {nxt} ارتقا پیدا کرد!\n\n"
                f"💰 هزینه: {fmt_num(cost)}\n"
                f"🎁 پاداش هر ابول: {fmt_num(ABOULI_REWARD[nxt])}\n"
                f"⚡ سرعت ماین: {fmt_num(RATE[nxt])} AP/s"
            )

    await target.message.edit_text(text, reply_markup=upgrade_abouli_kb())


async def show_spoon_upgrade(target, uid):
    r = user(uid)
    level = int(r[5])
    if level >= 10:
        text = "🥄 قاشق ابولی به حداکثر سطح ۱۰ رسیده."
    else:
        nxt = level + 1
        text = (
            f"🥄 ارتقای قاشق\n\n"
            f"سطح فعلی: {level}/10\n"
            f"سطح بعدی: {nxt}/10\n"
            f"💰 هزینه: {fmt_num(SPOON_COST[nxt])} AP\n"
            f"🍽️ زمان غذا: {60 - (nxt - 1) * 5} دقیقه"
        )
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=upgrade_spoon_kb())
    else:
        await target.answer(text, reply_markup=upgrade_spoon_kb(), **reply_kwargs(target))


async def buy_spoon(target, uid):
    r = user(uid)
    level = int(r[5])
    if level >= 10:
        text = "🥄 قاشق ابولی از قبل در بالاترین سطحه."
    else:
        nxt = level + 1
        cost = d(SPOON_COST[nxt])
        balance = d(r[2])
        if balance < cost:
            text = (
                f"❌ ابول پوینت کافی نداری.\n\n"
                f"💰 موجودی: {fmt_num(balance)}\n"
                f"💳 هزینه: {fmt_num(cost)}\n"
                f"📉 کمبود: {fmt_num(cost - balance)}"
            )
        else:
            q("UPDATE users SET ap=?,spoon=? WHERE user_id=?",
              (str(balance - cost), nxt, uid))
            text = (
                f"🎉 قاشق به سطح {nxt} ارتقا پیدا کرد!\n\n"
                f"💰 هزینه: {fmt_num(cost)}\n"
                f"🍽️ زمان غذای بعدی: {60 - (nxt - 1) * 5} دقیقه"
            )
    await target.message.edit_text(text, reply_markup=upgrade_spoon_kb())


@dp.message(F.text == "ارتقای قاشق")
async def spoon(m: Message):
    await show_spoon_upgrade(m, m.from_user.id)


@dp.message(F.text == "بانک ابولی")
async def bank(m: Message):
    r = user(m.from_user.id, m.from_user.full_name)
    await m.answer(
        f"🏦 بانک ابولی\n\n"
        f"🧾 شماره حساب: {r[11]}\n"
        f"👤 صاحب حساب: {r[1]}\n"
        f"💰 موجودی بانک: {fmt_num(r[10])} AP\n"
        f"📈 سود روزانه: ۳٪\n"
        f"⏰ ساعت سود: ۰۷:۰۰",
        reply_markup=bank_kb(),
        **reply_kwargs(m)
    )


async def money_op(m, kind):
    r = user(m.from_user.id, m.from_user.full_name)
    p = m.text.split()
    if len(p) != 2:
        await m.answer(f"فرمت: {kind} 5000", **reply_kwargs(m))
        return
    try:
        a = d(p[1])
    except Exception:
        await m.answer("❌ مقدار نامعتبر.", **reply_kwargs(m))
        return
    if a <= 0:
        await m.answer("❌ مقدار باید بیشتر از صفر باشد.", **reply_kwargs(m))
        return

    if kind == "واریز":
        if d(r[2]) < a:
            await m.answer("❌ موجودی اصلی کافی نیست.", **reply_kwargs(m))
            return
        q("UPDATE users SET ap=?,bank=? WHERE user_id=?",
          (str(d(r[2]) - a), str(d(r[10]) + a), m.from_user.id))
    else:
        if d(r[10]) < a:
            await m.answer("❌ موجودی بانک کافی نیست.", **reply_kwargs(m))
            return
        q("UPDATE users SET ap=?,bank=? WHERE user_id=?",
          (str(d(r[2]) + a), str(d(r[10]) - a), m.from_user.id))

    await m.answer(
        f"✅ {fmt_num(a)} AP {'واریز شد' if kind == 'واریز' else 'برداشت شد'}.",
        **reply_kwargs(m)
    )


@dp.message(F.text.startswith("واریز "))
async def dep(m: Message):
    await money_op(m, "واریز")


@dp.message(F.text.startswith("برداشت "))
async def wit(m: Message):
    await money_op(m, "برداشت")


@dp.message(F.text.startswith("انتقال "))
async def transfer(m: Message):
    p = m.text.split()
    if len(p) != 3 or not p[1].isdigit():
        await m.answer("فرمت: انتقال [شماره حساب] [مقدار]", **reply_kwargs(m))
        return
    try:
        a = d(p[2])
    except Exception:
        await m.answer("❌ مقدار نامعتبر.", **reply_kwargs(m))
        return
    if a <= 0:
        await m.answer("❌ مقدار نامعتبر.", **reply_kwargs(m))
        return

    s = user(m.from_user.id, m.from_user.full_name)
    r = q("SELECT * FROM users WHERE account=?", (p[1],), True)
    if not r:
        await m.answer("❌ شماره حساب پیدا نشد.", **reply_kwargs(m))
        return
    if d(s[10]) < a:
        await m.answer("❌ موجودی بانک کافی نیست.", **reply_kwargs(m))
        return

    q("UPDATE users SET bank=? WHERE user_id=?", (str(d(s[10]) - a), s[0]))
    q("UPDATE users SET bank=? WHERE user_id=?", (str(d(r[10]) + a), r[0]))
    await m.answer(f"✅ {fmt_num(a)} AP به حساب {p[1]} منتقل شد.", **reply_kwargs(m))


@dp.message(F.text == "تراکنش‌ها")
async def tx(m: Message):
    rows = q("SELECT kind,amount,note FROM tx WHERE user_id=? ORDER BY id DESC LIMIT 10",
             (m.from_user.id,))
    body = "\n".join(
        f"• {x[0]}: {fmt_num(x[1])} AP — {x[2]}" for x in rows
    ) if rows else "تراکنشی نیست."
    await m.answer("🧾 تراکنش‌ها\n\n" + body, **reply_kwargs(m))


@dp.callback_query(F.data == "profile")
async def cb_profile(c: CallbackQuery):
    await c.answer()
    await send_profile(c, edit=True)


@dp.callback_query(F.data == "upgrade_abouli")
async def cb_upgrade_abouli(c: CallbackQuery):
    await c.answer()
    await show_abouli_upgrade(c, c.from_user.id)


@dp.callback_query(F.data == "buy_abouli")
async def cb_buy_abouli(c: CallbackQuery):
    await c.answer()
    await buy_abouli(c, c.from_user.id)


@dp.callback_query(F.data == "upgrade_spoon")
async def cb_upgrade_spoon(c: CallbackQuery):
    await c.answer()
    await show_spoon_upgrade(c, c.from_user.id)


@dp.callback_query(F.data == "buy_spoon")
async def cb_buy_spoon(c: CallbackQuery):
    await c.answer()
    await buy_spoon(c, c.from_user.id)


@dp.callback_query(F.data == "bank")
async def cb_bank(c: CallbackQuery):
    await c.answer()
    r = user(c.from_user.id, c.from_user.full_name)
    await c.message.edit_text(
        f"🏦 بانک ابولی\n\n"
        f"🧾 شماره حساب: {r[11]}\n"
        f"👤 صاحب حساب: {r[1]}\n"
        f"💰 موجودی بانک: {fmt_num(r[10])} AP\n"
        f"📈 سود روزانه: ۳٪\n"
        f"⏰ ساعت سود: ۰۷:۰۰",
        reply_markup=bank_kb()
    )


@dp.callback_query(F.data == "food")
async def cb_food(c: CallbackQuery):
    await c.answer()
    mine(c.from_user.id)
    r = user(c.from_user.id, c.from_user.full_name)
    left = cd(r[5]) - (time.time() - float(r[8]))
    if left > 0:
        await c.message.edit_text(
            f"🍽️ هنوز {fmt_time(left)} تا غذای بعدی مونده.",
            reply_markup=profile_kb()
        )
        return

    f = random.choices(FOODS, weights=[x[1] for x in FOODS])[0]
    new = min(10, int(r[6]) + f[2])
    now = time.time()
    q("UPDATE users SET hunger=?,last_food=? WHERE user_id=?",
      (new, now, c.from_user.id))
    await c.message.edit_text(
        f"🍖 ابولی غذا گرفت!\n\n"
        f"🍽️ غذا: {f[0]}\n"
        f"❤️ سیری: +{f[2]}\n"
        f"🥣 شکم: {r[6]}/10 → {new}/10\n"
        f"⏱️ غذای بعدی: {int(cd(r[5]) / 60)} دقیقه",
        reply_markup=profile_kb()
    )


@dp.callback_query(F.data.in_({"bank_deposit", "bank_withdraw", "bank_transfer"}))
async def cb_bank_help(c: CallbackQuery):
    await c.answer()
    messages = {
        "bank_deposit": "برای واریز بنویس:\nواریز [مقدار]\nمثال: واریز 500",
        "bank_withdraw": "برای برداشت بنویس:\nبرداشت [مقدار]\nمثال: برداشت 500",
        "bank_transfer": "برای انتقال بنویس:\nانتقال [شماره حساب] [مقدار]",
    }
    await c.message.edit_text(messages[c.data], reply_markup=bank_kb())


@dp.message(F.text.startswith("حذف پوینت "))
async def remove(m: Message):
    if m.from_user.id != ADMIN_ID:
        return
    p = m.text.split()
    if len(p) != 3 or not p[1].isdigit():
        await m.answer("فرمت: حذف پوینت [ID] [مقدار]", **reply_kwargs(m))
        return
    try:
        a = d(p[2])
    except Exception:
        await m.answer("❌ مقدار نامعتبر.", **reply_kwargs(m))
        return
    r = user(int(p[1]))
    if a <= 0 or d(r[2]) < a:
        await m.answer("❌ مقدار نامعتبر یا موجودی ناکافی.", **reply_kwargs(m))
        return
    q("UPDATE users SET ap=? WHERE user_id=?", (str(d(r[2]) - a), r[0]))
    await m.answer(f"✅ {fmt_num(a)} AP حذف شد.", **reply_kwargs(m))


@dp.message(F.text.startswith("اضافه پوینت "))
async def add(m: Message):
    if m.from_user.id != ADMIN_ID:
        return
    p = m.text.split()
    if len(p) != 3 or not p[1].isdigit():
        await m.answer("فرمت: اضافه پوینت [ID] [مقدار]", **reply_kwargs(m))
        return
    try:
        a = d(p[2])
    except Exception:
        await m.answer("❌ مقدار نامعتبر.", **reply_kwargs(m))
        return
    if a <= 0:
        await m.answer("❌ مقدار نامعتبر.", **reply_kwargs(m))
        return
    r = user(int(p[1]))
    q("UPDATE users SET ap=? WHERE user_id=?", (str(d(r[2]) + a), r[0]))
    await m.answer(f"✅ {fmt_num(a)} AP اضافه شد.", **reply_kwargs(m))


async def interest():
    done=None
    while True:
        t=time.localtime(); key=time.strftime("%Y-%m-%d",t)
        if t.tm_hour==7 and t.tm_min==0 and done!=key:
            for uid,b in q("SELECT user_id,bank FROM users WHERE CAST(bank AS REAL)>0"):
                x=d(b); i=x*d(".03"); q("UPDATE users SET bank=? WHERE user_id=?",(str(x+i),uid))
            done=key
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
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Render health server listening on 0.0.0.0:{port}")

async def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN is required")

    init()
    asyncio.create_task(interest())

    bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode="HTML"))

    # Keep an HTTP port open so Render Web Service can monitor the process.
    await run_web_server()

    await dp.start_polling(bot)

if __name__=="__main__":
    asyncio.run(main())
