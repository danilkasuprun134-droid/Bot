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

ADMIN_IDS = [123456789]  # Список ID администраторов

bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

conn = sqlite3.connect("bot_database.db", check_same_thread=False)
cursor = conn.cursor()

def clean_username(username: str) -> str:
    """Чистит юзернейм от @ и приводит к нижнему регистру"""
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
        role TEXT DEFAULT 'User',
        zdkd INTEGER DEFAULT 0,
        spec_role TEXT DEFAULT ''
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
        assigned_role TEXT DEFAULT ''
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS bot_boosts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        text TEXT
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
        date TEXT,
        status TEXT DEFAULT 'pending'
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS pending_money_orders (
        order_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        pack_key TEXT,
        amount_coins INTEGER,
        price_uah INTEGER,
        date TEXT,
        status TEXT DEFAULT 'pending'
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS obgban_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        reason TEXT,
        date TEXT,
        status TEXT DEFAULT 'pending'
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS vip_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        price TEXT,
        currency TEXT,
        period TEXT,
        date TEXT,
        status TEXT DEFAULT 'approved'
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS donats_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        type TEXT,
        amount TEXT,
        currency TEXT,
        date TEXT,
        status TEXT DEFAULT 'approved'
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

def set_role(username: str, new_role: str):
    u_clean = clean_username(username)
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

def check_gwarn_count(user_id: int) -> int:
    cursor.execute("SELECT COUNT(*) FROM global_warns WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    return res[0] if res else 0

async def send_log_to_user(user_id: int, text: str):
    try:
        await bot.send_message(user_id, f"📝 <b>[ЛОГ СИСТЕМЫ]</b>\n{text}", parse_mode="HTML")
    except Exception:
        pass

def add_donat_record(user_id: int, username: str, type_str: str, amount: str, currency: str, status: str = "approved"):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute(
        "INSERT INTO donats_history (user_id, username, type, amount, currency, date, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, clean_username(username), type_str, amount, currency, now_str, status)
    )
    conn.commit()

# ==========================================
# 3. FSM СОСТОЯНИЯ И ПРАЙС-ЛИСТЫ
# ==========================================
class AdminProcessOrder(StatesGroup):
    waiting_for_details = State()

class BlagoState(StatesGroup):
    waiting_for_uah_amount = State()
    waiting_for_stars_amount = State()

class Rank8RoleSelect(StatesGroup):
    waiting_for_role = State()

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

        # Автоматический выдача 6 ранга (ГА) создателю / пригласившему бота
        user_db = get_user(user_id=user_id, username=username)
        if user_db and user_db[3] == 0:
            try:
                member = await bot.get_chat_member(event.chat.id, user_id)
                if member.status in ['creator', 'administrator']:
                    if user_db[21] == 0:  # Нет ЗДКД
                        update_user(user_id, rank=6, role="Главный Администратор (ГА)")
            except Exception:
                pass

    if user_id != OWNER_ID and check_gban(user_id):
        if event.chat.type in ['group', 'supergroup']:
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
async def cmd_start(message: Message):
    username = message.from_user.username
    if not username:
        await message.answer("⚠️ У вас не установлен Username в Настройках Telegram! Установите его, чтобы пользоваться ботом.")
        return

    user = get_user(user_id=message.from_user.id, username=username)
    await message.answer(f"Привет снова, @{clean_username(username)}! Ваш баланс: {user[5]} монет.")

@dp.message(Command("obgban"))
async def cmd_obgban(message: Message, command: CommandObject):
    if message.chat.type != "private":
        return await message.answer("⚠️ Команду <code>/obgban</code> нужно писать СТРОГО в ЛС бота!", parse_mode="HTML")

    if not command.args:
        return await message.answer(
            "📝 <b>Заявка на обжалование GBAN</b>\n\n"
            "Использование: <code>/obgban [Подробное описание причины почему нужно снять бан]</code>\n"
            "<i>Заявка рассматривается высшей администрацией (9+ ранг) раз в 7 дней.</i>",
            parse_mode="HTML"
        )

    user = message.from_user
    username = f"@{user.username}" if user.username else f"ID:{user.id}"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    cursor.execute(
        "INSERT INTO obgban_requests (user_id, username, reason, date) VALUES (?, ?, ?, ?)",
        (user.id, username, command.args, now_str)
    )
    conn.commit()

    await message.answer("✅ Ваша заявка на обжалование GBAN принята и отправлена на рассмотрение (9+ рангам)!")

@dp.message(Command("q"))
async def cmd_q(message: Message):
    if message.chat.type not in ['group', 'supergroup']:
        return await message.answer("⚠️ Команда работает только в группах!")
    try:
        await message.answer("👋 Покидаю группу по собственному желанию...")
        await bot.leave_chat(message.chat.id)
    except Exception as e:
        await message.answer(f"❌ Ошибка выходы из группы: {e}")

@dp.message(Command("nlist"))
async def cmd_nlist(message: Message):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    nick = user[16] or "Не установлен"
    await message.answer(f"🏷 Ваш локальный ник в группе: <b>{nick}</b>", parse_mode="HTML")

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    u = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    has_gban = check_gban(message.from_user.id)
    gwarns = check_gwarn_count(message.from_user.id)

    status_flags = ""
    if has_gban:
        status_flags += "\n🚨 <b>СТАТУС: Имеет активный GBAN!</b>"
    if gwarns > 0:
        status_flags += f"\n⚠️ <b>Глобальные варны (GWARN): {gwarns}/3</b>"

    text = (
        f"📊 <b>СТАТИСТИКА ПОЛЬЗОВАТЕЛЯ:</b>\n\n"
        f"👤 Имя/Ник: <b>{u[16] or message.from_user.full_name}</b> (@{u[1] or 'none'})\n"
        f"🏷 Ник в группе: <b>{u[16] or 'Не задан'}</b>\n"
        f"🎭 Локальная роль: <b>{u[20]}</b> | Спец-должность: <b>{u[22] or 'Нет'}</b>\n"
        f"🎭 Админ-ранг: <b>{u[3]}</b>\n"
        f"💰 Монеты: <b>{u[5]}</b>\n"
        f"⚡ EXP: <b>{u[6]}</b> | Уровень: <b>{u[7]}</b>\n"
        f"⭐ Репутация: <b>{u[8]}</b>\n"
        f"🔥 Серия бонусов: <b>{u[9]} дней</b>\n"
        f"👑 VIP-статус: <b>{'Активен (' + str(u[13]) + ')' if is_vip(u) else 'Нет'}</b>\n"
        f"💬 Сообщений: <b>{u[14]}</b> | ⚔️ Побед в дуэлях: <b>{u[15]}</b>"
        f"{status_flags}"
    )
    await message.answer(text, parse_mode="HTML")

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
        arg = command.args.strip()
        user_row = get_user(user_id=int(arg) if arg.isdigit() else None, username=clean_username(arg))

        if user_row:
            await message.answer(
                f"👤 <b>Пользователь:</b> @{user_row[1] or 'без_юзернейма'}\n"
                f"🆔 <b>ID:</b> <code>{user_row[0]}</code>",
                parse_mode="HTML"
            )
        else:
            await message.answer(f"❌ Пользователь <b>{arg}</b> не найден в базе данных бота.", parse_mode="HTML")
        return

    await message.answer(
        f"👤 <b>Ваш профиль:</b> @{message.from_user.username or 'без_юзернейма'}\n"
        f"🆔 <b>Ваш ID:</b> <code>{message.from_user.id}</code>",
        parse_mode="HTML"
    )

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

# ==========================================
# 6. ЭКОНОМИКА И ИГРОВЫЕ КОМАНДЫ
# ==========================================

@dp.message(Command("givevip"))
async def cmd_givevip(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 10 and message.from_user.id != OWNER_ID:
        return await message.answer("❌ Доступно строго Владельцу (10 ранг).")

    if not command.args or len(command.args.split()) < 2:
        return await message.answer("⚠️ Использование: <code>/givevip @username/user_id [кол-во дней]</code>", parse_mode="HTML")

    parts = command.args.split()
    target_arg = parts[0]
    days = parts[1]

    target_user = get_user(user_id=int(target_arg) if target_arg.isdigit() else None, username=clean_username(target_arg))
    if not target_user:
        return await message.answer("❌ Пользователь не найден!")

    if days.lower() == "forever":
        update_user(target_user[0], vip_until="forever")
        p_str = "Навсегда"
    else:
        v_until = (datetime.now() + timedelta(days=int(days))).strftime("%Y-%m-%d %H:%M:%S")
        update_user(target_user[0], vip_until=v_until)
        p_str = f"{days} дней"

    await message.answer(f"🎉 Вы успешно выдали VIP-статус пользователю ID:<code>{target_user[0]}</code> на <b>{p_str}</b>!", parse_mode="HTML")

@dp.message(Command("give_money"))
async def cmd_give_money(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 10 and message.from_user.id != OWNER_ID:
        return await message.answer("❌ Команда доступна исключительно Владельцу (10 ранг).")

    if not command.args or len(command.args.split()) < 2:
        return await message.answer("⚠️ Использование: <code>/give_money @username 10000</code>", parse_mode="HTML")

    parts = command.args.split()
    target_username = clean_username(parts[0])
    
    if not parts[1].isdigit():
        return await message.answer("⚠️ Укажите число монет цифрами.")
        
    amount = int(parts[1])
    if amount < 10000:
        return await message.answer("❌ Минимальная сумма выдачи: <b>10,000 монет</b>!", parse_mode="HTML")

    row = get_user(username=target_username)
    if not row:
        return await message.answer(f"❌ Пользователь @{target_username} не найден в базе данных!")

    target_id = row[0]
    new_coins = row[5] + amount
    update_user(target_id, coins=new_coins)

    add_donat_record(target_id, f"@{target_username}", "Выдача монет Владельцем", f"+{amount} монет", "Админ Выдача")
    await message.answer(f"✅ Успешно выдано <b>{amount} монет</b> пользователю @{target_username}! (Новый баланс: {new_coins})", parse_mode="HTML")

# ==========================================
# 7. ДОНАТЫ, ПОКУПКА МОНЕТ И ЗАЯВКИ
# ==========================================

@dp.message(Command("blago"))
async def cmd_blago(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Донат в ГРН (Банка Monobank)", callback_data="blago_uah")],
        [InlineKeyboardButton(text="⭐️ Донат в Telegram Stars", callback_data="blago_stars")]
    ])
    await message.answer("❤️ <b>Поддержка команды разработчиков бота</b>\nВыберите удобный способ оплаты:", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "blago_uah")
async def blago_uah_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        f"💳 <b>Поддержка проекта (Гривны)</b>\n\n"
        f"🔗 Ссылка на банку Monobank:\n{MONOBANK_JAR}\n\n"
        f"Введите сумму в грн, которую вы перевели (просто числом):",
        parse_mode="HTML"
    )
    await state.set_state(BlagoState.waiting_for_uah_amount)

@dp.message(BlagoState.waiting_for_uah_amount)
async def blago_uah_process(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("⚠️ Пожалуйста, введите корректное число (сумму в грн).")
    
    amount = message.text
    user = message.from_user
    username = f"@{user.username}" if user.username else f"ID: {user.id}"
    
    add_donat_record(user.id, username, "Поддержка бота (Благо)", f"{amount} грн", "грн")
    await state.clear()
    
    await message.answer("❤️ <b>Спасибо за вашу поддержку!</b> Заявка отправлена администраторам на подтверждение.\n<i>Вашу заявку рассмотрят в течение 24 часов. Хорошего дня!</i>", parse_mode="HTML")

@dp.callback_query(F.data.startswith("select_uah_"))
async def process_uah_selection(callback: CallbackQuery):
    period = callback.data.split("_")[2]
    info = PRICES_UAH[period]

    confirm_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Я оплатил(а)", callback_data=f"paid_uah_{period}_{info['price']}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="back_to_currency")]
        ]
    )

    await callback.message.edit_text(
        f"💳 <b>Оплата VIP ({info['text']})</b>\n\n"
        f"Переведите <b>{info['price']} грн</b> по ссылке на банку Monobank:\n"
        f"🔗 {MONOBANK_JAR}\n\n"
        "После перевода нажмите кнопку <b>«Я оплатил(а)»</b> ниже.",
        reply_markup=confirm_kb,
        parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("paid_uah_"))
