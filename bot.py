import asyncio, os, random, sqlite3, time
from aiohttp import web
from decimal import Decimal
from contextlib import closing
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.client.default import DefaultBotProperties

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 1873527787
DB = "abouli.db"
CHANNEL_USERNAME = "@abolsniper"
CHANNEL_URL = "https://t.me/abolsniper"
PROFILE_ALIASES = {"پروف ابولی", "پروفایل ابولی", "پروفای ابولی", "پروف ابولی ری"}
CAP = Decimal("30000")
RATE = {1:Decimal('.1'),2:Decimal('.2'),3:Decimal('.5'),4:Decimal('1'),5:Decimal('1.5'),6:Decimal('2'),7:Decimal('3'),8:Decimal('4'),9:Decimal('5'),10:Decimal('6')}
ABOULI_REWARD = {1:1,2:2,3:3,4:5,5:7,6:10,7:13,8:17,9:22,10:30}
ABOULI_COST = {1:100,2:200,3:400,4:500,5:600,6:700,7:800,8:900,9:1000,10:1100}
SPOON_COST = {2:100,3:250,4:500,5:800,6:1200,7:1800,8:2500,9:3500,10:5000}
FOODS = [('لوبیا',.4,1),('قورمه‌سبزی',.3,2),('کباب',.2,3),('جوجه',.1,4)]
dp=Dispatcher()

# Pending bank actions: user_id -> {'kind': 'deposit'|'withdraw', 'amount': Decimal, 'chat_id': int, 'message_id': int}
PENDING_BANK = {}

def init():
    with closing(sqlite3.connect(DB)) as c:
        c.executescript("""CREATE TABLE IF NOT EXISTS users(
        user_id INTEGER PRIMARY KEY,name TEXT,ap TEXT DEFAULT '0',mined TEXT DEFAULT '0',
        level INTEGER DEFAULT 1,spoon INTEGER DEFAULT 1,hunger INTEGER DEFAULT 0,
        last_mine REAL,last_food REAL DEFAULT 0,last_aboul REAL DEFAULT 0,
        bank TEXT DEFAULT '0',account TEXT UNIQUE,created REAL);
        CREATE TABLE IF NOT EXISTS tx(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,kind TEXT,amount TEXT,note TEXT,ts REAL);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);""")
        c.commit()
    if not q("SELECT 1 FROM settings WHERE key=?",("hunger_zero_migrated",),True):
        q("UPDATE users SET hunger=0")
        q("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",("hunger_zero_migrated",))

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
    n=Decimal(str(x))
    if n == n.to_integral(): return f'{int(n):,}'
    return f'{n:.2f}'.rstrip('0').rstrip('.')

def fmt_time(seconds):
    seconds=max(0,int(seconds)); return f'{seconds//60}:{seconds%60:02d}'

def rk(m): return {'reply_to_message_id':m.message_id}

def profile_kb(uid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='⬆️ ارتقای ابولی',callback_data=f'u:{uid}:upgrade_abouli'),InlineKeyboardButton(text='🥄 ارتقای قاشق',callback_data=f'u:{uid}:upgrade_spoon')],
        [InlineKeyboardButton(text='💰 برداشت پوینت‌های ماین‌شده',callback_data=f'u:{uid}:claim')]
    ])

def upgrade_abouli_kb(uid):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='⬆️ ارتقای ابولی',callback_data=f'u:{uid}:buy_abouli')],[InlineKeyboardButton(text='🔙 پروف ابولی',callback_data=f'u:{uid}:profile')]])

def upgrade_spoon_kb(uid):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='⬆️ ارتقای قاشق',callback_data=f'u:{uid}:buy_spoon')],[InlineKeyboardButton(text='🔙 پروف ابولی',callback_data=f'u:{uid}:profile')]])

def bank_kb(uid):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='💰 واریز',callback_data=f'u:{uid}:bank_deposit'),InlineKeyboardButton(text='💸 برداشت',callback_data=f'u:{uid}:bank_withdraw')],[InlineKeyboardButton(text='🔁 انتقال',callback_data=f'u:{uid}:bank_transfer')]])

