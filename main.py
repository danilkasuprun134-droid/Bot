import os
import sys
import logging
import random
import asyncio
import sqlite3
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
        zdkd INTEGER DEFAULT 0
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

    cursor.execute('''CREATE TABLE IF NOT EXISTS obgban_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        reason TEXT,
        date TEXT
    )''')

    conn.commit()

init_db()

# ==========================================
# 2. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ БАЗЫ ДАННЫХ
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
            "INSERT INTO users (user_id, username, rank, coins) VALUES (?, ?, ?, ?)",
            (user_id, u_clean, rank, 100)
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

def set_role(username_or_id, new_role: str):
    if str(username_or_id).isdigit():
        cursor.execute("UPDATE users SET role = ? WHERE user_id = ?", (new_role, int(username_or_id)))
    else:
        u_clean = clean_username(str(username_or_id))
        cursor.execute("UPDATE users SET role = ? WHERE LOWER(username) = ?", (new_role, u_clean))
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

def add_vip_time(user_id: int, period: str):
    user = get_user(user_id=user_id)
    if period.lower() in ["forever", "навсегда"]:
        update_user(user_id, vip_until="forever")
        return

    days_to_add = int(period) * 30
    now = datetime.now()

    if is_vip(user) and user[13] != 'forever':
        current_until = datetime.strptime(user[13], "%Y-%m-%d %H:%M:%S")
        new_until = current_until + timedelta(days=days_to_add)
    else:
        new_until = now + timedelta(days=days_to_add)

    update_user(user_id, vip_until=new_until.strftime("%Y-%m-%d %H:%M:%S"))

def check_gban(user_id: int) -> bool:
    if user_id == OWNER_ID: return False
    cursor.execute("SELECT 1 FROM global_bans WHERE user_id = ?", (user_id,))
    return cursor.fetchone() is not None

def add_gwarn(user_id: int, reason: str, by_user: str):
    cursor.execute("INSERT INTO global_warns (user_id, reason, by_user) VALUES (?, ?, ?)", (user_id, reason, by_user))
    conn.commit()
    cursor.execute("SELECT COUNT(*) FROM global_warns WHERE user_id = ?", (user_id,))
    cnt = cursor.fetchone()[0]
    if cnt >= 3:
        cursor.execute("INSERT OR REPLACE INTO global_bans (user_id, reason, by_user) VALUES (?, ?, ?)", 
                       (user_id, "Авто-GBAN за 3/3 GWARN", "System"))
        conn.commit()
        return True
    return False

# ==========================================
# 3. FSM СОСТОЯНИЯ И ПРАЙС-ЛИСТЫ
# ==========================================
class AdminProcessOrder(StatesGroup):
    waiting_for_details = State()

class BlagoState(StatesGroup):
    waiting_for_uah_amount = State()
    waiting_for_stars_amount = State()

class ObgbanState(StatesGroup):
    waiting_for_reason = State()

PRICES_UAH = {
    "1": {"price": 30, "text": "1 месяц — 30 грн"},
    "3": {"price": 75, "text": "3 месяца — 75 грн"},
    "6": {"price": 130, "text": "6 месяцев — 130 грн"},
    "12": {"price": 210, "text": "12 месяцев — 210 грн"},
    "forever": {"price": 500, "text": "Навсегда — 500 грн"},
}

PRICES_STARS = {
    "1": {"price": 50, "text": "1 месяц — 50 Stars ⭐️"},
    "3": {"price": 85, "text": "3 месяца — 85 Stars ⭐️"},
    "6": {"price": 150, "text": "6 месяцев — 150 Stars ⭐️"},
    "12": {"price": 250, "text": "12 месяцев — 250 Stars ⭐️"},
    "forever": {"price": 700, "text": "Навсегда — 700 Stars ⭐️"},
}

MONEY_PACKS_UAH = {
    "1000": {"coins": 1000, "price": 15, "text": "1,000 монет — 15 грн"},
    "5000": {"coins": 5000, "price": 70, "text": "5,000 монет — 70 грн"},
    "10000": {"coins": 10000, "price": 110, "text": "10,000 монет — 110 грн"},
}

MONEY_PACKS_STARS = {
    "1000": {"coins": 1000, "price": 25, "text": "1,000 монет — 25 Stars ⭐️"},
    "5000": {"coins": 5000, "price": 85, "text": "5,000 монет — 85 Stars ⭐️"},
    "10000": {"coins": 10000, "price": 150, "text": "10,000 монет — 150 Stars ⭐️"},
}

