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
        last_command TEXT,
        total_donated_uah INTEGER DEFAULT 0
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

    cursor.execute('''CREATE TABLE IF NOT EXISTS obgwarn_requests (
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

    cursor.execute('''CREATE TABLE IF NOT EXISTS marriages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user1_id INTEGER,
        user2_id INTEGER,
        wedding_date TEXT
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS promocodes (
        code TEXT PRIMARY KEY,
        coins INTEGER,
        activations_left INTEGER
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

    cursor.execute('''CREATE TABLE IF NOT EXISTS ungban_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        applicant_id INTEGER,
        applicant_username TEXT,
        target_id INTEGER,
        target_username TEXT,
        reason TEXT,
        date TEXT
    )''')

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN last_active TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN last_command TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN total_donated_uah INTEGER DEFAULT 0")
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
    user = get_user(user_id=user_id)
    # Проверка доната > 450 грн / 600 звезд (автоснятие gwarn)
    if user and user[25] >= 450:
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

async def send_log_to_user(user_id: int, text: str):
    try:
        await bot.send_message(user_id, f"📝 <b>[ЛОГ СИСТЕМЫ]</b>\n{text}", parse_mode="HTML")
    except Exception:
        pass

def add_donat_record(user_id: int, username: str, type_str: str, amount_str: str, currency: str, numeric_uah: int = 0):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute(
        "INSERT INTO donats_history (user_id, username, type, amount, currency, date) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, clean_username(username), type_str, amount_str, currency, now_str)
    )
    if numeric_uah > 0:
        user = get_user(user_id=user_id)
        current_donated = user[25] if len(user) > 25 and user[25] else 0
        update_user(user_id, total_donated_uah=current_donated + numeric_uah)
    conn.commit()

def log_admin_action(admin_id: int, admin_username: str, target_id: int, target_username: str, action: str, reason: str = ""):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute(
        "INSERT INTO admin_logs (admin_id, admin_username, target_id, target_username, action, reason, date) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (admin_id, clean_username(admin_username), target_id, clean_username(target_username), action, reason, now_str)
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

class ObgwarnState(StatesGroup):
    waiting_for_reason = State()

class SetAdminState(StatesGroup):
    waiting_for_role_choice = State()
    target_user_id = State()

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

@dp.message(Command("Obgwarn"))
async def cmd_obgwarn(message: Message, state: FSMContext):
    if message.chat.type != 'private':
        return await message.answer("⚠️ Команду <code>/Obgwarn</code> нужно писать строго в ЛС бота!", parse_mode="HTML")
    
    uid = message.from_user.id
    cursor.execute("SELECT COUNT(*) FROM global_warns WHERE user_id = ?", (uid,))
    if cursor.fetchone()[0] == 0:
        return await message.answer("❌ У вас нет активных GWARN, обжаловать нечего.")

    await message.answer(
        "📝 <b>Обжалование GWARN</b>\n\n"
        "Опишите причину, почему вы хотите снять GWARN.\n"
        "Отправьте текст обжалования ответным сообщением:",
        parse_mode="HTML"
    )
    await state.set_state(ObgwarnState.waiting_for_reason)

@dp.message(ObgwarnState.waiting_for_reason)
async def process_obgwarn_text(message: Message, state: FSMContext):
    uid = message.from_user.id
    uname = message.from_user.username or f"ID:{uid}"
    reason = message.text
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    cursor.execute("INSERT INTO obgwarn_requests (user_id, username, reason, date) VALUES (?, ?, ?, ?)",
                   (uid, uname, reason, date_str))
    conn.commit()
    await state.clear()
    await message.answer("✅ Ваша заявка на обжалование GWARN успешно отправлена 8+ рангам!")

    cursor.execute("SELECT user_id FROM users WHERE rank >= 8")
    for row in cursor.fetchall():
        try:
            await bot.send_message(
                row[0],
                f"🌐 <b>Новая заявка на обжалование GWARN!</b>\n\n"
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
    parts = [
        (
            "📜 <b>СПИСОК КОМАНД БОТА (Часть 1/5)</b>\n\n"
            "• <code>/start</code> — Запуск бота и приветствие | <i>Для всех (0+)</i>\n"
            "• <code>/id [@username]</code> — Узнать Telegram ID свой или чужой | <i>Для всех (0+)</i>\n"
            "• <code>/profile [@username]</code> — Посмотреть профиль игрока | <i>Для всех (0+)</i>\n"
            "• <code>/stats</code> — Подробная статистика профиля | <i>Для всех (0+)</i>\n"
            "• <code>/nlist</code> — Список всех кастомных ников в системе | <i>Для всех (0+)</i>\n"
            "• <code>/nonick</code> — Список пользователей без кастомного ника | <i>2+ ранг</i>\n"
            "• <code>/q</code> — Выйти из группового чата по собственному желанию | <i>Для всех (0+)</i>\n"
            "• <code>/obgban</code> — Подать заявку на обжалование GBAN (строго в ЛС) | <i>Для всех (0+)</i>\n"
            "• <code>/Obgwarn</code> — Подать заявку на обжалование GWARN (строго в ЛС) | <i>Для всех (0+)</i>\n"
            "• <code>/vip</code> — Купить VIP-статус за ГРН или Звёзды | <i>Для всех (0+)</i>\n"
        ),
        (
            "📜 <b>СПИСОК КОМАНД БОТА (Часть 2/5)</b>\n\n"
            "• <code>/buy_money</code> — Покупка игровой валюты (монет) | <i>Для всех (0+)</i>\n"
            "• <code>/givemevip</code> — Активировать себе VIP на 7 дней | <i>8+ ранг</i>\n"
            "• <code>/blago</code> — Поддержка проекта и донат | <i>Для всех (0+)</i>\n"
            "• <code>/Donats</code> — Просмотр истории собственных покупок и донатов | <i>Для всех (0+)</i>\n"
            "• <code>/rep [+/-]</code> — Изменить репутацию игроку (ответом на сообщение) | <i>Для всех (0+)</i>\n"
            "• <code>/bonus</code> — Забрать ежедневный бонус и укрепить серию | <i>Для всех (0+)</i>\n"
            "• <code>/top</code> — Топ-10 игроков текущего чата по монетам | <i>Для всех (0+)</i>\n"
            "• <code>/tops</code> — Глобальный межгрупповой топ-5 игроков | <i>Для всех (0+)</i>\n"
            "• <code>/shop [exp кол-во]</code> — Обычный магазин (покупка EXP за монеты) | <i>Для всех (0+)</i>\n"
            "• <code>/eshop</code> — Эксклюзивный магазин привилегий | <i>Для всех (0+)</i>\n"
        ),
        (
            "📜 <b>СПИСОК КОМАНД БОТА (Часть 3/5)</b>\n\n"
            "• <code>/role_shop</code> — Магазин кастомных ролей конкретного чата | <i>Для всех (0+)</i>\n"
            "• <code>/create_role [Текст] [#HEX] [Цена]</code> — Создать роль для магазина | <i>Для всех (0+)</i>\n"
            "• <code>/duel [ставка]</code> — Сыграть дуэль на монеты (ответом) | <i>Для всех (0+)</i>\n"
            "• <code>/transfer [сумма]</code> — Перевод монет другому игроку (ответом) | <i>Для всех (0+)</i>\n"
            "• <code>/report [текст]</code> — Отправить жалобу администрации чата | <i>1+ ранг</i>\n"
            "• <code>/marry</code> — Предложение виртуального брака (ответом) | <i>Для всех (0+)</i>\n"
            "• <code>/divorce</code> — Оформить развод | <i>Для всех (0+)</i>\n"
            "• <code>/promo [код]</code> — Активировать промокод на монеты | <i>Для всех (0+)</i>\n"
            "• <code>/kazino [ставка]</code> — Сыграть в казино (макс. 700 / 2000 с VIP) | <i>Для всех (0+)</i>\n"
            "• <code>/snick [ник]</code> — Установить кастомный ник пользователю | <i>2+ ранг</i>\n"
        ),
        (
            "📜 <b>СПИСОК КОМАНД БОТА (Часть 4/5)</b>\n\n"
            "• <code>/rnick</code> — Сбросить кастомный ник пользователю | <i>2+ ранг</i>\n"
            "• <code>/gnick</code> — Узнать настоящий и кастомный ник | <i>2+ ранг</i>\n"
            "• <code>/zov [причина]</code> — Глобальное оповещение участников (@everyone) | <i>3+ ранг</i>\n"
            "• <code>/news</code> — Посмотреть правила и устав бота в чате | <i>Для всех (0+)</i>\n"
            "• <code>/staff</code> — Показать состав модерации проекта | <i>1+ ранг</i>\n"
            "• <code>/warn</code> — Выдать варн (3 варна = авто-кик + мут на 10 мин) | <i>4+ ранг</i>\n"
            "• <code>/unwarn</code> — Снять один предупредительный варн | <i>4+ ранг</i>\n"
            "• <code>/mute [мин]</code> — Заглушить пользователя в чате | <i>4+ ранг</i>\n"
            "• <code>/unmute</code> — Снять мут с пользователя | <i>4+ ранг</i>\n"
            "• <code>/kick</code> — Кикнуть участника из чата | <i>4+ ранг</i>\n"
        ),
        (
            "📜 <b>СПИСОК КОМАНД БОТА (Часть 5/5)</b>\n\n"
            "• <code>/ban</code> — Заблокировать участника в чате | <i>4+ ранг</i>\n"
            "• <code>/unban</code> — Разблокировать участника в чате | <i>4+ ранг</i>\n"
            "• <code>/skick</code> / <code>/sban</code> — Массовые кики / баны по всем группам | <i>5+ ранги</i>\n"
            "• <code>/gwarn [причина]</code> — Выдать GWARN (авто-мут 15 мин везде, 3 GWARN = GBAN) | <i>8+ ранг</i>\n"
            "• <code>/gban [причина]</code> — Выдать глобальный бан (GBAN) | <i>9+ ранг</i>\n"
            "• <code>/zdkd [причина]</code> — Выдать запрет деятельности (ЗДКД) | <i>9+ ранг</i>\n"
            "• <code>/setaccess [@user/ID]</code> / <code>/unsetaccess</code> — Выдать / снять права ГА | <i>8+ ранг</i>\n"
            "• <code>/setadmin [@user/ID]</code> — Назначить 8 ранг (с выбором роли) | <i>9+ ранг</i>\n"
            "• <code>/setzam [ОЗГР/ЗГР] [@user/ID]</code> — Назначить 9 ранг | <i>10 ранг</i>\n"
            "• <code>/GB [#номер]</code> / <code>/GW [#номер]</code> — Рассмотрение обжалований GBAN/GWARN | <i>9+ / 8+ ранг</i>\n"
            "• <code>/Repbook [@user/ID]</code> — История обращений в репорт | <i>8+ ранг</i>\n"
        )
    ]
    for p in parts:
        await message.answer(p, parse_mode="HTML")

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
    user1_id = message.from_user.id
    user2_id = message.reply_to_message.from_user.id

    if user1_id == user2_id:
        return await message.answer("❌ Нельзя играть в дуэль самому с собой!")

    u1 = get_user(user_id=user1_id)
    u2 = get_user(user_id=user2_id)

    if u1[5] < bet:
        return await message.answer("❌ У вас недостаточно монет для ставки!")
    if u2[5] < bet:
        return await message.answer("❌ У вашего соперника недостаточно монет для ставки!")

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⚔️ Сыграть дуэль", callback_data=f"duel_play_{user1_id}_{user2_id}_{bet}")
    ]])
    await message.answer(
        f"⚔️ <b>Дуэль на монеты!</b>\n\n"
        f"👤 Вызывающий: @{u1[1] or user1_id}\n"
        f"👤 Соперник: @{u2[1] or user2_id}\n"
        f"💰 Ставка: <b>{bet} монет</b>\n\n"
        f"<i>Принять вызов может только тот, у кого хватает монет. Нажмите кнопку ниже:</i>",
        reply_markup=kb,
        parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("duel_play_"))
async def callback_duel_play(callback: CallbackQuery):
    _, _, u1_str, u2_str, bet_str = callback.data.split("_")
    u1_id = int(u1_str)
    u2_id = int(u2_str)
    bet = int(bet_str)

    if callback.from_user.id not in [u1_id, u2_id]:
        return await callback.answer("❌ Вы не являетесь участником этой дуэли!", show_alert=True)

    u1 = get_user(user_id=u1_id)
    u2 = get_user(user_id=u2_id)

    if u1[5] < bet or u2[5] < bet:
        return await callback.answer("❌ У одного из участников больше нет нужного количества монет!", show_alert=True)

    v1 = is_vip(u1)
    v2 = is_vip(u2)

    # Расчет шансов дуэли
    if v1 and not v2:
        p1, p2 = 55, 45
    elif v2 and not v1:
        p1, p2 = 45, 55
    else:
        p1, p2 = 50, 50

    winner_id = random.choices([u1_id, u2_id], weights=[p1, p2], k=1)[0]
    loser_id = u2_id if winner_id == u1_id else u1_id

    w_user = get_user(user_id=winner_id)
    l_user = get_user(user_id=loser_id)

    update_user(winner_id, coins=w_user[5] + bet, duel_wins=w_user[15] + 1)
    update_user(loser_id, coins=l_user[5] - bet)

    await callback.message.edit_text(
        f"⚔️ <b>Результаты дуэли (ставка {bet} монет):</b>\n\n"
        f"🏆 Победитель: <a href='tg://user?id={winner_id}'>Игрок</a> (+{bet} монет)\n"
        f"💀 Проигравший: <a href='tg://user?id={loser_id}'>Игрок</a> (-{bet} монет)",
        parse_mode="HTML"
    )

@dp.message(Command("kazino"))
async def cmd_kazino(message: Message, command: CommandObject):
    if not command.args or not command.args.isdigit():
        return await message.answer("⚠️ Укажите ставку: <code>/kazino 100</code>", parse_mode="HTML")

    bet = int(command.args)
    user = get_user(user_id=message.from_user.id)
    vip = is_vip(user)

    max_bet = 2000 if vip else 700
    if bet <= 0 or bet > max_bet:
        return await message.answer(f"❌ Недопустимая ставка! Для вашего статуса максимальная ставка: <b>{max_bet} монет</b>.", parse_mode="HTML")

    if user[5] < bet:
        return await message.answer("❌ У вас недостаточно монет на балансе!")

    win_chance = 60 if vip else 40
    is_win = random.choices([True, False], weights=[win_chance, 100 - win_chance], k=1)[0]

    if is_win:
        update_user(message.from_user.id, coins=user[5] + bet)
        await message.answer(f"🎰 <b>ПОБЕДА!</b> Вы выиграли <b>+{bet} монет</b>! 💰 (Баланс: {user[5] + bet})", parse_mode="HTML")
    else:
        update_user(message.from_user.id, coins=user[5] - bet)
        await message.answer(f"🎰 <b>ПРОИГРЫШ!</b> Вы потеряли <b>-{bet} монет</b>. 💸 (Баланс: {user[5] - bet})", parse_mode="HTML")

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
        return await message.answer("⚠️ Укажите суть жалобы: <code>/report Текст жалобы</code>", parse_mode="HTML")
    target_id = message.reply_to_message.from_user.id if message.reply_to_message else 0
    cursor.execute("INSERT INTO reports (chat_id, user_id, target_id, text, status) VALUES (?, ?, ?, ?, 'pending')",
                   (message.chat.id, message.from_user.id, target_id, command.args))
    conn.commit()
    r_id = cursor.lastrowid
    await message.answer(f"🚨 Ваша жалоба успешно отправлена администрации! (ID репорта: #{r_id})")

    # Рассылка 8+ рангам
    cursor.execute("SELECT user_id FROM users WHERE rank >= 8")
    for row in cursor.fetchall():
        try:
            await bot.send_message(
                row[0],
                f"🚨 <b>Новый репорт (#{r_id})!</b>\n"
                f"💬 Текст: {command.args}\n"
                f"Ответить можно командой: <code>/rep {r_id} Ваш ответ</code>",
                parse_mode="HTML"
            )
        except Exception:
            pass

@dp.message(Command("rep"))
async def cmd_rep_answer(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8:
        return await message.answer("❌ Отвечать на репорты могут только администраторы с 8+ ранга!")

    if not command.args:
        return await message.answer("⚠️ Использование: <code>/rep [ID репорта] [Текст ответа]</code>", parse_mode="HTML")

    parts = command.args.split(maxsplit=1)
    if not parts[0].isdigit():
        return await message.answer("⚠️ Укажите корректный ID репорта числом!")

    r_id = int(parts[0])
    answer_text = parts[1] if len(parts) > 1 else "Без ответа"

    cursor.execute("SELECT user_id, text FROM reports WHERE id = ? AND status = 'pending'", (r_id,))
    row = cursor.fetchone()
    if not row:
        return await message.answer("❌ Репорт с таким ID не найден или уже обработан.")

    author_id, rep_text = row
    cursor.execute("UPDATE reports SET status = 'resolved' WHERE id = ?", (r_id,))
    conn.commit()

    await message.answer(f"✅ Репорт #{r_id} успешно закрыт и отвечен.")
    try:
        await bot.send_message(
            author_id,
            f"📬 <b>Ответ на ваш репорт (#{r_id}):</b>\n"
            f"💬 Ваша жалоба: {rep_text}\n"
            f"🛡️ Ответ администратора: {answer_text}",
            parse_mode="HTML"
        )
    except Exception:
        pass

@dp.message(Command("Repbook"))
async def cmd_repbook(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8:
        return await message.answer("❌ История обращений доступна с 8+ ранга!")

    if not command.args:
        return await message.answer("⚠️ Использование: <code>/Repbook @username</code> или <code>/Repbook ID</code>", parse_mode="HTML")

    target_raw = command.args.split()[0]
    target_uid = int(target_raw) if target_raw.isdigit() else (get_user(username=clean_username(target_raw)) or [0])[0]

    cursor.execute("SELECT id, text, status FROM reports WHERE user_id = ? ORDER BY id DESC LIMIT 10", (target_uid,))
    rows = cursor.fetchall()

    if not rows:
        return await message.answer("📋 У этого пользователя нет обращений в репорт.")

    text = f"📋 <b>История репортов пользователя ({target_raw}):</b>\n\n"
    for r in rows:
        text += f"• ID #{r[0]} | Статус: {r[2]} | Текст: {r[1]}\n"
    await message.answer(text, parse_mode="HTML")

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
    amount_num = int(message.text)
    user = message.from_user
    username = f"@{user.username}" if user.username else f"ID: {user.id}"
    add_donat_record(user.id, username, "Благо", f"{amount_num} грн", "грн", numeric_uah=amount_num)
    await state.clear()
    await message.answer("❤️ Спасибо за поддержку! Сумма учтена в ваш донат-баланс.")

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
        f"Вашу заявку рассмотрят в течение 24 часов.",
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

    await callback.message.edit_text("⌛ <b>Заявка отправлена!</b> Ожидайте подтверждения.", parse_mode="HTML")

    admin_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"m_conf_{order_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"m_ref_{order_id}")
    ]])

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, f"💰 Заявка на монеты (#{order_id}) от {username_tag} на {pack['coins']} монет.", reply_markup=admin_kb)
        except Exception:
            pass

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
        f"💳 Переведите <b>{info['price']} грн</b>:\n🔗 {MONOBANK_JAR}\n\nНажмите после оплаты:",
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

    await callback.message.edit_text("⌛ <b>Заявка отправлена!</b> Ожидайте подтверждения.", parse_mode="HTML")
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
    add_donat_record(target_uid, username, f"VIP ({period} мес)", f"{price} грн", "грн", numeric_uah=int(price) if price.isdigit() else 0)
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
    add_donat_record(target_uid, username, f"Монеты ({coins})", f"{price} грн", "грн", numeric_uah=int(price) if price.isdigit() else 0)
    cursor.execute("DELETE FROM pending_money_orders WHERE order_id = ?", (order_id,))
    conn.commit()
    try: await bot.send_message(target_uid, f"🎉 Оплата подтверждена! Зачислено {coins} монет.", parse_mode="HTML")
    except Exception: pass
    await callback.message.edit_text(f"✅ Заявка #{order_id} подтверждена.", parse_mode="HTML")

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

    # Мут на 10 минут при варне
    try:
        until = datetime.now() + timedelta(minutes=10)
        await bot.restrict_chat_member(
            message.chat.id, tid,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until
        )
    except Exception:
        pass

    if warns >= 3:
        update_user(tid, warns=0)
        try: await bot.ban_chat_member(message.chat.id, tid)
        except Exception: pass
        await message.answer("💥 3/3 варнов, пользователь кикнут и получил мут на 10 минут!")
    else:
        update_user(tid, warns=warns)
        await message.answer(f"⚠️ Варн выдан ({warns}/3) + мут на 10 минут!")

