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
        total_donated_stars INTEGER DEFAULT 0
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
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN total_donated_stars INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE promocodes ADD COLUMN created_at TEXT")
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

def set_role(username_or_id, new_role: str, new_rank: int = None):
    if str(username_or_id).isdigit():
        if new_rank is not None:
            cursor.execute("UPDATE users SET role = ?, rank = ? WHERE user_id = ?", (new_role, new_rank, int(username_or_id)))
        else:
            cursor.execute("UPDATE users SET role = ? WHERE user_id = ?", (new_role, int(username_or_id)))
    else:
        u_clean = clean_username(str(username_or_id))
        if new_rank is not None:
            cursor.execute("UPDATE users SET role = ?, rank = ? WHERE LOWER(username) = ?", (new_role, new_rank, u_clean))
        else:
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

MONEY_PACKS_UAH = {
    "1000": {"coins": 1000, "price": 15, "text": "1,000 монет — 15 грн"},
    "5000": {"coins": 5000, "price": 70, "text": "5,000 монет — 70 грн"},
    "10000": {"coins": 10000, "price": 110, "text": "10,000 монет — 110 грн"},
    "15000": {"coins": 15000, "price": 140, "text": "15,000 монет — 140 грн"},
    "20000": {"coins": 20000, "price": 180, "text": "20,000 монет — 180 грн"},
}

# ==========================================
# 4. МИДДЛВАРИ И ОТСЛЕЖИВАНИЕ ДОБАВЛЕНИЯ БОТА
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

@dp.message(Command("ip"))
async def cmd_ip(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 7:
        return await message.answer("❌ Команда <code>/ip</code> доступна с 7+ ранга управления!", parse_mode="HTML")
    
    if not command.args:
        return await message.answer("⚠️ Укажите IP-адрес: <code>/ip 8.8.8.8</code>", parse_mode="HTML")

    ip_address = command.args.split()[0]
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"http://ip-api.com/json/{ip_address}?lang=ru") as resp:
                if resp.status != 200:
                    return await message.answer("❌ Не удалось получить данные по данному IP.")
                data = await resp.json()
                if data.get("status") == "fail":
                    return await message.answer(f"❌ Ошибка: {data.get('message', 'Неверный IP')}")

                text = (
                    f"🌐 <b>Информация по IP:</b> <code>{ip_address}</code>\n\n"
                    f"🌍 Страна: <b>{data.get('country', '-')} ({data.get('countryCode', '-')})</b>\n"
                    f"🏙 Регион/Город: <b>{data.get('regionName', '-')}, {data.get('city', '-')}</b>\n"
                    f"📮 Почтовый индекс: <b>{data.get('zip', '-')}</b>\n"
                    f"📡 Провайдер (ISP): <b>{data.get('isp', '-')}</b>\n"
                    f"🏢 Организация: <b>{data.get('org', '-')}</b>\n"
                    f"📌 Координаты: <code>{data.get('lat', '-')}, {data.get('lon', '-')}</code>"
                )
                await message.answer(text, parse_mode="HTML")
        except Exception as e:
            await message.answer(f"❌ Произошла ошибка при запросе к API: {e}")

@dp.message(Command("zov"))
async def cmd_zov(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 3:
        return await message.answer("❌ Команда <code>/zov</code> доступна с 3+ ранга!", parse_mode="HTML")
    
    reason = command.args if command.args else "Общий сбор!"
    await message.answer(f"📢 <b>ВНИМАНИЕ ВСЕМ!</b> @everyone\nПричина: <b>{reason}</b>", parse_mode="HTML")
    
    for _ in range(5):
        await message.answer(f"{reason}")
        await asyncio.sleep(0.5)

@dp.message(Command("id"))
async def cmd_id(message: Message, command: CommandObject):
    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
        return await message.answer(
            f"👤 <b>Пользователь:</b> @{target_user.username or 'без_юзернейма'}\n"
            f"🆔 <b>ID:</b> <code>{target_user.id}</code>",
            parse_mode="HTML"
        )
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

    await message.answer("📝 <b>Обжалование GBAN</b>\n\nОпишите подробно причину обжалования:", parse_mode="HTML")
    await state.set_state(ObgbanState.waiting_for_reason)

@dp.message(ObgbanState.waiting_for_reason)
async def process_obgban_text(message: Message, state: FSMContext):
    uid = message.from_user.id
    uname = message.from_user.username or f"ID:{uid}"
    reason = message.text
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    cursor.execute("INSERT INTO obgban_requests (user_id, username, reason, date) VALUES (?, ?, ?, ?)", (uid, uname, reason, date_str))
    conn.commit()
    await state.clear()
    await message.answer("✅ Заявка на обжалование GBAN отправлена 9+ рангам!")

@dp.message(Command("Obgwarn"))
async def cmd_obgwarn(message: Message, state: FSMContext):
    if message.chat.type != 'private':
        return await message.answer("⚠️ Команду <code>/Obgwarn</code> нужно писать строго в ЛС бота!", parse_mode="HTML")
    uid = message.from_user.id
    cursor.execute("SELECT COUNT(*) FROM global_warns WHERE user_id = ?", (uid,))
    if cursor.fetchone()[0] == 0:
        return await message.answer("❌ У вас нет активных GWARN.")

    await message.answer("📝 <b>Обжалование GWARN</b>\n\nОпишите причину:", parse_mode="HTML")
    await state.set_state(ObgwarnState.waiting_for_reason)

@dp.message(ObgwarnState.waiting_for_reason)
async def process_obgwarn_text(message: Message, state: FSMContext):
    uid = message.from_user.id
    uname = message.from_user.username or f"ID:{uid}"
    reason = message.text
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    cursor.execute("INSERT INTO obgwarn_requests (user_id, username, reason, date) VALUES (?, ?, ?, ?)", (uid, uname, reason, date_str))
    conn.commit()
    await state.clear()
    await message.answer("✅ Заявка на обжалование GWARN отправлена 8+ рангам!")

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

    if u1[5] < bet or u2[5] < bet:
        return await message.answer("❌ У кого-то из игроков недостаточно монет для ставки!")

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⚔️ Сыграть дуэль", callback_data=f"duel_play_{user1_id}_{user2_id}_{bet}")
    ]])
    await message.answer(
        f"⚔️ <b>Дуэль на монеты!</b>\nСтавка: <b>{bet} монет</b>\nНажмите кнопку ниже для старта:",
        reply_markup=kb, parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("duel_play_"))