# ==========================================
# 4. МИДДЛВАРИ
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

        if user_id != OWNER_ID and check_gban(user_id):
            try:
                await bot.ban_chat_member(event.chat.id, user_id)
                await event.answer(f"🚨 Пользователь @{username or user_id} имеет <b>GBAN</b> и был удалён из чата!", parse_mode="HTML")
            except Exception:
                pass
            return

    user = get_user(user_id=user_id, username=username)
    update_user(user_id, msg_count=user[14] + 1)

    return await handler(event, data)

# ==========================================
# 5. ОСНОВНЫЕ КОМАНДЫ И ОБЖАЛОВАНИЕ
# ==========================================

@dp.message(Command("start"))
async def cmd_start(message: Message, command: CommandObject):
    user_id = message.from_user.id
    username = message.from_user.username

    # Проверка: если бота пригласили в группу и это старт с аргументом владельца чата / авто-назначение ГА
    if message.chat.type in ['group', 'supergroup'] and command.args == "owner":
        update_user(user_id, rank=6, role="Главный Администратор (ГА)")
        await message.answer("👑 Вы назначены Главным Администратором (ГА) этой группы за приглашение бота!")
        return

    if not username:
        await message.answer("⚠️ У вас не установлен Username в Настройках Telegram! Установите его, чтобы пользоваться ботом.")
        return

    user = get_user(user_id=user_id, username=username)
    await message.answer(f"Привет снова, @{clean_username(username)}! Ваш баланс: {user[5]} монет.", parse_mode="Markdown")

@dp.message(Command("q"))
async def cmd_q(message: Message):
    if message.chat.type not in ['group', 'supergroup']:
        return await message.answer("❌ Команда работает только в групповых чатах.")
    try:
        await bot.ban_chat_member(message.chat.id, message.from_user.id)
        await bot.unban_chat_member(message.chat.id, message.from_user.id)
        await message.answer("👋 Вы успешно вышли из группы по собственному желанию.")
    except Exception as e:
        await message.answer(f"❌ Не удалось выйти из чата: {e}")

@dp.message(Command("obgban"))
async def cmd_obgban(message: Message, state: FSMContext):
    if message.chat.type != 'private':
        return await message.answer("⚠️ Команду <code>/obgban</code> нужно писать строго в ЛС бота!", parse_mode="HTML")
    
    uid = message.from_user.id
    if not check_gban(uid):
        return await message.answer("❌ У вас нет активного GBAN, обжаловать нечего.")

    await message.answer(
        "📝 <b>Обжалование GBAN</b>\n\n"
        "Опишите максимально подробно: почему вы получили бан, почему хотите его снять и т.д.\n"
        "<i>(Заявка рассматривается высшей администрацией раз в 7 дней)</i>\n\n"
        "Отправьте текст обжалования ответным сообщением:",
        parse_mode="HTML"
    )
    await state.set_state(ObgbanState.waiting_for_reason)

@dp.message(ObgbanState.waiting_for_reason)
async def process_obgban_text(message: Message, state: FSMContext):
    uid = message.from_user.id
    uname = message.from_user.username or f"ID:{uid}"
    reason = message.text
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    cursor.execute("INSERT INTO obgban_requests (user_id, username, reason, date) VALUES (?, ?, ?, ?)",
                   (uid, uname, reason, date_str))
    conn.commit()
    await state.clear()
    await message.answer("✅ Ваша заявка на обжалование GBAN успешно отправлена 9+ рангам!")

    # Уведомление 9+ рангов
    cursor.execute("SELECT user_id FROM users WHERE rank >= 9")
    for row in cursor.fetchall():
        try:
            await bot.send_message(
                row[0],
                f"🌐 <b>Новая заявка на обжалование GBAN!</b>\n\n"
                f"👤 От: @{uname} (<code>{uid}</code>)\n"
                f"📄 Текст: {reason}\n"
                f"📅 Дата: {date_str}",
                parse_mode="HTML"
            )
        except Exception:
            pass

@dp.message(Command("nlist"))
async def cmd_nlist(message: Message):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    nickname = user[16] or "Не задан"
    await message.answer(f"🏷 Ваш кастомный ник в группе (выдан через /snick): <b>{nickname}</b>", parse_mode="HTML")

