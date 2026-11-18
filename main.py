import os
import sys
import logging
import random
import asyncio
import sqlite3
import aiohttp
from datetime import datetime, timedelta
from threading import Thread
from flask import Flask

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup,
    InlineKeyboardButton, ChatPermissions, LabeledPrice, PreCheckoutQuery
)
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

# ==========================================
# 0. ВЕБ-СЕРВЕР ДЛЯ РАЗВЕРТЫВАНИЯ (RENDER 24/7)
# ==========================================
app = Flask('')

@app.route('/')
def home():
    return "Stars Manager Bot is active 24/7!"

@app.route('/healthz')
def healthz():
    return "OK", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask, daemon=True)
    t.start()

keep_alive()

# ==========================================
# 1. НАСТРОЙКИ И БАЗА ДАННЫХ
# ==========================================
logging.basicConfig(level=logging.INFO)

API_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")
MONOBANK_JAR = "https://send.monobank.ua/jar/8wVnXzoF3f"
CARD_DETAILS = "4441 0000 0000 0000"
OWNER_USERNAME = "nlyxx2686"
OWNER_ID = int(os.getenv("OWNER_ID", "123456789"))

ADMIN_IDS = [OWNER_ID]

bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

conn = sqlite3.connect("bot_database.db", check_same_thread=False)
cursor = conn.cursor()

def clean_username(username: str) -> str:
    if not username:
        return ""
    return username.replace("@", "").strip().lower()

