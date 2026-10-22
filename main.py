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
        zdkd INTEGER DEFAULT 0,
        last_active TEXT,
        last_command TEXT
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

    cursor.execute('''CREATE TABLE IF NOT EXISTS obnyl_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        old_coins INTEGER,
        old_exp INTEGER,
        old_level INTEGER,
        old_rep INTEGER,
        old_rank INTEGER,
        date TEXT
    )''')

    # Проверка столбцов для версий БД, созданных ранее
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN last_active TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN last_command TEXT")
    except sqlite3.OperationalError:
        pass

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

    days_to_add = int(period) * 30 if period.isdigit() else 7
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

async def send_log_to_user(user_id: int, text: str):
    try:
        await bot.send_message(user_id, f"📝 <b>[ЛОГ СИСТЕМЫ]</b>\n{text}", parse_mode="HTML")
    except Exception:
        pass

def add_donat_record(user_id: int, username: str, type_str: str, amount: str, currency: str):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute(
        "INSERT INTO donats_history (user_id, username, type, amount, currency, date) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, clean_username(username), type_str, amount, currency, now_str)
    )
    conn.commit()

# ==========================================
# 3. FSM СОСТОЯНИЯ И ПРАЙС-ЛИСТЫ
# ==========================================
class AdminProcessOrder(StatesGroup):
    waiting_for_details = State()

class AdminRejectOrder(StatesGroup):
    waiting_for_reason = State()
    order_type = State()
    order_id = State()

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
    "15000": {"coins": 15000, "price": 140, "text": "15,000 монет — 140 грн"},
    "20000": {"coins": 20000, "price": 180, "text": "20,000 монет — 180 грн"},
}