@dp.message(Command("profile"))
async def cmd_profile(message: Message, command: CommandObject):
    if command.args:
        user = get_user(username=command.args)
    else:
        user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")

    if user:
        u_id, u_name, _, rank, _, coins, exp, level, rep, _, _, _, _, vip_until, msg_cnt, duel_wins, nickname, _, _, _, _, role, zdkd = user
        gban_status = " | 🚨 <b>ИМЕЕТ GBAN</b>" if check_gban(u_id) else ""
        zdkd_status = " | 🚫 <b>ЗДКД активен</b>" if zdkd else ""
        await message.answer(
            f"👤 Профиль: @{u_name or 'без_юзернейма'}{gban_status}{zdkd_status}\n"
            f"🏷 Кастомный ник: {nickname or 'Не задан'}\n"
            f"🎭 Локальная роль: {role}\n"
            f"🎭 Админ-ранг: {rank}\n"
            f"💰 Монеты: {coins} монет\n"
            f"⚡ Уровень: {level} ({exp} EXP)\n"
            f"⭐ Репутация: {rep}\n"
            f"👑 VIP: {'Да' if is_vip(user) else 'Нет'}",
            parse_mode="HTML"
        )
    else:
        await message.answer("❌ Пользователь не найден в базе.")

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    u = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    gban_status = " | 🚨 <b>ИМЕЕТ GBAN</b>" if check_gban(message.from_user.id) else ""
    zdkd_status = " | 🚫 <b>ЗДКД активен</b>" if u[22] else ""
    
    text = (
        f"📊 <b>СТАТИСТИКА ПОЛЬЗОВАТЕЛЯ:</b>{gban_status}{zdkd_status}\n\n"
        f"👤 Имя/Ник: <b>{message.from_user.full_name}</b> (@{u[1] or 'none'})\n"
        f"🏷 Ник в группе: <b>{u[16] or 'Не задан'}</b>\n"
        f"🎭 Локальная роль: <b>{u[21]}</b> | Админ-ранг: <b>{u[3]}</b>\n"
        f"💰 Монеты: <b>{u[5]}</b>\n"
        f"⚡ EXP: <b>{u[6]}</b> | Уровень: <b>{u[7]}</b>\n"
        f"⭐ Репутация: <b>{u[8]}</b>\n"
        f"🔥 Серия бонусов: <b>{u[9]} дней</b>\n"
        f"👑 VIP-статус: <b>{'Активен (' + str(u[13]) + ')' if is_vip(u) else 'Нет'}</b>\n"
        f"💬 Сообщений: <b>{u[14]}</b> | ⚔️ Побед в дуэлях: <b>{u[15]}</b>"
    )
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("help"))
async def cmd_help(message: Message):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    rank = user[3]

    text = (
        "📜 <b>ПОЛНЫЙ СПИСОК КОМАНД БОТА</b>\n\n"
        "<b>🌍 Базовые команды:</b>\n"
        "• <code>/start</code> — Перезапустить бота\n"
        "• <code>/profile [@username]</code> — Профиль\n"
        "• <code>/stats</code> — Ваша статистика\n"
        "• <code>/nlist</code> — Ваш кастомный ник\n"
        "• <code>/q</code> — Выйти из группы\n"
        "• <code>/obgban</code> — Заявка на обжалование GBAN (в ЛС)\n"
        "• <code>/vip</code> — Купить VIP\n"
        "• <code>/buy_money</code> — Купить монеты\n"
        "• <code>/Bmomey</code> — Просмотр заявок на покупку монет (10+)\n"
        "• <code>/zayavka</code> — Единый реестр активных заявок (8+)\n"
        "• <code>/bonus</code> — Ежедневный бонус\n"
        "• <code>/top</code> / <code>/tops</code> — Топы\n"
        "• <code>/report [текст]</code> — Жалоба администрации\n\n"
    )
    if rank >= 4:
        text += (
            "<b>🛡️ Модерация & Управление:</b>\n"
            "• <code>/snick</code>, <code>/rnick</code>, <code>/gnick</code> — Управление никами (2+)\n"
            "• <code>/nonick</code> — Без ника (2+)\n"
            "• <code>/warn</code>, <code>/mute</code>, <code>/kick</code>, <code>/ban</code> (4+)\n"
            "• <code>/gwarn</code> (8+), <code>/gban</code> (9+), <code>/zdkd</code> (9+)\n"
            "• <code>/setga</code>, <code>/unsetga</code>, <code>/settex</code>, <code>/unsettex</code> (8+)\n"
            "• <code>/chechrep</code>, <code>/ghrep</code> (8+)\n"
            "• <code>/give_money</code> (10+), <code>/givevip</code> (10+)\n"
        )
    await message.answer(text, parse_mode="HTML")

# ==========================================
# 6. ЭКОНОМИКА И ИГРОВЫЕ КОМАНДЫ
# ==========================================