@dp.message(Command("unwarn"))
async def cmd_unwarn(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 4: return await message.answer("❌ С 4+ ранга.")
    if not message.reply_to_message: return await message.answer("⚠️ Ответьте на сообщение!")
    tid = message.reply_to_message.from_user.id
    target = get_user(user_id=tid)
    curr = target[19]
    if curr <= 0: return await message.answer("⚠️ У пользователя нет варнов.")
    update_user(tid, warns=curr - 1)
    await message.answer(f"✅ Предупреждение снято ({curr - 1}/3)!")

@dp.message(Command("mute"))
async def cmd_mute(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 4: return await message.answer("❌ С 4+ ранга.")
    if not message.reply_to_message: return await message.answer("⚠️ Ответьте на сообщение!")
    time_min = int(command.args) if command.args and command.args.isdigit() else 15
    until = datetime.now() + timedelta(minutes=time_min)
    try:
        await bot.restrict_chat_member(message.chat.id, message.reply_to_message.from_user.id, permissions=ChatPermissions(can_send_messages=False), until_date=until)
        await message.answer(f"🔇 Пользователь заглушен на {time_min} мин.!")
    except Exception as e:
        await message.answer(f"❌ Ошибка мута: {e}")

@dp.message(Command("unmute"))
async def cmd_unmute(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 4: return await message.answer("❌ С 4+ ранга.")
    if not message.reply_to_message: return await message.answer("⚠️ Ответьте на сообщение!")
    try:
        await bot.restrict_chat_member(
            message.chat.id, message.reply_to_message.from_user.id,
            permissions=ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True, can_add_web_page_previews=True)
        )
        await message.answer("🔊 Мут снят!")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@dp.message(Command("kick"))
async def cmd_kick(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 4: return await message.answer("❌ С 4+ ранга.")
    if not message.reply_to_message: return await message.answer("⚠️ Ответьте на сообщение!")
    tid = message.reply_to_message.from_user.id
    try:
        await bot.ban_chat_member(message.chat.id, tid)
        await bot.unban_chat_member(message.chat.id, tid)
        await message.answer("🚪 Пользователь кикнут!")
    except Exception as e:
        await message.answer(f"❌ Ошибка кика: {e}")

@dp.message(Command("ban"))
async def cmd_ban(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 4: return await message.answer("❌ С 4+ ранга.")
    if not message.reply_to_message: return await message.answer("⚠️ Ответьте на сообщение!")
    tid = message.reply_to_message.from_user.id
    try:
        await bot.ban_chat_member(message.chat.id, tid)
        await message.answer("⛔ Пользователь заблокирован в чате!")
    except Exception as e:
        await message.answer(f"❌ Ошибка бана: {e}")

@dp.message(Command("unban"))
async def cmd_unban(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 4: return await message.answer("❌ С 4+ ранга.")
    if not command.args: return await message.answer("⚠️ Укажите ID или @username.")
    t_user = get_user(user_id=int(command.args)) if command.args.isdigit() else get_user(username=clean_username(command.args))
    if not t_user: return await message.answer("❌ Игрок не найден.")
    try:
        await bot.unban_chat_member(message.chat.id, t_user[0], only_if_banned=True)
        await message.answer(f"✅ Пользователь @{t_user[1] or t_user[0]} разблокирован в этом чате!")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@dp.message(Command("skick"))
async def cmd_skick(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 5: return await message.answer("❌ С 5 ранга.")
    if not message.reply_to_message: return await message.answer("⚠️ Ответьте на сообщение нарушителя!")
    tid = message.reply_to_message.from_user.id
    cursor.execute("SELECT chat_id FROM known_chats")
    success = 0
    for ch in cursor.fetchall():
        try:
            await bot.ban_chat_member(ch[0], tid)
            await bot.unban_chat_member(ch[0], tid)
            success += 1
        except Exception: pass
    await message.answer(f"🚪 Кикнут из {success} групп!")

@dp.message(Command("sban"))
async def cmd_sban(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 5: return await message.answer("❌ С 5 ранга.")
    if not message.reply_to_message: return await message.answer("⚠️ Ответьте на сообщение нарушителя!")
    tid = message.reply_to_message.from_user.id
    cursor.execute("SELECT chat_id FROM known_chats")
    success = 0
    for ch in cursor.fetchall():
        try:
            await bot.ban_chat_member(ch[0], tid)
            success += 1
        except Exception: pass
    await message.answer(f"⛔ Забанен в {success} группах!")

@dp.message(Command("gwarn"))
async def cmd_gwarn(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 8: return await message.answer("❌ GWARN с 8+ ранга.")
    if not message.reply_to_message or not command.args:
        return await message.answer("⚠️ Ответьте на сообщение с причиной: <code>/gwarn Причина</code>", parse_mode="HTML")
    tid = message.reply_to_message.from_user.id
    
    # Мут на 15 минут во всех беседах
    until = datetime.now() + timedelta(minutes=15)
    cursor.execute("SELECT chat_id FROM known_chats")
    for ch in cursor.fetchall():
        try:
            await bot.restrict_chat_member(ch[0], tid, permissions=ChatPermissions(can_send_messages=False), until_date=until)
        except Exception: pass

    is_banned, msg = add_gwarn(tid, command.args, message.from_user.username or "Admin")
    await message.answer(f"🌐 {msg}", parse_mode="HTML")

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
# 9. УПРАВЛЕНИЕ ПРАВАМИ И ДОЛЖНОСТЯМИ (/setaccess, /setadmin, /setzam)
# ==========================================

@dp.message(Command("setaccess"))
async def cmd_setaccess(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8: return await message.answer("❌ Доступно с 8+ ранга.")
    if not command.args: return await message.answer("⚠️ Укажите @username или ID.")
    target_un = clean_username(command.args.split()[0])
    set_role(target_un, "Главный Администратор (ГА)")
    t_user = get_user(username=target_un)
    if t_user: update_user(t_user[0], rank=6)
    await message.answer(f"✅ Права ГА (6 уровень) выданы: @{target_un}")

@dp.message(Command("unsetaccess"))
async def cmd_unsetaccess(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8: return await message.answer("❌ Доступно с 8+ ранга.")
    if not command.args: return await message.answer("⚠️ Укажите @username или ID.")
    target_un = clean_username(command.args.split()[0])
    set_role(target_un, "User")
    t_user = get_user(username=target_un)
    if t_user: update_user(t_user[0], rank=0)
    await message.answer(f"📉 Права ГА сняты с: @{target_un}")

@dp.message(Command("setadmin"))
async def cmd_setadmin(message: Message, command: CommandObject, state: FSMContext):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 9: return await message.answer("❌ Назначение 8 рангов доступно с 9+ ранга.")
    if not command.args: return await message.answer("⚠️ Укажите @username или ID.")

    target_raw = command.args.split()[0]
    target_user = get_user(user_id=int(target_raw)) if target_raw.isdigit() else get_user(username=clean_username(target_raw))
    if not target_user: return await message.answer("❌ Пользователь не найден.")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1. ГСЗТХ", callback_data=f"setadm_1_{target_user[0]}")],
        [InlineKeyboardButton(text="2. ЗГСЗТХ", callback_data=f"setadm_2_{target_user[0]}")],
        [InlineKeyboardButton(text="3. ГСЗГА", callback_data=f"setadm_3_{target_user[0]}")],
        [InlineKeyboardButton(text="4. ЗГСЗГА", callback_data=f"setadm_4_{target_user[0]}")],
        [InlineKeyboardButton(text="5. ГСЗР", callback_data=f"setadm_5_{target_user[0]}")],
        [InlineKeyboardButton(text="6. ЗГСЗР", callback_data=f"setadm_6_{target_user[0]}")]
    ])
    await message.answer(f"🛡️ Выберите роль для назначения 8 ранга пользователю @{target_user[1] or target_user[0]}:", reply_markup=kb)

@dp.callback_query(F.data.startswith("setadm_"))
async def process_setadmin_callback(callback: CallbackQuery):
    _, role_idx, uid_str = callback.data.split("_")
    target_uid = int(uid_str)
    roles_dict = {
        "1": "ГСЗТХ",
        "2": "ЗГСЗТХ",
        "3": "ГСЗГА",
        "4": "ЗГСЗГА",
        "5": "ГСЗР",
        "6": "ЗГСЗР"
    }
    role_name = roles_dict.get(role_idx, "Администратор")
    update_user(target_uid, rank=8, role=role_name)
    await callback.message.edit_text(f"✅ Пользователю успешно выдан <b>8 ранг</b> с ролью: <b>{role_name}</b>!", parse_mode="HTML")

@dp.message(Command("setzam"))
async def cmd_setzam(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if message.from_user.id not in ADMIN_IDS and user[3] < 10:
        return await message.answer("❌ Назначение 9 ранга доступно строго Владельцу (10 ранг)!")
    if not command.args or len(command.args.split()) < 2:
        return await message.answer("⚠️ Использование: <code>/setzam [ОЗГР/ЗГР] [@username/ID]</code>", parse_mode="HTML")

    role_choice, target_raw = command.args.split()[:2]
    role_choice = role_choice.upper()
    if role_choice not in ["ОЗГР", "ЗГР"]:
        return await message.answer("⚠️ Выберите роль: <b>ОЗГР</b> или <b>ЗГР</b>!", parse_mode="HTML")

    target_user = get_user(user_id=int(target_raw)) if target_raw.isdigit() else get_user(username=clean_username(target_raw))
    if not target_user: return await message.answer("❌ Пользователь не найден.")

    full_role = "Основной Заместитель Главного Руководителя (ОЗГР)" if role_choice == "ОЗГР" else "Заместитель Главного Руководителя (ЗГР)"
    update_user(target_user[0], rank=9, role=full_role)
    await message.answer(f"👑 Назначен <b>9 ранг</b> ({full_role}) для пользователя @{target_user[1] or target_user[0]}!", parse_mode="HTML")

# ==========================================
# 10. РАССМОТРЕНИЕ ОБЖАЛОВАНИЙ (/GB и /GW)
# ==========================================

@dp.message(Command("GB"))
async def cmd_gb_review(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 9: return await message.answer("❌ Команда /GB доступна с 9+ ранга.")
    if not command.args or not command.args.isdigit():
        return await message.answer("⚠️ Укажите номер обжалования из списка в /gblist: <code>/GB 1</code>", parse_mode="HTML")

    req_id = int(command.args)
    cursor.execute("SELECT id, user_id, username, reason FROM obgban_requests WHERE id = ?", (req_id,))
    row = cursor.fetchone()
    if not row: return await message.answer("❌ Заявка на обжалование GBAN не найдена.")

    _, target_uid, target_un, req_reason = row
    cursor.execute("SELECT reason FROM global_bans WHERE user_id = ?", (target_uid,))
    ban_row = cursor.fetchone()
    ban_reason = ban_row[0] if ban_row else "Не указана"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Снять GBAN", callback_data=f"gb_unban_{req_id}_{target_uid}"),
            InlineKeyboardButton(text="❌ Оставить GBAN", callback_data=f"gb_keep_{req_id}_{target_uid}")
        ]
    ])
    await message.answer(
        f"🌐 <b>Обжалование GBAN #{req_id}</b>\n\n"
        f"👤 Нарушитель: @{target_un} (<code>{target_uid}</code>)\n"
        f"⛔ За что был получен GBAN: <b>{ban_reason}</b>\n"
        f"📄 Текст обжалования: {req_reason}",
        reply_markup=kb,
        parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("gb_unban_"))
async def callback_gb_unban(callback: CallbackQuery):
    _, _, req_id_str, uid_str = callback.data.split("_")
    target_uid = int(uid_str)
    req_id = int(req_id_str)

    cursor.execute("DELETE FROM global_bans WHERE user_id = ?", (target_uid,))
    cursor.execute("DELETE FROM obgban_requests WHERE id = ?", (req_id,))
    conn.commit()

    await callback.message.edit_text(f"✅ GBAN успешно снят с пользователя ( ID: <code>{target_uid}</code> ). Заявка закрыта.", parse_mode="HTML")
    try: await bot.send_message(target_uid, "🎉 Ваше обжалование GBAN одобрено! Бан снят.", parse_mode="HTML")
    except Exception: pass

@dp.callback_query(F.data.startswith("gb_keep_"))
async def callback_gb_keep(callback: CallbackQuery, state: FSMContext):
    _, _, req_id_str, uid_str = callback.data.split("_")
    await state.update_data(req_id=int(req_id_str), target_uid=int(uid_str))
    await state.set_state(AdminRejectOrder.waiting_for_reason)
    await callback.message.edit_text("✍️ Напишите причину, почему вы отклоняете обжалование GBAN:")

@dp.message(AdminRejectOrder.waiting_for_reason)
async def process_gb_reject_reason(message: Message, state: FSMContext):
    data = await state.get_data()
    req_id = data.get("req_id")
    target_uid = data.get("target_uid")
    reason = message.text

    cursor.execute("DELETE FROM obgban_requests WHERE id = ?", (req_id,))
    conn.commit()
    await state.clear()

    await message.answer("✅ Обжалование отклонено, причина отправлена игроку.")
    try:
        await bot.send_message(target_uid, f"❌ Ваше обжалование GBAN отклонено.\n📝 Причина: {reason}", parse_mode="HTML")
    except Exception: pass

@dp.message(Command("GW"))
async def cmd_gw_review(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8: return await message.answer("❌ Команда /GW доступна с 8+ ранга.")
    if not command.args or not command.args.isdigit():
        return await message.answer("⚠️ Укажите номер обжалования GWARN: <code>/GW 1</code>", parse_mode="HTML")

    req_id = int(command.args)
    cursor.execute("SELECT id, user_id, username, reason FROM obgwarn_requests WHERE id = ?", (req_id,))
    row = cursor.fetchone()
    if not row: return await message.answer("❌ Заявка на обжалование GWARN не найдена.")

    _, target_uid, target_un, req_reason = row
    cursor.execute("SELECT reason FROM global_warns WHERE user_id = ?", (target_uid,))
    warn_row = cursor.fetchone()
    warn_reason = warn_row[0] if warn_row else "Не указана"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Снять GWARN", callback_data=f"gw_unwarn_{req_id}_{target_uid}"),
            InlineKeyboardButton(text="❌ Оставить GWARN", callback_data=f"gw_keep_{req_id}_{target_uid}")
        ]
    ])
    await message.answer(
        f"🌐 <b>Обжалование GWARN #{req_id}</b>\n\n"
        f"👤 Нарушитель: @{target_un} (<code>{target_uid}</code>)\n"
        f"⚠️ Причина варна: <b>{warn_reason}</b>\n"
        f"📄 Текст обжалования: {req_reason}",
        reply_markup=kb,
        parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("gw_unwarn_"))
async def callback_gw_unwarn(callback: CallbackQuery):
    _, _, req_id_str, uid_str = callback.data.split("_")
    target_uid = int(uid_str)
    req_id = int(req_id_str)

    cursor.execute("DELETE FROM global_warns WHERE id IN (SELECT id FROM global_warns WHERE user_id = ? ORDER BY id DESC LIMIT 1)", (target_uid,))
    cursor.execute("DELETE FROM obgwarn_requests WHERE id = ?", (req_id,))
    conn.commit()

    await callback.message.edit_text(f"✅ Один GWARN успешно снят с пользователя ( ID: <code>{target_uid}</code> ).", parse_mode="HTML")
    try: await bot.send_message(target_uid, "🎉 Ваше обжалование GWARN одобрено! Варн снят.", parse_mode="HTML")
    except Exception: pass

@dp.callback_query(F.data.startswith("gw_keep_"))
async def callback_gw_keep(callback: CallbackQuery):
    _, _, req_id_str, uid_str = callback.data.split("_")
    req_id = int(req_id_str)
    cursor.execute("DELETE FROM obgwarn_requests WHERE id = ?", (req_id,))
    conn.commit()
    await callback.message.edit_text("❌ Обжалование GWARN отклонено.")

@dp.message(Command("gblist"))
async def cmd_gblist(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 9: return await message.answer("❌ Доступно с 9+ ранга.")
    cursor.execute("SELECT user_id, reason, by_user FROM global_bans")
    rows = cursor.fetchall()
    if not rows: return await message.answer("🌐 Список GBAN пуст.")
    text = "🚨 <b>СПИСОК ПОЛЬЗОВАТЕЛЕЙ В GBAN:</b>\n\n"
    for r in rows:
        text += f"• ID: <code>{r[0]}</code> | Причина: {r[1]}\n"
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