MONEY_PACKS_STARS = {
    "1000": {"coins": 1000, "price": 25, "text": "1,000 монет — 25 Stars ⭐️"},
    "5000": {"coins": 5000, "price": 85, "text": "5,000 монет — 85 Stars ⭐️"},
    "10000": {"coins": 10000, "price": 150, "text": "10,000 монет — 150 Stars ⭐️"},
    "15000": {"coins": 15000, "price": 200, "text": "15,000 монет — 200 Stars ⭐️"},
    "20000": {"coins": 20000, "price": 245, "text": "20,000 монет — 245 Stars ⭐️"},
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
    
    # Трекинг сообщений и последней активности пользователя
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    last_cmd = event.text if event.text else "Сообщение/Медиа"
    
    cursor.execute(
        "UPDATE users SET msg_count = msg_count + 1, last_active = ?, last_command = ? WHERE user_id = ?",
        (now_str, last_cmd, user_id)
    )
    conn.commit()

    return await handler(event, data)

# ==========================================
# 5. ОСНОВНЫЕ КОМАНДЫ, ПРОФИЛЬ И СПРАВКА
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
    await message.answer(f"Привет снова, @{clean_username(username)}! Ваш баланс: {user[5]} монет.", parse_mode="Markdown")

@dp.message(Command("id"))
async def cmd_id(message: Message, command: CommandObject):
    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
        return await message.answer(
            f"👤 <b>Пользователь:</b> @{target_user.username or 'без_юзернейма'}\n"
            f"🆔 <b>ID:</b> <code>{target_user.id}</code>",
            parse_mode="HTML"
        )

    if command.args:
        target_username = clean_username(command.args)
        user_row = get_user(username=target_username)

        if user_row:
            await message.answer(
                f"👤 <b>Пользователь:</b> @{target_username}\n"
                f"🆔 <b>ID:</b> <code>{user_row[0]}</code>",
                parse_mode="HTML"
            )
        else:
            await message.answer(
                f"❌ Пользователь <b>@{target_username}</b> не найден в базе данных бота.",
                parse_mode="HTML"
            )
        return

    await message.answer(
        f"👤 <b>Ваш профиль:</b> @{message.from_user.username or 'без_юзернейма'}\n"
        f"🆔 <b>Ваш ID:</b> <code>{message.from_user.id}</code>",
        parse_mode="HTML"
    )

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
    cursor.execute("SELECT user_id, username, custom_nickname FROM users WHERE custom_nickname IS NOT NULL AND custom_nickname != ''")
    rows = cursor.fetchall()

    if not rows:
        return await message.answer("📋 В базе пока нет пользователей с установленным кастомным ником.")

    text = "📋 <b>СПИСОК ВСЕХ КАСТОМНЫХ НИКОВ:</b>\n\n"
    for r in rows:
        tag = f"@{r[1]}" if r[1] else f"ID:{r[0]}"
        text += f"• <b>[{r[2]}]</b> [{tag}]\n"

    await message.answer(text, parse_mode="HTML")

@dp.message(Command("nonick"))
async def cmd_nonick(message: Message):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 2:
        return await message.answer("❌ Команда доступна с 2+ ранга модерации.")

    cursor.execute("SELECT user_id, username FROM users WHERE custom_nickname IS NULL OR custom_nickname = '' LIMIT 25")
    rows = cursor.fetchall()

    if not rows:
        return await message.answer("✅ В базе данных нет пользователей без кастомного ника.")

    text = "👥 <b>Список пользователей без кастомного ника:</b>\n\n"
    for r in rows:
        uname = f"@{r[1]}" if r[1] else f"ID:{r[0]}"
        text += f"• {uname} (ID: <code>{r[0]}</code>)\n"

    await message.answer(text, parse_mode="HTML")

@dp.message(Command("profile"))
async def cmd_profile(message: Message, command: CommandObject):
    if command.args:
        user = get_user(username=command.args)
    else:
        user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")

    if user:
        u_id, u_name, _, rank, _, coins, exp, level, rep, _, _, _, _, vip_until, msg_cnt, duel_wins, nickname, _, _, _, role, zdkd, *_ = user
        gban_status = " | 🚨 <b>ИМЕЕТ GBAN</b>" if check_gban(u_id) else ""
        zdkd_status = " | 🚫 <b>ЗДКД активен</b>" if zdkd else ""
        await message.answer(
            f"👤 Профиль: @{u_name or 'без_юзернейма'}{gban_status}{zdkd_status}\n"
            f"🏷 Кастомный ник: {nickname or 'Не задан'}\n"
            f"🎭 Локальная роль: {role}\n"
            f"🎭 Админ-ранг: {rank}\n"
            f"💰 Баланс: {coins} монет\n"
            f"⚡ Уровень: {level} ({exp} EXP)\n"
            f"⭐ Репутация: {rep}\n"
            f"👑 VIP: {'Да' if is_vip(user) else 'Нет'}",
            parse_mode="Markdown"
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
        "<b>🌍 1. Основные & Экономика & Магазины:</b>\n"
        "• <code>/profile [@username]</code> — Профиль\n"
        "• <code>/id [@username]</code> — Узнать Telegram ID\n"
        "• <code>/stats</code> — Статистика с ником и статусами\n"
        "• <code>/nlist</code> — Список всех кастомных ников\n"
        "• <code>/q</code> — Выйти из группы\n"
        "• <code>/obgban</code> — Заявка на обжалование GBAN (в ЛС)\n"
        "• <code>/vip</code> — Купить VIP (UAH / Stars)\n"
        "• <code>/buy_money</code> — Купить монеты\n"
        "• <code>/givemevip</code> — Выдать себе VIP на 7 дней (8+)\n"
        "• <code>/blago</code> — Поддержка проекта\n"
        "• <code>/Donats</code> — История покупок\n"
        "• <code>/rep [+/-]</code> — Изменить репутацию\n"
        "• <code>/bonus</code> — Ежедневный бонус\n"
        "• <code>/top</code> / <code>/tops</code> — Топы чата / Глобальный\n"
        "• <code>/shop</code> / <code>/eshop</code> — Магазины\n"
        "• <code>/role_shop</code> / <code>/create_role</code> — Магазин ролей\n"
        "• <code>/duel [ставка]</code> — Дуэль на монеты\n"
        "• <code>/transfer [user] [сумма]</code> — Перевод монет (до 1000/10000)\n"
        "• <code>/report [текст]</code> — Жалоба администрации\n\n"
        "<b>🛡️ 2. Модерация & Управление:</b>\n"
        "• <code>/snick</code>, <code>/rnick</code>, <code>/gnick</code> — Управление никами (2+)\n"
        "• <code>/nonick</code> — Пользователи без ника (2+)\n"
        "• <code>/zov [причина]</code> — Вызов участников (3+)\n"
        "• <code>/news</code> — Правила бота\n"
        "• <code>/olist</code> — Пользователи в сети в группе (5+)\n"
        "• <code>/olists</code> — Полная история взаимодействий с ботом (8+)\n"
        "• <code>/staff</code> — Состав модерации (1+)\n"
        "• <code>/warn</code>, <code>/mute</code>, <code>/kick</code>, <code>/ban</code> (4+)\n"
        "• <code>/skick</code>, <code>/sban</code> — Массовые кики/баны по группам (5+)\n"
        "• <code>/pin</code>, <code>/gban</code> (6+)\n"
        "• <code>/unban</code>, <code>/unmute</code>, <code>/unwarn</code> (5+)\n"
        "• <code>/gwarn</code> (8+), <code>/zdkd</code> (9+)\n"
        "• <code>/setga</code>, <code>/unsetga</code>, <code>/settex</code>, <code>/unsettex</code> (8+)\n"
        "• <code>/checkrep</code>, <code>/ghrep</code> (8+)\n"
        "• <code>/odnyllist</code> — История обнулений (8+)\n"
        "• <code>/Obnyl_money</code> — Обнуление баланса (9+)\n"
        "• <code>/Obnyl</code> — Полное обнуление аккаунта (10+)\n"
        "• <code>/zayavka</code>, <code>/Ovip</code>, <code>/Omoney</code>, <code>/Bmomey</code> (8-10+)\n"
        "• <code>/give_money</code>, <code>/givevip</code>, <code>/Global_news</code> (10+)\n"
        "• Логи: <code>/Pbook</code>, <code>/Pbooks</code>, <code>/book</code>, <code>/books</code>, <code>/book_global</code>\n"
    )
    await message.answer(text, parse_mode="HTML")

# ==========================================
# 6. ЭКОНОМИКА, МАГАЗИНЫ И ИГРОВЫЕ КОМАНДЫ
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
    
    limit = 10000 if is_vip(sender) else 1000

    if amount > limit:
        return await message.answer(f"❌ Ваш лимит перевода составляет <b>{limit} монет</b> в день!", parse_mode="HTML")

    if sender[5] < amount:
        return await message.answer("❌ У вас недостаточно монет на балансе.")

    target_id = message.reply_to_message.from_user.id
    target = get_user(user_id=target_id, username=message.reply_to_message.from_user.username or "")

    update_user(message.from_user.id, coins=sender[5] - amount)
    update_user(target_id, coins=target[5] + amount)
    await message.answer(f"💸 Переведено <b>{amount} монет</b> пользователю {message.reply_to_message.from_user.full_name}!", parse_mode="HTML")

@dp.message(Command("duel"))
async def cmd_duel(message: Message, command: CommandObject):
    if not message.reply_to_message or not command.args or not command.args.isdigit():
        return await message.answer("⚠️ Использование: ответьте на сообщение и укажите ставку <code>/duel 100</code>", parse_mode="HTML")

    bet = int(command.args)
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    max_bet = 2000 if is_vip(user) else 500
    min_bet = 1 if is_vip(user) else 10

    if not (min_bet <= bet <= max_bet):
        return await message.answer(f"❌ Допустимая ставка: от {min_bet} до {max_bet} монет!")

    if user[5] < bet:
        return await message.answer("❌ У вас недостаточно монет!")

    target_id = message.reply_to_message.from_user.id
    if target_id == message.from_user.id:
        return await message.answer("❌ Нельзя играть в дуэль самому с собой!")

    target = get_user(user_id=target_id, username=message.reply_to_message.from_user.username or "")
    if target[5] < bet:
        return await message.answer("❌ У соперника недостаточно монет!")

    winner_id = random.choice([message.from_user.id, target_id])
    loser_id = target_id if winner_id == message.from_user.id else message.from_user.id

    w_user = get_user(user_id=winner_id)
    l_user = get_user(user_id=loser_id)

    update_user(winner_id, coins=w_user[5] + bet, duel_wins=w_user[15] + 1)
    update_user(loser_id, coins=l_user[5] - bet)

    await message.answer(f"⚔️ В дуэли победил <a href='tg://user?id={winner_id}'>Игрок</a> и выиграл <b>{bet} монет</b>!", parse_mode="HTML")

@dp.message(Command("givemevip"))
async def cmd_givemevip(message: Message):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 8 and message.from_user.id not in ADMIN_IDS:
        return await message.answer("❌ Команда доступна только администраторам с 8+ ранга!")

    v_until = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    update_user(message.from_user.id, vip_until=v_until)
    await message.answer("🎉 Вам успешно активирован <b>VIP на 7 дней</b>!", parse_mode="HTML")

@dp.message(Command("shop"))
async def cmd_shop(message: Message, command: CommandObject):
    cursor.execute("SELECT shop_exp_rate FROM chat_settings WHERE chat_id = ?", (message.chat.id,))
    row = cursor.fetchone()
    rate = row[0] if row else 10

    if not command.args:
        return await message.answer(f"🏪 <b>ОБЫЧНЫЙ МАГАЗИН</b>\nКурс обмена: 1 EXP = {rate} монет.\nИспользование: <code>/shop exp [кол-во EXP]</code>", parse_mode="HTML")

    parts = command.args.split()
    if parts[0] == "exp" and len(parts) > 1 and parts[1].isdigit():
        exp_to_buy = int(parts[1])
        cost = exp_to_buy * rate
        user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
        if user[5] < cost:
            return await message.answer("❌ У вас недостаточно монет!")
        update_user(message.from_user.id, coins=user[5] - cost, exp=user[6] + exp_to_buy)
        await message.answer(f"✅ Куплено {exp_to_buy} EXP за {cost} монет!")

@dp.message(Command("eshop"))
async def cmd_eshop(message: Message):
    await message.answer("✨ <b>ЭКСКЛЮЗИВНЫЙ МАГАЗИН:</b>\nОбратитесь к Высшей Администрации для приобретения уникальных привилегий.", parse_mode="HTML")

@dp.message(Command("role_shop"))
async def cmd_role_shop(message: Message):
    cursor.execute("SELECT role_id, text, price FROM custom_roles WHERE chat_id = ?", (message.chat.id,))
    roles = cursor.fetchall()
    if not roles:
        return await message.answer("🛒 В этом чате пока нет созданных ролей.")
    text = "🛒 <b>МАГАЗИН РОЛЕЙ ЧАТА:</b>\n\n"
    for r in roles:
        text += f"ID: <code>{r[0]}</code> | {r[1]} — 💰 {r[2]} монет\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("create_role"))
async def cmd_create_role(message: Message, command: CommandObject):
    if not command.args:
        return await message.answer("⚠️ Использование: <code>/create_role [Текст] [#HEX-код] [Цена]</code>", parse_mode="HTML")
    try:
        raw = command.args
        text = raw[raw.find("[")+1:raw.find("]")]
        rest = raw[raw.find("]")+1:]
        color = rest[rest.find("[")+1:rest.find("]")]
        price = int(rest.split("[")[-1].replace("]", ""))

        cursor.execute("INSERT INTO custom_roles (creator_id, chat_id, text, color_code, price) VALUES (?, ?, ?, ?, ?)",
                       (message.from_user.id, message.chat.id, text, color, price))
        conn.commit()
        await message.answer(f"✅ Роль '{text}' успешно создана!")
    except Exception:
        await message.answer("❌ Ошибка формата!")

@dp.message(Command("report"))
async def cmd_report(message: Message, command: CommandObject):
    if not command.args:
        return await message.answer("⚠️ Укажите суть жалобы: <code>/report Текст</code>", parse_mode="HTML")
    target_id = message.reply_to_message.from_user.id if message.reply_to_message else 0
    cursor.execute("INSERT INTO reports (chat_id, user_id, target_id, text) VALUES (?, ?, ?, ?)",
                   (message.chat.id, message.from_user.id, target_id, command.args))
    conn.commit()
    await message.answer("🚨 Ваша жалоба отправлена администрации!")

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

@dp.message(Command("blago"))
async def cmd_blago(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Донат в ГРН", callback_data="blago_uah")],
        [InlineKeyboardButton(text="⭐️ Донат в Stars", callback_data="blago_stars")]
    ])
    await message.answer("❤️ <b>Поддержка команды разработчиков бота</b>", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "blago_uah")