@dp.message(Command("rep"))
async def cmd_rep(message: Message, command: CommandObject):
    if not message.reply_to_message:
        return await message.answer("⚠️ Команду нужно вызывать ответом на сообщение!")

    target_id = message.reply_to_message.from_user.id
    sender_id = message.from_user.id
    if target_id == sender_id:
        return await message.answer("❌ Нельзя изменять репутацию самому себе!")

    sender = get_user(user_id=sender_id, username=message.from_user.username or "")
    now_str = datetime.now().strftime("%Y-%m-%d")

    max_rep_count = 3 if is_vip(sender) else 1
    today_count = sender[11] if sender[12] == now_str else 0

    if today_count >= max_rep_count:
        return await message.answer(f"❌ Лимит изменений репутации на сегодня исчерпан ({today_count}/{max_rep_count})!")

    sign = command.args.strip() if command.args else "+"
    delta = 1 if sign != "-" else -1

    target = get_user(user_id=target_id, username=message.reply_to_message.from_user.username or "")
    update_user(target_id, rep=target[8] + delta)
    update_user(sender_id, rep_given_today=today_count + 1, last_rep_date=now_str)

    await message.answer(f"✅ Репутация изменена на {delta}! (Текущая: {target[8] + delta})")

@dp.message(Command("bonus"))
async def cmd_bonus(message: Message):
    uid = message.from_user.id
    user = get_user(user_id=uid, username=message.from_user.username or "")

    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")

    if user[10] == today_str:
        return await message.answer("❌ Вы уже забирали сегодняшний бонус! Приходите завтра.")

    yesterday_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    streak = user[9] + 1 if user[10] == yesterday_str else 1

    coins_add = 100 + (streak - 1) * 25
    exp_add = 50 + (streak - 1) * 10
    new_coins = user[5] + coins_add
    new_exp = user[6] + exp_add
    new_level = user[7]

    update_user(uid, coins=new_coins, exp=new_exp, level=new_level, rep=user[8] + 1, streak=streak, last_bonus=today_str)
    await message.answer(f"🎁 Бонус забран! Серия: {streak} дней. Получено: +{coins_add} монет.")

@dp.message(Command("top"))
async def cmd_top(message: Message):
    cursor.execute("SELECT username, user_id, coins, level, rep, streak, msg_count, duel_wins FROM users ORDER BY coins DESC LIMIT 10")
    rows = cursor.fetchall()
    text = "📊 <b>ТОП-10 ИГРОКОВ:</b>\n\n"
    for idx, r in enumerate(rows, 1):
        name = f"@{r[0]}" if r[0] else f"ID:{r[1]}"
        text += f"{idx}. {name} — 💰 {r[2]} | ⚡ {r[3]} лвл\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("tops"))
async def cmd_tops(message: Message):
    cursor.execute("SELECT user_id, username, coins FROM users ORDER BY coins DESC LIMIT 5")
    rows = cursor.fetchall()
    text = "🌐 <b>МЕЖГРУППОВОЙ ТОП-5:</b>\n\n"
    for idx, r in enumerate(rows, 1):
        name = f"@{r[1]}" if r[1] else f"ID:{r[0]}"
        text += f"{idx}. {name} — 💰 {r[2]} монет\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("transfer"))
async def cmd_transfer(message: Message, command: CommandObject):
    if not message.reply_to_message or not command.args or not command.args.isdigit():
        return await message.answer("⚠️ Ответьте на сообщение: <code>/transfer 500</code>", parse_mode="HTML")

    amount = int(command.args)
    sender = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    limit = 2000 if is_vip(sender) else 500

    if amount > limit or sender[5] < amount:
        return await message.answer("❌ Превышен лимит или недостаточно монет.")

    target_id = message.reply_to_message.from_user.id
    target = get_user(user_id=target_id, username=message.reply_to_message.from_user.username or "")

    update_user(message.from_user.id, coins=sender[5] - amount)
    update_user(target_id, coins=target[5] + amount)
    await message.answer(f"💸 Переведено <b>{amount} монет</b>!", parse_mode="HTML")

# ==========================================
# 7. ДОНАТЫ, ПОКУПКА МОНЕТ И VIP
# ==========================================

@dp.message(Command("Donats"))
async def cmd_donats(message: Message):
    uid = message.from_user.id
    cursor.execute("SELECT period, price, currency, date FROM vip_history WHERE user_id = ?", (uid,))
    vips = cursor.fetchall()
    cursor.execute("SELECT type, amount, currency, date FROM donats_history WHERE user_id = ?", (uid,))
    donats = cursor.fetchall()

    if not vips and not donats:
        return await message.answer("💳 <b>У вас пока нет покупок.</b>", parse_mode="HTML")

    text = "🧾 <b>ВАША ИСТОРИЯ ПОКУПОК:</b>\n\n"
    for v in vips:
        text += f"• VIP: {v[0]} | {v[1]} {v[2]} | {v[3]}\n"
    for d in donats:
        text += f"• {d[0]} | {d[1]} | {d[2]}\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("buy_money"))