def bank_confirm_kb(uid):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='✅ بله',callback_data=f'u:{uid}:bank_confirm_yes'),InlineKeyboardButton(text='❌ نه',callback_data=f'u:{uid}:bank_confirm_no')]])

def bank_text(uid):
    r=user(uid)
    return f'🏦 بانک ابولی 🏦\n\n💳 شماره حساب : {r[11]}\n👤 به نام : {r[1]}\n\n💰 موجودی بانک : {fmt_num(r[10])} ابولی'

async def profile_text(uid):
    mine(uid); r=user(uid)
    status='⛏️ فعال' if int(r[6])>0 and d(r[3])<CAP else '⛔ متوقف'
    return (f'🐮 پروف ابولی\n\n👤 {r[1]}\n⭐️ سطح ابولی: {r[4]}/10\n🥄 سطح قاشق: {r[5]}/10\n🥣 شکم: {r[6]}/10\n\n{status}\n⚡ سرعت ماین: {fmt_num(RATE[int(r[4])])} ابولی/s\n🪙 ماین‌شده: {fmt_num(r[3])}\n💰 موجودی ابولی: {fmt_num(r[2])}\n🎁 پاداش هر «ابول»: {fmt_num(ABOULI_REWARD[int(r[4])])}')


@dp.message(CommandStart())
async def start(m:Message):
    user(m.from_user.id,m.from_user.full_name)
    await m.answer('🐮 به ابولی خوش اومدی!\n\nابول\nپروف ابولی\nارتقای قاشق\nبانک ابولی',**rk(m))

@dp.message(F.text=='ابول')
async def aboul(m:Message):
    r=user(m.from_user.id,m.from_user.full_name); left=300-(time.time()-float(r[9]))
    if left>0:
        await m.answer(f'⏳ هنوز {fmt_time(left)} مونده تا دوباره ابول بگیری.',**rk(m)); return
    level=int(r[4]); reward=ABOULI_REWARD[level]; now=time.time()
    q('UPDATE users SET ap=CAST(ap AS REAL)+?,last_aboul=? WHERE user_id=?',(reward,now,m.from_user.id))
    q('INSERT INTO tx(user_id,kind,amount,note,ts) VALUES(?,?,?,?,?)',(m.from_user.id,'aboul',str(reward),'دستور ابول',now))
    r=user(m.from_user.id,m.from_user.full_name)
    await m.answer(f'🐮 شما یک ابول گرفتید!\n\n⭐️ سطح ابولی: {level}/10\n🪙 پاداش: {fmt_num(reward)} ابول پوینت\n💰 ابول پوینت هات: {fmt_num(r[2])}\n⏳ بعد از ۵ دقیقه میتونی دوباره ابول بگیری',**rk(m))

@dp.message(F.text.in_(PROFILE_ALIASES))
async def profile(m:Message):
    await m.answer(await profile_text(m.from_user.id),reply_markup=profile_kb(m.from_user.id),**rk(m))

@dp.message(F.text=='غذا')
async def food(m:Message):
    mine(m.from_user.id); r=user(m.from_user.id,m.from_user.full_name); left=cd(r[5])-(time.time()-float(r[8]))
    if left>0:
        await m.answer(f'🍽️ هنوز {fmt_time(left)} تا غذای بعدی مونده.',**rk(m)); return
    f=random.choices(FOODS,weights=[x[1] for x in FOODS])[0]; new=min(10,int(r[6])+f[2]); now=time.time()
    q('UPDATE users SET hunger=?,last_food=? WHERE user_id=?',(new,now,m.from_user.id))
    await m.answer(f'🍖 ابولی غذا گرفت!\n\n🍽️ غذا: {f[0]}\n❤️ سیری: +{f[2]}\n🥣 شکم: {r[6]}/10 → {new}/10\n⏱️ غذای بعدی: {int(cd(r[5])/60)} دقیقه',**rk(m))