async def callback_duel_play(callback: CallbackQuery):
    _, _, u1_str, u2_str, bet_str = callback.data.split("_")
    u1_id, u2_id, bet = int(u1_str), int(u2_str), int(bet_str)

    if callback.from_user.id not in [u1_id, u2_id]:
        return await callback.answer("❌ Вы не участник этой дуэли!", show_alert=True)

    u1 = get_user(user_id=u1_id)
    u2 = get_user(user_id=u2_id)
    if u1[5] < bet or u2[5] < bet:
        return await callback.answer("❌ У кого-то недостаточно монет!", show_alert=True)

    v1, v2 = is_vip(u1), is_vip(u2)
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
        f"⚔️ <b>Результаты дуэли (ставка {bet}):</b>\n"
        f"🏆 Победитель: <a href='tg://user?id={winner_id}'>Игрок</a> (+{bet})\n"
        f"💀 Проигравший: <a href='tg://user?id={loser_id}'>Игрок</a> (-{bet})",
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
        return await message.answer(f"❌ Максимальная ставка для вас: <b>{max_bet} монет</b>.", parse_mode="HTML")
    if user[5] < bet:
        return await message.answer("❌ Недостаточно монет!")

    win_chance = 60 if vip else 40
    is_win = random.choices([True, False], weights=[win_chance, 100 - win_chance], k=1)[0]

    if is_win:
        update_user(message.from_user.id, coins=user[5] + bet)
        await message.answer(f"🎰 <b>ПОБЕДА!</b> Выиграно +{bet} монет! 💰", parse_mode="HTML")
    else:
        update_user(message.from_user.id, coins=user[5] - bet)
        await message.answer(f"🎰 <b>ПРОИГРЫШ!</b> Потеряно -{bet} монет. 💸", parse_mode="HTML")

@dp.message(Command("report"))
async def cmd_report(message: Message, command: CommandObject):
    if not command.args:
        return await message.answer("⚠️ Укажите суть жалобы: <code>/report Текст</code>", parse_mode="HTML")
    target_id = message.reply_to_message.from_user.id if message.reply_to_message else 0
    cursor.execute("INSERT INTO reports (chat_id, user_id, target_id, text, status) VALUES (?, ?, ?, ?, 'pending')",
                   (message.chat.id, message.from_user.id, target_id, command.args))
    conn.commit()
    r_id = cursor.lastrowid
    await message.answer(f"🚨 Репорт отправлен администрации! (ID: #{r_id})")

    cursor.execute("SELECT user_id FROM users WHERE rank >= 8")
    for row in cursor.fetchall():
        try:
            await bot.send_message(row[0], f"🚨 <b>Новый репорт (#{r_id})!</b>\n{command.args}\nОтвет: <code>/rep {r_id} ответ</code>", parse_mode="HTML")
        except Exception: pass