async def cmd_buy_money(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплата в ГРН", callback_data="buy_money_uah")],
        [InlineKeyboardButton(text="⭐ Оплата в TG Stars", callback_data="buy_money_stars")]
    ])
    await message.answer("💰 <b>ПОКУПКА ИГРОВЫХ МОНЕТ</b>\nВыберите способ оплаты:", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "buy_money_uah")
async def buy_money_uah_menu(callback: CallbackQuery):
    buttons = [[InlineKeyboardButton(text=v["text"], callback_data=f"buy_m_uah_{k}")] for k, v in MONEY_PACKS_UAH.items()]
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="buy_money_back")])
    await callback.message.edit_text("💳 <b>Выберите пакет монет:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

@dp.callback_query(F.data.startswith("buy_m_uah_"))
async def process_buy_m_uah(callback: CallbackQuery):
    pack_key = callback.data.split("_")[3]
    pack = MONEY_PACKS_UAH[pack_key]
    user = callback.from_user

    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил(а)", callback_data=f"paid_m_uah_{pack_key}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="buy_money_back")]
    ])
    await callback.message.edit_text(
        f"💳 <b>Покупка монет ({pack['coins']} монет)</b>\n\n"
        f"Переведите <b>{pack['price']} грн</b> на банку:\n🔗 {MONOBANK_JAR}\n\n"
        f"Вашу заявку рассмотрят в течение 24 часов. Хорошего дня!",
        reply_markup=confirm_kb, parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("paid_m_uah_"))
async def process_paid_m_uah(callback: CallbackQuery):
    pack_key = callback.data.split("_")[3]
    pack = MONEY_PACKS_UAH[pack_key]
    user = callback.from_user
    username_tag = f"@{user.username}" if user.username else f"ID:{user.id}"
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    cursor.execute("INSERT INTO pending_money_orders (user_id, username, coins, price, currency, date) VALUES (?, ?, ?, ?, ?, ?)",
                   (user.id, username_tag, pack['coins'], str(pack['price']), "грн", date_str))
    conn.commit()
    order_id = cursor.lastrowid

    await callback.message.edit_text("⌛ <b>Ваша заявка отправлена администраторам!</b> Вашу заявку рассмотрят в течение 24 часов. Хорошего дня!", parse_mode="HTML")

    # Уведомление 8+ рангов
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"💰 <b>Новая заявка на покупку монет (#{order_id})!</b>\n"
                f"👤 Пользователь: {username_tag} (<code>{user.id}</code>)\n"
                f"🪙 Пакет: {pack['coins']} монет ({pack['price']} грн)",
                parse_mode="HTML"
            )
        except Exception:
            pass

@dp.message(Command("Bmomey"))
async def cmd_bmomey(message: Message):
    user = get_user(user_id=message.from_user.id)
    if message.from_user.id not in ADMIN_IDS and user[3] < 10:
        return await message.answer("❌ Команда доступна с 10 ранга.")

    cursor.execute("SELECT order_id, user_id, username, coins, price, date FROM pending_money_orders")
    orders = cursor.fetchall()
    if not orders:
        return await message.answer("📥 Заявок на покупку монет нет.")

    text = "📥 <b>Заявки на покупку монет:</b>\n\n"
    for o in orders:
        text += f"🔹 ID: <code>{o[0]}</code> | Пользователь: {o[2]} (<code>{o[1]}</code>) | Монет: {o[3]} | Сумма: {o[4]} грн\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("Omoney"))
async def cmd_omoney(message: Message):
    user = get_user(user_id=message.from_user.id)
    if message.from_user.id not in ADMIN_IDS and user[3] < 8:
        return await message.answer("❌ Доступно с 8+ ранга.")

    cursor.execute("SELECT user_id, username, coins, price, date FROM pending_money_orders")
    orders = cursor.fetchall()
    if not orders:
        return await message.answer("📋 Список одобрения монет пуст.")

    text = "📋 <b>Заявки на покупку монет (Ожидают):</b>\n\n"
    for o in orders:
        text += f"• Пользователь: {o[1]} (<code>{o[0]}</code>) — {o[2]} монет ({o[3]} грн)\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("Ovip"))
async def cmd_ovip(message: Message):
    user = get_user(user_id=message.from_user.id)
    if message.from_user.id not in ADMIN_IDS and user[3] < 8:
        return await message.answer("❌ Доступно с 8+ ранга.")

    cursor.execute("SELECT user_id, username, period, price, date FROM pending_vip_orders")
    orders = cursor.fetchall()
    if not orders:
        return await message.answer("📋 Заявки на VIP отсутствуют.")

    text = "📋 <b>Заявки на VIP-статус:</b>\n\n"
    for o in orders:
        text += f"• Пользователь: {o[1]} (<code>{o[0]}</code>) — Срок: {o[2]} мес. ({o[3]} грн)\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("Uovip"))