async def process_uah_paid(callback: CallbackQuery):
    data_parts = callback.data.split("_")
    period = data_parts[2]
    price = data_parts[3]

    user = callback.from_user
    username = f"@{user.username}" if user.username else f"ID: {user.id}"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    cursor.execute(
        "INSERT INTO pending_vip_orders (user_id, username, period, price, currency, date) VALUES (?, ?, ?, ?, ?, ?)",
        (user.id, username, period, price, "грн", now_str)
    )
    conn.commit()
    order_id = cursor.lastrowid

    await callback.message.edit_text("⌛ <b>Ваша заявка отправлена администраторам!</b>\n<i>Вашу заявку рассмотрят в течение 24 часов. Хорошего дня!</i>", parse_mode="HTML")

    period_str = "Навсегда" if period == "forever" else f"{period} мес."
    admin_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"adm_confirm_{order_id}"),
                InlineKeyboardButton(text="❌ Отказать", callback_data=f"adm_refuse_{order_id}")
            ]
        ]
    )

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"📥 <b>Новая заявка на VIP (#{order_id})</b>\n\n"
                f"👤 Пользователь: {username} (<code>{user.id}</code>)\n"
                f"⏱ Срок: {period_str}\n"
                f"💰 Сумма: {price} грн",
                reply_markup=admin_kb,
                parse_mode="HTML"
            )
        except Exception:
            pass

