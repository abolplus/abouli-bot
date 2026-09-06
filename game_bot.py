"""Telegram group game bot - test build.
Python 3.11+, aiogram 3.x, aiosqlite.
Set BOT_TOKEN and ADMIN_ID in environment variables.
Set CHANNEL_ID to the numeric channel ID whose comments should reward praise.
"""
import asyncio, os, random, re, sqlite3
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

DB = os.getenv("DB_PATH", "game.db")
TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "1873527787"))
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
TEHRAN = ZoneInfo("Asia/Tehran")

FOODS = [
    ("عدس‌پلو", 2, 35), ("قورمه‌سبزی", 3, 30), ("آبگوشت", 3, 15),
    ("جوجه‌کباب", 4, 10), ("کباب", 5, 10)
]
PRAISE_RE = re.compile(r"(?:ابول|ابوالفضل|داش\s*ابول|ابول‌)[\s\S]{0,45}(?:عشق|بنازمت|فدات|مرام|عالی|خفن|سلطان|داداش|دمت|عاشق|بهترین|گلی|خوج|خوژتیپ)", re.I)

CREATE = [
"""CREATE TABLE IF NOT EXISTS users(
 id INTEGER PRIMARY KEY, name TEXT, money INTEGER NOT NULL DEFAULT 0,
 house_level INTEGER NOT NULL DEFAULT 0, worker_food INTEGER NOT NULL DEFAULT 0,
 worker_pocket INTEGER NOT NULL DEFAULT 0, last_worker_tick TEXT, last_food TEXT,
 pending_food TEXT, last_catch TEXT, last_relation TEXT, last_subsidy TEXT,
 last_active TEXT, blocked INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
)""",
"""CREATE TABLE IF NOT EXISTS groups(chat_id INTEGER PRIMARY KEY, title TEXT, last_seen TEXT)""",
"""CREATE TABLE IF NOT EXISTS marriages(id INTEGER PRIMARY KEY AUTOINCREMENT,
 user1 INTEGER NOT NULL, user2 INTEGER NOT NULL, mahr INTEGER NOT NULL,
 payer_id INTEGER NOT NULL, married_at TEXT NOT NULL)""",
"""CREATE TABLE IF NOT EXISTS gifts(id INTEGER PRIMARY KEY AUTOINCREMENT,
 sender INTEGER, receiver INTEGER, amount INTEGER, created_at TEXT)""",
"""CREATE TABLE IF NOT EXISTS missions(user_id INTEGER, day TEXT, slot INTEGER,
 kind TEXT, target INTEGER, progress INTEGER DEFAULT 0, reward INTEGER, claimed INTEGER DEFAULT 0,
 PRIMARY KEY(user_id,day,slot))""",
"""CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT)""",
]

DEFAULTS = {
 "kas_amount":"10", "kas_cooldown":"300", "worker_income":"500", "worker_hunger_loss":"2",
 "worker_cap":"2000", "food_cooldown":"3600", "subsidy":"200", "relation_cooldown":"3600",
 "party_catch":"50", "party_reward":"100", "party_fine":"150", "praise_reward":"100",
}

def now(): return datetime.now(timezone.utc)
def iso(dt): return dt.astimezone(timezone.utc).isoformat()
def parse(s): return datetime.fromisoformat(s) if s else None
def local_date(): return datetime.now(TEHRAN).date().isoformat()

async def db_init():
    async with aiosqlite.connect(DB) as db:
        for q in CREATE: await db.execute(q)
        for k,v in DEFAULTS.items(): await db.execute("INSERT OR IGNORE INTO settings VALUES(?,?)", (k,v))
        await db.commit()

async def setting(k):
    async with aiosqlite.connect(DB) as db:
        cur=await db.execute("SELECT value FROM settings WHERE key=?",(k,)); r=await cur.fetchone(); return int(r[0])

async def get_user(uid, name=""):
    async with aiosqlite.connect(DB) as db:
        cur=await db.execute("SELECT * FROM users WHERE id=?",(uid,)); r=await cur.fetchone()
        if r: return r
        t=iso(now()); await db.execute("INSERT INTO users(id,name,last_worker_tick,last_active,created_at) VALUES(?,?,?,?,?)",(uid,name,t,t,t)); await db.commit()
        cur=await db.execute("SELECT * FROM users WHERE id=?",(uid,)); return await cur.fetchone()