async def cmd_uovip(message: Message):
    await message.answer("📋 <b>Список пользователей без оплаченного VIP:</b> (Все пользователи базы без активного VIP)", parse_mode="HTML")

@dp.message(Command("Onmoney"))
async def cmd_onmoney(message: Message):
    await message.answer("❌ <b>Список отклоненных или пустых оплат.</b>", parse_mode="HTML")

@dp.message(Command("vip"))
async def cmd_vip(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплата в ГРН", callback_data="buy_vip_uah")],
        [InlineKeyboardButton(text="⭐️ Оплата Звёздами TG", callback_data="buy_vip_stars")]
    ])
    await message.answer("✨ <b>Выберите способ оплаты VIP-статуса:</b>", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "buy_vip_uah")
async def select_uah(callback: CallbackQuery):
    buttons = [[InlineKeyboardButton(text=v["text"], callback_data=f"select_uah_{k}")] for k, v in PRICES_UAH.items()]
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_currency")])
    await callback.message.edit_text("💳 <b>Выберите период VIP:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

@dp.callback_query(F.data.startswith("select_uah_"))
async def process_uah_selection(callback: CallbackQuery):
    period = callback.data.split("_")[2]
    info = PRICES_UAH[period]
    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил(а)", callback_data=f"paid_uah_{period}_{info['price']}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="back_to_currency")]
    ])
    await callback.message.edit_text(
        f"💳 <b>Оплата VIP ({info['text']})</b>\n\nПереведите <b>{info['price']} грн</b> на банку:\n🔗 {MONOBANK_JAR}\n\n"
        f"Вашу заявку рассмотрят в течение 24 часов. Хорошего дня!",
        reply_markup=confirm_kb, parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("paid_uah_"))
async def process_uah_paid(callback: CallbackQuery):
    _, _, period, price = callback.data.split("_")
    user = callback.from_user
    username = f"@{user.username}" if user.username else f"ID: {user.id}"
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    cursor.execute("INSERT INTO pending_vip_orders (user_id, username, period, price, currency, date) VALUES (?, ?, ?, ?, ?, ?)",
                   (user.id, username, period, price, "грн", date_str))
    conn.commit()
    await callback.message.edit_text("⌛ <b>Ваша заявка отправлена администраторам!</b> Вашу заявку рассмотрят в течение 24 часов. Хорошего дня!", parse_mode="HTML")

