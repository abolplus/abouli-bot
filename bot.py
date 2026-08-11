import asyncio, os, random, sqlite3, time
from decimal import Decimal
from contextlib import closing
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.client.default import DefaultBotProperties

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 1873527787
DB = "abouli.db"
CAP = Decimal("30000")
RATE = {1:Decimal(".1"),2:Decimal(".2"),3:Decimal(".5"),4:Decimal("1"),5:Decimal("1.5"),6:Decimal("2"),7:Decimal("3"),8:Decimal("4"),9:Decimal("5"),10:Decimal("5")}
ABOULI_COST = {1:100,2:200,3:400,4:500,5:600,6:700,7:800,8:900,9:1000,10:1100}
SPOON_COST = {2:100,3:250,4:500,5:800,6:1200,7:1800,8:2500,9:3500,10:5000}
FOODS = [("گوش لوبیا",.4,1),("قورمه‌سبزی",.3,2),("کباب",.2,3),("جوجه",.1,4)]
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

def kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="ابول"),KeyboardButton(text="پروف ابولی")],[KeyboardButton(text="غذا"),KeyboardButton(text="ارتقای قاشق")],[KeyboardButton(text="بانک ابولی")]],resize_keyboard=True)

@dp.message(CommandStart())
async def start(m:Message):
    user(m.from_user.id,m.from_user.full_name)
    await m.answer("🐮 به ابولی خوش اومدی!\n\nابول | پروف ابولی | غذا | ارتقای قاشق | بانک ابولی",reply_markup=kb())

@dp.message(F.text=="ابول")
async def aboul(m:Message):
    r=user(m.from_user.id,m.from_user.full_name); left=300-(time.time()-float(r[9]))
    if left>0:return await m.answer(f"⏳ ابول بعدی: {int(left)//60}:{int(left)%60:02d}")
    now=time.time(); q("UPDATE users SET ap=CAST(ap AS REAL)+1,last_aboul=? WHERE user_id=?",(now,m.from_user.id))
    q("INSERT INTO tx(user_id,kind,amount,note,ts) VALUES(?,?,?,?,?)",(m.from_user.id,"aboul","1","دستور ابول",now))
    await m.answer("🐮 ابول!\n🪙 +1 ابول پوینت\n⏱️ ابول بعدی: ۵ دقیقه")

@dp.message(F.text=="پروف ابولی")
async def profile(m:Message):
    mine(m.from_user.id); r=user(m.from_user.id,m.from_user.full_name)
    left=max(0,cd(r[5])-(time.time()-float(r[8])))
    status="⛏️ فعال" if int(r[6])>0 and d(r[3])<CAP else "⛔ متوقف"
    await m.answer(f"🐮 پروف ابولی\n\n👤 {r[1]}\n⭐ سطح ابولی: {r[4]}/10\n🥄 سطح قاشق: {r[5]}/10\n🍽️ شکم: {r[6]}/10\n\n{status}\n⚡ سرعت: {RATE[int(r[4])]} AP/s\n🪙 ماین‌شده: {d(r[3]):,.8f} / {CAP:,}\n💰 دارایی: {d(r[2]):,.8f} AP\n⏱️ غذای بعدی: {int(left)//60}:{int(left)%60:02d}")

@dp.message(F.text=="غذا")
async def food(m:Message):
    mine(m.from_user.id); r=user(m.from_user.id,m.from_user.full_name)
    left=cd(r[5])-(time.time()-float(r[8]))
    if left>0:return await m.answer(f"🍽️ غذای بعدی تا {int(left)//60}:{int(left)%60:02d}")
    f=random.choices(FOODS,weights=[x[1] for x in FOODS])[0]; new=min(10,int(r[6])+f[2]); now=time.time()
    q("UPDATE users SET hunger=?,last_food=? WHERE user_id=?",(new,now,m.from_user.id))
    await m.answer(f"🐮 ابولی غذا گرفت!\n\n🍽️ غذا: {f[0]}\n❤️ سیری: +{f[2]}\n🥣 شکم: {r[6]}/10 → {new}/10\n⏱️ غذای بعدی: {int(cd(r[5])/60)} دقیقه")

@dp.message(F.text=="ارتقای قاشق")
async def spoon(m:Message):
    r=user(m.from_user.id,m.from_user.full_name); n=r[5]+1
    if r[5]>=10:return await m.answer("🥄 قاشق ابولی MAX است.")
    await m.answer(f"🥄 قاشق سطح {r[5]}/10\n⬆️ سطح بعد: {n}\n💰 هزینه: {SPOON_COST[n]} AP\n🍽️ زمان غذا: {60-(n-1)*5} دقیقه\n\nبرای خرید: ارتقای قاشق {n}")

@dp.message(F.text.startswith("ارتقای قاشق "))
async def spoon_buy(m:Message):
    r=user(m.from_user.id,m.from_user.full_name); p=m.text.split()
    if len(p)!=3 or not p[2].isdigit():return await m.answer("فرمت: ارتقای قاشق 2")
    n=int(p[2])
    if n!=r[5]+1 or n>10:return await m.answer("❌ فقط لول بعدی مجاز است.")
    cost=d(SPOON_COST[n])
    if d(r[2])<cost:return await m.answer("❌ موجودی کافی نیست.")
    q("UPDATE users SET ap=?,spoon=? WHERE user_id=?",(str(d(r[2])-cost),n,m.from_user.id))
    await m.answer(f"🥄 قاشق به سطح {n} رسید!\n🍽️ زمان غذا: {60-(n-1)*5} دقیقه")