async def blago_uah_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(f"💳 Ссылка на банку Monobank:\n{MONOBANK_JAR}\n\nВведите сумму в грн:", parse_mode="HTML")
    await state.set_state(BlagoState.waiting_for_uah_amount)

@dp.message(BlagoState.waiting_for_uah_amount)
async def blago_uah_process(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("⚠️ Введите корректное число.")
    amount = message.text
    user = message.from_user
    username = f"@{user.username}" if user.username else f"ID: {user.id}"
    add_donat_record(user.id, username, "Благо", f"{amount} грн", "грн")
    await state.clear()
    await message.answer("❤️ Спасибо за поддержку! Заявка отправлена администраторам.")

@dp.message(Command("buy_money"))
async def cmd_buy_money(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплата в ГРН", callback_data="buy_money_uah")],
        [InlineKeyboardButton(text="⭐ Оплата в TG Stars", callback_data="buy_money_stars")]
    ])
    await message.answer("💰 <b>ПОКУПКА МОНЕТ</b>\nВыберите способ оплаты:", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "buy_money_uah")
async def buy_money_uah_menu(callback: CallbackQuery):
    buttons = [[InlineKeyboardButton(text=v["text"], callback_data=f"buy_m_uah_{k}")] for k, v in MONEY_PACKS_UAH.items()]
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="buy_money_back")])
    await callback.message.edit_text("💳 <b>Выберите пакет монет:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

@dp.callback_query(F.data.startswith("buy_m_uah_"))
async def process_buy_m_uah(callback: CallbackQuery):
    pack_key = callback.data.split("_")[3]
    pack = MONEY_PACKS_UAH[pack_key]
    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил(а)", callback_data=f"paid_m_uah_{pack_key}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="buy_money_back")]
    ])
    await callback.message.edit_text(
        f"💳 <b>Покупка ({pack['coins']} монет)</b>\n\nПереведите <b>{pack['price']} грн</b>:\n🔗 {MONOBANK_JAR}\n\n"
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

    await callback.message.edit_text("⌛ <b>Заявка отправлена!</b> Вашу заявку рассмотрят в течение 24 часов. Хорошего дня!", parse_mode="HTML")

    admin_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"m_conf_{order_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"m_ref_{order_id}")
    ]])

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, f"💰 Заявка на монеты (#{order_id}) от {username_tag} на {pack['coins']} монет.", reply_markup=admin_kb)
        except Exception:
            pass