async def show_abouli_upgrade(c):
    r=user(c.from_user.id); level=int(r[4])
    if level>=10: text='⭐️ ابولی به حداکثر سطح ۱۰ رسیده.'
    else:
        n=level+1; text=f'⭐️ ارتقای ابولی\n\nسطح فعلی: {level}/10\nسطح بعدی: {n}/10\n💰 هزینه: {fmt_num(ABOULI_COST[n])} AP\n🎁 پاداش فعلی: {fmt_num(ABOULI_REWARD[level])}\n🎁 پاداش بعدی: {fmt_num(ABOULI_REWARD[n])}'
    await c.message.edit_text(text,reply_markup=upgrade_abouli_kb(c.from_user.id))

async def buy_abouli(c):
    r=user(c.from_user.id); level=int(r[4])
    if level>=10: text='⭐️ ابولی از قبل در بالاترین سطحه.'
    else:
        n=level+1; cost=d(ABOULI_COST[n]); bal=d(r[2])
        if bal<cost: text=f'❌ ابول پوینت کافی نداری.\n\n💰 موجودی: {fmt_num(bal)}\n💳 هزینه: {fmt_num(cost)}\n📉 کمبود: {fmt_num(cost-bal)}'
        else:
            q('UPDATE users SET ap=?,level=? WHERE user_id=?',(str(bal-cost),n,c.from_user.id))
            text=f'🎉 ابولی به سطح {n} ارتقا پیدا کرد!\n\n💰 هزینه: {fmt_num(cost)}\n🎁 پاداش هر ابول: {fmt_num(ABOULI_REWARD[n])}\n⚡ سرعت ماین: {fmt_num(RATE[n])} AP/s'
    await c.message.edit_text(text,reply_markup=upgrade_abouli_kb(c.from_user.id))

async def show_spoon_upgrade(c):
    r=user(c.from_user.id); level=int(r[5])
    if level>=10: text='🥄 قاشق ابولی به حداکثر سطح ۱۰ رسیده.'
    else:
        n=level+1; text=f'🥄 ارتقای قاشق\n\nسطح فعلی: {level}/10\nسطح بعدی: {n}/10\n💰 هزینه: {fmt_num(SPOON_COST[n])} AP\n🍽️ زمان غذا: {60-(n-1)*5} دقیقه'
    await c.message.edit_text(text,reply_markup=upgrade_spoon_kb(c.from_user.id))

async def buy_spoon(c):
    r=user(c.from_user.id); level=int(r[5])
    if level>=10: text='🥄 قاشق ابولی از قبل در بالاترین سطحه.'
    else:
        n=level+1; cost=d(SPOON_COST[n]); bal=d(r[2])
        if bal<cost: text=f'❌ ابول پوینت کافی نداری.\n\n💰 موجودی: {fmt_num(bal)}\n💳 هزینه: {fmt_num(cost)}\n📉 کمبود: {fmt_num(cost-bal)}'
        else:
            q('UPDATE users SET ap=?,spoon=? WHERE user_id=?',(str(bal-cost),n,c.from_user.id))
            text=f'🎉 قاشق به سطح {n} ارتقا پیدا کرد!\n\n💰 هزینه: {fmt_num(cost)}\n🍽️ زمان غذای بعدی: {60-(n-1)*5} دقیقه'
    await c.message.edit_text(text,reply_markup=upgrade_spoon_kb(c.from_user.id))

@dp.message(F.text=='ارتقای قاشق')
async def spoon(m:Message):
    c=type('C',(),{'from_user':m.from_user,'message':m})(); await show_spoon_upgrade(c)

@dp.message(F.text.startswith('ارتقای قاشق '))
async def spoon_buy_old(m:Message):
    await spoon(m)

@dp.message(F.text=='بانک ابولی')
async def bank(m:Message):
    user(m.from_user.id,m.from_user.full_name)
    await m.answer(bank_text(m.from_user.id),reply_markup=bank_kb(m.from_user.id),**rk(m))