@dp.message(F.text=="بانک ابولی")
async def bank(m:Message):
    r=user(m.from_user.id,m.from_user.full_name)
    await m.answer(f"🏦 بانک ابولی\n\n🧾 شماره حساب: {r[11]}\n👤 صاحب حساب: {r[1]}\n💰 موجودی: {d(r[10]):,.8f} AP\n📈 سود روزانه: ۳٪\n⏰ ساعت سود: ۰۷:۰۰\n\nواریز [مقدار]\nبرداشت [مقدار]\nانتقال [شماره حساب] [مقدار]\nتراکنش‌ها")

async def money_op(m,kind):
    r=user(m.from_user.id,m.from_user.full_name); p=m.text.split()
    if len(p)!=2:return await m.answer(f"فرمت: {kind} 5000")
    try:a=d(p[1])
    except:return await m.answer("❌ مقدار نامعتبر.")
    if a<=0:return await m.answer("❌ مقدار باید بیشتر از صفر باشد.")
    if kind=="واریز":
        if d(r[2])<a:return await m.answer("❌ موجودی اصلی کافی نیست.")
        q("UPDATE users SET ap=?,bank=? WHERE user_id=?",(str(d(r[2])-a),str(d(r[10])+a),m.from_user.id))
    else:
        if d(r[10])<a:return await m.answer("❌ موجودی بانک کافی نیست.")
        q("UPDATE users SET ap=?,bank=? WHERE user_id=?",(str(d(r[2])+a),str(d(r[10])-a),m.from_user.id))
    await m.answer(f"✅ {a} AP {'واریز شد' if kind=='واریز' else 'برداشت شد'}.")

@dp.message(F.text.startswith("واریز "))
async def dep(m:Message): await money_op(m,"واریز")
@dp.message(F.text.startswith("برداشت "))
async def wit(m:Message): await money_op(m,"برداشت")

@dp.message(F.text.startswith("انتقال "))
async def transfer(m:Message):
    p=m.text.split()
    if len(p)!=3 or not p[1].isdigit():return await m.answer("فرمت: انتقال [شماره حساب] [مقدار]")
    try:a=d(p[2])
    except:return await m.answer("❌ مقدار نامعتبر.")
    if a<=0:return await m.answer("❌ مقدار نامعتبر.")
    s=user(m.from_user.id,m.from_user.full_name); r=q("SELECT * FROM users WHERE account=?",(p[1],),True)
    if not r:return await m.answer("❌ شماره حساب پیدا نشد.")
    if d(s[10])<a:return await m.answer("❌ موجودی بانک کافی نیست.")
    q("UPDATE users SET bank=? WHERE user_id=?",(str(d(s[10])-a),s[0]))
    q("UPDATE users SET bank=? WHERE user_id=?",(str(d(r[10])+a),r[0]))
    await m.answer(f"✅ {a} AP به حساب {p[1]} منتقل شد.")

@dp.message(F.text=="تراکنش‌ها")
async def tx(m:Message):
    rows=q("SELECT kind,amount,note FROM tx WHERE user_id=? ORDER BY id DESC LIMIT 10",(m.from_user.id,))
    await m.answer("🧾 تراکنش‌ها\n\n" + ("\n".join(f"• {x[0]}: {x[1]} AP — {x[2]}" for x in rows) if rows else "تراکنشی نیست."))

@dp.message(F.text.startswith("حذف پوینت "))
async def remove(m:Message):
    if m.from_user.id!=ADMIN_ID:return
    p=m.text.split()
    if len(p)!=3 or not p[1].isdigit():return await m.answer("فرمت: حذف پوینت [ID] [مقدار]")
    try:a=d(p[2])
    except:return await m.answer("❌ مقدار نامعتبر.")
    r=user(int(p[1]))
    if a<=0 or d(r[2])<a:return await m.answer("❌ مقدار نامعتبر یا موجودی ناکافی.")
    q("UPDATE users SET ap=? WHERE user_id=?",(str(d(r[2])-a),r[0]))
    await m.answer(f"✅ {a} AP حذف شد.")

@dp.message(F.text.startswith("اضافه پوینت "))
async def add(m:Message):
    if m.from_user.id!=ADMIN_ID:return
    p=m.text.split()
    if len(p)!=3 or not p[1].isdigit():return await m.answer("فرمت: اضافه پوینت [ID] [مقدار]")
    try:a=d(p[2])
    except:return await m.answer("❌ مقدار نامعتبر.")
    if a<=0:return await m.answer("❌ مقدار نامعتبر.")
    r=user(int(p[1])); q("UPDATE users SET ap=? WHERE user_id=?",(str(d(r[2])+a),r[0]))
    await m.answer(f"✅ {a} AP اضافه شد.")

async def interest():
    done=None
    while True:
        t=time.localtime(); key=time.strftime("%Y-%m-%d",t)
        if t.tm_hour==7 and t.tm_min==0 and done!=key:
            for uid,b in q("SELECT user_id,bank FROM users WHERE CAST(bank AS REAL)>0"):
                x=d(b); i=x*d(".03"); q("UPDATE users SET bank=? WHERE user_id=?",(str(x+i),uid))
            done=key
        await asyncio.sleep(20)

async def main():
    if not TOKEN: raise RuntimeError("BOT_TOKEN is required")
    init(); asyncio.create_task(interest())
    bot=Bot(TOKEN,default=DefaultBotProperties(parse_mode="HTML"))
    await dp.start_polling(bot)

if __name__=="__main__": asyncio.run(main())