def init_db():
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT UNIQUE,
        lang TEXT DEFAULT 'ru',
        rank INTEGER DEFAULT 0,
        roles TEXT DEFAULT '',
        coins INTEGER DEFAULT 100,
        exp INTEGER DEFAULT 0,
        level INTEGER DEFAULT 1,
        rep INTEGER DEFAULT 0,
        streak INTEGER DEFAULT 0,
        last_bonus TEXT,
        rep_given_today INTEGER DEFAULT 0,
        last_rep_date TEXT,
        vip_until TEXT,
        msg_count INTEGER DEFAULT 0,
        duel_wins INTEGER DEFAULT 0,
        custom_nickname TEXT,
        muted_until TEXT,
        rep_muted_until TEXT,
        warns INTEGER DEFAULT 0,
        gwarns INTEGER DEFAULT 0,
        role TEXT DEFAULT 'User',
        zdkd INTEGER DEFAULT 0,
        last_active TEXT,
        last_command TEXT,
        total_donated_uah INTEGER DEFAULT 0,
        total_donated_stars INTEGER DEFAULT 0,
        assigned_date TEXT,
        assigned_by TEXT,
        purchased_role TEXT DEFAULT '0'
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS global_bans (
        user_id INTEGER PRIMARY KEY,
        reason TEXT,
        by_user TEXT
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS global_warns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        reason TEXT,
        by_user TEXT
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS custom_roles (
        role_id INTEGER PRIMARY KEY AUTOINCREMENT,
        creator_id INTEGER,
        chat_id INTEGER,
        text TEXT,
        color_code TEXT,
        price INTEGER DEFAULT 0,
        monthly_income INTEGER DEFAULT 0
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS user_roles_owned (
        user_id INTEGER,
        role_id INTEGER
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER,
        user_id INTEGER,
        target_id INTEGER,
        text TEXT,
        status TEXT DEFAULT 'pending',
        assigned_role INTEGER DEFAULT 0
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS chat_settings (
        chat_id INTEGER PRIMARY KEY,
        rules TEXT DEFAULT '',
        shop_exp_rate INTEGER DEFAULT 10
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS logs_access (
        user_id INTEGER PRIMARY KEY,
        level INTEGER DEFAULT 0
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS known_chats (
        chat_id INTEGER PRIMARY KEY,
        chat_title TEXT
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS pending_vip_orders (
        order_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        period TEXT,
        price TEXT,
        currency TEXT,
        date TEXT
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS pending_money_orders (
        order_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        coins INTEGER,
        price TEXT,
        currency TEXT,
        date TEXT
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS vip_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        price TEXT,
        currency TEXT,
        period TEXT,
        reason TEXT,
        date TEXT
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS donats_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        type TEXT,
        amount TEXT,
        currency TEXT,
        date TEXT
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS blago_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        amount TEXT,
        currency TEXT,
        status TEXT DEFAULT 'pending',
        date TEXT
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS tex_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        date TEXT
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS obgban_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        reason TEXT,
        date TEXT
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS obgwarn_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        reason TEXT,
        date TEXT
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS global_news_table (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        news_text TEXT
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS action_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action_text TEXT,
        date TEXT
    )''')

    conn.commit()

init_db()

def get_user(user_id: int = None, username: str = ""):
    row = None
    u_clean = clean_username(username)

    if user_id:
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
    elif u_clean:
        cursor.execute("SELECT * FROM users WHERE LOWER(username) = ?", (u_clean,))
        row = cursor.fetchone()

    if not row and user_id:
        rank = 10 if user_id == OWNER_ID or (u_clean and u_clean == OWNER_USERNAME.lower()) else 0
        role = 'Owner' if rank == 10 else 'User'
        cursor.execute(
            "INSERT INTO users (user_id, username, rank, role, coins) VALUES (?, ?, ?, ?, ?)",
            (user_id, u_clean, rank, role, 100)
        )
        conn.commit()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
    elif row and u_clean and row[1] != u_clean:
        cursor.execute("UPDATE users SET username = ? WHERE user_id = ?", (u_clean, row[0]))
        conn.commit()

    return row

def update_user(user_id: int, **kwargs):
    fields = ", ".join([f"{k} = ?" for k in kwargs.keys()])
    values = list(kwargs.values()) + [user_id]
    cursor.execute(f"UPDATE users SET {fields} WHERE user_id = ?", values)
    conn.commit()

def is_vip(user_row) -> bool:
    if not user_row or not user_row[13]:
        return False
    if user_row[13] == 'forever':
        return True
    try:
        until = datetime.strptime(user_row[13], "%Y-%m-%d %H:%M:%S")
        return datetime.now() < until
    except Exception:
        return False

def check_gban(user_id: int) -> bool:
    if user_id == OWNER_ID: return False
    cursor.execute("SELECT 1 FROM global_bans WHERE user_id = ?", (user_id,))
    return cursor.fetchone() is not None

def log_action(user_id: int, text: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO action_logs (user_id, action_text, date) VALUES (?, ?, ?)", (user_id, text, now))
    conn.commit()

# ==========================================
# 2. FSM СОСТОЯНИЯ И ПРАЙС-ЛИСТЫ
# ==========================================
class BlagoState(StatesGroup):
    waiting_for_username = State()

class ObgbanState(StatesGroup):
    waiting_for_reason = State()

class ObgwarnState(StatesGroup):
    waiting_for_reason = State()

PRICES_UAH = {
    "1": {"price": 30, "text": "1 месяц — 30 грн"},
    "3": {"price": 75, "text": "3 месяца — 75 грн"},
    "6": {"price": 130, "text": "6 месяцев — 130 грн"},
    "12": {"price": 210, "text": "12 месяцев — 210 грн"},
    "forever": {"price": 500, "text": "Навсегда — 500 грн"},
}

STARS_PACKS = [1, 5, 10, 20, 25, 50, 100, 150, 200, 250, 300, 500, 1000]

# ==========================================
# 3. МИДДЛВАРИ
# ==========================================
@dp.message.middleware()
async def global_middleware(handler, event: Message, data):
    if not event.from_user:
        return await handler(event, data)

    user_id = event.from_user.id
    username = event.from_user.username or ""

    if event.chat.type in ['group', 'supergroup']:
        cursor.execute("INSERT OR REPLACE INTO known_chats (chat_id, chat_title) VALUES (?, ?)",
                       (event.chat.id, event.chat.title or "Group"))
        conn.commit()

    if event.new_chat_members:
        for member in event.new_chat_members:
            if member.id == (await bot.me()).id:
                update_user(user_id, rank=6, role="Главный Администратор (ГА)")
                await event.answer(f"👑 Пользователь @{username or user_id} пригласил бота в группу и автоматически получил права <b>Главного Администратора (ГА, 6 уровень)</b>!", parse_mode="HTML")

    if user_id != OWNER_ID and check_gban(user_id):
        try:
            await bot.ban_chat_member(event.chat.id, user_id)
            await event.answer(f"🚨 Пользователь @{username or user_id} имеет <b>GBAN</b> и был удалён из чата!", parse_mode="HTML")
        except Exception:
            pass
        return

    user = get_user(user_id=user_id, username=username)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    last_cmd = event.text if event.text else "Сообщение/Медиа"

    cursor.execute(
        "UPDATE users SET msg_count = msg_count + 1, last_active = ?, last_command = ? WHERE user_id = ?",
        (now_str, last_cmd, user_id)
    )
    conn.commit()

    return await handler(event, data)

# ==========================================
# 4. ОСНОВНЫЕ КОМАНДЫ И УПРАВЛЕНИЕ
# ==========================================
@dp.message(Command("start"))
async def cmd_start(message: Message, command: CommandObject):
    user_id = message.from_user.id
    username = message.from_user.username

    if message.chat.type in ['group', 'supergroup'] and command.args == "owner":
        update_user(user_id, rank=6, role="Главный Администратор (ГА)")
        await message.answer("👑 Вы назначены Главным Администратором (ГА) этой группы за приглашение бота!")
        return

    if not username:
        return await message.answer("⚠️ У вас не установлен Username в Настройках Telegram! Установите его, чтобы пользоваться ботом.")

    user = get_user(user_id=user_id, username=username)
    await message.answer(f"Привет снова, @{clean_username(username)}! Ваш баланс: {user[5]} монет.", parse_mode="Markdown")

@dp.message(Command("stats"))
async def cmd_stats(message: Message, command: CommandObject):
    target = message.from_user
    if command.args:
        arg = command.args.split()[0]
        u_row = get_user(user_id=int(arg)) if arg.isdigit() else get_user(username=clean_username(arg))
        if not u_row:
            return await message.answer("❌ Пользователь не найден.")
    else:
        u_row = get_user(user_id=target.id, username=target.username or "")

    uid, uname, lang, rank, roles, coins, exp, level, rep, streak, last_bonus, rep_given, last_rep, vip, msgs, duels, nickname, muted, rep_muted, warns, gwarns, role, zdkd, l_active, l_cmd, d_uah, d_stars, a_date, a_by, p_role = u_row[:30]
    
    text = (
        f"📊 <b>Статистика пользователя @{uname or uid}:</b>

"
        f"💰 Монеты: <b>{coins}</b>
"
        f"🏷 Кастомный ник: <b>{nickname or 'Не установлен'}</b>
"
        f"📈 Уровень: <b>{level}</b> (EXP: {exp})
"
        f"🛡 Админ-права / Роль: <b>{role}</b> (Ранг: {rank})
"
        f"🛒 Купленная роль: <b>{p_role if p_role != '0' else 'Отсутствует'}</b>"
    )
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("pin"))
async def cmd_pin(message: Message):
    if not message.reply_to_message:
        return await message.answer("⚠️ Ответьте на сообщение, которое нужно закрепить.")
    try:
        await message.chat.pin_message(message.reply_to_message.message_id)
        await message.answer("📌 Сообщение закреплено!")
    except Exception as e:
        await message.answer(f"❌ Ошибка закрепления: {e}")

@dp.message(Command("shop"))
async def cmd_shop(message: Message, command: CommandObject):
    args = command.args.split() if command.args else []
    if not args or not args[0].isdigit():
        return await message.answer("🛍 <b>Магазин:</b> обмен монет на EXP (курс: 1 EXP = 100 монет).
Использование: <code>/shop [количество_exp]</code>", parse_mode="HTML")
    
    exp_buy = int(args[0])
    cost = exp_buy * 100
    uid = message.from_user.id
    user = get_user(user_id=uid)

    if user[5] < cost:
        return await message.answer(f"❌ Недостаточно монет! Нужно {cost} монет (у вас {user[5]}).")

    new_coins = user[5] - cost
    new_exp = user[6] + exp_buy
    lvl = user[7]

    def needed_exp(l):
        if l <= 15: return 250
        elif l <= 30: return 1500
        elif l <= 50: return 10000
        return 25000

    need = needed_exp(lvl)
    while new_exp >= need:
        new_exp -= need
        lvl += 1
        need = needed_exp(lvl)

    update_user(uid, coins=new_coins, exp=new_exp, level=lvl)
    await message.answer(f"✅ Успешно куплено {exp_buy} EXP за {cost} монет!")

@dp.message(Command("snick"))
async def cmd_snick(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 2:
        return await message.answer("❌ Доступно со 2+ ранга.")
    if not message.reply_to_message or not command.args:
        return await message.answer("⚠️ Ответьте на сообщение пользователя и укажите ник: <code>/snick [ник]</code>", parse_mode="HTML")
    
    target_id = message.reply_to_message.from_user.id
    nick = command.args
    update_user(target_id, custom_nickname=nick)
    await message.answer(f"✅ Кастомный ник установлен: {nick}")

@dp.message(Command("rnick"))
async def cmd_rnick(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 2:
        return await message.answer("❌ Доступно со 2+ ранга.")
    if not message.reply_to_message:
        return await message.answer("⚠️ Ответьте на сообщение пользователя.")
    update_user(message.reply_to_message.from_user.id, custom_nickname=None)
    await message.answer("✅ Кастомный ник удален.")

@dp.message(Command("gnick"))
async def cmd_gnick(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 2:
        return await message.answer("❌ Доступно со 2+ ранга.")
    if not message.reply_to_message:
        return await message.answer("⚠️ Ответьте на сообщение пользователя.")
    t = get_user(user_id=message.reply_to_message.from_user.id)
    await message.answer(f"👤 Ник: @{t[1] or 'нет'} | Кастомный ник: {t[16] or 'Нет'}")

@dp.message(Command("staff"))
async def cmd_staff(message: Message):
    cursor.execute("SELECT username, user_id, role, rank FROM users WHERE rank >= 4 ORDER BY rank DESC")
    rows = cursor.fetchall()
    if not rows:
        return await message.answer("🛡️ Администрация 4+ ранга не найдена.")
    text = "🛡️ <b>Администрация (4+ ранг):</b>

"
    for r in rows:
        text += f"• @{r[0] or r[1]} — {r[2]} (Ранг {r[3]})
"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("eshop"))
async def cmd_eshop(message: Message):
    await message.answer("🎁 Магазин подарков от руководства. Следите за общими бонусами через /gbonus!")

@dp.message(Command("myadm"))
async def cmd_myadm(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 10:
        return await message.answer("❌ Доступно с 10 ранга.")
    cursor.execute("SELECT user_id, username, role, rank, assigned_date, assigned_by FROM users WHERE rank >= 8 ORDER BY rank DESC")
    rows = cursor.fetchall()
    text = "👑 <b>Администрация 8-10 рангов:</b>

"
    for r in rows:
        text += f"• @{r[1] or r[0]} (ID: <code>{r[0]}</code>) | {r[2]} (Ранг {r[3]})
  Поставлен: {r[4] or 'Не указано'} | Кем: {r[5] or 'Система'}

"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("vlist"))
async def cmd_vlist(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8:
        return await message.answer("❌ Доступно с 8+ ранга.")
    cursor.execute("SELECT user_id, username, vip_until FROM users WHERE vip_until IS NOT NULL")
    rows = cursor.fetchall()
    if not rows:
        return await message.answer("💎 Нет VIP пользователей.")
    text = "💎 <b>Список VIP:</b>

"
    for r in rows:
        uid, uname, v_date = r
        cursor.execute("SELECT price, currency, period, reason, date FROM vip_history WHERE user_id = ? ORDER BY id DESC LIMIT 1", (uid,))
        h = cursor.fetchone()
        if h:
            text += f"• @{uname or uid} | С {h[5]} по {v_date} | За что: {h[4] or 'Покупка'} ({h[2]} {h[3]})
"
        else:
            text += f"• @{uname or uid} | До: {v_date}
"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("donatslist"))
async def cmd_donatslist(message: Message):
    cursor.execute("SELECT username, user_id, total_donated_uah, total_donated_stars FROM users ORDER BY total_donated_uah DESC LIMIT 10")
    rows = cursor.fetchall()
    text = "🏆 <b>Топ-10 донатеров:</b>

"
    for idx, r in enumerate(rows, 1):
        text += f"{idx}. @{r[0] or r[1]} — {r[2]} грн | {r[3]} ⭐️
"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("news"))
async def cmd_news(message: Message):
    cursor.execute("SELECT news_text FROM global_news_table ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    news = row[0] if row else "Правила не установлены."
    await message.answer(f"📜 <b>Правила бота:</b>

{news}", parse_mode="HTML")

@dp.message(Command("Global_news"))
async def cmd_global_news(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 10:
        return await message.answer("❌ Доступно с 10 ранга.")
    if not command.args:
        return await message.answer("⚠️ Укажите текст правил.")
    cursor.execute("INSERT INTO global_news_table (news_text) VALUES (?)", (command.args,))
    conn.commit()
    await message.answer("✅ Правила успешно обновлены!")

@dp.message(Command("dpromo"))
async def cmd_dpromo(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 10:
        return await message.answer("❌ Доступно с 10 ранга.")
    await message.answer("✅ Промокод удален.")

@dp.message(Command("Buy_role"))
async def cmd_buy_role(message: Message, command: CommandObject):
    uid = message.from_user.id
    user = get_user(user_id=uid)
    if not command.args:
        return await message.answer("🛍 Покупка роли стоит 5000 монет. Использование: <code>/Buy_role [название]</code>", parse_mode="HTML")
    role_name = command.args
    cost = 5000
    if user[5] < cost:
        return await message.answer(f"❌ Нужно {cost} монет!")
    update_user(uid, coins=user[5] - cost, purchased_role=role_name)
    await message.answer(f"🎉 Роль '{role_name}' успешно куплена!")

@dp.message(Command("bonus"))
async def cmd_bonus(message: Message):
    uid = message.from_user.id
    user = get_user(user_id=uid)
    today = datetime.now().strftime("%Y-%m-%d")
    if user[10] == today:
        return await message.answer("⏳ Вы уже получили бонус сегодня!")

    streak = user[9] + 1 if user[10] and (datetime.now() - datetime.strptime(user[10], "%Y-%m-%d")).days == 1 else 1
    
    if random.random() < 0.00001:
        coins = random.randint(2001, 15000)
    else:
        coins = random.randint(100, 2000)
    
    exp = random.randint(150, 7500)
    update_user(uid, coins=user[5] + coins, exp=user[6] + exp, streak=streak, last_bonus=today)
    await message.answer(f"🎁 Бонус получен! 🔥 Серия: {streak} дней
💰 Монеты: +{coins}
📈 EXP: +{exp}")

@dp.message(Command("gbonus"))
async def cmd_gbonus(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8:
        return await message.answer("❌ Доступно с 8+ ранга.")
    if not command.args or not command.args.isdigit():
        return await message.answer("⚠️ Укажите сумму: <code>/gbonus [сумма]</code>", parse_mode="HTML")
    amt = int(command.args)
    cursor.execute("UPDATE users SET coins = coins + ?", (amt,))
    conn.commit()
    await message.answer(f"🎉 Выдан общий бонус всем участникам: {amt} монет!")

@dp.message(Command("duel"))
async def cmd_duel(message: Message, command: CommandObject):
    if not message.reply_to_message or not command.args or not command.args.isdigit():
        return await message.answer("⚠️ Использование: ответьте на сообщение и укажите ставку <code>/duel 100</code> (10-500, с VIP до 1000)", parse_mode="HTML")
    bet = int(command.args)
    u1_id = message.from_user.id
    u2_id = message.reply_to_message.from_user.id

    if u1_id == u2_id:
        return await message.answer("❌ Нельзя играть в дуэль самому с собой!")

    u1 = get_user(user_id=u1_id)
    u2 = get_user(user_id=u2_id)
    max_bet = 1000 if is_vip(u1) else 500
    if bet < 10 or bet > max_bet:
        return await message.answer(f"❌ Неверная ставка (10-{max_bet}).")
    if u1[5] < bet or u2[5] < bet:
        return await message.answer("❌ У кого-то из игроков недостаточно монет!")

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⚔️ Принять дуэль", callback_data=f"duel_play_{u1_id}_{u2_id}_{bet}")
    ]])
    await message.answer(f"⚔️ Дуэль создана! Ставка: {bet} монет. Нажмите кнопку для принятия:", reply_markup=kb)

@dp.callback_query(F.data.startswith("duel_play_"))
async def cb_duel_play(callback: CallbackQuery):
    _, _, u1_str, u2_str, bet_str = callback.data.split("_")
    u1_id, u2_id, bet = int(u1_str), int(u2_str), int(bet_str)
    
    if callback.from_user.id not in [u1_id, u2_id]:
        return await callback.answer("❌ Вы не участник этой дуэли!", show_alert=True)

    u1 = get_user(user_id=u1_id)
    u2 = get_user(user_id=u2_id)
    if u1[5] < bet or u2[5] < bet:
        return await callback.answer("❌ У кого-то недостаточно монет!", show_alert=True)

    v1, v2 = is_vip(u1), is_vip(u2)
    p1 = 55 if v1 and not v2 else (45 if v2 and not v1 else 50)
    winner = random.choices([u1_id, u2_id], weights=[p1, 100 - p1], k=1)[0]
    loser = u2_id if winner == u1_id else u1_id

    w_user = get_user(user_id=winner)
    l_user = get_user(user_id=loser)

    prize = bet * 2 if is_vip(w_user) else int(bet * 2 * 0.95)

    update_user(winner, coins=w_user[5] + prize - bet, duel_wins=w_user[15] + 1)
    update_user(loser, coins=l_user[5] - bet)

    await callback.message.edit_text(f"⚔️ Дуэль завершена! Победитель получил {prize} монет.")

@dp.message(Command("Gban"))
async def cmd_gban(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 9:
        return await message.answer("❌ Доступно с 9+ ранга.")
    args = command.args.split(maxsplit=1) if command.args else []
    if not args:
        return await message.answer("⚠️ Использование: <code>/Gban @username [причина]</code>", parse_mode="HTML")
    target_raw, reason = args[0], (args[1] if len(args) > 1 else "Нарушение")
    target = get_user(user_id=int(target_raw)) if target_raw.isdigit() else get_user(username=clean_username(target_raw))
    if not target:
        return await message.answer("❌ Пользователь не найден.")
    cursor.execute("INSERT OR REPLACE INTO global_bans (user_id, reason, by_user) VALUES (?, ?, ?)", (target[0], reason, message.from_user.username))
    conn.commit()
    await message.answer(f"🚨 Пользователь @{target[1] or target[0]} получил GBAN.
Причина: {reason}")

@dp.message(Command("Gwarn"))
async def cmd_gwarn(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8:
        return await message.answer("❌ Доступно с 8+ ранга.")
    args = command.args.split(maxsplit=1) if command.args else []
    if not args:
        return await message.answer("⚠️ Использование: <code>/Gwarn @username [причина]</code>", parse_mode="HTML")
    target_raw, reason = args[0], (args[1] if len(args) > 1 else "Нарушение")
    target = get_user(user_id=int(target_raw)) if target_raw.isdigit() else get_user(username=clean_username(target_raw))
    if not target:
        return await message.answer("❌ Пользователь не найден.")
    cursor.execute("INSERT INTO global_warns (user_id, reason, by_user) VALUES (?, ?, ?)", (target[0], reason, message.from_user.username))
    conn.commit()
    await message.answer(f"⚠️ Пользователю @{target[1] or target[0]} выдан GWARN.
Причина: {reason}")

@dp.message(Command("Give_money"))
async def cmd_give_money(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 10:
        return await message.answer("❌ Доступно с 10 ранга.")
    args = command.args.split(maxsplit=2) if command.args else []
    if len(args) < 2:
        return await message.answer("⚠️ Использование: <code>/Give_money @username [количество] [причина]</code>", parse_mode="HTML")
    target_raw, amt_str = args[0], args[1]
    reason = args[2] if len(args) > 2 else "Не указана"
    if not amt_str.isdigit():
        return await message.answer("⚠️ Количество должно быть числом.")
    amt = int(amt_str)
    target = get_user(user_id=int(target_raw)) if target_raw.isdigit() else get_user(username=clean_username(target_raw))
    if not target:
        return await message.answer("❌ Пользователь не найден.")
    update_user(target[0], coins=target[5] + amt)
    await message.answer(f"✅ Пользователю @{target[1] or target[0]} выдано {amt} монет.
Причина: {reason}")

@dp.message(Command("unsetzam"))
async def cmd_unsetzam(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 10:
        return await message.answer("❌ Доступно с 10 ранга.")
    args = command.args.split(maxsplit=1) if command.args else []
    if not args:
        return await message.answer("⚠️ Использование: <code>/unsetzam @username [причина]</code>", parse_mode="HTML")
    raw, reason = args[0], (args[1] if len(args) > 1 else "Не указана")
    target = get_user(user_id=int(raw)) if raw.isdigit() else get_user(username=clean_username(raw))
    if not target:
        return await message.answer("❌ Пользователь не найден.")
    update_user(target[0], rank=0, role='User')
    await message.answer(f"📉 С пользователя @{target[1] or target[0]} снят 9 ранг.
Причина: {reason}")

@dp.message(Command("unsetadm"))
async def cmd_unsetadm(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 9:
        return await message.answer("❌ Доступно с 9 ранга.")
    args = command.args.split(maxsplit=1) if command.args else []
    if not args:
        return await message.answer("⚠️ Использование: <code>/unsetadm @username [причина]</code>", parse_mode="HTML")
    raw, reason = args[0], (args[1] if len(args) > 1 else "Не указана")
    target = get_user(user_id=int(raw)) if raw.isdigit() else get_user(username=clean_username(raw))
    if not target:
        return await message.answer("❌ Пользователь не найден.")
    update_user(target[0], rank=0, role='User')
    await message.answer(f"📉 С пользователя @{target[1] or target[0]} снят 8 ранг.
Причина: {reason}")

@dp.message(Command("tops"))
async def cmd_tops(message: Message):
    text = "🌐 <b>Межгрупповые топы проекта:</b>

"
    for title, query in [
        ("🔥 По серии /bonus:", "SELECT username, streak FROM users ORDER BY streak DESC LIMIT 5"),
        ("💰 По монетам:", "SELECT username, coins FROM users ORDER BY coins DESC LIMIT 5"),
        ("📈 По уровню:", "SELECT username, level FROM users ORDER BY level DESC LIMIT 5"),
        ("⚔️ По победам в дуэлях:", "SELECT username, duel_wins FROM users ORDER BY duel_wins DESC LIMIT 5")
    ]:
        cursor.execute(query)
        rows = cursor.fetchall()
        text += f"{title}
"
        for r in rows:
            text += f"• @{r[0] or 'нет'} — {r[1]}
"
        text += "
"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("zayavka"))
async def cmd_zayavka(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8:
        return await message.answer("❌ У вас нет прав на просмотр заявок.")
    cursor.execute("SELECT COUNT(*) FROM tex_requests")
    tex_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM obgban_requests")
    ban_count = cursor.fetchone()[0]
    await message.answer(f"📋 <b>Активные заявки:</b>
• На техника: {tex_count} (/Tlist)
• Обжалований GBAN: {ban_count}", parse_mode="HTML")

@dp.message(Command("Flogs"))
async def cmd_flogs(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8:
        return await message.answer("❌ Доступно с 8+ ранга.")
    if not command.args:
        return await message.answer("⚠️ Укажите пользователя: <code>/Flogs user_id/@username</code>", parse_mode="HTML")
    raw = command.args.split()[0]
    t = get_user(user_id=int(raw)) if raw.isdigit() else get_user(username=clean_username(raw))
    if not t:
        return await message.answer("❌ Пользователь не найден.")
    
    uid, uname = t[0], t[1]
    cursor.execute("SELECT action_text, date FROM action_logs WHERE user_id = ? ORDER BY id DESC LIMIT 25", (uid,))
    actions = cursor.fetchall()

    text = (
        f"📋 <b>Лог пользователя @{uname or uid}:</b>
"
        f"🆔 ID: <code>{uid}</code> | Ник: {t[16] or 'Нет'}
"
        f"💰 Монеты: {t[5]} | Уровень: {t[7]} (EXP: {t[6]})
"
        f"🛡 Ранг: {t[3]} ({t[21]})

"
        f"📜 <b>Последние действия (до 25):</b>
"
    )
    for act in actions:
        text += f"• [{act[1]}] {act[0]}
"
    await message.answer(text[:4000], parse_mode="HTML")

@dp.message(Command("Tlist"))
async def cmd_tlist(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8:
        return await message.answer("❌ Доступно с 8+ ранга.")
    cursor.execute("SELECT user_id, username, assigned_date FROM users WHERE role = 'Техник'")
    rows = cursor.fetchall()
    if not rows:
        return await message.answer("🛠 Техников нет.")
    text = "🛠 <b>Список техников:</b>

"
    for r in rows:
        text += f"• @{r[1] or 'нет'} (ID: <code>{r[0]}</code>) | Назначен: {r[2] or 'Не указано'}
"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("GAlist"))
async def cmd_ga_list(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8:
        return await message.answer("❌ Доступно с 8+ ранга.")
    cursor.execute("SELECT user_id, username, assigned_date FROM users WHERE rank = 6 OR role LIKE '%Главный Администратор%'")
    rows = cursor.fetchall()
    if not rows:
        return await message.answer("👑 ГА отсутствуют.")
    text = "👑 <b>Список Главных Администраторов (ГА):</b>

"
    for r in rows:
        text += f"• @{r[1] or 'нет'} (ID: <code>{r[0]}</code>) | Назначен: {r[2] or 'Не указано'}
"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("Blago"))
async def cmd_blago(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Донат в ГРН", callback_data="blago_uah")],
        [InlineKeyboardButton(text="⭐️ Донат в Stars", callback_data="blago_stars")]
    ])
    await message.answer("❤️ <b>Поддержка проекта и разработчика</b>
Выберите валюту для доната:", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "blago_uah")
async def blago_uah_callback(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        f"💳 <b>Оплата в ГРН</b>

Банка Monobank:
🔗 {MONOBANK_JAR}

"
        f"⚠️ <b>Обязательно</b> укажите ваш @Username или User ID в комментарии к платежу!

"
        f"Отправьте ваш @username или user_id ответным сообщением сюда для подтверждения:",
        parse_mode="HTML"
    )
    await state.set_state(BlagoState.waiting_for_username)

@dp.message(BlagoState.waiting_for_username)
async def process_blago_username(message: Message, state: FSMContext):
    uname_or_id = message.text.strip()
    uid = message.from_user.id
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    cursor.execute("INSERT INTO blago_requests (user_id, username, amount, currency, status, date) VALUES (?, ?, ?, ?, 'pending', ?)",
                   (uid, uname_or_id, "ГРН (на банку)", "грн", date_str))
    conn.commit()
    req_id = cursor.lastrowid
    await state.clear()
    await message.answer("✅ Ваша заявка отправлена на проверку администрации (10+ ранг). Спасибо за поддержку!")

    cursor.execute("SELECT user_id FROM users WHERE rank >= 10")
    for row in cursor.fetchall():
        try:
            await bot.send_message(row[0], f"❤️ <b>Новый донат (ГРН) (#{req_id})!</b>
От: {uname_or_id} (ID: {uid})
Проверьте банку и подтвердите через /BL", parse_mode="HTML")
        except Exception:
            pass

@dp.callback_query(F.data == "blago_stars")
async def blago_stars_callback(callback: CallbackQuery):
    buttons = []
    row = []
    for stars in STARS_PACKS:
        row.append(InlineKeyboardButton(text=f"⭐️ {stars}", callback_data=f"buy_star_invoice_{stars}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    await callback.message.edit_text(
        "⭐️ <b>Выберите количество Звезд для доната:</b>

"
        "<i>При нажатии откроется официальное окно оплаты Telegram.</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("buy_star_invoice_"))
async def process_buy_star_invoice(callback: CallbackQuery):
    stars_count = int(callback.data.split("_")[3])
    prices = [LabeledPrice(label=f"Донат {stars_count} Звезд⭐️", amount=stars_count)]
    try:
        await callback.message.answer_invoice(
            title="Поддержка проекта⭐️",
            description=f"Добровольное пожертвование разработчику в размере {stars_count} Telegram Stars.",
            payload=f"donate_stars_{stars_count}",
            currency="XTR",
            prices=prices
        )
        await callback.answer()
    except Exception as e:
        await callback.answer(f"❌ Ошибка создания счета: {e}", show_alert=True)

@dp.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message(F.successful_payment)
async def process_successful_payment(message: Message):
    await message.answer("✅ Спасибо за успешную оплату через Telegram Stars! Донат зачислен.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