async def money_op(m,kind):
    r=user(m.from_user.id,m.from_user.full_name); p=m.text.split()
    if len(p)!=2: await m.answer(f'فرمت: {kind} 5000',**rk(m)); return
    try:a=d(p[1])
    except: await m.answer('❌ مقدار نامعتبر.',**rk(m)); return
    if a<=0: await m.answer('❌ مقدار باید بیشتر از صفر باشد.',**rk(m)); return
    if kind=='واریز':
        if d(r[2])<a: await m.answer('❌ موجودی اصلی کافی نیست.',**rk(m)); return
        q('UPDATE users SET ap=?,bank=? WHERE user_id=?',(str(d(r[2])-a),str(d(r[10])+a),m.from_user.id))
    else:
        if d(r[10])<a: await m.answer('❌ موجودی بانک کافی نیست.',**rk(m)); return
        q('UPDATE users SET ap=?,bank=? WHERE user_id=?',(str(d(r[2])+a),str(d(r[10])-a),m.from_user.id))
    await m.answer(f'✅ {fmt_num(a)} AP {"واریز شد" if kind=="واریز" else "برداشت شد"}.',**rk(m))

@dp.message(F.text.startswith('واریز '))
async def dep(m:Message): await money_op(m,'واریز')
@dp.message(F.text.startswith('برداشت '))
async def wit(m:Message): await money_op(m,'برداشت')
@dp.message(F.text.startswith('انتقال '))
async def transfer(m:Message):
    p=m.text.split()
    if len(p)!=3 or not p[1].isdigit(): await m.answer('فرمت: انتقال [شماره حساب] [مقدار]',**rk(m)); return
    try:a=d(p[2])
    except: await m.answer('❌ مقدار نامعتبر.',**rk(m)); return
    if a<=0: await m.answer('❌ مقدار نامعتبر.',**rk(m)); return
    s=user(m.from_user.id,m.from_user.full_name); r=q('SELECT * FROM users WHERE account=?',(p[1],),True)
    if not r: await m.answer('❌ شماره حساب پیدا نشد.',**rk(m)); return
    if d(s[10])<a: await m.answer('❌ موجودی بانک کافی نیست.',**rk(m)); return
    q('UPDATE users SET bank=? WHERE user_id=?',(str(d(s[10])-a),s[0])); q('UPDATE users SET bank=? WHERE user_id=?',(str(d(r[10])+a),r[0]))
    await m.answer(f'✅ {fmt_num(a)} AP به حساب {p[1]} منتقل شد.',**rk(m))

@dp.message(F.text=='تراکنش‌ها')
async def tx(m:Message):
    rows=q('SELECT kind,amount,note FROM tx WHERE user_id=? ORDER BY id DESC LIMIT 10',(m.from_user.id,)); body='\n'.join(f'• {x[0]}: {fmt_num(x[1])} AP — {x[2]}' for x in rows) if rows else 'تراکنشی نیست.'
    await m.answer('🧾 تراکنش‌ها\n\n'+body,**rk(m))