@dp.message(Command("give_money"))
async def cmd_give_money(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 10:
        return await message.answer("❌ Команда доступна исключительно 10 рангу.")

    if not command.args or len(command.args.split()) < 2:
        return await message.answer("⚠️ Использование: <code>/give_money @username 10000</code>", parse_mode="HTML")

    parts = command.args.split()
    target_username = clean_username(parts[0])
    if not parts[1].isdigit():
        return await message.answer("⚠️ Укажите число монет цифрами.")

    amount = int(parts[1])
    if amount < 10000:
        return await message.answer("❌ Минимальная сумма выдачи монет для 10 ранга составляет <b>10000</b>!", parse_mode="HTML")

    row = get_user(username=target_username)
    if not row:
        return await message.answer(f"❌ Пользователь @{target_username} не найден в базе!")

    update_user(row[0], coins=row[5] + amount)
    await message.answer(f"✅ Успешно выдано <b>{amount} монет</b> пользователю @{target_username}!", parse_mode="HTML")

@dp.message(Command("givevip"))
async def cmd_givevip(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 10:
        return await message.answer("❌ Команда доступна исключительно 10 рангу.")

    if not command.args or len(command.args.split()) < 2:
        return await message.answer("⚠️ Использование: <code>/givevip @username 30</code>", parse_mode="HTML")

    parts = command.args.split()
    target_clean = clean_username(parts[0])
    days_str = parts[1]

    t_user = get_user(username=target_clean)
    if not t_user:
        return await message.answer("❌ Пользователь не найден в базе.")

    add_vip_time(t_user[0], days_str)
    await message.answer(f"✅ Пользователю @{target_clean} успешно выдан VIP на {days_str} дней/мес!", parse_mode="HTML")

# ==========================================
# 8. МОДЕРАЦИЯ И АДМИНИСТРИРОВАНИЕ (8-10 Ранги)
# ==========================================

@dp.message(Command("snick"))
async def cmd_snick(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 2: return await message.answer("❌ Доступно с 2 ранга.")
    
    target_id = None
    if message.reply_to_message:
        target_id = message.reply_to_message.from_user.id
    elif command.args:
        parts = command.args.split(maxsplit=1)
        if parts[0].startswith("@"):
            t_row = get_user(username=parts[0])
            if t_row: target_id = t_row[0]
            nickname = parts[1] if len(parts) > 1 else ""
        else:
            nickname = command.args

    if not target_id and message.reply_to_message:
        target_id = message.reply_to_message.from_user.id

    if not target_id or not command.args:
        return await message.answer("⚠️ Использование: ответом на сообщение или <code>/snick @username Ник</code>", parse_mode="HTML")

    update_user(target_id, custom_nickname=command.args)
    await message.answer(f"✅ Установлен локальный ник: <b>{command.args}</b>", parse_mode="HTML")

@dp.message(Command("warn"))
async def cmd_warn(message: Message):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 4: return await message.answer("❌ Строго с 4+ ранга.")
    if not message.reply_to_message: return await message.answer("⚠️ Ответьте на сообщение!")

    tid = message.reply_to_message.from_user.id
    target = get_user(user_id=tid)
    warns = target[19] + 1

    if warns >= 3:
        update_user(tid, warns=0)
        try:
            await bot.ban_chat_member(message.chat.id, tid)
            await message.answer("💥 Пользователь получил 3/3 варнов и был кикнут!")
        except Exception: pass
    else:
        update_user(tid, warns=warns)
        await message.answer(f"⚠️ Выдан варн ({warns}/3)!")

@dp.message(Command("gwarn"))
async def cmd_gwarn(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 8: return await message.answer("❌ GWARN доступен с 8+ ранга.")
    if not message.reply_to_message or not command.args:
        return await message.answer("⚠️ Укажите причину ответом на сообщение: <code>/gwarn Причина</code>", parse_mode="HTML")

    tid = message.reply_to_message.from_user.id
    b_name = message.from_user.username or "Admin"
    is_banned = add_gwarn(tid, command.args, b_name)

    if is_banned:
        await message.answer("🌐 Пользователь набрал 3/3 GWARN и автоматически получил <b>GBAN</b>!", parse_mode="HTML")
    else:
        await message.answer("🌐 Выдан глобальный варн (GWARN)!", parse_mode="HTML")

@dp.message(Command("gban"))
async def cmd_gban(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 9: return await message.answer("❌ GBAN доступен с 9+ ранга.")
    if not message.reply_to_message or not command.args:
        return await message.answer("⚠️ Ответьте на сообщение и укажите причину: <code>/gban Причина</code>", parse_mode="HTML")

    tid = message.reply_to_message.from_user.id
    cursor.execute("INSERT OR REPLACE INTO global_bans VALUES (?, ?, ?)", (tid, command.args, message.from_user.username))
    conn.commit()
    await message.answer("🌐 Глобальный бан (GBAN) успешно выдан!", parse_mode="HTML")

@dp.message(Command("zdkd"))
async def cmd_zdkd(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 9: return await message.answer("❌ Команда /zdkd доступна с 9+ ранга.")
    if not message.reply_to_message and not command.args:
        return await message.answer("⚠️ Использование: ответом на сообщение или <code>/zdkd @username Причина</code>", parse_mode="HTML")

    tid = message.reply_to_message.from_user.id if message.reply_to_message else get_user(username=clean_username(command.args.split()[0]))[0]
    update_user(tid, zdkd=1)
    await message.answer("🚫 Пользователю выдан <b>ЗДКД</b> (Закрыт доступ к должностям 6+ ранга).", parse_mode="HTML")

@dp.message(Command("setzam"))
async def cmd_setzam(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 10: return await message.answer("❌ Назначать замов может только 10 ранг (ГР).")
    if not command.args:
        return await message.answer("⚠️ Использование: <code>/setzam @username [ОЗГР / ЗГР]</code>", parse_mode="HTML")

    parts = command.args.split(maxsplit=1)
    target_un = clean_username(parts[0])
    zam_role = parts[1] if len(parts) > 1 else "Заместитель"

    set_role(target_un, zam_role)
    t_user = get_user(username=target_un)
    if t_user: update_user(t_user[0], rank=8)

    await message.answer(f"👑 Пользователь @{target_un} назначен на должность: <b>{zam_role}</b>!", parse_mode="HTML")

    # Уведомление в ЛС всем участникам
    cursor.execute("SELECT user_id FROM users")
    for row in cursor.fetchall():
        try:
            await bot.send_message(
                row[0],
                f"🎉 На должность <b>{zam_role}</b> становится @{target_un}!\nПожелаем удачи и больше достижений в будущем! Грац 🥂",
                parse_mode="HTML"
            )
        except Exception:
            pass

@dp.message(Command("setga"))
async def cmd_setga(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 8: return await message.answer("❌ Доступно с 8+ ранга.")
    if not command.args: return await message.answer("⚠️ Укажите юзернейм: <code>/setga @username Причина</code>", parse_mode="HTML")

    target_un = clean_username(command.args.split()[0])
    set_role(target_un, "Главный Администратор (ГА)")
    t_user = get_user(username=target_un)
    if t_user: update_user(t_user[0], rank=6)
    await message.answer(f"✅ Пользователь @{target_un назначен Главным Администратором (ГА).", parse_mode="HTML")

@dp.message(Command("unsetga"))
async def cmd_unsetga(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 8: return await message.answer("❌ Доступно с 8+ ранга.")
    target_un = clean_username(command.args.split()[0] if command.args else "")
    set_role(target_un, "User")
    t_user = get_user(username=target_un)
    if t_user: update_user(t_user[0], rank=0)
    await message.answer(f"📉 Пользователь @{target_un} снят с поста ГА.", parse_mode="HTML")

@dp.message(Command("settex"))
async def cmd_settex(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 8: return await message.answer("❌ Назначать ТС может только 8+ ранг после одобрения.")
    target_un = clean_username(command.args.split()[0] if command.args else "")
    set_role(target_un, "Технический специалист (ТС)")
    t_user = get_user(username=target_un)
    if t_user: update_user(t_user[0], rank=7)
    await message.answer(f"✅ Пользователь @{target_un} назначен Техническим специалистом (ТС).", parse_mode="HTML")

@dp.message(Command("unsettex"))
async def cmd_unsettex(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 8: return await message.answer("❌ Доступно с 8+ ранга.")
    target_un = clean_username(command.args.split()[0] if command.args else "")
    set_role(target_un, "User")
    t_user = get_user(username=target_un)
    if t_user: update_user(t_user[0], rank=0)
    await message.answer(f"📉 Пользователь @{target_un} снят с поста ТС.", parse_mode="HTML")

@dp.message(Command("chechrep"))
async def cmd_chechrep(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8: return await message.answer("❌ Доступно с 8+ ранга.")
    cursor.execute("SELECT id, text FROM reports WHERE status = 'pending'")
    rows = cursor.fetchall()
    if not rows: return await message.answer("📋 Активных жалоб нет.")
    text = "📋 <b>ВСЕ ЖАЛОБЫ (/report):</b>\n\n"
    for r in rows:
        text += f"• ID: {r[0]} | Суть: {r[1]}\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("ghrep"))
async def cmd_ghrep(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8: return await message.answer("❌ Доступно с 8+ ранга.")
    await message.answer(f"✅ Репорты успешно переданы нужной роли: <b>{command.args or 'Общие'}</b>", parse_mode="HTML")

@dp.message(Command("zayavka"))
async def cmd_zayavka(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8: return await message.answer("❌ Реестр заявок доступен с 8+ ранга.")
    
    cursor.execute("SELECT COUNT(*) FROM pending_vip_orders")
    vip_cnt = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM pending_money_orders")
    money_cnt = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM obgban_requests")
    obg_cnt = cursor.fetchone()[0]

    text = (
        "📋 <b>ЕДИНЫЙ РЕЕСТР АКТИВНЫХ ЗАЯВОК:</b>\n\n"
        f"👑 Заявки VIP (всего {vip_cnt}): используйте <code>/Ovip</code>\n"
        f"💰 Заявки Монеты (всего {money_cnt}): используйте <code>/Omoney</code>\n"
        f"🌐 Обжалование GBAN (всего {obg_cnt})\n"
    )
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("Global_news", prefix="/"))
@dp.message(Command("global_news", prefix="/"))
async def cmd_global_news(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 10: return await message.answer("❌ Рассылка правил и глобальных новостей доступна только 10 рангу.")
    if not command.args:
        return await message.answer("⚠️ Укажите текст правил/новости: <code>/Global_news Пункт 1 Накрутка...</code>", parse_mode="HTML")

    news_text = f"📢 <b>ПРАВИЛА И НОВОСТИ СИСТЕМЫ (10 ранг):</b>\n\n{command.args}"
    cursor.execute("SELECT chat_id FROM known_chats")
    chats = cursor.fetchall()
    cnt = 0
    for ch in chats:
        try:
            await bot.send_message(ch[0], news_text, parse_mode="HTML")
            cnt += 1
        except Exception:
            pass

    # Также рассылка в ЛС всем пользователям
    cursor.execute("SELECT user_id FROM users")
    for u in cursor.fetchall():
        try:
            await bot.send_message(u[0], news_text, parse_mode="HTML")
        except Exception:
            pass

    await message.answer(f"✅ Правила успешно разосланы в <b>{cnt}</b> чатов и в ЛС пользователям!", parse_mode="HTML")

# ==========================================
# 9. ЗАПУСК БОТА
# ==========================================
async def main():
    logging.info("Starting Stars Manager Bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped!")