@dp.message(Command("Bmomey"))
async def cmd_bmomey(message: Message):
    user = get_user(user_id=message.from_user.id)
    if message.from_user.id not in ADMIN_IDS and user[3] < 10:
        return await message.answer("❌ Доступно с 10 ранга.")
    cursor.execute("SELECT order_id, user_id, username, coins, price FROM pending_money_orders")
    orders = cursor.fetchall()
    if not orders: return await message.answer("📥 Заявок нет.")
    text = "📥 <b>Заявки на монеты:</b>\n"
    for o in orders: text += f"ID: {o[0]} | @{o[2]} | {o[3]} монет ({o[4]} грн)\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("Omoney"))
async def cmd_omoney(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8: return await message.answer("❌ Доступно с 8+ ранга.")
    cursor.execute("SELECT user_id, username, coins, price FROM pending_money_orders")
    orders = cursor.fetchall()
    text = "📋 <b>Ожидающие монеты:</b>\n"
    for o in orders: text += f"• @{o[1]} — {o[2]} монет\n"
    await message.answer(text if orders else "Пусто", parse_mode="HTML")

@dp.message(Command("Ovip"))
async def cmd_ovip(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8: return await message.answer("❌ Доступно с 8+ ранга.")
    cursor.execute("SELECT user_id, username, period, price FROM pending_vip_orders")
    orders = cursor.fetchall()
    text = "📋 <b>Заявки на VIP:</b>\n"
    for o in orders: text += f"• @{o[1]} — {o[2]} мес. ({o[3]} грн)\n"
    await message.answer(text if orders else "Пусто", parse_mode="HTML")

@dp.message(Command("Uovip"))
async def cmd_uovip(message: Message):
    await message.answer("📋 Список пользователей без VIP.", parse_mode="HTML")

@dp.message(Command("Onmoney"))
async def cmd_onmoney(message: Message):
    await message.answer("❌ Список отклоненных заявок.", parse_mode="HTML")

@dp.message(Command("vip"))
async def cmd_vip(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплата в ГРН", callback_data="buy_vip_uah")],
        [InlineKeyboardButton(text="⭐️ Оплата Звёздами", callback_data="buy_vip_stars")]
    ])
    await message.answer("✨ <b>Выберите способ оплаты VIP:</b>", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "buy_vip_uah")
async def select_uah(callback: CallbackQuery):
    buttons = [[InlineKeyboardButton(text=v["text"], callback_data=f"select_uah_{k}")] for k, v in PRICES_UAH.items()]
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_currency")])
    await callback.message.edit_text("💳 Выберите период:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

@dp.callback_query(F.data.startswith("select_uah_"))
async def process_uah_selection(callback: CallbackQuery):
    period = callback.data.split("_")[2]
    info = PRICES_UAH[period]
    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил(а)", callback_data=f"paid_uah_{period}_{info['price']}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="back_to_currency")]
    ])
    await callback.message.edit_text(
        f"💳 Переведите <b>{info['price']} грн</b>:\n🔗 {MONOBANK_JAR}\n\nВашу заявку рассмотрят в течение 24 часов. Хорошего дня!",
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
    order_id = cursor.lastrowid

    await callback.message.edit_text("⌛ <b>Заявка отправлена!</b> Вашу заявку рассмотрят в течение 24 часов. Хорошего дня!", parse_mode="HTML")
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"vip_conf_{order_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"vip_ref_{order_id}")
    ]])
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, f"📥 Заявка на VIP (#{order_id}) от {username}", reply_markup=admin_kb)
        except Exception: pass

@dp.callback_query(F.data.startswith("vip_conf_"))
async def admin_confirm_vip(callback: CallbackQuery):
    user = get_user(user_id=callback.from_user.id)
    if callback.from_user.id not in ADMIN_IDS and user[3] < 8:
        return await callback.answer("❌ Прав недостаточно", show_alert=True)
    order_id = int(callback.data.split("_")[2])
    cursor.execute("SELECT user_id, username, period, price FROM pending_vip_orders WHERE order_id = ?", (order_id,))
    row = cursor.fetchone()
    if not row: return await callback.answer("Заявка не найдена", show_alert=True)
    target_uid, username, period, price = row
    add_vip_time(target_uid, period)
    cursor.execute("DELETE FROM pending_vip_orders WHERE order_id = ?", (order_id,))
    conn.commit()
    try: await bot.send_message(target_uid, "🎉 Оплата подтверждена! VIP активирован.", parse_mode="HTML")
    except Exception: pass
    await callback.message.edit_text(f"✅ Заявка #{order_id} подтверждена.", parse_mode="HTML")

@dp.callback_query(F.data.startswith("m_conf_"))
async def admin_confirm_money(callback: CallbackQuery):
    user = get_user(user_id=callback.from_user.id)
    if callback.from_user.id not in ADMIN_IDS and user[3] < 8:
        return await callback.answer("❌ Прав недостаточно", show_alert=True)
    order_id = int(callback.data.split("_")[2])
    cursor.execute("SELECT user_id, username, coins, price FROM pending_money_orders WHERE order_id = ?", (order_id,))
    row = cursor.fetchone()
    if not row: return await callback.answer("Заявка не найдена", show_alert=True)
    target_uid, username, coins, price = row
    t_user = get_user(user_id=target_uid)
    update_user(target_uid, coins=t_user[5] + coins)
    cursor.execute("DELETE FROM pending_money_orders WHERE order_id = ?", (order_id,))
    conn.commit()
    try: await bot.send_message(target_uid, f"🎉 Оплата подтверждена! Зачислено {coins} монет.", parse_mode="HTML")
    except Exception: pass
    await callback.message.edit_text(f"✅ Заявка #{order_id} подтверждена.", parse_mode="HTML")

# --- Отклонение заявок с причиной (FSM) ---

@dp.callback_query(F.data.startswith("vip_ref_"))
async def admin_refuse_vip_start(callback: CallbackQuery, state: FSMContext):
    user = get_user(user_id=callback.from_user.id)
    if callback.from_user.id not in ADMIN_IDS and user[3] < 8:
        return await callback.answer("❌ Прав недостаточно", show_alert=True)
    order_id = int(callback.data.split("_")[2])
    await state.update_data(order_id=order_id, order_type="vip")
    await state.set_state(AdminRejectOrder.waiting_for_reason)
    await callback.message.answer(f"❌ <b>Отклонение VIP (#{order_id})</b>\nНапишите причину отклонения:", parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("m_ref_"))