async def touch(uid,name=""):
    u=await get_user(uid,name)
    if u[13]: return u
    t=iso(now())
    async with aiosqlite.connect(DB) as db:
        await db.execute("UPDATE users SET name=?,last_active=? WHERE id=?",(name,t,uid)); await db.commit()
    return await get_user(uid,name)

async def update_worker(uid):
    async with aiosqlite.connect(DB) as db:
        cur=await db.execute("SELECT worker_food,worker_pocket,last_worker_tick FROM users WHERE id=?",(uid,)); r=await cur.fetchone()
        if not r: return
        food,pocket,last=r; last=parse(last) or now(); hours=max(0,int((now()-last).total_seconds()//3600))
        if hours:
            income=await setting("worker_income"); loss=await setting("worker_hunger_loss"); cap=await setting("worker_cap")
            for _ in range(hours):
                food=max(0,food-loss)
                if food>0 and pocket<cap: pocket=min(cap,pocket+income)
            await db.execute("UPDATE users SET worker_food=?,worker_pocket=?,last_worker_tick=? WHERE id=?",(food,pocket,iso(now()),uid)); await db.commit()

async def add_money(uid,amount):
    async with aiosqlite.connect(DB) as db:
        await db.execute("UPDATE users SET money=money+? WHERE id=?",(amount,uid)); await db.commit()

async def marriage(uid):
    async with aiosqlite.connect(DB) as db:
        cur=await db.execute("SELECT user1,user2,mahr,payer_id,married_at FROM marriages WHERE user1=? OR user2=?",(uid,uid)); return await cur.fetchone()

async def missions_make(uid):
    day=local_date()
    async with aiosqlite.connect(DB) as db:
        cur=await db.execute("SELECT COUNT(*) FROM missions WHERE user_id=? AND day=?",(uid,day));
        if (await cur.fetchone())[0]: return
        pool=[("kas",5,50),("kas",10,100),("food",1,75),("feed",1,75),("party",1,100),("withdraw",1,80),("house",1,150),("gift",1,100),("praise",1,100),("relation",1,120),("kas",20,180),("feed",3,150)]
        chosen=random.sample(pool,5)
        for i,(k,t,reward) in enumerate(chosen): await db.execute("INSERT INTO missions VALUES(?,?,?,?,?,?,?,0)",(uid,day,i,k,t,0,reward))
        await db.commit()

async def mission_progress(uid,kind,inc=1):
    day=local_date(); await missions_make(uid)
    async with aiosqlite.connect(DB) as db:
        await db.execute("UPDATE missions SET progress=MIN(target,progress+?) WHERE user_id=? AND day=? AND kind=? AND claimed=0",(inc,uid,day,kind)); await db.commit()

async def claim_mission(uid,slot):
    day=local_date();
    async with aiosqlite.connect(DB) as db:
        cur=await db.execute("SELECT target,progress,reward,claimed FROM missions WHERE user_id=? AND day=? AND slot=?",(uid,day,slot)); r=await cur.fetchone()
        if not r or r[3] or r[1]<r[0]: return 0
        await db.execute("UPDATE missions SET claimed=1 WHERE user_id=? AND day=? AND slot=?",(uid,day,slot)); await db.execute("UPDATE users SET money=money+? WHERE id=?",(r[2],uid)); await db.commit(); return r[2]

async def schedule_subsidy():
    while True:
        await asyncio.sleep(30)
        day=local_date();
        async with aiosqlite.connect(DB) as db:
            cur=await db.execute("SELECT id,last_active,last_subsidy FROM users WHERE blocked=0"); rows=await cur.fetchall(); amount=await setting("subsidy"); cutoff=now()-timedelta(days=3)
            for uid,last,lastsub in rows:
                if parse(last) and parse(last)>=cutoff and lastsub!=day:
                    await db.execute("UPDATE users SET money=money+?,last_subsidy=? WHERE id=?",(amount,day,uid))
            await db.commit()

async def cleanup():
    while True:
        await asyncio.sleep(3600)
        cutoff=now()-timedelta(days=7)
        async with aiosqlite.connect(DB) as db:
            cur=await db.execute("SELECT id FROM users WHERE last_active<?",(iso(cutoff),)); ids=[x[0] for x in await cur.fetchall()]
            for uid in ids:
                await db.execute("DELETE FROM marriages WHERE user1=? OR user2=?",(uid,uid)); await db.execute("DELETE FROM missions WHERE user_id=?",(uid,)); await db.execute("DELETE FROM users WHERE id=?",(uid,))
            await db.commit()

async def delete_later(bot,chat_id,message_id):
    await asyncio.sleep(30)
    try: await bot.delete_message(chat_id,message_id)
    except: pass

async def ensure_group(m):
    if m.chat.type in ("group","supergroup"):
        async with aiosqlite.connect(DB) as db:
            await db.execute("INSERT INTO groups(chat_id,title,last_seen) VALUES(?,?,?) ON CONFLICT(chat_id) DO UPDATE SET title=excluded.title,last_seen=excluded.last_seen",(m.chat.id,m.chat.title,iso(now()))); await db.commit()

async def profile_text(uid):
    u=await get_user(uid); await update_worker(uid); u=await get_user(uid); mar=await marriage(uid)
    spouse="نداری"
    if mar:
        sid=mar[1] if mar[0]==uid else mar[0]; su=await get_user(sid); spouse=su[1] or str(sid)
    house_val={0:0,1:10000,2:25000,3:55000}[u[3]]
    return (f"👤 {u[1]}\n\n💰 موجودی: {u[4]} تومان\n💎 دارایی تقریبی: {u[4]+house_val} تومان\n"
            f"🏠 خانه: سطح {u[3]}\n👷 کارگر: {'فعال' if u[6]>0 and u[5]>0 else 'متوقف'}\n"
            f"💍 همسر: {spouse}\n📅 شروع بازی: {u[14][:10]}")

def profile_kb(uid):
    rows=[[InlineKeyboardButton(text="👷 کارگر",callback_data="worker"),InlineKeyboardButton(text="🏠 خانه",callback_data="house")],
          [InlineKeyboardButton(text="💰 دارایی",callback_data="assets"),InlineKeyboardButton(text="🎯 مأموریت‌ها",callback_data="missions")],
          [InlineKeyboardButton(text="📖 راهنما",callback_data="help")]]
    if uid==ADMIN_ID: rows.append([InlineKeyboardButton(text="👑 پنل مدیریت",callback_data="admin")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

async def safe_name(m): return m.from_user.full_name or str(m.from_user.id)

bot=Bot(TOKEN) if TOKEN else None
dp=Dispatcher()

@dp.message(F.chat.type.in_({"group","supergroup"}))
async def group_messages(m:Message):
    await ensure_group(m); await touch(m.from_user.id,await safe_name(m)); await update_worker(m.from_user.id); await missions_make(m.from_user.id)
    text=(m.text or "").strip()
    if not text: return
    # Commands without slash, as requested
    if text=="کث":
        u=await get_user(m.from_user.id); last=parse(u[9]); cd=await setting("kas_cooldown")
        if last and (now()-last).total_seconds()<cd:
            mins=max(1,int((cd-(now()-last).total_seconds()+59)//60)); r=await m.reply(f"⏳ هنوز {mins} دقیقه مونده."); asyncio.create_task(delete_later(bot,m.chat.id,r.message_id)); return
        amount=await setting("kas_amount"); await add_money(m.from_user.id,amount)
        async with aiosqlite.connect(DB) as db: await db.execute("UPDATE users SET last_catch=? WHERE id=?",(iso(now()),m.from_user.id)); await db.commit()
        await mission_progress(m.from_user.id,"kas")
        r=await m.reply(f"💰 +{amount} تومان"); asyncio.create_task(delete_later(bot,m.chat.id,r.message_id)); return
    if text=="غذا":
        u=await get_user(m.from_user.id); last=parse(u[10]); cd=await setting("food_cooldown")
        if last and (now()-last).total_seconds()<cd:
            mins=max(1,int((cd-(now()-last).total_seconds()+59)//60)); r=await m.reply(f"🍖 هنوز {mins} دقیقه مونده تا غذای بعدی."); asyncio.create_task(delete_later(bot,m.chat.id,r.message_id)); return
        x=random.randint(1,100); acc=0
        for name,val,pct in FOODS:
            acc+=pct
            if x<=acc: food=(name,val); break
        async with aiosqlite.connect(DB) as db: await db.execute("UPDATE users SET last_food=?,pending_food=? WHERE id=?",(iso(now()),f"{food[0]}|{food[1]}",m.from_user.id)); await db.commit()
        kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🍖 دادن به کارگر",callback_data="feed")]])
        r=await m.reply(f"💎 شما با موفقیت {food[0]} گرفتید\n⭐️ سطح: {u[3]}\n🍖 ارزش غذایی: {food[1]}\n⌛️ از دکمه زیر به کارگرت بده⬇️",reply_markup=kb); asyncio.create_task(delete_later(bot,m.chat.id,r.message_id)); await mission_progress(m.from_user.id,"food"); return
    if text=="پروفایلم":
        r=await m.reply(await profile_text(m.from_user.id),reply_markup=profile_kb(m.from_user.id)); return
    if text=="طلاق":
        mar=await marriage(m.from_user.id)
        if not mar: r=await m.reply("💔 شما همسری ندارید."); asyncio.create_task(delete_later(bot,m.chat.id,r.message_id)); return
        if (now()-parse(mar[5])).total_seconds()<43200: r=await m.reply("⏳ طلاق بعد از ۱۲ ساعت از ازدواج امکان‌پذیره."); asyncio.create_task(delete_later(bot,m.chat.id,r.message_id)); return
        other=mar[1] if mar[0]==m.from_user.id else mar[0]
        async with aiosqlite.connect(DB) as db:
            await db.execute("DELETE FROM marriages WHERE id=?",(mar[0],))
            if mar[3]==m.from_user.id: await db.execute("UPDATE users SET money=money+? WHERE id=?",(mar[2],other))
            await db.commit()
        r=await m.reply("💔 طلاق انجام شد."); asyncio.create_task(delete_later(bot,m.chat.id,r.message_id)); return
    if text=="رابطه":
        mar=await marriage(m.from_user.id)
        if not mar: r=await m.reply("🤝 برای این قابلیت باید ازدواج کرده باشی."); asyncio.create_task(delete_later(bot,m.chat.id,r.message_id)); return
        u=await get_user(m.from_user.id); last=parse(u[11]); cd=await setting("relation_cooldown")
        if last and (now()-last).total_seconds()<cd:
            mins=max(1,int((cd-(now()-last).total_seconds()+59)//60)); r=await m.reply(f"⏳ {mins} دقیقه دیگه دوباره می‌تونی فعالیت زوجین انجام بدی."); asyncio.create_task(delete_later(bot,m.chat.id,r.message_id)); return
        other=mar[1] if mar[0]==m.from_user.id else mar[0]; reward={1:150,2:250,3:500}.get(u[3],150)
        await add_money(m.from_user.id,reward); await add_money(other,reward)
        async with aiosqlite.connect(DB) as db: await db.execute("UPDATE users SET last_relation=? WHERE id IN (?,?)",(iso(now()),m.from_user.id,other)); await db.commit()
        await mission_progress(m.from_user.id,"relation"); r=await m.reply(f"🤝 فعالیت زوجین انجام شد. شما و همسرتان هر کدام +{reward} تومان گرفتید."); asyncio.create_task(delete_later(bot,m.chat.id,r.message_id)); return
    if text=="پارتی":
        mar=await marriage(m.from_user.id)
        if not mar: r=await m.reply("🎉 برای پارتی باید یک زوج داشته باشی."); asyncio.create_task(delete_later(bot,m.chat.id,r.message_id)); return
        other=mar[1] if mar[0]==m.from_user.id else mar[0]; catch=random.randint(1,100)<=await setting("party_catch")
        if catch:
            fine=await setting("party_fine")
            async with aiosqlite.connect(DB) as db:
                await db.execute("UPDATE users SET money=MAX(0,money-?) WHERE id=?",(fine,m.from_user.id)); await db.execute("UPDATE users SET money=MAX(0,money-?) WHERE id=?",(fine,other)); await db.commit()
            txt="🚨 شما حین پارتی دستگیر شدید!"
        else:
            rew=await setting("party_reward"); await add_money(m.from_user.id,rew); await add_money(other,rew); txt=f"🎉 پارتی با موفقیت انجام شد! هر دو نفر +{rew} تومان گرفتید."
        await mission_progress(m.from_user.id,"party"); r=await m.reply(txt); asyncio.create_task(delete_later(bot,m.chat.id,r.message_id)); return
    if text.startswith("هدیه ") and m.reply_to_message:
        try: amount=int(text.split(maxsplit=1)[1])
        except: return
        target=m.reply_to_message.from_user.id
        if target==m.from_user.id or amount<=0: return
        u=await get_user(m.from_user.id)
        if u[4]<amount: r=await m.reply("💸 موجودی کافی نیست."); asyncio.create_task(delete_later(bot,m.chat.id,r.message_id)); return
        kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ تأیید",callback_data=f"gift:{target}:{amount}"),InlineKeyboardButton(text="❌ لغو",callback_data="cancel")]])
        await m.reply(f"🎁 انتقال {amount} تومان به {m.reply_to_message.from_user.full_name}؟",reply_markup=kb); return
    if text.startswith("ازدواج با ") and m.reply_to_message:
        if not re.search(r"\d+",text): return
        mahr=int(re.search(r"\d+",text).group()); target=m.reply_to_message.from_user.id
        if target==m.from_user.id or mahr<=0: return
        u=await get_user(m.from_user.id)
        if u[3]<1: r=await m.reply("🏠 برای ازدواج باید خانه داشته باشی."); asyncio.create_task(delete_later(bot,m.chat.id,r.message_id)); return
        if await marriage(m.from_user.id) or await marriage(target): r=await m.reply("💍 یکی از شما قبلاً ازدواج کرده."); asyncio.create_task(delete_later(bot,m.chat.id,r.message_id)); return
        if u[4]<mahr: r=await m.reply("💸 موجودی برای مهریه کافی نیست."); asyncio.create_task(delete_later(bot,m.chat.id,r.message_id)); return
        kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💍 قبول",callback_data=f"marry:{m.from_user.id}:{mahr}"),InlineKeyboardButton(text="❌ رد",callback_data="cancel")]])
        await m.reply(f"💍 {await safe_name(m)} با مهریه {mahr} تومان پیشنهاد ازدواج داده. قبول می‌کنی؟",reply_markup=kb); return

@dp.callback_query()
async def callbacks(q:CallbackQuery):
    uid=q.from_user.id; await touch(uid,q.from_user.full_name); await update_worker(uid); data=q.data or ""
    if data=="cancel": await q.message.delete(); await q.answer(); return
    if data=="feed":
        u=await get_user(uid)
        if not u[12]: await q.answer("غذایی برای دادن نداری.",show_alert=True); return
        name,val=u[12].split("|",1); new=min(10,u[5]+int(val))
        async with aiosqlite.connect(DB) as db: await db.execute("UPDATE users SET worker_food=?,pending_food=NULL WHERE id=?",(new,uid)); await db.commit()
        await mission_progress(uid,"feed"); await q.answer(f"🍖 {name} به کارگر داده شد."); await q.message.edit_text(f"👷 غذای {name} داده شد. سیری کارگر: {new}/10",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 برگشت",callback_data="back")],[InlineKeyboardButton(text="📖 راهنما",callback_data="help")]])); return
    if data.startswith("gift:"):
        _,target,amount=data.split(":"); target=int(target); amount=int(amount)
        u=await get_user(uid)
        if u[4]<amount: await q.answer("موجودی کافی نیست.",show_alert=True); return
        await add_money(uid,-amount); await add_money(target,amount); await mission_progress(uid,"gift"); await q.message.edit_text("🎁 هدیه با موفقیت ارسال شد."); await q.answer(); return
    if data.startswith("marry:"):
        proposer=int(data.split(":")[1]); mahr=int(data.split(":")[2])
        if uid==proposer or await marriage(uid) or await marriage(proposer): await q.answer("این پیشنهاد دیگر معتبر نیست.",show_alert=True); return
        pu=await get_user(proposer)
        if pu[4]<mahr: await q.answer("موجودی پیشنهاددهنده کافی نیست.",show_alert=True); return
        async with aiosqlite.connect(DB) as db:
            await db.execute("UPDATE users SET money=money-? WHERE id=?",(mahr,proposer)); await db.execute("INSERT INTO marriages(user1,user2,mahr,payer_id,married_at) VALUES(?,?,?,?,?)",(proposer,uid,mahr,proposer,iso(now()))); await db.commit()
        await q.message.edit_text("💍 ازدواج با موفقیت انجام شد!"); await q.answer(); return
    if data=="back": await q.message.edit_text(await profile_text(uid),reply_markup=profile_kb(uid)); return
    if data=="worker":
        u=await get_user(uid); status="فعال 🟢" if u[5]>0 and u[6]<await setting("worker_cap") else "متوقف 🔴"
        kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💰 برداشت پول",callback_data="withdraw")],[InlineKeyboardButton(text="🔙 برگشت",callback_data="back")],[InlineKeyboardButton(text="📖 راهنما",callback_data="help")]])
        await q.message.edit_text(f"👷 کارگر\n\n🍖 سیری: {u[5]}/10\n💰 جیب کارگر: {u[6]} تومان\n📊 وضعیت: {status}",reply_markup=kb); return
    if data=="withdraw":
        u=await get_user(uid); amount=u[6]
        if amount: await add_money(uid,amount)
        async with aiosqlite.connect(DB) as db: await db.execute("UPDATE users SET worker_pocket=0 WHERE id=?",(uid,)); await db.commit()
        await mission_progress(uid,"withdraw"); await q.answer(f"💰 {amount} تومان برداشت شد."); await q.message.edit_text(await profile_text(uid),reply_markup=profile_kb(uid)); return
    if data=="house":
        u=await get_user(uid)
        if u[3]==0: kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 خرید خانه - ۱۰٬۰۰۰",callback_data="buyhouse")],[InlineKeyboardButton(text="🔙 برگشت",callback_data="back")],[InlineKeyboardButton(text="📖 راهنما",callback_data="help")]])
        elif u[3]<3: cost={1:15000,2:30000}[u[3]]; kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"🔨 بازسازی - {cost:,}",callback_data="renovate")],[InlineKeyboardButton(text="🔙 برگشت",callback_data="back")],[InlineKeyboardButton(text="📖 راهنما",callback_data="help")]])
        else: kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 برگشت",callback_data="back")],[InlineKeyboardButton(text="📖 راهنما",callback_data="help")]])
        await q.message.edit_text(f"🏠 خانه شما: سطح {u[3]}/3",reply_markup=kb); return
    if data=="buyhouse":
        u=await get_user(uid)
        if u[4]<10000: await q.answer("پول کافی نیست.",show_alert=True); return
        async with aiosqlite.connect(DB) as db: await db.execute("UPDATE users SET money=money-10000,house_level=1 WHERE id=?",(uid,)); await db.commit()
        await mission_progress(uid,"house"); await q.answer("🏠 خانه خریداری شد."); await q.message.edit_text(await profile_text(uid),reply_markup=profile_kb(uid)); return
    if data=="renovate":
        u=await get_user(uid); cost={1:15000,2:30000}.get(u[3])
        if not cost: await q.answer("امکان بازسازی نیست.",show_alert=True); return
        if u[4]<cost: await q.answer("پول کافی نیست.",show_alert=True); return
        async with aiosqlite.connect(DB) as db: await db.execute("UPDATE users SET money=money-?,house_level=house_level+1 WHERE id=?",(cost,uid)); await db.commit()
        await q.answer("🔨 خانه ارتقا یافت."); await q.message.edit_text(await profile_text(uid),reply_markup=profile_kb(uid)); return
    if data=="assets": await q.message.edit_text((await profile_text(uid))+"\n\n💎 دارایی‌ها شامل موجودی و ارزش خرید/ارتقای خانه است.",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 برگشت",callback_data="back")],[InlineKeyboardButton(text="📖 راهنما",callback_data="help")]])); return
    if data=="missions":
        await missions_make(uid); day=local_date()
        async with aiosqlite.connect(DB) as db: cur=await db.execute("SELECT slot,kind,target,progress,reward,claimed FROM missions WHERE user_id=? AND day=? ORDER BY slot",(uid,day)); rows=await cur.fetchall()
        names={"kas":"کث","food":"گرفتن غذا","feed":"غذا دادن به کارگر","party":"پارتی","withdraw":"برداشت پول کارگر","house":"خرید خانه","gift":"هدیه","praise":"تعریف در کامنت","relation":"فعالیت زوجین"}
        lines=["🎯 مأموریت‌های امروز:"]
        buttons=[]
        for slot,k,t,p,r,c in rows:
            lines.append(f"{slot+1}. {names.get(k,k)}: {p}/{t} — 💰{r}{' ✅' if c else ''}")
            if p>=t and not c: buttons.append([InlineKeyboardButton(text=f"🎁 دریافت مأموریت {slot+1}",callback_data=f"claim:{slot}")])
        buttons += [[InlineKeyboardButton(text="🔙 برگشت",callback_data="back")],[InlineKeyboardButton(text="📖 راهنما",callback_data="help")]]
        await q.message.edit_text("\n".join(lines),reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)); return
    if data.startswith("claim:"):
        reward=await claim_mission(uid,int(data.split(":")[1])); await q.answer(f"💰 {reward} تومان دریافت شد." if reward else "هنوز کامل نشده یا قبلاً گرفتی.",show_alert=True); return
    if data=="help":
        txt="📖 راهنما\n\nکث — دریافت پول\nغذا — دریافت غذای تصادفی\nپروفایلم — پروفایل\nهدیه N — در ریپلای برای انتقال پول\nازدواج با N تومن — در ریپلای به شخص موردنظر\nطلاق — طلاق بعد از ۱۲ ساعت\nرابطه — فعالیت زوجین\nپارتی — فعالیت شانسی زوجین\n\nبقیه امکانات از دکمه‌های پروفایل انجام می‌شوند."
        await q.message.edit_text(txt,reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 برگشت",callback_data="back")]])); return
    if data=="admin":
        if uid!=ADMIN_ID: await q.answer("دسترسی ندارید.",show_alert=True); return
        async with aiosqlite.connect(DB) as db:
            ucount=(await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())[0]; gcount=(await (await db.execute("SELECT COUNT(*) FROM groups")).fetchone())[0]; total=(await (await db.execute("SELECT COALESCE(SUM(money+worker_pocket),0) FROM users")).fetchone())[0]; mc=(await (await db.execute("SELECT COUNT(*) FROM marriages")).fetchone())[0]
        await q.message.edit_text(f"👑 پنل مدیریت\n\n👤 کاربران: {ucount}\n👥 گروه‌ها: {gcount}\n💰 پول اقتصاد: {total}\n💍 ازدواج‌ها: {mc}",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📊 آمار",callback_data="admin")],[InlineKeyboardButton(text="🔙 برگشت",callback_data="back")]])); return
    await q.answer()

@dp.message(Command("start"))
async def start(m:Message):
    await touch(m.from_user.id,await safe_name(m)); await ensure_group(m); await m.answer("🤖 ربات بازی آماده‌ست!\nداخل گروه از دستورها استفاده کن: پروفایلم، کث، غذا، هدیه، ازدواج و... 💰")

async def main():
    if not TOKEN: raise RuntimeError("BOT_TOKEN is not set")
    await db_init()
    asyncio.create_task(schedule_subsidy()); asyncio.create_task(cleanup())
    await dp.start_polling(bot)

if __name__=="__main__": asyncio.run(main())