@dp.callback_query(F.data.startswith("buy_m_uah_"))
async def process_buy_m_uah(callback: CallbackQuery):
    pack_key = callback.data.split("_")[3]
    pack = MONEY_PACKS_UAH[pack_key]
    user = callback.from_user
    username_tag = f"@{user.username}" if user.username else f"ID:{user.id}"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    cursor.execute(
        "INSERT INTO pending_money_orders (user_id, username, pack_key, amount_coins, price_uah, date) VALUES (?, ?, ?, ?, ?, ?)",
        (user.id, username_tag, pack_key, pack["coins"], pack["price"], now_str)
    )
    conn.commit()

    await callback.message.edit_text(
        f"💳 <b>Заявка на покупку монет отправлена!</b>\n"
        f"Переведите <b>{pack['price']} грн</b> на банку:\n🔗 {MONOBANK_JAR}\n\n"
        f"<i>Вашу заявку рассмотрят в течение 24 часов. Хорошего дня!</i>",
        parse_mode="HTML"
    )

@dp.message(Command("zayavka"))
async def cmd_zayavka(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8:
        return await message.answer("❌ Просмотр полного реестра заявок доступен с 8+ ранга.")

    cursor.execute("SELECT order_id, username, period, price FROM pending_vip_orders WHERE status = 'pending'")
    vips = cursor.fetchall()

    cursor.execute("SELECT order_id, username, amount_coins, price_uah FROM pending_money_orders WHERE status = 'pending'")
    money = cursor.fetchall()

    cursor.execute("SELECT id, username, reason FROM obgban_requests WHERE status = 'pending'")
    obgbans = cursor.fetchall()

    text = "📋 <b>ЕДИНЫЙ РЕЕСТР АКТИВНЫХ ЗАЯВОК:</b>\n\n"
    text += f"👑 <b>Заявки VIP (всего {len(vips)}):</b>\n"
    for v in vips:
        text += f"• #{v[0]} от {v[1]} | Срок: {v[2]} | Сумма: {v[3]} грн\n"

    text += f"\n💰 <b>Заявки Монеты (всего {len(money)}):</b>\n"
    for m in money:
        text += f"• #{m[0]} от {m[1]} | {m[2]} монет | {m[3]} грн\n"

    text += f"\n🌐 <b>Заявки на Обжалование GBAN (9+ ранг) (всего {len(obgbans)}):</b>\n"
    for o in obgbans:
        text += f"• #{o[0]} от {o[1]} | Причина: {o[2][:30]}...\n"

    await message.answer(text, parse_mode="HTML")

@dp.message(Command("Bmoney"))
async def cmd_bmoney(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8:
        return

    cursor.execute("SELECT * FROM pending_money_orders WHERE status = 'pending'")
    orders = cursor.fetchall()
    if not orders:
        return await message.answer("💰 Активных заявок на покупку монет нет.")

    text = "💰 <b>Заявки на покупку монет:</b>\n\n"
    for o in orders:
        text += f"🔹 Заявка #{o[0]} | {o[2]} | {o[4]} монет за {o[5]} грн ({o[6]})\n"

    await message.answer(text, parse_mode="HTML")

@dp.message(Command("Ovip"))
async def cmd_ovip(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8: return
    cursor.execute("SELECT username, period, price, date FROM vip_history WHERE status = 'approved'")
    rows = cursor.fetchall()
    text = "👑 <b>Список подтвержденных покупок VIP:</b>\n\n" + "\n".join([f"• {r[0]} | {r[1]} | {r[2]}грн ({r[3]})" for r in rows])
    await message.answer(text if rows else "Список пуст.", parse_mode="HTML")

@dp.message(Command("Uovip"))
async def cmd_uovip(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8: return
    cursor.execute("SELECT username, period, price, date FROM vip_history WHERE status = 'refused'")
    rows = cursor.fetchall()
    text = "❌ <b>Список отклоненных заявок VIP:</b>\n\n" + "\n".join([f"• {r[0]} | {r[1]} | {r[2]}грн ({r[3]})" for r in rows])
    await message.answer(text if rows else "Список пуст.", parse_mode="HTML")

@dp.message(Command("Omoney"))
async def cmd_omoney(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8: return
    cursor.execute("SELECT username, amount, date FROM donats_history WHERE type = 'Покупка монет' AND status = 'approved'")
    rows = cursor.fetchall()
    text = "💰 <b>Список подтвержденных покупок монет:</b>\n\n" + "\n".join([f"• {r[0]} | {r[1]} ({r[2]})" for r in rows])
    await message.answer(text if rows else "Список пуст.", parse_mode="HTML")

@dp.message(Command("Onmoney"))
async def cmd_onmoney(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8: return
    cursor.execute("SELECT username, amount, date FROM donats_history WHERE type = 'Покупка монет' AND status = 'refused'")
    rows = cursor.fetchall()
    text = "❌ <b>Список отклоненных покупок монет:</b>\n\n" + "\n".join([f"• {r[0]} | {r[1]} ({r[2]})" for r in rows])
    await message.answer(text if rows else "Список пуст.", parse_mode="HTML")

# ==========================================
# 8. ИЕРАРХИЯ, СНЕК, НАЗНАЧЕНИЯ И НАКАЗАНИЯ
# ==========================================

@dp.message(Command("setzam"))
async def cmd_setzam(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 10 and message.from_user.id != OWNER_ID:
        return await message.answer("❌ Доступно исключительно Главного Руководителю (10 ранг).")

    if not command.args:
        return await message.answer("⚠️ Использование: <code>/setzam @username/user_id</code>", parse_mode="HTML")

    target_arg = command.args.strip()
    target_user = get_user(user_id=int(target_arg) if target_arg.isdigit() else None, username=clean_username(target_arg))

    if not target_user:
        return await message.answer("❌ Пользователь не найден!")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1️⃣ Первый Заместитель (ОЗГР)", callback_data=f"zam_pos_1_{target_user[0]}")],
        [InlineKeyboardButton(text="2️⃣ Второй Заместитель (ЗГР)", callback_data=f"zam_pos_2_{target_user[0]}")]
    ])

    await message.answer(f"👑 Выберите должность Заместителя для @{target_user[1] or target_user[0]}:", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data.startswith("zam_pos_"))
async def process_zam_assignment(callback: CallbackQuery):
    parts = callback.data.split("_")
    pos_type = parts[2]
    target_uid = int(parts[3])

    pos_title = "Первый Заместитель (ОЗГР)" if pos_type == "1" else "Второй Заместитель (ЗГР)"
    update_user(target_uid, rank=9, role=pos_title)

    target_user = get_user(user_id=target_uid)
    uname = f"@{target_user[1]}" if target_user[1] else f"ID:{target_uid}"

    congrat_text = (
        f"🎉 <b>НОВОЕ НАЗНАЧЕНИЕ В РУКОВОДСТВЕ!</b>\n\n"
        f"На должность <b>{pos_title}</b> становится {uname}!\n"
        f"Пожелаем удачи и больше достижений в будущем! Грац! 👏"
    )

    cursor.execute("SELECT chat_id FROM known_chats")
    chats = cursor.fetchall()
    for ch in chats:
        try:
            await bot.send_message(ch[0], congrat_text, parse_mode="HTML")
        except Exception:
            pass

    await callback.message.edit_text(f"✅ Пользователь {uname} успешно назначен на должность <b>{pos_title}</b> (9 ранг)!", parse_mode="HTML")

@dp.message(Command("setaccess"))
@dp.message(Command("giverang"))
async def cmd_giverang(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 7:
        return await message.answer("❌ Доступно с 7+ ранга.")

    if not command.args or len(command.args.split()) < 2:
        return await message.answer("⚠️ Использование: <code>/giverang @username [1-10]</code>", parse_mode="HTML")

    parts = command.args.split()
    target_un = clean_username(parts[0])
    new_rank = int(parts[1]) if parts[1].isdigit() else 1

    t_user = get_user(username=target_un)
    if not t_user:
        return await message.answer("❌ Пользователь не найден!")

    if new_rank == 8:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="ГСЗТС", callback_data=f"r8_1_{t_user[0]}"), InlineKeyboardButton(text="ЗГСЗТС", callback_data=f"r8_2_{t_user[0]}")],
            [InlineKeyboardButton(text="ГСЗГА", callback_data=f"r8_3_{t_user[0]}"), InlineKeyboardButton(text="ЗГСЗГА", callback_data=f"r8_4_{t_user[0]}")],
            [InlineKeyboardButton(text="ГСЗР", callback_data=f"r8_5_{t_user[0]}"), InlineKeyboardButton(text="ЗГСЗР", callback_data=f"r8_6_{t_user[0]}")]
        ])
        return await message.answer(f"🎭 Выберите обязательную роль 8 ранга для @{target_un}:", reply_markup=kb)

    update_user(t_user[0], rank=new_rank)
    await message.answer(f"✅ Админ-ранг пользователя @{target_un} обновлен до <b>{new_rank}</b>!", parse_mode="HTML")

@dp.callback_query(F.data.startswith("r8_"))
async def process_r8_role_select(callback: CallbackQuery):
    _, role_idx, target_uid = callback.data.split("_")
    roles_map = {
        "1": "ГСЗТС (Главный следящий за Тех. специалистами)",
        "2": "ЗГСЗТС (Зам. Главного следящего за Тех. специалистами)",
        "3": "ГСЗГА (Главный следящий за Главными администраторами)",
        "4": "ЗГСЗГА (Зам. Главного следящего за Главными администраторами)",
        "5": "ГСЗР (Главный следящий за Репортами)",
        "6": "ЗГСЗР (Зам. Главного следящего за Репортами)"
    }
    spec = roles_map.get(role_idx, "Спец-Администратор")
    update_user(int(target_uid), rank=8, role="Спец-Администратор", spec_role=spec)

    try:
        await bot.send_message(
            int(target_uid),
            f"🎉 <b>Поздравляем! Вы назначены на 8 ранг с ролью: {spec}</b>\n\n"
            f"📌 <i>Примечание: Чтобы подняться с ЗГС до ГС, необходимо отстоять минимум 15 дней. Руководство может отказать в повышении без объяснения причин.</i>",
            parse_mode="HTML"
        )
    except Exception:
        pass

    await callback.message.edit_text(f"✅ Пользователю успешно выдан 8 ранг и спец-роль: <b>{spec}</b>!", parse_mode="HTML")

@dp.message(Command("snick"))
async def cmd_snick(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 2: return await message.answer("❌ Доступно с 2+ ранга.")

    if not command.args:
        return await message.answer("⚠️ Использование: ответом на сообщение или <code>/snick @username НовыйНик</code>", parse_mode="HTML")

    if message.reply_to_message:
        target_id = message.reply_to_message.from_user.id
        new_nick = command.args.strip()
    else:
        parts = command.args.split(maxsplit=1)
        if len(parts) < 2:
            return await message.answer("⚠️ Использование: <code>/snick @username НовыйНик</code>", parse_mode="HTML")
        target_u = get_user(username=clean_username(parts[0]))
        if not target_u: return await message.answer("❌ Пользователь не найден!")
        target_id = target_u[0]
        new_nick = parts[1].strip()

    update_user(target_id, custom_nickname=new_nick)
    await message.answer(f"✅ Пользователю успешно установлен локальный ник: <b>{new_nick}</b>", parse_mode="HTML")

@dp.message(Command("zdkd"))
async def cmd_zdkd(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 9:
        return await message.answer("❌ Доступно высшему руководству (9+ ранг).")

    if not command.args:
        return await message.answer("⚠️ Использование: <code>/zdkd @username/user_id Причина</code>", parse_mode="HTML")

    parts = command.args.split(maxsplit=1)
    target_arg = parts[0]
    reason = parts[1] if len(parts) > 1 else "Нарушение регламента"

    target_user = get_user(user_id=int(target_arg) if target_arg.isdigit() else None, username=clean_username(target_arg))
    if not target_user:
        return await message.answer("❌ Пользователь не найден!")

    update_user(target_user[0], zdkd=1, rank=0, role="User")
    await message.answer(f"⛔ Пользователю ID:<code>{target_user[0]}</code> выдан **ЗДКД** (Закрыт Доступ к Должностям)!\nПричина: {reason}", parse_mode="HTML")

@dp.message(Command("setga"))
async def cmd_setga(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8: return await message.answer("❌ Доступно с 8+ ранга.")
    if not command.args: return await message.answer("⚠️ Использование: <code>/setga @username/id_user Причина</code>", parse_mode="HTML")

    parts = command.args.split(maxsplit=1)
    target_u = get_user(user_id=int(parts[0]) if parts[0].isdigit() else None, username=clean_username(parts[0]))
    if not target_u: return await message.answer("❌ Пользователь не найден!")
    if target_u[21] == 1: return await message.answer("❌ У данного пользователя активен ЗДКД!")

    update_user(target_u[0], rank=6, role="Главный Администратор (ГА)")
    await message.answer(f"👑 Пользователь ID:<code>{target_u[0]}</code> назначен ГА (6 ранг)!", parse_mode="HTML")

@dp.message(Command("unsetga"))
async def cmd_unsetga(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8: return await message.answer("❌ Доступно с 8+ ранга.")
    if not command.args: return await message.answer("⚠️ Использование: <code>/unsetga @username/id_user Причина</code>", parse_mode="HTML")

    parts = command.args.split(maxsplit=1)
    target_u = get_user(user_id=int(parts[0]) if parts[0].isdigit() else None, username=clean_username(parts[0]))
    if target_u: update_user(target_u[0], rank=0, role="User")
    await message.answer(f"📉 Пользователь снят с должности ГА.", parse_mode="HTML")

@dp.message(Command("settex"))
async def cmd_settex(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8: return await message.answer("❌ Назначение ТС утверждается строго 8+ рангами.")
    if not command.args: return await message.answer("⚠️ Использование: <code>/settex @username/id_user Причина</code>", parse_mode="HTML")

    parts = command.args.split(maxsplit=1)
    target_u = get_user(user_id=int(parts[0]) if parts[0].isdigit() else None, username=clean_username(parts[0]))
    if not target_u: return await message.answer("❌ Пользователь не найден!")

    update_user(target_u[0], rank=7, role="Технический специалист (ТС)")
    await message.answer(f"🛠 Пользователь ID:<code>{target_u[0]}</code> успешно назначен Тех. Специалистом (7 ранг)!", parse_mode="HTML")

@dp.message(Command("unsettex"))
async def cmd_unsettex(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8: return await message.answer("❌ Доступно с 8+ ранга.")
    if not command.args: return await message.answer("⚠️ Использование: <code>/unsettex @username/id_user Причина</code>", parse_mode="HTML")

    parts = command.args.split(maxsplit=1)
    target_u = get_user(user_id=int(parts[0]) if parts[0].isdigit() else None, username=clean_username(parts[0]))
    if target_u: update_user(target_u[0], rank=0, role="User")
    await message.answer(f"📉 Технический специалист снят с должности.", parse_mode="HTML")

@dp.message(Command("gban"))
async def cmd_gban(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 6: return await message.answer("❌ Форму на GBAN могут подавать модераторы с 6+ ранга.")
    if not command.args: return await message.answer("⚠️ Использование: <code>/gban @username/user_id Причина</code>", parse_mode="HTML")

    parts = command.args.split(maxsplit=1)
    target_arg = parts[0]
    reason = parts[1] if len(parts) > 1 else "Нарушение правил бота"

    target_u = get_user(user_id=int(target_arg) if target_arg.isdigit() else None, username=clean_username(target_arg))
    if not target_u: return await message.answer("❌ Пользователь не найден!")

    if user[3] >= 9:
        cursor.execute("INSERT OR REPLACE INTO global_bans VALUES (?, ?, ?)", (target_u[0], reason, message.from_user.username))
        conn.commit()
        await message.answer(f"🌐 <b>Глобальный бан (GBAN) официально задействован!</b>\nПользователь ID:<code>{target_u[0]}</code>", parse_mode="HTML")
    else:
        await message.answer(f"📥 <b>Форма на GBAN для ID:<code>{target_u[0]}</code> отправлена на утверждение 9+ рангам!</b>\n<i>Напоминание: ГА обязан хранить доказательства 7 дней.</i>", parse_mode="HTML")

@dp.message(Command("gwarn"))
async def cmd_gwarn(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 6: return await message.answer("❌ Подавать форму на GWARN можно с 6+ ранга.")
    if not command.args: return await message.answer("⚠️ Использование: <code>/gwarn @username/user_id Причина</code>", parse_mode="HTML")

    parts = command.args.split(maxsplit=1)
    target_arg = parts[0]
    reason = parts[1] if len(parts) > 1 else "Нарушение правил бота (НПБ)"

    target_u = get_user(user_id=int(target_arg) if target_arg.isdigit() else None, username=clean_username(target_arg))
    if not target_u: return await message.answer("❌ Пользователь не найден!")

    if user[3] >= 8:
        cursor.execute("INSERT INTO global_warns (user_id, reason, by_user) VALUES (?, ?, ?)", (target_u[0], reason, message.from_user.username))
        conn.commit()

        cnt = check_gwarn_count(target_u[0])
        if cnt >= 3:
            cursor.execute("INSERT OR REPLACE INTO global_bans VALUES (?, ?, ?)", (target_u[0], "Автоматически: 3/3 GWARN", "Система"))
            cursor.execute("DELETE FROM global_warns WHERE user_id = ?", (target_u[0],))
            conn.commit()
            await message.answer(f"💥 Пользователь ID:<code>{target_u[0]}</code> получил 3/3 GWARN и автоматически забанен в GBAN!", parse_mode="HTML")
        else:
            await message.answer(f"⚠️ Выдан глобальный варн (GWARN {cnt}/3) для ID:<code>{target_u[0]}</code>!", parse_mode="HTML")
    else:
        await message.answer(f"📥 <b>Форма на GWARN отправлена на утверждение 8+ рангам!</b>", parse_mode="HTML")

@dp.message(Command("chechrep"))
async def cmd_chechrep(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8: return

    cursor.execute("SELECT id, chat_id, user_id, text, assigned_role FROM reports WHERE status = 'pending'")
    reps = cursor.fetchall()
    if not reps:
        return await message.answer("📑 Список активных репортов пуст.")

    text = "📑 <b>АКТИВНЫЕ РЕПОРТЫ СИСТЕМЫ:</b>\n\n"
    for r in reps:
        text += f"• Репорт #{r[0]} | От: ID:<code>{r[2]}</code> | Суть: {r[3]} | Передан: {r[4] or 'Всем'}\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("ghrep"))
async def cmd_ghrep(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 8: return
    if not command.args or len(command.args.split()) < 2:
        return await message.answer("⚠️ Использование: <code>/ghrep [ID репорта] [Роль]</code>\nПример: <code>/ghrep 1 ГСЗТС</code>", parse_mode="HTML")

    parts = command.args.split()
    rep_id = parts[0]
    role_target = parts[1]

    cursor.execute("UPDATE reports SET assigned_role = ? WHERE id = ?", (role_target, rep_id))
    conn.commit()
    await message.answer(f"✅ Репорт #{rep_id} успешно перенаправлен роли: <b>{role_target}</b>!", parse_mode="HTML")

@dp.message(Command("Global_news", prefix="/"))
@dp.message(Command("global_news", prefix="/"))
async def cmd_global_news(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 10 and message.from_user.id != OWNER_ID:
        return await message.answer("❌ Изменение правил и глобальная рассылка доступны строго с 10 ранга.")

    if not command.args:
        return await message.answer("⚠️ Укажите текст новости/правил: <code>/Global_news Текст</code>", parse_mode="HTML")

    news_text = f"📢 <b>ГЛОБАЛЬНЫЕ ПРАВИЛА И НОВОСТИ СИСТЕМЫ:</b>\n\n{command.args}"

    cursor.execute("SELECT chat_id FROM known_chats")
    chats = cursor.fetchall()

    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()

    cnt = 0
    for ch in chats:
        try:
            await bot.send_message(ch[0], news_text, parse_mode="HTML")
            cnt += 1
        except Exception:
            pass

    for u in users:
        try:
            await bot.send_message(u[0], news_text, parse_mode="HTML")
        except Exception:
            pass

    await message.answer(f"✅ Глобальные правила успешно разосланы по <b>{cnt}</b> группам и в ЛС пользователям!", parse_mode="HTML")

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