async def admin_refuse_money_start(callback: CallbackQuery, state: FSMContext):
    user = get_user(user_id=callback.from_user.id)
    if callback.from_user.id not in ADMIN_IDS and user[3] < 8:
        return await callback.answer("❌ Прав недостаточно", show_alert=True)
    order_id = int(callback.data.split("_")[2])
    await state.update_data(order_id=order_id, order_type="money")
    await state.set_state(AdminRejectOrder.waiting_for_reason)
    await callback.message.answer(f"❌ <b>Отклонение монет (#{order_id})</b>\nНапишите причину отклонения:", parse_mode="HTML")
    await callback.answer()

@dp.message(AdminRejectOrder.waiting_for_reason)
async def process_admin_rejection_reason(message: Message, state: FSMContext):
    user = get_user(user_id=message.from_user.id)
    if message.from_user.id not in ADMIN_IDS and user[3] < 8: return
    data = await state.get_data()
    order_id = data.get("order_id")
    order_type = data.get("order_type")
    reason = message.text

    table_name = "pending_vip_orders" if order_type == "vip" else "pending_money_orders"
    cursor.execute(f"SELECT user_id, username FROM {table_name} WHERE order_id = ?", (order_id,))
    row = cursor.fetchone()
    if row:
        target_uid, username = row
        cursor.execute(f"DELETE FROM {table_name} WHERE order_id = ?", (order_id,))
        conn.commit()
        try:
            await bot.send_message(target_uid, f"❌ Ваша заявка (#{order_id}) отклонена.\n📝 Причина: {reason}", parse_mode="HTML")
        except Exception: pass
        await message.answer(f"✅ Заявка #{order_id} отклонена. Причина отправлена.", parse_mode="HTML")
    else:
        await message.answer("⚠️ Заявка уже обработана.")
    await state.clear()