@dp.callback_query(F.data.startswith('u:'))
async def callbacks(c:CallbackQuery):
    parts=(c.data or '').split(':')
    if len(parts)!=3:
        await c.answer('دکمه نامعتبر است.',show_alert=True); return
    try: owner=int(parts[1])
    except ValueError:
        await c.answer('دکمه نامعتبر است.',show_alert=True); return
    if owner != c.from_user.id:
        await c.answer('❌ این دکمه برای شما نیست.',show_alert=True); return
    action=parts[2]
    uid=c.from_user.id
    if action=='profile':
        await c.answer(); await c.message.edit_text(await profile_text(uid),reply_markup=profile_kb(uid)); return
    if action=='upgrade_abouli':
        await c.answer(); await show_abouli_upgrade(c); return
    if action=='buy_abouli':
        await c.answer(); await buy_abouli(c); return
    if action=='upgrade_spoon':
        await c.answer(); await show_spoon_upgrade(c); return
    if action=='buy_spoon':
        await c.answer(); await buy_spoon(c); return
    if action=='claim':
        r=user(uid); mined=d(r[3])
        if mined<=0:
            text='⛏️ فعلاً پوینت ماین‌شده‌ای برای برداشت نداری.'
        else:
            q('UPDATE users SET ap=CAST(ap AS REAL)+?,mined=\'0\',last_mine=? WHERE user_id=?',(str(mined),time.time(),uid))
            text=f'✅ {fmt_num(mined)} ابولی ماین‌شده به موجودی منتقل شد.\n\n⛏️ ماین‌شده فعلی: 0'
        await c.answer(); await c.message.edit_text(text,reply_markup=profile_kb(uid)); return
    if action=='bank':
        await c.answer(); await c.message.edit_text(bank_text(uid),reply_markup=bank_kb(uid)); return
    if action in {'bank_deposit','bank_withdraw'}:
        await c.answer()
        kind='deposit' if action=='bank_deposit' else 'withdraw'
        PENDING_BANK[uid]={'kind':kind,'chat_id':c.message.chat.id,'message_id':c.message.message_id}
        title='واریز' if kind=='deposit' else 'برداشت'
        await c.message.edit_text(f'🏦 بانک ابولی 🏦\n\n💳 شماره حساب : {user(uid)[11]}\n👤 به نام : {user(uid)[1]}\n\n🔢 مقدار {title} را در یک پیام بفرستید.')
        return
    if action=='bank_transfer':
        await c.answer('برای انتقال: انتقال [شماره حساب] [مقدار]',show_alert=True); return
    if action in {'bank_confirm_yes','bank_confirm_no'}:
        await c.answer()
        pending=PENDING_BANK.pop(uid,None)
        if action=='bank_confirm_no' or not pending or 'amount' not in pending:
            await c.message.edit_text(bank_text(uid),reply_markup=bank_kb(uid)); return
        amount=pending['amount']; r=user(uid,c.from_user.full_name)
        if pending['kind']=='deposit':
            if d(r[2])<amount:
                await c.message.edit_text(f'❌ موجودی ابولی کافی نیست.\n\n💰 موجودی: {fmt_num(r[2])} ابولی\n💳 مبلغ درخواستی: {fmt_num(amount)} ابولی',reply_markup=bank_kb(uid)); return
            q('UPDATE users SET ap=?,bank=? WHERE user_id=?',(str(d(r[2])-amount),str(d(r[10])+amount),uid))
        else:
            if d(r[10])<amount:
                await c.message.edit_text(f'❌ موجودی بانک کافی نیست.\n\n🏦 موجودی بانک: {fmt_num(r[10])} ابولی\n💳 مبلغ درخواستی: {fmt_num(amount)} ابولی',reply_markup=bank_kb(uid)); return
            q('UPDATE users SET ap=?,bank=? WHERE user_id=?',(str(d(r[2])+amount),str(d(r[10])-amount),uid))
        await c.message.edit_text(bank_text(uid),reply_markup=bank_kb(uid)); return
    await c.answer('دکمه نامعتبر است.',show_alert=True)

@dp.message(F.text)
async def pending_bank_amount(m:Message):
    pending = PENDING_BANK.get(m.from_user.id)
    if not pending:
        return
    raw = (m.text or '').strip()
    try:
        amount = d(raw)
    except Exception:
        return
    if amount <= 0:
        return

    kind = pending['kind']
    PENDING_BANK[m.from_user.id] = {**pending, 'amount': amount}
    title = 'واریز' if kind == 'deposit' else 'برداشت'
    text = f'🏦 بانک ابولی 🏦\n\n💳 شماره حساب : {user(m.from_user.id)[11]}\n👤 به نام : {user(m.from_user.id)[1]}\n\n❓ آیا از {title} {fmt_num(amount)} ابولی به حساب بانکی خود اطمینان دارید ؟'
    try:
        await m.bot.edit_message_text(chat_id=pending['chat_id'], message_id=pending['message_id'], text=text, reply_markup=bank_confirm_kb(m.from_user.id))
    except Exception:
        PENDING_BANK.pop(m.from_user.id, None)