@dp.message(Command("rep"))
async def cmd_rep_answer(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8: return await message.answer("❌ Доступно с 8+ ранга.")
    if not command.args: return await message.answer("⚠️ Использование: <code>/rep [ID] [Текст]</code>", parse_mode="HTML")

    parts = command.args.split(maxsplit=1)
    if not parts[0].isdigit(): return await message.answer("⚠️ Укажите числовой ID репорта.")
    r_id = int(parts[0])
    answer_text = parts[1] if len(parts) > 1 else "Без ответа"

    cursor.execute("SELECT user_id, text FROM reports WHERE id = ? AND status = 'pending'", (r_id,))
    row = cursor.fetchone()
    if not row: return await message.answer("❌ Репорт не найден или закрыт.")

    author_id, rep_text = row
    cursor.execute("UPDATE reports SET status = 'resolved' WHERE id = ?", (r_id,))
    conn.commit()

    await message.answer(f"✅ Репорт #{r_id} закрыт.")
    try:
        await bot.send_message(author_id, f"📬 <b>Ответ на репорт #{r_id}:</b>\n{answer_text}", parse_mode="HTML")
    except Exception: pass

@dp.message(Command("Repbook"))
async def cmd_repbook(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8: return await message.answer("❌ Доступно с 8+ ранга.")
    if not command.args: return await message.answer("⚠️ Укажите @username или ID.")
    target_raw = command.args.split()[0]
    target_uid = int(target_raw) if target_raw.isdigit() else (get_user(username=clean_username(target_raw)) or [0])[0]

    cursor.execute("SELECT id, text, status FROM reports WHERE user_id = ? ORDER BY id DESC LIMIT 10", (target_uid,))
    rows = cursor.fetchall()
    if not rows: return await message.answer("📋 Обращений нет.")

    text = f"📋 <b>История репортов ({target_raw}):</b>\n\n"
    for r in rows:
        text += f"• #{r[0]} | Статус: {r[2]} | {r[1]}\n"
    await message.answer(text, parse_mode="HTML")

# ==========================================
# 7. ДОНАТЫ И ПОКУПКИ (/Blago, /Donats, /BL)
# ==========================================

@dp.message(Command("Blago"))
async def cmd_blago(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Донат в ГРН", callback_data="blago_uah")],
        [InlineKeyboardButton(text="⭐️ Донат в Stars", callback_data="blago_stars")]
    ])
    await message.answer("❤️ <b>Поддержка проекта и разработчика</b>\nВыберите валюту для доната:", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "blago_uah")
async def blago_uah_callback(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        f"💳 <b>Оплата в ГРН</b>\n\nБанка Monobank:\n🔗 {MONOBANK_JAR}\n\n"
        f"⚠️ <b>Обязательно</b> укажите ваш @Username или User ID в комментарии к платежу!\n\n"
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
            await bot.send_message(row[0], f"❤️ <b>Новый донат (ГРН) (#{req_id})!</b>\nОт: {uname_or_id} (ID: {uid})\nПроверьте банку и подтвердите через /BL", parse_mode="HTML")
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
        "⭐️ <b>Выберите количество Звезд для доната:</b>\n\n"
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
    payment = message.successful_payment
    if payment.invoice_payload.startswith("donate_stars_"):
        stars_count = int(payment.invoice_payload.split("_")[2])
        uid = message.from_user.id
        uname = message.from_user.username or f"ID:{uid}"
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        user = get_user(user_id=uid)
        current_stars = user[26] if len(user) > 26 and user[26] else 0
        update_user(uid, total_donated_stars=current_stars + stars_count)

        cursor.execute(
            "INSERT INTO donats_history (user_id, username, type, amount, currency, date) VALUES (?, ?, ?, ?, ?, ?)",
            (uid, uname, "Донат Stars", f"{stars_count} Звезд", "Stars", date_str)
        )
        conn.commit()

        await message.answer(
            f"🎉 <b>Оплата прошла успешно!</b>\n\n"
            f"Спасибо огромное за донат в <b>{stars_count} Звезд⭐️</b>!\n"
            f"Платеж зачтен в вашу статистику покупок (`/Donats`). ❤️",
            parse_mode="HTML"
        )

@dp.message(Command("Donats"))
async def cmd_donats(message: Message):
    uid = message.from_user.id
    user = get_user(user_id=uid)
    uah_donated = user[25] if len(user) > 25 and user[25] else 0
    stars_donated = user[26] if len(user) > 26 and user[26] else 0

    cursor.execute("SELECT period, price, currency, date FROM vip_history WHERE user_id = ?", (uid,))
    vips = cursor.fetchall()
    cursor.execute("SELECT type, amount, currency, date FROM donats_history WHERE user_id = ?", (uid,))
    donats = cursor.fetchall()

    text = (
        f"🧾 <b>СТАТИСТИКА ВАШИХ ДОНАТОВ И ПОКУПОК:</b>\n\n"
        f"💵 Всего задоначено в ГРН: <b>{uah_donated} грн</b>\n"
        f"⭐ Всего задоначено Звездами: <b>{stars_donated} ⭐️</b>\n\n"
    )

    if vips or donats:
        text += "<b>История:</b>\n"
        for v in vips:
            text += f"• VIP: {v[0]} | {v[1]} {v[2]} | {v[3]}\n"
        for d in donats:
            text += f"• {d[0]} | {d[1]} | {d[2]}\n"
    else:
        text += "У вас пока нет записей о покупках."

    await message.answer(text, parse_mode="HTML")

@dp.message(Command("BL"))
async def cmd_bl_list(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 10:
        return await message.answer("❌ Команда <code>/BL</code> доступна только с 10 ранга!", parse_mode="HTML")

    cursor.execute("SELECT id, user_id, username, amount, currency, date FROM blago_requests WHERE status = 'pending'")
    rows = cursor.fetchall()

    if not rows:
        return await message.answer("📋 Нет активных заявок на проверку донатов через /Blago.")

    text = "📋 <b>СПИСОК ОЖИДАЮЩИХ ПОДТВЕРЖДЕНИЯ ДОНАТОВ:</b>\n\n"
    for r in rows:
        text += f"• <b>ID #{r[0]}</b> | От: {r[2]} (<code>{r[1]}</code>) | Сумма: {r[3]} | Дата: {r[5]}\n"
        
    text += "\n<i>Для подтверждения:</i> <code>/bl_confirm [ID]</code>\n<i>Для отклонения:</i> <code>/bl_reject [ID]</code>"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("bl_confirm"))
async def cmd_bl_confirm(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 10: return
    if not command.args or not command.args.isdigit():
        return await message.answer("⚠️ Укажите ID заявки: <code>/bl_confirm 1</code>", parse_mode="HTML")
    
    req_id = int(command.args)
    cursor.execute("SELECT user_id, username FROM blago_requests WHERE id = ? AND status = 'pending'", (req_id,))
    row = cursor.fetchone()
    if not row: return await message.answer("❌ Заявка не найдена.")

    target_uid, uname = row
    cursor.execute("UPDATE blago_requests SET status = 'accepted' WHERE id = ?", (req_id,))
    
    t_user = get_user(user_id=target_uid)
    current_uah = t_user[25] if len(t_user) > 25 and t_user[25] else 0
    update_user(target_uid, total_donated_uah=current_uah + 100)

    cursor.execute("INSERT INTO donats_history (user_id, username, type, amount, currency, date) VALUES (?, ?, ?, ?, ?, ?)",
                   (target_uid, uname, "Благо (ГРН)", "Поддержал автора ✅", "грн", datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()

    await message.answer(f"✅ Донат заявки #{req_id} подтвержден!")
    try:
        await bot.send_message(target_uid, "🎉 Ваша заявка о поддержке автора (донат) подтверждена администратором! Спасибо ❤️", parse_mode="HTML")
    except Exception:
        pass

@dp.message(Command("bl_reject"))
async def cmd_bl_reject(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 10: return
    if not command.args or not command.args.isdigit():
        return await message.answer("⚠️ Укажите ID заявки: <code>/bl_reject 1</code>", parse_mode="HTML")
    
    req_id = int(command.args)
    cursor.execute("SELECT user_id FROM blago_requests WHERE id = ? AND status = 'pending'", (req_id,))
    row = cursor.fetchone()
    if not row: return await message.answer("❌ Заявка не найдена.")

    target_uid = row[0]
    cursor.execute("UPDATE blago_requests SET status = 'rejected' WHERE id = ?", (req_id,))
    conn.commit()

    await message.answer(f"❌ Заявка #{req_id} отклонена.")
    try:
        await bot.send_message(target_uid, "❌ Ваша заявка о поддержке автора отклонена администрацией.", parse_mode="HTML")
    except Exception:
        pass

# ==========================================
# 8. МОДЕРАЦИЯ И АДМИНИСТРИРОВАНИЕ
# ==========================================

@dp.message(Command("warn"))
async def cmd_warn(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 4: return await message.answer("❌ С 4+ ранга.")
    if not message.reply_to_message: return await message.answer("⚠️ Ответьте на сообщение!")
    tid = message.reply_to_message.from_user.id
    target = get_user(user_id=tid)
    warns = target[19] + 1

    try:
        await bot.restrict_chat_member(message.chat.id, tid, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now() + timedelta(minutes=10))
    except Exception: pass

    if warns >= 3:
        update_user(tid, warns=0)
        try: await bot.ban_chat_member(message.chat.id, tid)
        except Exception: pass
        await message.answer("💥 3/3 варнов, пользователь кикнут + мут на 10 мин!")
    else:
        update_user(tid, warns=warns)
        await message.answer(f"⚠️ Варн выдано ({warns}/3) + мут на 10 мин!")

@dp.message(Command("unwarn"))
async def cmd_unwarn(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 4: return await message.answer("❌ С 4+ ранга.")
    if not message.reply_to_message: return await message.answer("⚠️ Ответьте на сообщение!")
    tid = message.reply_to_message.from_user.id
    target = get_user(user_id=tid)
    curr = target[19]
    if curr <= 0: return await message.answer("⚠️ Варнов нет.")
    update_user(tid, warns=curr - 1)
    await message.answer(f"✅ Варн снят ({curr - 1}/3)!")

@dp.message(Command("mute"))
async def cmd_mute(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 4: return await message.answer("❌ С 4+ ранга.")
    if not message.reply_to_message: return await message.answer("⚠️ Ответьте на сообщение!")
    time_min = int(command.args) if command.args and command.args.isdigit() else 15
    try:
        await bot.restrict_chat_member(message.chat.id, message.reply_to_message.from_user.id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now() + timedelta(minutes=time_min))
        await message.answer(f"🔇 Мут на {time_min} мин. выдано!")
    except Exception as e: await message.answer(f"❌ Ошибка: {e}")

@dp.message(Command("unmute"))
async def cmd_unmute(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 4: return await message.answer("❌ С 4+ ранга.")
    if not message.reply_to_message: return await message.answer("⚠️ Ответьте на сообщение!")
    try:
        await bot.restrict_chat_member(message.chat.id, message.reply_to_message.from_user.id, permissions=ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True))
        await message.answer("🔊 Мут снят!")
    except Exception as e: await message.answer(f"❌ Ошибка: {e}")

@dp.message(Command("ban"))
async def cmd_ban(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 4: return await message.answer("❌ С 4+ ранга.")
    if not message.reply_to_message: return await message.answer("⚠️ Ответьте на сообщение!")
    try:
        await bot.ban_chat_member(message.chat.id, message.reply_to_message.from_user.id)
        await message.answer("⛔ Бан выдано!")
    except Exception as e: await message.answer(f"❌ Ошибка: {e}")

@dp.message(Command("unban"))
async def cmd_unban(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 4: return await message.answer("❌ С 4+ ранга.")
    if not command.args: return await message.answer("⚠️ Укажите ID или юзернейм.")
    t_user = get_user(user_id=int(command.args)) if command.args.isdigit() else get_user(username=clean_username(command.args))
    if not t_user: return await message.answer("❌ Игрок не найден.")
    try:
        await bot.unban_chat_member(message.chat.id, t_user[0], only_if_banned=True)
        await message.answer(f"✅ Разбанено!")
    except Exception as e: await message.answer(f"❌ Ошибка: {e}")

@dp.message(Command("gwarn"))
async def cmd_gwarn(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8: return await message.answer("❌ С 8+ ранга.")
    if not message.reply_to_message or not command.args: return await message.answer("⚠️ Укажите причину.")
    tid = message.reply_to_message.from_user.id

    until = datetime.now() + timedelta(minutes=15)
    cursor.execute("SELECT chat_id FROM known_chats")
    for ch in cursor.fetchall():
        try: await bot.restrict_chat_member(ch[0], tid, permissions=ChatPermissions(can_send_messages=False), until_date=until)
        except Exception: pass

    is_banned, msg = add_gwarn(tid, command.args, message.from_user.username or "Admin")
    await message.answer(f"🌐 {msg}", parse_mode="HTML")

# Управление техниками (/settex, /Tlist)
@dp.message(Command("settex"))
async def cmd_settex(message: Message):
    uid = message.from_user.id
    uname = message.from_user.username or f"ID:{uid}"
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    cursor.execute("INSERT INTO tex_requests (user_id, username, date) VALUES (?, ?, ?)", (uid, uname, date_str))
    conn.commit()
    req_id = cursor.lastrowid
    await message.answer("✅ Ваша заявка на получение роли Техника успешно отправлена 8+ рангам!")

    cursor.execute("SELECT user_id FROM users WHERE rank >= 8")
    for row in cursor.fetchall():
        try:
            await bot.send_message(row[0], f"🛠 <b>Новая заявка на Техника (#{req_id})!</b>\nОт: @{uname} (<code>{uid}</code>)\nПроверьте через /Tlist", parse_mode="HTML")
        except Exception:
            pass

@dp.message(Command("Tlist"))
async def cmd_tlist(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8:
        return await message.answer("❌ Команда <code>/Tlist</code> доступна с 8+ ранга!", parse_mode="HTML")

    cursor.execute("SELECT id, user_id, username, date FROM tex_requests")
    rows = cursor.fetchall()
    if not rows:
        return await message.answer("📋 Нет активных заявок на должность техника.")

    text = "🛠 <b>СПИСОК ЗАЯВОК НА ТЕХНИКОВ:</b>\n\n"
    for r in rows:
        text += f"• <b>ID #{r[0]}</b> | @{r[2]} (<code>{r[1]}</code>) | Время: {r[3]}\n"
    
    text += "\nИспользуйте: <code>/tex_accept [ID]</code> или <code>/tex_reject [ID]</code>"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("tex_accept"))
async def cmd_tex_accept(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8: return
    if not command.args or not command.args.isdigit(): return await message.answer("⚠️ Укажите ID заявки.")
    req_id = int(command.args)

    cursor.execute("SELECT user_id, username FROM tex_requests WHERE id = ?", (req_id,))
    row = cursor.fetchone()
    if not row: return await message.answer("❌ Заявка не найдена.")

    target_uid, uname = row
    set_role(target_uid, "Техник", new_rank=4)
    cursor.execute("DELETE FROM tex_requests WHERE id = ?", (req_id,))
    conn.commit()

    await message.answer(f"✅ Заявка #{req_id} одобрена! Пользователь @{uname} назначен Техником.")
    try:
        await bot.send_message(target_uid, "🎉 Ваша заявка на Техника одобрена!", parse_mode="HTML")
    except Exception:
        pass

@dp.message(Command("tex_reject"))
async def cmd_tex_reject(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8: return
    if not command.args or not command.args.isdigit(): return await message.answer("⚠️ Укажите ID заявки.")
    req_id = int(command.args)

    cursor.execute("SELECT user_id, username FROM tex_requests WHERE id = ?", (req_id,))
    row = cursor.fetchone()
    if not row: return await message.answer("❌ Заявка не найдена.")

    target_uid = row[0]
    cursor.execute("DELETE FROM tex_requests WHERE id = ?", (req_id,))
    conn.commit()

    await message.answer(f"❌ Заявка #{req_id} отклонена.")
    try:
        await bot.send_message(target_uid, "❌ Ваша заявка на Техника отклонена.", parse_mode="HTML")
    except Exception:
        pass

# Управление ГА (/Setga /Unsetga)
@dp.message(Command("Setga"))
async def cmd_setga(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8: return await message.answer("❌ Доступно с 8+ ранга.")
    if not command.args: return await message.answer("⚠️ Укажите @username или ID.")
    target_raw = command.args.split()[0]
    
    target_uid = int(target_raw) if target_raw.isdigit() else (get_user(username=clean_username(target_raw)) or [0])[0]
    if not target_uid: return await message.answer("❌ Пользователь не найден.")

    set_role(target_uid, "Главный Администратор (ГА)", new_rank=6)
    await message.answer(f"✅ Права Главного Администратора (ГА, 6 уровень) успешно выданы пользователю (ID: <code>{target_uid}</code>)!", parse_mode="HTML")

@dp.message(Command("Unsetga"))
async def cmd_unsetga(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8: return await message.answer("❌ Доступно с 8+ ранга.")
    if not command.args: return await message.answer("⚠️ Укажите @username или ID.")
    target_raw = command.args.split()[0]
    
    target_uid = int(target_raw) if target_raw.isdigit() else (get_user(username=clean_username(target_raw)) or [0])[0]
    if not target_uid: return await message.answer("❌ Пользователь не найден.")

    set_role(target_uid, "User", new_rank=0)
    await message.answer(f"📉 Права ГА сняты с пользователя (ID: <code>{target_uid}</code>).", parse_mode="HTML")

@dp.message(Command("setaccess"))
async def cmd_setaccess(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8: return await message.answer("❌ С 8+ ранга.")
    if not command.args: return await message.answer("⚠️ Укажите @username или ID.")
    target_un = clean_username(command.args.split()[0])
    set_role(target_un, "Главный Администратор (ГА)")
    t_user = get_user(username=target_un)
    if t_user: update_user(t_user[0], rank=6)
    await message.answer(f"✅ Права ГА (6 лвл) выданы: @{target_un}")

@dp.message(Command("unsetaccess"))
async def cmd_unsetaccess(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8: return await message.answer("❌ С 8+ ранга.")
    if not command.args: return await message.answer("⚠️ Укажите @username или ID.")
    target_un = clean_username(command.args.split()[0])
    set_role(target_un, "User")
    t_user = get_user(username=target_un)
    if t_user: update_user(t_user[0], rank=0)
    await message.answer(f"📉 Права сняты с: @{target_un}")

@dp.message(Command("setadmin"))
async def cmd_setadmin(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 9: return await message.answer("❌ С 9+ ранга.")
    if not command.args: return await message.answer("⚠️ Укажите @username или ID.")
    target_raw = command.args.split()[0]
    target_user = get_user(user_id=int(target_raw)) if target_raw.isdigit() else get_user(username=clean_username(target_raw))
    if not target_user: return await message.answer("❌ Игрок не найден.")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1. ГСЗТХ", callback_data=f"setadm_1_{target_user[0]}")],
        [InlineKeyboardButton(text="2. ЗГСЗТХ", callback_data=f"setadm_2_{target_user[0]}")],
        [InlineKeyboardButton(text="3. ГСЗГА", callback_data=f"setadm_3_{target_user[0]}")],
        [InlineKeyboardButton(text="4. ЗГСЗГА", callback_data=f"setadm_4_{target_user[0]}")],
        [InlineKeyboardButton(text="5. ГСЗР", callback_data=f"setadm_5_{target_user[0]}")],
        [InlineKeyboardButton(text="6. ЗГСЗР", callback_data=f"setadm_6_{target_user[0]}")]
    ])
    await message.answer(f"🛡️ Выберите роль для 8 ранга (@{target_user[1] or target_user[0]}):", reply_markup=kb)

@dp.callback_query(F.data.startswith("setadm_"))
async def process_setadmin_callback(callback: CallbackQuery):
    _, role_idx, uid_str = callback.data.split("_")
    target_uid = int(uid_str)
    roles_dict = {"1": "ГСЗТХ", "2": "ЗГСЗТХ", "3": "ГСЗГА", "4": "ЗГСЗГА", "5": "ГСЗР", "6": "ЗГСЗР"}
    role_name = roles_dict.get(role_idx, "Администратор")
    update_user(target_uid, rank=8, role=role_name)
    await callback.message.edit_text(f"✅ Выдан 8 ранг с ролью: <b>{role_name}</b>!", parse_mode="HTML")

@dp.message(Command("setzam"))
async def cmd_setzam(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if message.from_user.id not in ADMIN_IDS and user[3] < 10: return await message.answer("❌ Доступно только Владельцу (10 ранг).")
    if not command.args or len(command.args.split()) < 2: return await message.answer("⚠️ Использование: <code>/setzam [ОЗГР/ЗГР] [@user]</code>", parse_mode="HTML")
    role_choice, target_raw = command.args.split()[:2]
    role_choice = role_choice.upper()
    if role_choice not in ["ОЗГР", "ЗГР"]: return await message.answer("⚠️ Выберите: ОЗГР или ЗГР")
    target_user = get_user(user_id=int(target_raw)) if target_raw.isdigit() else get_user(username=clean_username(target_raw))
    if not target_user: return await message.answer("❌ Игрок не найден.")
    full_role = "Основной Заместитель Главного Руководителя (ОЗГР)" if role_choice == "ОЗГР" else "Заместитель Главного Руководителя (ЗГР)"
    update_user(target_user[0], rank=9, role=full_role)
    await message.answer(f"👑 Назначен 9 ранг ({full_role})!", parse_mode="HTML")

# Промокоды с проверкой на 72 часа
@dp.message(Command("promo"))
async def cmd_promo(message: Message, command: CommandObject):
    if not command.args:
        return await message.answer("⚠️ Введите промокод: <code>/promo КОД</code>", parse_mode="HTML")

    code = command.args.strip().upper()
    uid = message.from_user.id

    cursor.execute("SELECT coins, activations_left, created_at FROM promocodes WHERE code = ?", (code,))
    row = cursor.fetchone()

    if not row:
        return await message.answer("❌ Промокод не найден или не существует.")

    coins, activations, created_at_str = row
    
    try:
        created_at = datetime.strptime(created_at_str, "%Y-%m-%d %H:%M:%S")
        if datetime.now() - created_at > timedelta(hours=72):
            return await message.answer("❌ Срок действия этого промокода истёк (прошло более 72 часов).")
    except Exception:
        pass

    if activations <= 0:
        return await message.answer("❌ У этого промокода закончились активации.")

    cursor.execute("SELECT 1 FROM used_promos WHERE user_id = ? AND code = ?", (uid, code))
    if cursor.fetchone():
        return await message.answer("❌ Вы уже активировали этот промокод!")

    user = get_user(user_id=uid)
    update_user(uid, coins=user[5] + coins)
    cursor.execute("UPDATE promocodes SET activations_left = activations_left - 1 WHERE code = ?", (code,))
    cursor.execute("INSERT INTO used_promos (user_id, code) VALUES (?, ?)", (uid, code))
    conn.commit()

    await message.answer(f"🎉 Промокод успешно активирован! Вам начислено <b>{coins} монет</b> 💰", parse_mode="HTML")

# ==========================================
# 9. ОБЖАЛОВАНИЯ /GB И /GW
# ==========================================

@dp.message(Command("GB"))
async def cmd_gb_review(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 9: return await message.answer("❌ С 9+ ранга.")
    if not command.args or not command.args.isdigit(): return await message.answer("⚠️ Укажите номер из /gblist: <code>/GB 1</code>", parse_mode="HTML")
    req_id = int(command.args)
    cursor.execute("SELECT id, user_id, username, reason FROM obgban_requests WHERE id = ?", (req_id,))
    row = cursor.fetchone()
    if not row: return await message.answer("❌ Заявка не найдена.")
    _, target_uid, target_un, req_reason = row
    cursor.execute("SELECT reason FROM global_bans WHERE user_id = ?", (target_uid,))
    ban_row = cursor.fetchone()
    ban_reason = ban_row[0] if ban_row else "Не указана"

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Снять", callback_data=f"gb_unban_{req_id}_{target_uid}"),
        InlineKeyboardButton(text="❌ Оставить", callback_data=f"gb_keep_{req_id}_{target_uid}")
    ]])
    await message.answer(f"🌐 <b>Обжалование GBAN #{req_id}</b>\nИгрок: @{target_un}\nПричина бана: {ban_reason}\nТекст: {req_reason}", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data.startswith("gb_unban_"))
async def cb_gb_unban(callback: CallbackQuery):
    _, _, req_id_str, uid_str = callback.data.split("_")
    target_uid, req_id = int(uid_str), int(req_id_str)
    cursor.execute("DELETE FROM global_bans WHERE user_id = ?", (target_uid,))
    cursor.execute("DELETE FROM obgban_requests WHERE id = ?", (req_id,))
    conn.commit()
    await callback.message.edit_text("✅ GBAN снят!")
    try: await bot.send_message(target_uid, "🎉 Ваше обжалование GBAN одобрено!", parse_mode="HTML")
    except Exception: pass

@dp.callback_query(F.data.startswith("gb_keep_"))
async def cb_gb_keep(callback: CallbackQuery, state: FSMContext):
    _, _, req_id_str, uid_str = callback.data.split("_")
    await state.update_data(req_id=int(req_id_str), target_uid=int(uid_str))
    await state.set_state(AdminRejectOrder.waiting_for_reason)
    await callback.message.edit_text("✍️ Напишите причину отклонения обжалования:")

@dp.message(AdminRejectOrder.waiting_for_reason)
async def process_gb_reject(message: Message, state: FSMContext):
    data = await state.get_data()
    req_id, target_uid, reason = data.get("req_id"), data.get("target_uid"), message.text
    cursor.execute("DELETE FROM obgban_requests WHERE id = ?", (req_id,))
    conn.commit()
    await state.clear()
    await message.answer("✅ Отклонено.")
    try: await bot.send_message(target_uid, f"❌ Обжалование отклонено.\nПричина: {reason}", parse_mode="HTML")
    except Exception: pass

@dp.message(Command("GW"))
async def cmd_gw_review(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8: return await message.answer("❌ С 8+ ранга.")
    if not command.args or not command.args.isdigit(): return await message.answer("⚠️ Укажите номер: <code>/GW 1</code>", parse_mode="HTML")
    req_id = int(command.args)
    cursor.execute("SELECT id, user_id, username, reason FROM obgwarn_requests WHERE id = ?", (req_id,))
    row = cursor.fetchone()
    if not row: return await message.answer("❌ Заявка не найдена.")
    _, target_uid, target_un, req_reason = row
    cursor.execute("SELECT reason FROM global_warns WHERE user_id = ?", (target_uid,))
    warn_row = cursor.fetchone()
    warn_reason = warn_row[0] if warn_row else "Не указана"

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Снять варн", callback_data=f"gw_unwarn_{req_id}_{target_uid}"),
        InlineKeyboardButton(text="❌ Оставить", callback_data=f"gw_keep_{req_id}_{target_uid}")
    ]])
    await message.answer(f"🌐 <b>Обжалование GWARN #{req_id}</b>\nИгрок: @{target_un}\nПричина: {warn_reason}\nТекст: {req_reason}", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data.startswith("gw_unwarn_"))
async def cb_gw_unwarn(callback: CallbackQuery):
    _, _, req_id_str, uid_str = callback.data.split("_")
    target_uid, req_id = int(uid_str), int(req_id_str)
    cursor.execute("DELETE FROM global_warns WHERE id IN (SELECT id FROM global_warns WHERE user_id = ? ORDER BY id DESC LIMIT 1)", (target_uid,))
    cursor.execute("DELETE FROM obgwarn_requests WHERE id = ?", (req_id,))
    conn.commit()
    await callback.message.edit_text("✅ GWARN снят!")
    try: await bot.send_message(target_uid, "🎉 Обжалование GWARN одобрено!", parse_mode="HTML")
    except Exception: pass

@dp.callback_query(F.data.startswith("gw_keep_"))
async def cb_gw_keep(callback: CallbackQuery):
    _, _, req_id_str, _ = callback.data.split("_")
    cursor.execute("DELETE FROM obgwarn_requests WHERE id = ?", (int(req_id_str),))
    conn.commit()
    await callback.message.edit_text("❌ Обжалование отклонено.")

@dp.message(Command("gblist"))
async def cmd_gblist(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 9: return await message.answer("❌ С 9+ ранга.")
    cursor.execute("SELECT user_id, reason FROM global_bans")
    rows = cursor.fetchall()
    if not rows: return await message.answer("🌐 Список GBAN пуст.")
    text = "🚨 <b>Список GBAN:</b>\n\n"
    for r in rows: text += f"• ID: <code>{r[0]}</code> | Причина: {r[1]}\n"
    await message.answer(text, parse_mode="HTML")

# ==========================================
# 10. ЗАПУСК БОТА
# ==========================================
async def main():
    logging.info("Starting Stars Manager Bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped!")