@dp.message(Command("give_money"))
async def cmd_give_money(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 10: return await message.answer("❌ Доступно только 10 рангу.")
    if not command.args or len(command.args.split()) < 2:
        return await message.answer("⚠️ Использование: <code>/give_money @username 10000</code>", parse_mode="HTML")
    parts = command.args.split()
    target_username = clean_username(parts[0])
    if not parts[1].isdigit(): return await message.answer("⚠️ Укажите число.")
    amount = int(parts[1])
    if amount < 10000: return await message.answer("❌ Минимальная сумма выдачи: <b>10000</b> монет!", parse_mode="HTML")
    row = get_user(username=target_username)
    if not row: return await message.answer("❌ Пользователь не найден.")
    update_user(row[0], coins=row[5] + amount)
    await message.answer(f"✅ Выдано <b>{amount} монет</b> пользователю @{target_username}!", parse_mode="HTML")

@dp.message(Command("givevip"))
async def cmd_givevip(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 10: return await message.answer("❌ Доступно только 10 рангу.")
    if not command.args or len(command.args.split()) < 2:
        return await message.answer("⚠️ Использование: <code>/givevip @username 30</code>", parse_mode="HTML")
    parts = command.args.split()
    t_user = get_user(username=clean_username(parts[0]))
    if not t_user: return await message.answer("❌ Пользователь не найден.")
    add_vip_time(t_user[0], parts[1])
    await message.answer(f"✅ VIP успешно выдан!", parse_mode="HTML")

# ==========================================
# 8. МОДЕРАЦИЯ И АДМИНИСТРИРОВАНИЕ
# ==========================================

@dp.message(Command("snick"))
async def cmd_snick(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 2: return await message.answer("❌ Доступно с 2 ранга.")
    
    target_id = None
    new_nick = ""

    if message.reply_to_message:
        target_id = message.reply_to_message.from_user.id
        new_nick = command.args or ""
    elif command.args:
        parts = command.args.split(maxsplit=1)
        if parts[0].startswith("@"):
            t_row = get_user(username=parts[0])
            if t_row: 
                target_id = t_row[0]
                new_nick = parts[1] if len(parts) > 1 else ""
        else:
            new_nick = command.args

    if not target_id or not new_nick:
        return await message.answer("⚠️ Использование: ответом на сообщение <code>/snick НовыйНик</code> или <code>/snick @username НовыйНик</code>", parse_mode="HTML")

    update_user(target_id, custom_nickname=new_nick)
    await message.answer(f"✅ Установлен локальный ник: <b>{new_nick}</b>", parse_mode="HTML")

@dp.message(Command("rnick"))
async def cmd_rnick(message: Message):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 2: return await message.answer("❌ Доступно с 2 ранга.")
    if not message.reply_to_message: return await message.answer("⚠️ Ответьте на сообщение пользователя!")

    update_user(message.reply_to_message.from_user.id, custom_nickname="")
    await message.answer("✅ Никнейм успешно сброшен до исходного.")

@dp.message(Command("gnick"))
async def cmd_gnick(message: Message):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 2: return await message.answer("❌ Доступно с 2 ранга.")
    if not message.reply_to_message: return await message.answer("⚠️ Ответьте на сообщение пользователя!")

    t = get_user(user_id=message.reply_to_message.from_user.id)
    await message.answer(f"👤 Настоящий ник: @{t[1] or 'без_юзернейма'} | Кастомный ник: <b>{t[16] or 'Нет'}</b>", parse_mode="HTML")

@dp.message(Command("staff"))
async def cmd_staff(message: Message):
    cursor.execute("SELECT username, rank, role FROM users WHERE rank >= 1 OR role != 'User' LIMIT 20")
    rows = cursor.fetchall()
    text = "🛡️ <b>СОСТАВ МОДЕРАЦИИ:</b>\n\n"
    for r in rows:
        text += f"• @{r[0] or 'id'} — Ранг: {r[1]} | Роль: {r[2]}\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("warn"))
async def cmd_warn(message: Message):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 4: return await message.answer("❌ С 4+ ранга.")
    if not message.reply_to_message: return await message.answer("⚠️ Ответьте на сообщение!")
    tid = message.reply_to_message.from_user.id
    target = get_user(user_id=tid)
    warns = target[19] + 1
    if warns >= 3:
        update_user(tid, warns=0)
        try: await bot.ban_chat_member(message.chat.id, tid)
        except Exception: pass
        await message.answer("💥 3/3 варнов, пользователь кикнут!")
    else:
        update_user(tid, warns=warns)
        await message.answer(f"⚠️ Варн выдан ({warns}/3)!")

@dp.message(Command("skick"))
async def cmd_skick(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 5:
        return await message.answer("❌ Команда /skick доступна модераторам с 5+ ранга!")

    if not message.reply_to_message:
        return await message.answer("⚠️ Ответьте на сообщение нарушителя!")

    target_id = message.reply_to_message.from_user.id
    target_uname = message.reply_to_message.from_user.username or f"ID:{target_id}"
    reason = command.args or "Кик со всех подконтрольных групп"

    cursor.execute("SELECT chat_id FROM known_chats")
    chats = cursor.fetchall()

    success_count = 0
    for ch in chats:
        c_id = ch[0]
        try:
            member = await bot.get_chat_member(c_id, message.from_user.id)
            if member.status in ['administrator', 'creator']:
                await bot.ban_chat_member(c_id, target_id)
                await bot.unban_chat_member(c_id, target_id)
                success_count += 1
        except Exception:
            pass

    await message.answer(f"🚪 <b>Пользователь @{target_uname} был кикнут из {success_count} подконтрольных групп!</b>\nПричина: {reason}", parse_mode="HTML")

@dp.message(Command("sban"))
async def cmd_sban(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 5:
        return await message.answer("❌ Команда /sban доступна модераторам с 5+ ранга!")

    if not message.reply_to_message:
        return await message.answer("⚠️ Ответьте на сообщение нарушителя!")

    target_id = message.reply_to_message.from_user.id
    target_uname = message.reply_to_message.from_user.username or f"ID:{target_id}"
    reason = command.args or "Блокировка во всех подконтрольных группах"

    cursor.execute("SELECT chat_id FROM known_chats")
    chats = cursor.fetchall()

    success_count = 0
    for ch in chats:
        c_id = ch[0]
        try:
            member = await bot.get_chat_member(c_id, message.from_user.id)
            if member.status in ['administrator', 'creator']:
                await bot.ban_chat_member(c_id, target_id)
                success_count += 1
        except Exception:
            pass

    await message.answer(f"⛔ <b>Пользователь @{target_uname} заблокирован в {success_count} подконтрольных группах!</b>\nПричина: {reason}", parse_mode="HTML")

@dp.message(Command("gwarn"))
async def cmd_gwarn(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 8: return await message.answer("❌ GWARN с 8+ ранга.")
    if not message.reply_to_message or not command.args:
        return await message.answer("⚠️ Ответьте на сообщение с причиной: <code>/gwarn Причина</code>", parse_mode="HTML")
    tid = message.reply_to_message.from_user.id
    is_banned = add_gwarn(tid, command.args, message.from_user.username or "Admin")
    if is_banned: await message.answer("🌐 3/3 GWARN! Автоматический GBAN.", parse_mode="HTML")
    else: await message.answer("🌐 GWARN выдан!", parse_mode="HTML")

@dp.message(Command("gban"))
async def cmd_gban(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 9: return await message.answer("❌ GBAN с 9+ ранга.")
    if not message.reply_to_message or not command.args:
        return await message.answer("⚠️ Ответьте на сообщение: <code>/gban Причина</code>", parse_mode="HTML")
    tid = message.reply_to_message.from_user.id
    cursor.execute("INSERT OR REPLACE INTO global_bans VALUES (?, ?, ?)", (tid, command.args, message.from_user.username))
    conn.commit()
    await message.answer("🌐 GBAN выдан!", parse_mode="HTML")

@dp.message(Command("zdkd"))
async def cmd_zdkd(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 9: return await message.answer("❌ ЗДКД с 9+ ранга.")
    tid = message.reply_to_message.from_user.id if message.reply_to_message else get_user(username=clean_username(command.args.split()[0]))[0]
    update_user(tid, zdkd=1)
    await message.answer("🚫 Выдан ЗДКД.", parse_mode="HTML")

# ==========================================
# 9. ЛОГИ И ДОСТУПЫ
# ==========================================

@dp.message(Command("Pbook"))
async def cmd_pbook(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 5: return await message.answer("❌ С 5 ранга.")
    cursor.execute("INSERT OR REPLACE INTO logs_access VALUES (?, 1)", (message.from_user.id,))
    conn.commit()
    await send_log_to_user(message.from_user.id, "Доступ к Pbook одобрен!")
    await message.answer("✅ Логи отправлены в ЛС.")

@dp.message(Command("Pbooks"))
async def cmd_Pbooks(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 6: return await message.answer("❌ С 6 ранга.")
    cursor.execute("INSERT OR REPLACE INTO logs_access VALUES (?, 2)", (message.from_user.id,))
    conn.commit()
    await send_log_to_user(message.from_user.id, "Расширенный доступ одобрен!")
    await message.answer("✅ Отправлено в ЛС.")

@dp.message(Command("book"))
async def cmd_book(message: Message):
    await send_log_to_user(message.from_user.id, "Локальный лог чата: стабильно.")
    await message.answer("📖 Отправлено в ЛС.")

@dp.message(Command("books"))
async def cmd_books(message: Message):
    await send_log_to_user(message.from_user.id, "Расширенный лог чата активен.")
    await message.answer("📖 Отправлено в ЛС.")

@dp.message(Command("book_global"))
async def cmd_book_global(message: Message):
    await send_log_to_user(message.from_user.id, "Глобальный лог системы.")
    await message.answer("🌐 Отправлено в ЛС.")

# ==========================================
# 10. УПРАВЛЕНИЕ ДОЛЖНОСТЯМИ И РЕЕСТРЫ
# ==========================================

@dp.message(Command("setzam"))
async def cmd_setzam(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 10: return await message.answer("❌ Только для 10 ранга.")
    parts = command.args.split(maxsplit=1)
    target_un = clean_username(parts[0])
    zam_role = parts[1] if len(parts) > 1 else "Заместитель"
    set_role(target_un, zam_role)
    t_user = get_user(username=target_un)
    if t_user: update_user(t_user[0], rank=8)
    await message.answer(f"👑 Назначен: {zam_role} — @{target_un}")

@dp.message(Command("setga"))
async def cmd_setga(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8: return await message.answer("❌ С 8 ранга.")
    target_un = clean_username(command.args.split()[0] if command.args else "")
    set_role(target_un, "Главный Администратор (ГА)")
    t_user = get_user(username=target_un)
    if t_user: update_user(t_user[0], rank=6)
    await message.answer(f"✅ ГА назначен: @{target_un}")

@dp.message(Command("unsetga"))
async def cmd_unsetga(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8: return await message.answer("❌ С 8 ранга.")
    target_un = clean_username(command.args.split()[0] if command.args else "")
    set_role(target_un, "User")
    t_user = get_user(username=target_un)
    if t_user: update_user(t_user[0], rank=0)
    await message.answer(f"📉 Снят с ГА: @{target_un}")

@dp.message(Command("settex"))
async def cmd_settex(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8: return await message.answer("❌ С 8 ранга.")
    target_un = clean_username(command.args.split()[0] if command.args else "")
    set_role(target_un, "Технический специалист (ТС)")
    t_user = get_user(username=target_un)
    if t_user: update_user(t_user[0], rank=7)
    await message.answer(f"✅ ТС назначен: @{target_un}")

@dp.message(Command("unsettex"))
async def cmd_unsettex(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8: return await message.answer("❌ С 8 ранга.")
    target_un = clean_username(command.args.split()[0] if command.args else "")
    set_role(target_un, "User")
    t_user = get_user(username=target_un)
    if t_user: update_user(t_user[0], rank=0)
    await message.answer(f"📉 ТС снят: @{target_un}")

@dp.message(Command("checkrep"))
async def cmd_checkrep(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8: return await message.answer("❌ С 8 ранга.")
    cursor.execute("SELECT id, text FROM reports WHERE status = 'pending'")
    rows = cursor.fetchall()
    text = "📋 <b>Жалобы:</b>\n" + "".join([f"• ID: {r[0]} | {r[1]}\n" for r in rows])
    await message.answer(text if rows else "📋 Жалоб нет.", parse_mode="HTML")

@dp.message(Command("ghrep"))
async def cmd_ghrep(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8: return await message.answer("❌ С 8 ранга.")
    await message.answer(f"✅ Репорты переданы роли: <b>{command.args or 'Общие'}</b>", parse_mode="HTML")

@dp.message(Command("zayavka"))
async def cmd_zayavka(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8: return await message.answer("❌ С 8 ранга.")
    cursor.execute("SELECT COUNT(*) FROM pending_vip_orders")
    vip_cnt = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM pending_money_orders")
    money_cnt = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM obgban_requests")
    obg_cnt = cursor.fetchone()[0]
    await message.answer(f"📋 <b>Реестр заявок:</b>\n👑 VIP: {vip_cnt}\n💰 Монеты: {money_cnt}\n🌐 Обжалования: {obg_cnt}", parse_mode="HTML")

@dp.message(Command("glist"))
async def cmd_glist(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 6: return await message.answer("❌ С 6 ранга.")
    cursor.execute("SELECT user_id, reason FROM global_bans")
    rows = cursor.fetchall()
    text = "🌐 <b>GBAN списки:</b>\n" + "".join([f"• ID {r[0]} — {r[1]}\n" for r in rows])
    await message.answer(text if rows else "🌐 Список пуст.", parse_mode="HTML")

@dp.message(Command("gwlist"))
async def cmd_gwlist(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 6: return await message.answer("❌ С 6 ранга.")
    cursor.execute("SELECT user_id, reason FROM global_warns")
    rows = cursor.fetchall()
    text = "🌐 <b>GWARN списки:</b>\n" + "".join([f"• ID {r[0]} — {r[1]}\n" for r in rows])
    await message.answer(text if rows else "🌐 Список пуст.", parse_mode="HTML")

@dp.message(Command("Global_news", prefix="/"))
@dp.message(Command("global_news", prefix="/"))
async def cmd_global_news(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 10: return await message.answer("❌ Доступно только 10 рангу.")
    if not command.args: return await message.answer("⚠️ Укажите текст рассылки.")
    news_text = f"📢 <b>ПРАВИЛА / НОВОСТИ СИСТЕМЫ:</b>\n\n{command.args}"
    
    cursor.execute("SELECT chat_id FROM known_chats")
    chats = cursor.fetchall()
    for ch in chats:
        cursor.execute("INSERT OR REPLACE INTO chat_settings (chat_id, rules) VALUES (?, ?)", (ch[0], command.args))
        try: await bot.send_message(ch[0], news_text, parse_mode="HTML")
        except Exception: pass
    conn.commit()
        
    cursor.execute("SELECT user_id FROM users")
    for u in cursor.fetchall():
        try: await bot.send_message(u[0], news_text, parse_mode="HTML")
        except Exception: pass

    await message.answer("✅ Рассылка успешно завершена!")

# ==========================================
# 11. КОМАНДЫ ЗОВ, НОВОСТИ, ОБНУЛЕНИЯ И АКТИВНОСТЬ
# ==========================================

@dp.message(Command("zov"))
async def cmd_zov(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 3:
        return await message.answer("❌ Команда /zov доступна модераторам с 3+ ранга!")

    if not command.args:
        return await message.answer("⚠️ Укажите причину вызова: <code>/zov Важная причина</code>", parse_mode="HTML")

    reason = command.args
    await message.answer(
        f"📢 <b>ВЫЗОВ УЧАСТНИКОВ (ОПОВЕЩЕНИЕ)!</b>\n\n"
        f"👤 <b>Вызвал:</b> @{message.from_user.username or message.from_user.id}\n"
        f"💬 <b>Причина:</b> {reason}\n\n"
        f"🔔 @everyone @online",
        parse_mode="HTML"
    )

@dp.message(Command("news"))
async def cmd_news(message: Message):
    cursor.execute("SELECT rules FROM chat_settings WHERE chat_id = ?", (message.chat.id,))
    row = cursor.fetchone()
    rules_text = row[0] if row and row[0] else "Правила системы пока не установлены администрацией."

    await message.answer(
        f"📜 <b>ПРАВИЛА И УСТАВ БОТА:</b>\n\n{rules_text}",
        parse_mode="HTML"
    )

@dp.message(Command("Obnyl"))
async def cmd_obnyl(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if message.from_user.id not in ADMIN_IDS and user[3] < 10:
        return await message.answer("❌ Полное обнуление доступно строго Владельцу (10 ранг)!")

    if not command.args:
        return await message.answer("⚠️ Использование: <code>/Obnyl @username</code> или <code>/Obnyl ID</code>", parse_mode="HTML")

    target_raw = command.args.split()[0]
    
    if target_raw.isdigit():
        target_user = get_user(user_id=int(target_raw))
    else:
        target_user = get_user(username=clean_username(target_raw))

    if not target_user:
        return await message.answer("❌ Пользователь не найден в базе данных!")

    target_uid = target_user[0]
    target_un = target_user[1] or f"ID:{target_uid}"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    cursor.execute(
        "INSERT INTO obnyl_history (user_id, username, old_coins, old_exp, old_level, old_rep, old_rank, date) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (target_uid, target_un, target_user[5], target_user[6], target_user[7], target_user[8], target_user[3], now_str)
    )
    conn.commit()

    update_user(
        target_uid,
        coins=0,
        exp=0,
        level=1,
        rep=0,
        streak=0,
        msg_count=0,
        duel_wins=0,
        warns=0,
        gwarns=0,
        custom_nickname="",
        rank=0 if target_uid != OWNER_ID else 10,
        role="User" if target_uid != OWNER_ID else "Owner"
    )

    await message.answer(
        f"💥 <b>ПОЛНОЕ ОБНУЛЕНИЕ АККАУНТА!</b>\n\n"
        f"👤 Аккаунт: @{target_un} (<code>{target_uid}</code>)\n"
        f"✅ Все монеты, EXP, уровень, репутация, ранги и статистика сброшены.\n"
        f"👑 <i>Купленный VIP-статус сохранен.</i>",
        parse_mode="HTML"
    )

@dp.message(Command("Obnyl_money"))
async def cmd_obnyl_money(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if message.from_user.id not in ADMIN_IDS and user[3] < 9:
        return await message.answer("❌ Обнуление баланса доступно с 9+ ранга!")

    if not command.args:
        return await message.answer("⚠️ Использование: <code>/Obnyl_money @username</code> или <code>/Obnyl_money ID</code>", parse_mode="HTML")

    target_raw = command.args.split()[0]
    
    if target_raw.isdigit():
        target_user = get_user(user_id=int(target_raw))
    else:
        target_user = get_user(username=clean_username(target_raw))

    if not target_user:
        return await message.answer("❌ Пользователь не найден в базе данных!")

    target_uid = target_user[0]
    target_un = target_user[1] or f"ID:{target_uid}"
    old_coins = target_user[5]

    update_user(target_uid, coins=0)

    await message.answer(
        f"💰 <b>ОБНУЛЕНИЕ БАЛАНСА!</b>\n\n"
        f"👤 Пользователь: @{target_un} (<code>{target_uid}</code>)\n"
        f"📉 Баланс сброшен с <b>{old_coins} монет</b> до <b>0</b>.",
        parse_mode="HTML"
    )

@dp.message(Command("odnyllist"))
async def cmd_odnyllist(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if message.from_user.id not in ADMIN_IDS and user[3] < 8:
        return await message.answer("❌ Просмотр истории обнулений доступен с 8+ ранга!")

    if not command.args:
        return await message.answer("⚠️ Использование: <code>/odnyllist @username</code> или <code>/odnyllist ID</code>", parse_mode="HTML")

    target_raw = command.args.split()[0]
    
    if target_raw.isdigit():
        target_uid = int(target_raw)
        cursor.execute("SELECT * FROM obnyl_history WHERE user_id = ? ORDER BY id DESC LIMIT 10", (target_uid,))
    else:
        u_clean = clean_username(target_raw)
        cursor.execute("SELECT * FROM obnyl_history WHERE LOWER(username) = ? ORDER BY id DESC LIMIT 10", (u_clean,))

    rows = cursor.fetchall()

    if not rows:
        return await message.answer("📋 Данный пользователь ни разу не подвергался полному обнулению.")

    text = f"📋 <b>ИСТОРИЯ ОБНУЛЕНИЙ ДЛЯ {target_raw}:</b>\n\n"
    for r in rows:
        text += (
            f"📅 <b>Дата:</b> {r[8]}\n"
            f"💰 Монет было: {r[3]}\n"
            f"⚡ EXP было: {r[4]} (Уровень {r[5]})\n"
            f"⭐ Репутации было: {r[6]}\n"
            f"🎭 Админ-ранг был: {r[7]}\n"
            f"-----------------------------------\n"
        )

    await message.answer(text, parse_mode="HTML")

@dp.message(Command("olist"))
async def cmd_olist(message: Message):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if message.from_user.id not in ADMIN_IDS and user[3] < 5:
        return await message.answer("❌ Команда /olist доступна с 5+ ранга!")

    if message.chat.type not in ['group', 'supergroup']:
        return await message.answer("❌ Команда /olist работает только в группах.")

    cursor.execute("""
        SELECT username, user_id, last_active 
        FROM users 
        WHERE last_active IS NOT NULL 
        ORDER BY last_active DESC LIMIT 30
    """)
    rows = cursor.fetchall()

    if not rows:
        return await message.answer("📋 В сети сейчас никого нет или данные не собраны.")

    text = f"🟢 <b>СПИСОК УЧАСТНИКОВ В СЕТИ (ЧАТ):</b>\n\n"
    for r in rows:
        uname = f"@{r[0]}" if r[0] else "без_юзернейма"
        text += f"• {uname} | <code>{r[1]}</code> | Был(а) в сети: {r[2]}\n"

    await message.answer(text, parse_mode="HTML")

@dp.message(Command("olists"))
async def cmd_olists(message: Message):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if message.from_user.id not in ADMIN_IDS and user[3] < 8:
        return await message.answer("❌ Команда /olists доступна с 8+ ранга!")

    cursor.execute("""
        SELECT username, user_id, last_active, last_command 
        FROM users 
        WHERE last_active IS NOT NULL 
        ORDER BY last_active DESC LIMIT 50
    """)
    rows = cursor.fetchall()

    if not rows:
        return await message.answer("📋 В базе данных пока нет зафиксированной активности.")

    text = "📋 <b>РЕЕСТР ВСЕХ ВЗАИМОДЕЙСТВИЙ С БОТОМ:</b>\n\n"
    for r in rows:
        uname = f"@{r[0]}" if r[0] else "без_юзернейма"
        last_act = r[2] or "Неизвестно"
        last_cmd = r[3] or "Нет данных"
        
        text += f"{uname}  <code>{r[1]}</code>  {last_act}  {last_cmd}\n"

    await message.answer(text, parse_mode="HTML")

# ==========================================
# 12. ЗАПУСК БОТА
# ==========================================
async def main():
    logging.info("Starting Stars Manager Bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped!")