@dp.callback_query(F.data=='bank_confirm_no')
async def cb_bank_no(c:CallbackQuery):
    await c.answer()
    PENDING_BANK.pop(c.from_user.id, None)
    await c.message.edit_text(bank_text(c.from_user.id), reply_markup=bank_kb(c.from_user.id))

@dp.callback_query(F.data=='bank_confirm_yes')
async def cb_bank_yes(c:CallbackQuery):
    await c.answer()
    pending = PENDING_BANK.pop(c.from_user.id, None)
    if not pending or 'amount' not in pending:
        await c.message.edit_text(bank_text(c.from_user.id), reply_markup=bank_kb(c.from_user.id))
        return

    amount = pending['amount']; r = user(c.from_user.id, c.from_user.full_name)
    if pending['kind'] == 'deposit':
        if d(r[2]) < amount:
            await c.message.edit_text(f'❌ موجودی اصلی کافی نیست.\n\n💰 موجودی: {fmt_num(r[2])} AP\n💳 مبلغ درخواستی: {fmt_num(amount)} AP', reply_markup=bank_kb(c.from_user.id))
            return
        q('UPDATE users SET ap=?,bank=? WHERE user_id=?',(str(d(r[2])-amount),str(d(r[10])+amount),c.from_user.id))
    else:
        if d(r[10]) < amount:
            await c.message.edit_text(f'❌ موجودی بانک کافی نیست.\n\n🏦 موجودی بانک: {fmt_num(r[10])} AP\n💳 مبلغ درخواستی: {fmt_num(amount)} AP', reply_markup=bank_kb(c.from_user.id))
            return
        q('UPDATE users SET ap=?,bank=? WHERE user_id=?',(str(d(r[2])+amount),str(d(r[10])-amount),c.from_user.id))
    await c.message.edit_text(bank_text(c.from_user.id), reply_markup=bank_kb(c.from_user.id))

@dp.message(F.text.startswith('حذف پوینت '))
async def remove(m:Message):
    if m.from_user.id!=ADMIN_ID:return
    p=m.text.split()
    if len(p)!=3 or not p[1].isdigit(): await m.answer('فرمت: حذف پوینت [ID] [مقدار]',**rk(m)); return
    try:a=d(p[2])
    except: await m.answer('❌ مقدار نامعتبر.',**rk(m)); return
    r=user(int(p[1]))
    if a<=0 or d(r[2])<a: await m.answer('❌ مقدار نامعتبر یا موجودی ناکافی.',**rk(m)); return
    q('UPDATE users SET ap=? WHERE user_id=?',(str(d(r[2])-a),r[0])); await m.answer(f'✅ {fmt_num(a)} AP حذف شد.',**rk(m))
@dp.message(F.text.startswith('اضافه پوینت '))
async def add(m:Message):
    if m.from_user.id!=ADMIN_ID:return
    p=m.text.split()
    if len(p)!=3 or not p[1].isdigit(): await m.answer('فرمت: اضافه پوینت [ID] [مقدار]',**rk(m)); return
    try:a=d(p[2])
    except: await m.answer('❌ مقدار نامعتبر.',**rk(m)); return
    if a<=0: await m.answer('❌ مقدار نامعتبر.',**rk(m)); return
    r=user(int(p[1])); q('UPDATE users SET ap=? WHERE user_id=?',(str(d(r[2])+a),r[0])); await m.answer(f'✅ {fmt_num(a)} AP اضافه شد.',**rk(m))

