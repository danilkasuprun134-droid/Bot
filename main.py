```python
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
# 1. НАСТРОЙКИ И БАЗА ДАННЫХ (ПОЛНАЯ СХЕМА)
# ==========================================
logging.basicConfig(level=logging.INFO)

API_TOKEN = os.environ.get("BOT_TOKEN", "ТВОЙ_ТОКЕН_БОТА")
MONOBANK_JAR = "https://send.monobank.ua/jar/8wVnXzoF3f"
CARD_DETAILS = "4441 0000 0000 0000"
OWNER_USERNAME = "nlyxx2686"
OWNER_ID = 123456789  # ⚠️ Укажите ваш настоящий Telegram ID

ADMIN_IDS = [123456789]

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
        coins INTEGER DEFAULT 0,
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

    cursor.execute('''CREATE TABLE IF NOT EXISTS global_news_table (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        news_text TEXT
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS known_chats (
        chat_id INTEGER PRIMARY KEY,
        chat_title TEXT
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS user_chats_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        chat_id INTEGER,
        chat_title TEXT,
        last_seen TEXT
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS action_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action_text TEXT,
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

    cursor.execute('''CREATE TABLE IF NOT EXISTS marriages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user1_id INTEGER,
        user2_id INTEGER,
        wedding_date TEXT
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS promocodes (
        code TEXT PRIMARY KEY,
        coins INTEGER,
        activations_left INTEGER,
        created_at TEXT
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS used_promos (
        user_id INTEGER,
        code TEXT
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS admin_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER,
        admin_username TEXT,
        target_id INTEGER,
        target_username TEXT,
        action TEXT,
        reason TEXT,
        date TEXT
    )''')

    for col_def in [
        ("assigned_date", "TEXT"), ("assigned_by", "TEXT"), 
        ("purchased_role", "TEXT DEFAULT '0'"), ("total_donated_uah", "INTEGER DEFAULT 0"),
        ("total_donated_stars", "INTEGER DEFAULT 0"), ("last_active", "TEXT"), ("last_command", "TEXT")
    ]:
        try:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col_def[0]} {col_def[1]}")
        except sqlite3.OperationalError:
            pass

    conn.commit()

init_db()

# ==========================================
# 2. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ И ЛОГИРОВАНИЕ
# ==========================================

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
        cursor.execute(
            "INSERT INTO users (user_id, username, rank, coins, role) VALUES (?, ?, ?, ?, ?)",
            (user_id, u_clean, rank, 100, 'Owner' if rank == 10 else 'User')
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

def set_role(username_or_id, new_role: str, new_rank: int = None, by_user: str = "System"):
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    if str(username_or_id).isdigit():
        uid = int(username_or_id)
        if new_rank is not None:
            cursor.execute("UPDATE users SET role = ?, rank = ?, assigned_date = ?, assigned_by = ? WHERE user_id = ?", (new_role, new_rank, date_str, by_user, uid))
        else:
            cursor.execute("UPDATE users SET role = ?, assigned_date = ?, assigned_by = ? WHERE user_id = ?", (new_role, date_str, by_user, uid))
    else:
        u_clean = clean_username(str(username_or_id))
        if new_rank is not None:
            cursor.execute("UPDATE users SET role = ?, rank = ?, assigned_date = ?, assigned_by = ? WHERE LOWER(username) = ?", (new_role, new_rank, date_str, by_user, u_clean))
        else:
            cursor.execute("UPDATE users SET role = ?, assigned_date = ?, assigned_by = ? WHERE LOWER(username) = ?", (new_role, date_str, by_user, u_clean))
    conn.commit()
    return cursor.rowcount > 0

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

def add_gwarn(user_id: int, reason: str, by_user: str):
    user = get_user(user_id=user_id)
    if user and len(user) > 25 and user[25] >= 450:
        return False, "Автоматически снят gwarn (пользователь пожертвовал >= 450 грн)!"

    cursor.execute("INSERT INTO global_warns (user_id, reason, by_user) VALUES (?, ?, ?)", (user_id, reason, by_user))
    conn.commit()
    cursor.execute("SELECT COUNT(*) FROM global_warns WHERE user_id = ?", (user_id,))
    cnt = cursor.fetchone()[0]
    if cnt >= 3:
        cursor.execute("INSERT OR REPLACE INTO global_bans (user_id, reason, by_user) VALUES (?, ?, ?)", 
                       (user_id, "Авто-GBAN за 3/3 GWARN", "System"))
        conn.commit()
        return True, "3/3 GWARN! Автоматический GBAN."
    return False, "GWARN выдан!"

def log_user_action(user_id: int, text: str):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO action_logs (user_id, action_text, date) VALUES (?, ?, ?)", (user_id, text, now_str))
    conn.commit()

# ==========================================
# 3. FSM СОСТОЯНИЯ
# ==========================================
class BlagoState(StatesGroup):
    waiting_for_username = State()

class ObgbanState(StatesGroup):
    waiting_for_reason = State()

class ObgwarnState(StatesGroup):
    waiting_for_reason = State()

# ==========================================
# 4. МИДДЛВАРЬ ДЛЯ ЛОГИРОВАНИЯ И АКТИВНОСТИ
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
        cursor.execute("INSERT OR IGNORE INTO user_chats_log (user_id, chat_id, chat_title, last_seen) VALUES (?, ?, ?, ?)",
                       (user_id, event.chat.id, event.chat.title or "Group", datetime.now().strftime("%Y-%m-%d %H:%M")))
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
    
    update_user(user_id, msg_count=user[14] + 1, last_active=now_str, last_command=last_cmd)
    log_user_action(user_id, f"Действие/Сообщение: {last_cmd[:50]}")

    return await handler(event, data)

# ==========================================
# 5. ОСНОВНЫЕ КОМАНДЫ И СТАТИСТИКА
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
        await message.answer("⚠️ У вас не установлен Username в Настройках Telegram! Установите его, чтобы пользоваться ботом.")
        return

    user = get_user(user_id=user_id, username=username)
    await message.answer(f"Привет, @{clean_username(username)}! Ваш баланс: {user[5]} монет. Используйте /help для списка команд.", parse_mode="Markdown")

@dp.message(Command("stats"))
async def cmd_stats(message: Message, command: CommandObject):
    target = message.from_user
    if command.args:
        raw = command.args.split()[0]
        t_user = get_user(user_id=int(raw)) if raw.isdigit() else get_user(username=clean_username(raw))
        if t_user:
            u_row = t_user
        else:
            return await message.answer("❌ Пользователь не найден.")
    else:
        u_row = get_user(user_id=target.id, username=target.username or "")

    uid, uname, lang, rank, roles, coins, exp, level, rep, streak, last_bonus, _, _, vip, msgs, duels, nickname, _, _, warns, gwarns, role, zdkd, _, _, donated_uah, donated_stars, assigned_date, assigned_by, purchased_role = u_row[:30]
    vip_status = "Активен до " + str(vip) if is_vip(u_row) else "Отсутствует"

    text = (
        f"📊 <b>Статистика пользователя @{uname or uid}:</b>\n\n"
        f"💰 Монеты: <b>{coins}</b>\n"
        f"🏷 Кастомный ник: <b>{nickname or 'Не установлен'}</b>\n"
        f"📈 Уровень: <b>{level}</b> (EXP: {exp})\n"
        f"🛡 Админ-права / Роль: <b>{role}</b> (Ранг: {rank})\n"
        f"🛒 Купленная роль: <b>{purchased_role if purchased_role != '0' else 'Отсутствует'}</b>\n"
        f"👑 VIP-статус: <b>{vip_status}</b>\n"
        f"⭐ Донаты (UAH): <b>{donated_uah} грн</b> | Звезд: <b>{donated_stars} ⭐️</b>\n"
        f"💬 Сообщений написано: <b>{msgs}</b>\n"
        f"⚔️ Побед в дуэлях: <b>{duels}</b>\n"
        f"❤️ Репутация: <b>{rep}</b>"
    )
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("pin"))
async def cmd_pin(message: Message):
    if not message.reply_to_message:
        return await message.answer("⚠️ Эту команду нужно вызывать ответом на сообщение!")
    if message.chat.type not in ['group', 'supergroup']:
        return await message.answer("❌ Команда работает только в групповых чатах.")
    try:
        await message.chat.pin_message(message.reply_to_message.message_id)
        await message.answer("📌 Сообщение успешно закреплено!")
    except Exception as e:
        await message.answer(f"❌ Не удалось закрепить сообщение: {e}")

@dp.message(Command("shop"))
async def cmd_shop(message: Message, command: CommandObject):
    args = command.args.split() if command.args else []
    if not args or not args[0].isdigit():
        return await message.answer(
            "🛍 <b>Магазин бота:</b>\n\n"
            "• Обмен монет на EXP (курс: 1 EXP = 100 монет):\n"
            "  <code>/shop [количество_exp]</code>\n"
            "  <i>Пример: <code>/shop 10</code> (спишет 1000 монет, даст 10 EXP)</i>",
            parse_mode="HTML"
        )
    
    exp_to_buy = int(args[0])
    cost = exp_to_buy * 100
    uid = message.from_user.id
    user = get_user(user_id=uid)

    if user[5] < cost:
        return await message.answer(f"❌ Недостаточно монет! Требуется <b>{cost} монет</b> (у вас {user[5]}).", parse_mode="HTML")

    new_coins = user[5] - cost
    new_exp = user[6] + exp_to_buy
    curr_level = user[7]
    
    needed_exp = 250 if curr_level <= 15 else (1500 if curr_level <= 30 else (10000 if curr_level <= 50 else 25000))
    while new_exp >= needed_exp:
        new_exp -= needed_exp
        curr_level += 1
        needed_exp = 250 if curr_level <= 15 else (1500 if curr_level <= 30 else (10000 if curr_level <= 50 else 25000))

    update_user(uid, coins=new_coins, exp=new_exp, level=curr_level)
    await message.answer(f"✅ Успешно куплено <b>{exp_to_buy} EXP</b> за <b>{cost} монет</b>! 💰", parse_mode="HTML")

@dp.message(Command("snick"))
async def cmd_snick(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 2:
        return await message.answer("❌ Команда <code>/snick</code> доступна со 2+ ранга!", parse_mode="HTML")
    args = command.args.split(maxsplit=1) if command.args else []
    if not message.reply_to_message or not args:
        return await message.answer("⚠️ Использование: ответьте на сообщение участника и введите <code>/snick [ник]</code>", parse_mode="HTML")

    target_id = message.reply_to_message.from_user.id
    nick = args[0]
    update_user(target_id, custom_nickname=nick)
    await message.answer(f"✅ Кастомный ник <b>{nick}</b> успешно установлен!", parse_mode="HTML")

@dp.message(Command("rnick"))
async def cmd_rnick(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 2:
        return await message.answer("❌ Команда <code>/rnick</code> доступна со 2+ ранга!", parse_mode="HTML")
    if not message.reply_to_message:
        return await message.answer("⚠️ Ответьте на сообщение участника, чтобы убрать ник.")

    target_id = message.reply_to_message.from_user.id
    update_user(target_id, custom_nickname=None)
    await message.answer("✅ Кастомный ник успешно убран!", parse_mode="HTML")

@dp.message(Command("gnick"))
async def cmd_gnick(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 2:
        return await message.answer("❌ Команда <code>/gnick</code> доступна со 2+ ранга!", parse_mode="HTML")
    if not message.reply_to_message:
        return await message.answer("⚠️ Ответьте на сообщение персонажа.")

    target_id = message.reply_to_message.from_user.id
    t_user = get_user(user_id=target_id)
    await message.answer(
        f"👤 <b>Информация о персонаже:</b>\n"
        f"• Username: @{t_user[1] or 'нет'}\n"
        f"• Кастомный ник: <b>{t_user[16] or 'Не установлен'}</b>",
        parse_mode="HTML"
    )

@dp.message(Command("staff"))
async def cmd_staff(message: Message):
    cursor.execute("SELECT username, user_id, role, rank FROM users WHERE rank >= 4 ORDER BY rank DESC")
    rows = cursor.fetchall()
    if not rows:
        return await message.answer("🛡️ Администрация выше 4+ ранга не найдена.")

    text = "🛡️ <b>СПИСОК АДМИНИСТРАЦИИ (4+ РАНГ):</b>\n\n"
    for r in rows:
        text += f"• @{r[0] or r[1]} — <b>{r[2]}</b> (Ранг: {r[3]})\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("eshop"))
async def cmd_eshop(message: Message):
    await message.answer(
        "🎁 <b>Эксклюзивный магазин подарков (eshop):</b>\n\n"
        "Здесь руководство выдает подарки и бонусы.\n"
        "Используйте команду <code>/gbonus [сумма]</code> (доступно руководству), чтобы раздать подарок всем!",
        parse_mode="HTML"
    )

@dp.message(Command("myadm"))
async def cmd_myadm(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 10:
        return await message.answer("❌ Команда <code>/myadm</code> доступна с 10 ранга!", parse_mode="HTML")

    cursor.execute("SELECT user_id, username, role, rank, assigned_date, assigned_by FROM users WHERE rank IN (8, 9, 10) ORDER BY rank DESC")
    rows = cursor.fetchall()
    if not rows:
        return await message.answer("📋 Администраторов 8-10 рангов нет.")

    text = "👑 <b>СПИСОК АДМИНИСТРАЦИИ (8-10 РАНГИ):</b>\n\n"
    for r in rows:
        text += f"• @{r[1] or r[0]} (<code>{r[0]}</code>) — <b>{r[2]}</b> (Ранг {r[3]})\n  Поставлен: {r[4] or 'Не указано'} | Кем: {r[5] or 'Система'}\n\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("vlist"))
async def cmd_vlist(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8:
        return await message.answer("❌ Команда <code>/vlist</code> доступна с 8+ ранга!", parse_mode="HTML")

    cursor.execute("SELECT user_id, username, vip_until FROM users WHERE vip_until IS NOT NULL")
    rows = cursor.fetchall()
    if not rows:
        return await message.answer("💎 Пользователей с VIP-статусом пока нет.")

    text = "💎 <b>СПИСОК ПОЛЬЗОВАТЕЛЕЙ С VIP-СТАТУСОМ:</b>\n\n"
    for r in rows:
        uid, uname, vip_date = r
        cursor.execute("SELECT price, currency, period, reason, date FROM vip_history WHERE user_id = ? ORDER BY id DESC LIMIT 1", (uid,))
        h = cursor.fetchone()
        if h:
            price, currency, period, reason, date_got = h
            text += f"• @{uname or uid} (<code>{uid}</code>)\n  Вип с {date_got} по {vip_date} | За что: {reason or 'Покупка'} ({price} {currency})\n\n"
        else:
            text += f"• @{uname or uid} (<code>{uid}</code>) | Активен до: {vip_date}\n\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("donatslist"))
async def cmd_donatslist(message: Message):
    cursor.execute("SELECT username, user_id, total_donated_uah, total_donated_stars FROM users ORDER BY total_donated_uah DESC, total_donated_stars DESC LIMIT 10")
    rows = cursor.fetchall()
    if not rows:
        return await message.answer("🏆 Топ донатеров пуст.")

    text = "🏆 <b>ТОП-10 САМЫХ КРУТЫХ ДОНАТЕРОВ:</b>\n\n"
    for idx, r in enumerate(rows, 1):
        text += f"{idx}. @{r[0] or r[1]} — <b>{r[2]} грн</b> | <b>{r[3]} ⭐️</b>\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("news"))
async def cmd_news(message: Message):
    cursor.execute("SELECT news_text FROM global_news_table ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    news = row[0] if row else "Правила бота еще не установлены руководящим составом."
    await message.answer(f"📜 <b>Правила бота:</b>\n\n{news}", parse_mode="HTML")

@dp.message(Command("Global_news"))
async def cmd_global_news(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 10:
        return await message.answer("❌ Команда <code>/Global_news</code> доступна только с 10 ранга!", parse_mode="HTML")
    if not command.args:
        return await message.answer("⚠️ Укажите текст правил: <code>/Global_news [текст]</code>", parse_mode="HTML")

    cursor.execute("INSERT INTO global_news_table (news_text) VALUES (?)", (command.args,))
    conn.commit()
    await message.answer("✅ Правила бота успешно установлены и обновлены!")

@dp.message(Command("dpromo"))
async def cmd_dpromo(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 10:
        return await message.answer("❌ Команда <code>/dpromo</code> доступна с 10 ранга!", parse_mode="HTML")
    if not command.args:
        return await message.answer("⚠️ Укажите промокод: <code>/dpromo [код]</code>", parse_mode="HTML")

    code = command.args.split()[0].upper()
    cursor.execute("DELETE FROM promocodes WHERE code = ?", (code,))
    conn.commit()
    await message.answer(f"✅ Промокод <code>{code}</code> успешно удален.", parse_mode="HTML")

@dp.message(Command("Buy_role"))
async def cmd_buy_role(message: Message, command: CommandObject):
    uid = message.from_user.id
    user = get_user(user_id=uid)
    args = command.args.split() if command.args else []
    
    if not args:
        return await message.answer(
            "🛍 <b>Покупка персональной роли:</b>\n"
            "Стоимость: 5000 монет.\n"
            "Использование: <code>/Buy_role [название_роли]</code>",
            parse_mode="HTML"
        )
    
    role_name = " ".join(args)
    cost = 5000
    if user[5] < cost:
        return await message.answer(f"❌ Недостаточно монет! Нужно <b>{cost} монет</b>.", parse_mode="HTML")

    update_user(uid, coins=user[5] - cost, purchased_role=role_name)
    await message.answer(f"🎉 Вы успешно купили роль: <b>{role_name}</b> за {cost} монет!", parse_mode="HTML")

@dp.message(Command("bonus"))
async def cmd_bonus(message: Message):
    uid = message.from_user.id
    user = get_user(user_id=uid)
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")

    if user[10] == today_str:
        return await message.answer("⏳ Вы уже забрали сегодняшний бонус! Ждите завтрашнего дня.")

    streak = user[9]
    if user[10]:
        last_date = datetime.strptime(user[10], "%Y-%m-%d")
        if (now - last_date).days == 1:
            streak += 1
        elif (now - last_date).days > 1:
            streak = 1
    else:
        streak = 1

    rand_chance = random.random()
    if rand_chance < 0.00001:
        coins = random.randint(2001, 15000)
    else:
        coins = random.randint(100, 2000)

    exp = random.randint(150, 7500)
    new_coins = user[5] + coins
    new_exp = user[6] + exp
    curr_level = user[7]

    def get_needed_exp(lvl):
        if lvl <= 15: return 250
        elif lvl <= 30: return 1500
        elif lvl <= 50: return 10000
        else: return 25000

    needed_exp = get_needed_exp(curr_level)
    while new_exp >= needed_exp:
        new_exp -= needed_exp
        curr_level += 1
        needed_exp = get_needed_exp(curr_level)

    update_user(uid, coins=new_coins, exp=new_exp, level=curr_level, streak=streak, last_bonus=today_str)
    await message.answer(
        f"🎁 <b>Ежедневный бонус получен! 🔥 Серия: {streak} дней</b>\n\n"
        f"💰 Монеты: <b>+{coins}</b>\n"
        f"📈 EXP: <b>+{exp}</b>\n"
        f"⭐ Уровень: <b>{curr_level}</b>",
        parse_mode="HTML"
    )

@dp.message(Command("gbonus"))
async def cmd_gbonus(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8:
        return await message.answer("❌ Команда <code>/gbonus</code> доступна с 8+ ранга!", parse_mode="HTML")
    if not command.args or not command.args.isdigit():
        return await message.answer("⚠️ Укажите сумму: <code>/gbonus [сумма]</code>", parse_mode="HTML")

    amount = int(command.args)
    cursor.execute("UPDATE users SET coins = coins + ?", (amount,))
    conn.commit()
    await message.answer(f"🎉 Выдан общий бонус в размере <b>{amount} монет</b> всем участникам проекта!", parse_mode="HTML")

@dp.message(Command("duel"))
async def cmd_duel(message: Message, command: CommandObject):
    if not command.args or not command.args.isdigit():
        return await message.answer("⚠️ Укажите ставку: <code>/duel [ставка]</code> (10-500, с VIP до 1000)", parse_mode="HTML")

    bet = int(command.args)
    u1_id = message.from_user.id
    u1_row = get_user(user_id=u1_id)
    max_bet = 1000 if is_vip(u1_row) else 500

    if bet < 10 or bet > max_bet:
        return await message.answer(f"❌ Неверная ставка! Допустимо от 10 до {max_bet} монет.")
    if u1_row[5] < bet:
        return await message.answer("❌ У вас недостаточно монет для создания дуэли!")

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⚔️ Принять дуэль", callback_data=f"accept_duel_{u1_id}_{bet}")
    ]])
    await message.answer(
        f"⚔️ <b>Дуэль создана!</b>\n"
        f"👤 Игрок: @{message.from_user.username or u1_id}\n"
        f"💰 Ставка: <b>{bet} монет</b>\n\n"
        f"<i>Любой участник группы может нажать кнопку ниже, чтобы принять вызов!</i>",
        reply_markup=kb, parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("accept_duel_"))
async def callback_accept_duel(callback: CallbackQuery):
    _, _, u1_str, bet_str = callback.data.split("_")
    u1_id, bet = int(u1_str), int(bet_str)
    u2_id = callback.from_user.id

    if u1_id == u2_id:
        return await callback.answer("❌ Нельзя принять собственную дуэль!", show_alert=True)

    u1 = get_user(user_id=u1_id)
    u2 = get_user(user_id=u2_id)

    if u1[5] < bet or u2[5] < bet:
        return await callback.answer("❌ У одного из участников недостаточно монет!", show_alert=True)

    vip1, vip2 = is_vip(u1), is_vip(u2)
    p1 = 55 if vip1 and not vip2 else (45 if vip2 and not vip1 else 50)
    p2 = 100 - p1

    winner_id = random.choices([u1_id, u2_id], weights=[p1, p2], k=1)[0]
    loser_id = u2_id if winner_id == u1_id else u1_id

    w_user = get_user(user_id=winner_id)
    l_user = get_user(user_id=loser_id)

    if is_vip(w_user):
        prize = bet * 2
    else:
        prize = int(bet * 2 * 0.95)

    update_user(winner_id, coins=w_user[5] + prize - bet, duel_wins=w_user[15] + 1)
    update_user(loser_id, coins=l_user[5] - bet)

    await callback.message.edit_text(
        f"⚔️ <b>Дуэль завершена!</b>\n"
        f"🏆 Победитель: <a href='tg://user?id={winner_id}'>Игрок</a> (+{prize} монет)\n"
        f"💀 Проигравший: <a href='tg://user?id={loser_id}'>Игрок</a> (-{bet} монет)",
        parse_mode="HTML"
    )

@dp.message(Command("Gban"))
async def cmd_gban(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 9:
        return await message.answer("❌ Команда <code>/Gban</code> доступна с 9+ ранга!", parse_mode="HTML")
    args = command.args.split(maxsplit=1) if command.args else []
    if not args:
        return await message.answer("⚠️ Использование: <code>/Gban @username/user_id причина</code>", parse_mode="HTML")

    target_raw = args[0]
    reason = args[1] if len(args) > 1 else "Нарушение правил"
    target = get_user(user_id=int(target_raw)) if target_raw.isdigit() else get_user(username=clean_username(target_raw))
    if not target:
        return await message.answer("❌ Пользователь не найден.")

    cursor.execute("INSERT OR REPLACE INTO global_bans (user_id, reason, by_user) VALUES (?, ?, ?)",
                   (target[0], reason, message.from_user.username or "Admin"))
    conn.commit()
    await message.answer(f"🚨 Пользователь @{target[1] or target[0]} получил <b>GBAN</b> (глобальный бан).\nПричина: {reason}", parse_mode="HTML")

@dp.message(Command("Gwarn"))
async def cmd_gwarn(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8:
        return await message.answer("❌ Команда <code>/Gwarn</code> доступна с 8+ ранга!", parse_mode="HTML")
    args = command.args.split(maxsplit=1) if command.args else []
    if not args:
        return await message.answer("⚠️ Использование: <code>/Gwarn @username/user_id причина</code>", parse_mode="HTML")

    target_raw = args[0]
    reason = args[1] if len(args) > 1 else "Нарушение правил"
    target = get_user(user_id=int(target_raw)) if target_raw.isdigit() else get_user(username=clean_username(target_raw))
    if not target:
        return await message.answer("❌ Пользователь не найден.")

    is_banned, msg = add_gwarn(target[0], reason, message.from_user.username or "Admin")
    await message.answer(f"🌐 <b>{msg}</b> (Игрок: @{target[1] or target[0]})", parse_mode="HTML")

@dp.message(Command("Give_money"))
async def cmd_give_money(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 10:
        return await message.answer("❌ Команда <code>/Give_money</code> доступна с 10 ранга!", parse_mode="HTML")
    args = command.args.split(maxsplit=2) if command.args else []
    if len(args) < 2:
        return await message.answer("⚠️ Использование: <code>/Give_money @username/user_id количество [причина]</code>", parse_mode="HTML")

    target_raw, amount_str = args[0], args[1]
    reason = args[2] if len(args) > 2 else "Не указана"
    if not amount_str.isdigit():
        return await message.answer("⚠️ Количество должно быть числом.")
    amount = int(amount_str)

    target = get_user(user_id=int(target_raw)) if target_raw.isdigit() else get_user(username=clean_username(target_raw))
    if not target:
        return await message.answer("❌ Пользователь не найден.")

    update_user(target[0], coins=target[5] + amount)
    await message.answer(f"✅ Пользователю @{target[1] or target[0]} выдано <b>{amount} монет</b> 💰\nПричина: {reason}", parse_mode="HTML")

@dp.message(Command("unsetzam"))
async def cmd_unsetzam(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 10:
        return await message.answer("❌ Доступно с 10 ранга.", parse_mode="HTML")
    args = command.args.split(maxsplit=1) if command.args else []
    if not args:
        return await message.answer("⚠️ Использование: <code>/unsetzam @username/id_user [причина]</code>", parse_mode="HTML")

    raw, reason = args[0], (args[1] if len(args) > 1 else "Не указана")
    target = get_user(user_id=int(raw)) if raw.isdigit() else get_user(username=clean_username(raw))
    if not target:
        return await message.answer("❌ Пользователь не найден.")

    set_role(target[0], "User", new_rank=0, by_user=message.from_user.username or "Owner")
    await message.answer(f"📉 С пользователя @{target[1] or target[0]} снят 9 ранг (зам).\nПричина: {reason}", parse_mode="HTML")

@dp.message(Command("unsetadm"))
async def cmd_unsetadm(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 9:
        return await message.answer("❌ Доступно с 9 ранга.", parse_mode="HTML")
    args = command.args.split(maxsplit=1) if command.args else []
    if not args:
        return await message.answer("⚠️ Использование: <code>/unsetadm @username/id_user [причина]</code>", parse_mode="HTML")

    raw, reason = args[0], (args[1] if len(args) > 1 else "Не указана")
    target = get_user(user_id=int(raw)) if raw.isdigit() else get_user(username=clean_username(raw))
    if not target:
        return await message.answer("❌ Пользователь не найден.")

    set_role(target[0], "User", new_rank=0, by_user=message.from_user.username or "Admin")
    await message.answer(f"📉 С пользователя @{target[1] or target[0]} снят 8 ранг (админ).\nПричина: {reason}", parse_mode="HTML")

@dp.message(Command("tops"))
async def cmd_tops(message: Message):
    text = "🌐 <b>МЕЖГРУППОВЫЕ ТОПЫ ПРОЕКТА:</b>\n\n"
    
    cursor.execute("SELECT username, streak FROM users ORDER BY streak DESC LIMIT 5")
    s_rows = cursor.fetchall()
    text += "🔥 <b>По серии сбора /bonus:</b>\n"
    for r in s_rows: text += f"• @{r[0] or 'нет'} — {r[1]} дней\n"

    cursor.execute("SELECT username, coins FROM users ORDER BY coins DESC LIMIT 5")
    c_rows = cursor.fetchall()
    text += "\n💰 <b>По монетам:</b>\n"
    for r in c_rows: text += f"• @{r[0] or 'нет'} — {r[1]} монет\n"

    cursor.execute("SELECT username, level FROM users ORDER BY level DESC LIMIT 5")
    l_rows = cursor.fetchall()
    text += "\n📈 <b>По уровню:</b>\n"
    for r in l_rows: text += f"• @{r[0] or 'нет'} — {r[1]} лвл\n"

    cursor.execute("SELECT username, duel_wins FROM users ORDER BY duel_wins DESC LIMIT 5")
    d_rows = cursor.fetchall()
    text += "\n⚔️ <b>По победам в дуэлях:</b>\n"
    for r in d_rows: text += f"• @{r[0] or 'нет'} — {r[1]} побед\n"

    await message.answer(text, parse_mode="HTML")

@dp.message(Command("zayavka"))
async def cmd_zayavka(message: Message):
    user = get_user(user_id=message.from_user.id)
    rank = user[3]
    if rank < 8:
        return await message.answer("❌ У вас нет прав на просмотр заявок.")

    text = "📋 <b>Активные заявки для вашего ранга:</b>\n\n"
    if rank >= 8:
        cursor.execute("SELECT id, username FROM tex_requests")
        tex = cursor.fetchall()
        text += f"• Заявок на техника: {len(tex)} (смотреть /Tlist)\n"
    if rank >= 9:
        cursor.execute("SELECT id, username FROM obgban_requests")
        bans = cursor.fetchall()
        text += f"• Обжалований GBAN: {len(bans)}\n"
    
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("Flogs"))
async def cmd_flogs(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8:
        return await message.answer("❌ Команда <code>/Flogs</code> доступна с 8+ ранга!", parse_mode="HTML")
    if not command.args:
        return await message.answer("⚠️ Укажите пользователя: <code>/Flogs user_id/@username</code>", parse_mode="HTML")

    raw = command.args.split()[0]
    t_row = get_user(user_id=int(raw)) if raw.isdigit() else get_user(username=clean_username(raw))
    if not t_row:
        return await message.answer("❌ Пользователь не найден в базе данных.")

    uid, uname, _, rank, _, coins, exp, level, rep, _, _, _, _, vip, msgs, duels, nickname, _, _, _, _, role, _, _, _, donated_uah, donated_stars = t_row[:27]
    
    cursor.execute("SELECT action_text, date FROM action_logs WHERE user_id = ? ORDER BY id DESC LIMIT 25", (uid,))
    actions = cursor.fetchall()

    cursor.execute("SELECT chat_title FROM user_chats_log WHERE user_id = ?", (uid,))
    chats = [c[0] for c in cursor.fetchall()]

    donat_info = f"UAH: {donated_uah} грн, Stars: {donated_stars} ⭐️" if (donated_uah > 0 or donated_stars > 0) else "Нет"

    text = (
        f"📋 <b>Полный лог пользователя (@{uname or uid}):</b>\n\n"
        f"🆔 Telegram ID: <code>{uid}</code>\n"
        f"🏷 Кастомный ник: {nickname or 'Нет'}\n"
        f"💰 Монеты: {coins} | Уровень: {level} (EXP: {exp})\n"
        f"🛡 Админ-ранг: {rank} ({role})\n"
        f"💬 Сообщений всего: {msgs}\n"
        f"💳 Донаты: {donat_info}\n"
        f"📌 Группы с ботом: {', '.join(chats) if chats else 'Нет данных'}\n\n"
        f"📜 <b>Последние действия с ботом (до 25):</b>\n"
    )
    for act in actions:
        text += f"• [{act[1]}] {act[0]}\n"

    await message.answer(text[:4000], parse_mode="HTML")

@dp.message(Command("Tlist"))
async def cmd_tlist(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8:
        return await message.answer("❌ Команда <code>/Tlist</code> доступна с 8+ ранга!", parse_mode="HTML")

    cursor.execute("SELECT user_id, username, assigned_date FROM users WHERE role = 'Техник'")
    rows = cursor.fetchall()
    if not rows:
        return await message.answer("🛠 Список техников пуст.")

    text = "🛠 <b>СПИСОК ТЕХНИКОВ ПРОЕКТА:</b>\n\n"
    for r in rows:
        text += f"• @{r[1] or 'нет'} (<code>{r[0]}</code>) | Назначен: {r[2] or 'Не указано'}\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("GAlist"))
async def cmd_ga_list(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8:
        return await message.answer("❌ Команда доступна с 8+ ранга.", parse_mode="HTML")

    cursor.execute("SELECT user_id, username, assigned_date FROM users WHERE rank = 6 OR role LIKE '%Главный Администратор%'")
    rows = cursor.fetchall()
    if not rows:
        return await message.answer("👑 Главных Администраторов (ГА) нет.")

    text = "👑 <b>СПИСОК ГЛАВНЫХ АДМИНИСТРАТОРОВ (ГА):</b>\n\n"
    for r in rows:
        text += f"• @{r[1] or 'нет'} (<code>{r[0]}</code>) | Назначен: {r[2] or 'Не указано'}\n"
    await message.answer(text, parse_mode="HTML")

# ==========================================
# 11. ЗАПУСК БОТА
# ==========================================
async def main():
    logging.info("Starting Stars Manager Bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped!")
```