@dp.message(F.text.startswith('افزایش ابول پوینت '))
async def admin_add_reply(m:Message):
    if m.from_user.id!=ADMIN_ID: return
    if not m.reply_to_message or not m.reply_to_message.from_user:
        await m.answer('❌ باید روی پیام کاربر ریپلای کنی.',**rk(m)); return
    p=m.text.split()
    if len(p)!=4:
        await m.answer('فرمت: افزایش ابول پوینت [مقدار]',**rk(m)); return
    try:a=d(p[3])
    except: await m.answer('❌ مقدار نامعتبر.',**rk(m)); return
    if a<=0: await m.answer('❌ مقدار باید بیشتر از صفر باشد.',**rk(m)); return
    target=m.reply_to_message.from_user; r=user(target.id,target.full_name)
    q('UPDATE users SET ap=? WHERE user_id=?',(str(d(r[2])+a),target.id))
    await m.answer(f'✅ {fmt_num(a)} ابولی به {target.full_name} اضافه شد.',**rk(m))

@dp.message(F.text.startswith('کاهش ابول پوینت '))
async def admin_remove_reply(m:Message):
    if m.from_user.id!=ADMIN_ID: return
    if not m.reply_to_message or not m.reply_to_message.from_user:
        await m.answer('❌ باید روی پیام کاربر ریپلای کنی.',**rk(m)); return
    p=m.text.split()
    if len(p)!=4:
        await m.answer('فرمت: کاهش ابول پوینت [مقدار]',**rk(m)); return
    try:a=d(p[3])
    except: await m.answer('❌ مقدار نامعتبر.',**rk(m)); return
    if a<=0: await m.answer('❌ مقدار باید بیشتر از صفر باشد.',**rk(m)); return
    target=m.reply_to_message.from_user; r=user(target.id,target.full_name)
    if d(r[2])<a:
        await m.answer(f'❌ موجودی ابولی کاربر کافی نیست. موجودی: {fmt_num(r[2])}',**rk(m)); return
    q('UPDATE users SET ap=? WHERE user_id=?',(str(d(r[2])-a),target.id))
    await m.answer(f'✅ {fmt_num(a)} ابولی از {target.full_name} کم شد.',**rk(m))

async def interest():
    done=None
    while True:
        t=time.localtime(); key=time.strftime("%Y-%m-%d",t)
        if t.tm_hour==7 and t.tm_min==0 and done!=key:
            for uid,b in q("SELECT user_id,bank FROM users WHERE CAST(bank AS REAL)>0"):
                x=d(b); i=x*d(".03"); q("UPDATE users SET bank=? WHERE user_id=?",(str(x+i),uid))
            done=key
        await asyncio.sleep(20)

async def is_channel_member(bot,uid):
    try:
        member=await bot.get_chat_member(CHANNEL_USERNAME,uid)
        if member.status in {'creator','administrator','member'}: return True
        if member.status=='restricted': return bool(getattr(member,'is_member',False))
    except Exception:
        pass
    return False

def join_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='📢 عضویت در کانال',url=CHANNEL_URL)]])

class MembershipMiddleware(BaseMiddleware):
    async def __call__(self,handler,event,data):
        if isinstance(event,Message) and not await is_channel_member(event.bot,event.from_user.id):
            await event.answer('🔒 برای بازی کردن در کانال عضو شوید',reply_markup=join_kb())
            return
        return await handler(event,data)

dp.message.outer_middleware(MembershipMiddleware())

async def health(request):
    return web.Response(text='OK')

async def run_web_server():
    port=int(os.getenv('PORT','10000'))
    app=web.Application()
    app.router.add_get('/',health)
    app.router.add_get('/health',health)
    runner=web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner,'0.0.0.0',port).start()

async def main():
    if not TOKEN: raise RuntimeError("BOT_TOKEN is required")
    init(); asyncio.create_task(interest())
    await run_web_server()
    bot=Bot(TOKEN,default=DefaultBotProperties(parse_mode="HTML"))
    await dp.start_polling(bot)

if __name__=="__main__": asyncio.run(main())
