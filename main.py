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

# Инициализация SQLite DB
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
        role TEXT DEFAULT 'User'
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

    conn.commit()

init_db()

# ==========================================
# 2. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ БАЗЫ ДАННЫХ
# ==========================================

def get_user(user_id: int = None, username: str = ""):
    """Получение юзера по ID или по Username"""
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

class BlagoState(StatesGroup):
    waiting_for_uah_amount = State()
    waiting_for_stars_amount = State()

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
# 5. ОСНОВНЫЕ КОМАНДЫ (С ВАЛИДАЦИЕЙ USERNAME)
# ==========================================

@dp.message(Command("start"))
async def cmd_start(message: Message):
    username = message.from_user.username
    
    if not username:
        await message.answer("⚠️ У вас не установлен **Username** в Настройках Telegram! Установите его, чтобы пользоваться ботом.", parse_mode="Markdown")
        return

    user = get_user(user_id=message.from_user.id, username=username)
    await message.answer(f"Привет снова, **@{clean_username(username)}**! Ваш баланс: {user[5]} монет.", parse_mode="Markdown")

@dp.message(Command("profile"))
async def cmd_profile(message: Message):
    args = message.text.split()
    
    if len(args) > 1:
        target_username = args[1]
        user = get_user(username=target_username)
    else:
        user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")

    if user:
        u_id, u_name, _, rank, _, coins, exp, level, rep, _, _, _, _, vip_until, msg_cnt, duel_wins, nickname, _, _, _, role = user
        await message.answer(
            f"👤 **Профиль:** @{u_name or 'без_юзернейма'}\n"
            f"🏷 **Локальная роль:** {role}\n"
            f"🎭 **Админ-ранг:** {rank}\n"
            f"💰 **Баланс:** {coins} монет\n"
            f"⚡ **Уровень:** {level} ({exp} EXP)\n"
            f"⭐ **Репутация:** {rep}\n"
            f"👑 **VIP:** {'Да' if is_vip(user) else 'Нет'}",
            parse_mode="Markdown"
        )
    else:
        target_name = args[1].replace('@', '') if len(args) > 1 else message.from_user.username
        await message.answer(f"❌ Пользователь @{target_name} не найден в базе.")

@dp.message(Command("setadmin"))
async def cmd_setadmin(message: Message):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 10 and message.from_user.id != OWNER_ID:
        await message.answer("❌ У вас нет прав на эту команду.")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("⚠️ Использование: `/setadmin @username`", parse_mode="Markdown")
        return

    target_username = args[1]
    success = set_role(target_username, "Admin")

    if success:
        target_user = get_user(username=target_username)
        if target_user:
            update_user(target_user[0], rank=5)
        await message.answer(f"✅ Пользователю **{target_username}** успешно выдана роль **Admin**!", parse_mode="Markdown")
    else:
        await message.answer(f"❌ Пользователь **{target_username.replace('@', '')}** не найден в базе. Пусть сначала напишет `/start` боту.", parse_mode="Markdown")

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

@dp.message(Command("help"))
async def cmd_help(message: Message):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    rank = user[3]
    
    text = (
        "📜 <b>ПОЛНЫЙ СПИСОК КОМАНД БОТА</b>\n\n"
        "<b>🌍 1. Основные & Экономика & VIP & Донаты:</b>\n"
        "• <code>/profile [@username]</code> — Просмотр профиля по юзернейму\n"
        "• <code>/id [@username]</code> — Узнать Telegram ID пользователя\n"
        "• <code>/vip</code> — Купить VIP-статус (Гривны / TG Stars)\n"
        "• <code>/buy_money</code> — Купить монеты (Гривны / TG Stars)\n"
        "• <code>/blago</code> — Поддержка команды бота (Произвольный донат)\n"
        "• <code>/Donats</code> — Ваша история покупок и донатов\n"
        "• <code>/rep [+/-]</code> — Повысить/понизить репутацию (1/день, VIP: 3/день)\n"
        "• <code>/bonus</code> — Ежедневный бонус с серией и уровнями\n"
        "• <code>/top</code> / <code>/tops</code> — Топ группы / Межгрупповой топ\n"
        "• <code>/sell_role</code> — Продать уникальную Legend роль за 50k монет\n"
        "• <code>/stats</code> — Ваша статистика профиля\n"
        "• <code>/shop</code> / <code>/eshop</code> — Магазин монеты-EXP / Эксклюзивы\n"
        "• <code>/givemevip</code> / <code>/pleasevip</code> — Тестовые VIP-запросы\n"
        "• <code>/role_info</code> / <code>/role_shop</code> / <code>/my_role</code>\n"
        "• <code>/create_role</code> / <code>/money_role</code>\n"
        "• <code>/duel [ставка]</code> — Дуэль на монеты\n"
        "• <code>/transfer [user] [кол-во]</code> — Перевод монет\n"
        "• <code>/report [текст]</code> — Жалоба администрации\n\n"
        "<b>🛡️ 2. Модерация (1-6 Ранги):</b>\n"
        "• <code>/snick</code>, <code>/rnick</code>, <code>/gnick</code> — Управление никами (2+)\n"
        "• <code>/nonick</code> — Список пользователей без кастомного ника (2+)\n"
        "• <code>/staff</code> — Модерация онлайн (1+)\n"
        "• <code>/warn</code>, <code>/mute</code>, <code>/kick</code>, <code>/ban</code> (4+)\n"
        "• <code>/skick</code> — Кик со всех групп\n"
        "• <code>/sban</code> — Бан во всех группах\n"
        "• <code>/gban</code> — Форма на глобальный бан (6+)\n"
        "• <code>/pin</code> — Закреп правил чата (6+)\n"
        "• <code>/unban</code>, <code>/unmute</code>, <code>/unwarn</code> (5-6+)\n\n"
    )
    if rank >= 3:
        text += (
            "<b>👑 3. Расширенное руководство (7-10 Ранги):</b>\n"
            "• <code>/setadmin @username</code> — Выдать роль админа по юзернейму\n"
            "• Логи: <code>/Pbook</code>, <code>/Pbooks</code>, <code>/book</code>, <code>/books</code>, <code>/book_global</code>\n"
            "• Власть: <code>/setaccess</code>, <code>/giverang</code>, <code>/ungiverang</code>, <code>/setzam</code>, <code>/unsetzam</code>\n"
            "• Высшие: <code>/repgh</code>, <code>/muterep</code>, <code>/bot_boost</code>, <code>/checkrep</code>, <code>/checkboost</code>\n"
            "• Выдача монет: <code>/give_money @username [кол-во]</code> (10 ранг)\n"
            "• Глобал: <code>/glist</code>, <code>/gwlist</code>, <code>/ungban</code>, <code>/ungwarn</code>, <code>/Global news</code>\n"
            "• Мониторинг VIP: <code>/Bvip</code> (Заявки), <code>/bookvip</code> (История покупок)\n"
            "💡 <i>Используйте <code>/help1</code> ... <code>/help10</code> для просмотра команд по рангам.</i>"
        )
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text.regexp(r"^/help([1-9]|10)$"))
async def cmd_help_ranks(message: Message):
    rank_num = int(message.text.replace("/help", ""))
    await message.answer(f"📋 <b>Команды для уровня доступа {rank_num}+:</b>\nКоманды данного ранга активны в соответствии с вашим статусом в системе.", parse_mode="HTML")

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
    
    await message.answer(f"✅ Вы изменили репутацию пользователю {message.reply_to_message.from_user.full_name} на {delta}! (Текущая: {target[8] + delta})")

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
    
    if streak < 20:
        coins_add = 100 + (streak - 1) * 25
        exp_add = 50 + (streak - 1) * 10
    else:
        coins_add = 100 + (streak - 1) * 150
        exp_add = 50 + (streak - 1) * 100
        
    coins_add = min(coins_add, 1500000)
    exp_add = min(exp_add, 500)
    
    new_coins = user[5] + coins_add
    new_exp = user[6] + exp_add
    new_level = user[7]
    
    req_exp = 100
    for lvl in range(1, new_level + 1):
        if lvl < 30: req_exp += 50
        elif lvl < 50: req_exp += 70
        else: req_exp += 150
        
    lvl_up_text = ""
    if new_exp >= req_exp:
        new_level += 1
        new_coins += 50
        lvl_up_text = f"\n🎉 <b>Поздравляем! Новый уровень: {new_level}! (+50 монет)</b>"
        
        if new_level % 10 == 0:
            reward_type = random.choice(["coins", "exp", "vip"])
            if reward_type == "coins":
                r_coins = random.randint(5000, 10000)
                new_coins += r_coins
                lvl_up_text += f"\n🎁 Награда за {new_level} лвл: +{r_coins} монет!"
            elif reward_type == "exp":
                r_exp = random.randint(100, 2000)
                new_exp += r_exp
                lvl_up_text += f"\n🎁 Награда за {new_level} лвл: +{r_exp} EXP!"
            elif reward_type == "vip":
                vip_days = random.randint(3, 14)
                v_until = (datetime.now() + timedelta(days=vip_days)).strftime("%Y-%m-%d %H:%M:%S")
                update_user(uid, vip_until=v_until)
                lvl_up_text += f"\n🎁 Награда за {new_level} лвл: VIP на {vip_days} дней!"

    update_user(uid, coins=new_coins, exp=new_exp, level=new_level, rep=user[8] + 1, streak=streak, last_bonus=today_str)
    
    await message.answer(
        f"🎁 <b>Ежедневный бонус забран!</b>\n"
        f"🔥 Серия: <b>{streak} дней</b>\n"
        f"💰 Получено: +{coins_add} монет, +{exp_add} EXP, +1 Репутация\n"
        f"{lvl_up_text}", parse_mode="HTML"
    )

@dp.message(Command("top"))
async def cmd_top(message: Message):
    cursor.execute("SELECT username, user_id, coins, level, rep, streak, msg_count, duel_wins FROM users ORDER BY coins DESC LIMIT 10")
    rows = cursor.fetchall()
    
    text = "📊 <b>ТОП-10 ИГРОКОВ ЧАТА (ПО МОНЕТАМ):</b>\n\n"
    for idx, r in enumerate(rows, 1):
        name = f"@{r[0]}" if r[0] else f"ID:{r[1]}"
        text += f"{idx}. {name} — 💰 {r[2]} | ⚡ {r[3]} лвл | ⭐ {r[4]} реп | 💬 {r[6]} сообщ.\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("tops"))
async def cmd_tops(message: Message):
    cursor.execute("SELECT user_id, username, coins FROM users ORDER BY coins DESC LIMIT 5")
    rows = cursor.fetchall()
    
    text = "🌐 <b>МЕЖГРУППОВОЙ ТОП-5 (ГЛОБАЛЬНЫЙ):</b>\n\n"
    for idx, r in enumerate(rows, 1):
        name = f"@{r[1]}" if r[1] else f"ID:{r[0]}"
        tag = " 👑 [VIP Т1]" if idx == 1 else " 🌟 [Legend]"
        text += f"{idx}. {name} — 💰 {r[2]} монет {tag}\n"
        
        if idx == 1:
            v_until = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
            update_user(r[0], vip_until=v_until)
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("sell_role"))
async def cmd_sell_role(message: Message):
    uid = message.from_user.id
    user = get_user(user_id=uid, username=message.from_user.username or "")
    update_user(uid, coins=user[5] + 50000)
    await message.answer("💰 Вы продали роль <b>Legend</b> и получили <b>50,000 монет</b>!", parse_mode="HTML")

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    u = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    text = (
        f"📊 <b>СТАТИСТИКА ПОЛЬЗОВАТЕЛЯ:</b>\n\n"
        f"👤 Имя/Ник: <b>{u[16] or message.from_user.full_name}</b> (@{u[1] or 'none'})\n"
        f"🎭 Локальная роль: <b>{u[20]}</b> | Админ-ранг: <b>{u[3]}</b>\n"
        f"💰 Монеты: <b>{u[5]}</b>\n"
        f"⚡ EXP: <b>{u[6]}</b> | Уровень: <b>{u[7]}</b>\n"
        f"⭐ Репутация: <b>{u[8]}</b>\n"
        f"🔥 Серия бонусов: <b>{u[9]} дней</b>\n"
        f"👑 VIP-статус: <b>{'Активен (' + str(u[13]) + ')' if is_vip(u) else 'Нет'}</b>\n"
        f"💬 Сообщений: <b>{u[14]}</b> | ⚔️ Побед в дуэлях: <b>{u[15]}</b>"
    )
    await message.answer(text, parse_mode="HTML")

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
    await message.answer("✨ <b>ЭКСКЛЮЗИВНЫЙ МАГАЗИН РОЛЕЙ (8+ ранги):</b>\nДля покупки уникальных глобальных ролей обратитесь к Высшей Администрации.", parse_mode="HTML")

@dp.message(Command("givemevip"))
async def cmd_givemevip(message: Message):
    uid = message.from_user.id
    cursor.execute("SELECT 1 FROM user_roles_owned WHERE user_id = ? AND role_id = -999", (uid,))
    if cursor.fetchone():
        return await message.answer("❌ Вы уже активировали разовый тестовый VIP!")
    
    v_until = (datetime.now() + timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S")
    update_user(uid, vip_until=v_until)
    cursor.execute("INSERT INTO user_roles_owned VALUES (?, -999)", (uid,))
    conn.commit()
    await message.answer("🎉 Вам бесплатно выдан <b>VIP на 48 часов</b>!", parse_mode="HTML")

@dp.message(Command("role_info"))
async def cmd_role_info(message: Message):
    await message.answer("ℹ️ <b>Что такое Роль?</b>\nРоль — это уникальная плашка-надпись в вашем <code>/stats</code>. Созданная роль продается только в этой группе!", parse_mode="HTML")

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

@dp.message(Command("my_role"))
async def cmd_my_role(message: Message):
    cursor.execute("SELECT role_id, text, monthly_income FROM custom_roles WHERE creator_id = ?", (message.from_user.id,))
    roles = cursor.fetchall()
    text = "🎨 <b>ВАШИ СОЗДАННЫЕ РОЛИ:</b>\n\n"
    for r in roles:
        text += f"ID: {r[0]} | {r[1]} | Доход за месяц: {r[2]} монет\n"
    await message.answer(text if roles else "У вас нет созданных ролей.", parse_mode="HTML")

@dp.message(Command("create_role"))
async def cmd_create_role(message: Message, command: CommandObject):
    if not command.args:
        return await message.answer("⚠️ Использование: <code>/create_role [Текст] [#HEX-код] [Цена]</code>\nПример: <code>/create_role [Босс] [#FF0000] [10000]</code>", parse_mode="HTML")
    try:
        raw = command.args
        text = raw[raw.find("[")+1:raw.find("]")]
        rest = raw[raw.find("]")+1:]
        color = rest[rest.find("[")+1:rest.find("]")]
        price = int(rest.split("[")[-1].replace("]", ""))
        
        cursor.execute("INSERT INTO custom_roles (creator_id, chat_id, text, color_code, price) VALUES (?, ?, ?, ?, ?)",
                       (message.from_user.id, message.chat.id, text, color, price))
        conn.commit()
        await message.answer(f"✅ Роль '{text}' успешно создана и добавлена в <code>/role_shop</code>!")
    except Exception:
        await message.answer("❌ Ошибка формата! Проверьте скобки и параметры.")

@dp.message(Command("money_role"))
async def cmd_money_role(message: Message):
    cursor.execute("SELECT SUM(monthly_income) FROM custom_roles WHERE creator_id = ?", (message.from_user.id,))
    inc = cursor.fetchone()[0] or 0
    if inc <= 0:
        return await message.answer("❌ На ваших ролях нет накопленных средств.")
    
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    update_user(message.from_user.id, coins=user[5] + inc)
    cursor.execute("UPDATE custom_roles SET monthly_income = 0 WHERE creator_id = ?", (message.from_user.id,))
    conn.commit()
    await message.answer(f"💰 Вы успешно сняли <b>{inc} монет</b> со своих ролей!", parse_mode="HTML")

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

@dp.message(Command("transfer"))
async def cmd_transfer(message: Message, command: CommandObject):
    if not message.reply_to_message or not command.args or not command.args.isdigit():
        return await message.answer("⚠️ Ответьте на сообщение: <code>/transfer 500</code>", parse_mode="HTML")
    
    amount = int(command.args)
    sender = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    limit = 2000 if is_vip(sender) else 500
    
    if amount > limit:
        return await message.answer(f"❌ Ваш лимит перевода: {limit} монет в день!")
    if sender[5] < amount:
        return await message.answer("❌ У вас нет столько монет!")

    target_id = message.reply_to_message.from_user.id
    target = get_user(user_id=target_id, username=message.reply_to_message.from_user.username or "")
    
    update_user(message.from_user.id, coins=sender[5] - amount)
    update_user(target_id, coins=target[5] + amount)
    await message.answer(f"💸 Успешно переведено <b>{amount} монет</b> пользователю {message.reply_to_message.from_user.full_name}!", parse_mode="HTML")

@dp.message(Command("report"))
async def cmd_report(message: Message, command: CommandObject):
    if not command.args:
        return await message.answer("⚠️ Укажите суть жалобы: <code>/report Спам в чате</code>", parse_mode="HTML")
    
    target_id = message.reply_to_message.from_user.id if message.reply_to_message else 0
    cursor.execute("INSERT INTO reports (chat_id, user_id, target_id, text) VALUES (?, ?, ?, ?)",
                   (message.chat.id, message.from_user.id, target_id, command.args))
    conn.commit()
    await message.answer("🚨 Ваша жалоба отправлена администрации!")

# ==========================================
# 7. ДОНАТЫ, ПОКУПКА МОНЕТ И БЛАГОТВОРИТЕЛЬНОСТЬ
# ==========================================

@dp.message(Command("Donats"))
async def cmd_donats(message: Message):
    uid = message.from_user.id
    
    cursor.execute("SELECT period, price, currency, date FROM vip_history WHERE user_id = ?", (uid,))
    vips = cursor.fetchall()
    
    cursor.execute("SELECT type, amount, currency, date FROM donats_history WHERE user_id = ?", (uid,))
    donats = cursor.fetchall()
    
    if not vips and not donats:
        return await message.answer("💳 <b>У вас пока нет покупок или донатов.</b>", parse_mode="HTML")

    text = "🧾 <b>ВАША ИСТОРИЯ ПОКУПОК И ДОНАТОВ:</b>\n\n"
    
    if vips:
        text += "👑 <b>VIP Подписки:</b>\n"
        for v in vips:
            text += f"• Срок: {v[0]} | Сумма: {v[1]} {v[2]} | Дата: {v[3]}\n"
        text += "\n"
        
    if donats:
        text += "💎 <b>Монеты & Донаты:</b>\n"
        for d in donats:
            text += f"• {d[0]} | {d[1]} | Валюта: {d[2]} | Дата: {d[3]}\n"

    await message.answer(text, parse_mode="HTML")

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
    
    await message.answer("❤️ <b>Спасибо за вашу поддержку!</b> Заявка на донат отправлена администраторам на подтверждение.", parse_mode="HTML")

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"❤️ <b>Новый донат проекта (/blago)!</b>\n\n"
                f"👤 Пользователь: {username} (<code>{user.id}</code>)\n"
                f"💰 Сумма: {amount} грн",
                parse_mode="HTML"
            )
        except Exception:
            pass

@dp.callback_query(F.data == "blago_stars")
async def blago_stars_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("⭐️ <b>Поддержка проекта (Telegram Stars)</b>\n\nВведите количество Stars, которое хотите пожертвовать (просто числом):", parse_mode="HTML")
    await state.set_state(BlagoState.waiting_for_stars_amount)

@dp.message(BlagoState.waiting_for_stars_amount)
async def blago_stars_process(message: Message, state: FSMContext):
    if not message.text.isdigit() or int(message.text) <= 0:
        return await message.answer("⚠️ Введите положительное число Stars.")
    
    stars_cnt = int(message.text)
    await state.clear()
    
    prices = [LabeledPrice(label="Благотворительность", amount=stars_cnt)]
    await bot.send_invoice(
        chat_id=message.chat.id,
        title="Поддержка команды бота",
        description=f"Донат на проект в размере {stars_cnt} Stars ⭐️",
        payload=f"donat_blago_{stars_cnt}",
        currency="XTR",
        prices=prices
    )

@dp.message(Command("buy_money"))
async def cmd_buy_money(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплата в ГРН", callback_data="buy_money_uah")],
        [InlineKeyboardButton(text="⭐ Оплата в TG Stars", callback_data="buy_money_stars")]
    ])
    await message.answer("💰 <b>ПОКУПКА ИГРОВЫХ МОНЕТ</b>\nВыберите способ оплаты:", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "buy_money_uah")
async def buy_money_uah_menu(callback: CallbackQuery):
    buttons = []
    for k, v in MONEY_PACKS_UAH.items():
        buttons.append([InlineKeyboardButton(text=v["text"], callback_data=f"buy_m_uah_{k}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="buy_money_back")])
    
    await callback.message.edit_text("💳 <b>Выберите пакет монет (Оплата в грн):</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

@dp.callback_query(F.data == "buy_money_stars")
async def buy_money_stars_menu(callback: CallbackQuery):
    buttons = []
    for k, v in MONEY_PACKS_STARS.items():
        buttons.append([InlineKeyboardButton(text=v["text"], callback_data=f"buy_m_stars_{k}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="buy_money_back")])
    
    await callback.message.edit_text("⭐️ <b>Выберите пакет монет (Оплата TG Stars):</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

@dp.callback_query(F.data == "buy_money_back")
async def buy_money_back(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплата в ГРН", callback_data="buy_money_uah")],
        [InlineKeyboardButton(text="⭐️ Оплата в TG Stars", callback_data="buy_money_stars")]
    ])
    await callback.message.edit_text("💰 <b>ПОКУПКА ИГРОВЫХ МОНЕТ</b>\nВыберите способ оплаты:", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data.startswith("buy_m_uah_"))
async def process_buy_m_uah(callback: CallbackQuery):
    pack_key = callback.data.split("_")[3]
    pack = MONEY_PACKS_UAH[pack_key]
    user = callback.from_user
    
    if not user.username:
        return await callback.answer("❌ У вас не установлен @username! Пожалуйста, установите username в настройках Telegram для оплаты через грн.", show_alert=True)
    
    username_tag = f"@{user.username}"
    
    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил(а)", callback_data=f"paid_m_uah_{pack_key}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="buy_money_back")]
    ])

    await callback.message.edit_text(
        f"💳 <b>Покупка монет ({pack['coins']} монет)</b>\n\n"
        f"Переведите <b>{pack['price']} грн</b> на банку:\n"
        f"🔗 Ссылка: {MONOBANK_JAR}\n\n"
        f"📌 <b>ОБЯЗАТЕЛЬНО</b> при переводе или после нажмите кнопку ниже.\n"
        f"Ваш логин: <b>{username_tag}</b>",
        reply_markup=confirm_kb,
        parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("paid_m_uah_"))
async def process_paid_m_uah(callback: CallbackQuery):
    pack_key = callback.data.split("_")[3]
    pack = MONEY_PACKS_UAH[pack_key]
    user = callback.from_user
    username_tag = f"@{user.username}" if user.username else f"ID:{user.id}"
    
    await callback.message.edit_text("⌛ <b>Ваша заявка на покупку монет отправлена администраторам!</b>\nПосле проверки монеты будут зачислены.", parse_mode="HTML")
    
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"💰 <b>Заявка на покупку монет!</b>\n\n"
                f"👤 Пользователь: {username_tag} (<code>{user.id}</code>)\n"
                f"🪙 Пакет: {pack['coins']} монет\n"
                f"💵 Сумма: {pack['price']} грн\n\n"
                f"Выдать монеты: <code>/give_money {username_tag} {pack['coins']}</code>",
                parse_mode="HTML"
            )
        except Exception:
            pass

@dp.callback_query(F.data.startswith("buy_m_stars_"))
async def process_buy_m_stars(callback: CallbackQuery):
    pack_key = callback.data.split("_")[3]
    pack = MONEY_PACKS_STARS[pack_key]

    prices = [LabeledPrice(label=f"{pack['coins']} монет", amount=pack["price"])]

    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title=f"Покупка {pack['coins']} монет",
        description=f"Зачисление {pack['coins']} монет на ваш игровой баланс.",
        payload=f"buy_coins_{pack['coins']}",
        currency="XTR",
        prices=prices
    )
    await callback.answer()

@dp.message(Command("give_money"))
async def cmd_give_money(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id)
    if user[3] < 10:
        return await message.answer("❌ Команда доступна исключительно Владельцу (10 ранг).")

    if not command.args or len(command.args.split()) < 2:
        return await message.answer("⚠️ Использование: <code>/give_money @username 1000</code>", parse_mode="HTML")

    parts = command.args.split()
    target_username = clean_username(parts[0])
    
    if not parts[1].isdigit():
        return await message.answer("⚠️ Укажите число монет цифрами.")
        
    amount = int(parts[1])

    row = get_user(username=target_username)

    if not row:
        return await message.answer(f"❌ Пользователь @{target_username} не найден в базе данных!")

    target_id = row[0]
    current_coins = row[5]
    new_coins = current_coins + amount
    update_user(target_id, coins=new_coins)

    add_donat_record(target_id, f"@{target_username}", "Покупка монет", f"+{amount} монет", "Админ Выдача")

    await message.answer(f"✅ Успешно выдано <b>{amount} монет</b> пользователю @{target_username}! (Новый баланс: {new_coins})", parse_mode="HTML")
    try:
        await bot.send_message(target_id, f"🎉 Вам зачислено <b>{amount} монет</b>! Ваш баланс: <b>{new_coins}</b>.", parse_mode="HTML")
    except Exception:
        pass

# ==========================================
# 8. ИНТЕГРИРОВАННЫЙ МАГАЗИН VIP (UAH / TG STARS)
# ==========================================

def get_vip_currency_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплата в ГРН", callback_data="buy_vip_uah")],
            [InlineKeyboardButton(text="⭐️ Оплата Звёздами TG", callback_data="buy_vip_stars")]
        ]
    )

def get_prices_keyboard(currency: str):
    prices = PRICES_UAH if currency == "uah" else PRICES_STARS
    buttons = []
    for key, data in prices.items():
        buttons.append([InlineKeyboardButton(text=data["text"], callback_data=f"select_{currency}_{key}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_currency")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@dp.message(Command("vip"))
async def cmd_vip(message: Message):
    await message.answer("✨ <b>Выберите способ оплаты VIP-статуса:</b>", reply_markup=get_vip_currency_keyboard(), parse_mode="HTML")

@dp.callback_query(F.data == "back_to_currency")
async def back_to_currency(callback: CallbackQuery):
    await callback.message.edit_text("✨ <b>Выберите способ оплаты VIP-статуса:</b>", reply_markup=get_vip_currency_keyboard(), parse_mode="HTML")

@dp.callback_query(F.data == "buy_vip_uah")
async def select_uah(callback: CallbackQuery):
    await callback.message.edit_text("💳 <b>Выберите период VIP (Оплата в грн):</b>\nПосле выбора вам будут предоставлены реквизиты для оплаты.", reply_markup=get_prices_keyboard("uah"), parse_mode="HTML")

@dp.callback_query(F.data == "buy_vip_stars")
async def select_stars(callback: CallbackQuery):
    await callback.message.edit_text("⭐️ <b>Выберите период VIP (Оплата Telegram Stars):</b>", reply_markup=get_prices_keyboard("stars"), parse_mode="HTML")

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

    # 🔗 Исправлено: выдаем ссылку на банку Monobank вместо номера карты
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
    _, _, period, price = callback.data.split("_")
    user = callback.from_user
    username = f"@{user.username}" if user.username else f"ID: {user.id}"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    cursor.execute(
        "INSERT INTO pending_vip_orders (user_id, username, period, price, currency, date) VALUES (?, ?, ?, ?, ?, ?)",
        (user.id, username, period, price, "грн", now_str)
    )
    conn.commit()
    order_id = cursor.lastrowid

    await callback.message.edit_text("⌛ <b>Ваша заявка отправлена администраторам!</b>\nОжидайте проверки и активации VIP-статуса.", parse_mode="HTML")

    admin_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"adm_confirm_{order_id}"),
                InlineKeyboardButton(text="❌ Отказать", callback_data=f"adm_refuse_{order_id}")
            ]
        ]
    )

    period_str = "Навсегда" if period == "forever" else f"{period} мес."

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

@dp.callback_query(F.data.startswith("select_stars_"))
async def process_stars_selection(callback: CallbackQuery):
    period = callback.data.split("_")[2]
    info = PRICES_STARS[period]

    title = f"VIP Подписка ({period} мес.)" if period != "forever" else "VIP Навсегда"
    description = f"Активация VIP-статуса в боте на {info['text']}"

    prices = [LabeledPrice(label="VIP", amount=info["price"])]

    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title=title,
        description=description,
        payload=f"stars_vip_{period}",
        currency="XTR",
        prices=prices
    )
    await callback.answer()

@dp.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message(F.successful_payment)
async def successful_payment_handler(message: Message):
    payment = message.successful_payment
    payload = payment.invoice_payload.split("_")
    user = message.from_user
    username = f"@{user.username}" if user.username else f"ID: {user.id}"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    if payload[0] == "stars" and payload[1] == "vip":
        period = payload[2]
        price = payment.total_amount
        period_str = "Навсегда" if period == "forever" else f"{period} мес."

        add_vip_time(user.id, period)

        cursor.execute(
            "INSERT INTO vip_history (user_id, username, price, currency, period, date) VALUES (?, ?, ?, ?, ?, ?)",
            (user.id, username, str(price), "звезд TG", period_str, now_str)
        )
        conn.commit()

        await message.answer(f"🎉 <b>Оплата прошла успешно!</b>\nВам активирован VIP-статус на: <b>{period_str}</b>.", parse_mode="HTML")

    elif payload[0] == "buy" and payload[1] == "coins":
        coins_amt = int(payload[2])
        u = get_user(user_id=user.id, username=user.username or "")
        update_user(user.id, coins=u[5] + coins_amt)
        
        add_donat_record(user.id, username, "Покупка монет", f"+{coins_amt} монет", f"{payment.total_amount} Stars")
        await message.answer(f"🎉 <b>Оплата прошла успешно!</b>\nВам начислено <b>{coins_amt} монет</b>!", parse_mode="HTML")

    elif payload[0] == "donat" and payload[1] == "blago":
        stars_amt = payload[2]
        add_donat_record(user.id, username, "Поддержка проекта (Благо)", f"{stars_amt} Stars", "Stars")
        await message.answer(f"❤️ <b>Спасибо за вашу поддержку в {stars_amt} Stars!</b>", parse_mode="HTML")

@dp.message(Command("Bvip"))
async def cmd_bvip(message: Message):
    user = get_user(user_id=message.from_user.id)
    if message.from_user.id not in ADMIN_IDS and user[3] < 8:
        return

    cursor.execute("SELECT * FROM pending_vip_orders")
    orders = cursor.fetchall()

    if not orders:
        return await message.answer("📥 <b>Активных заявок на покупку VIP нет.</b>", parse_mode="HTML")

    text = "📥 <b>Заявки на оплаченный VIP:</b>\n\n"
    for order in orders:
        p_str = "Навсегда" if order[3] == "forever" else f"{order[3]} мес."
        text += (
            f"🔹 <b>Заявка #{order[0]}</b>\n"
            f"👤 Пользователь: {order[2]} (<code>{order[1]}</code>)\n"
            f"⏱ Выбранный срок: {p_str}\n"
            f"💰 Заявленная сумма: {order[4]} {order[5]}\n"
            f"📅 Дата: {order[6]}\n\n"
        )

    await message.answer(text, parse_mode="HTML")

@dp.callback_query(F.data.startswith("adm_refuse_"))
async def admin_refuse_order(callback: CallbackQuery):
    user = get_user(user_id=callback.from_user.id)
    if callback.from_user.id not in ADMIN_IDS and user[3] < 8:
        return

    order_id = int(callback.data.split("_")[2])
    cursor.execute("SELECT user_id, username FROM pending_vip_orders WHERE order_id = ?", (order_id,))
    row = cursor.fetchone()

    if row:
        cursor.execute("DELETE FROM pending_vip_orders WHERE order_id = ?", (order_id,))
        conn.commit()
        try:
            await bot.send_message(row[0], "❌ Ваша заявка на активацию VIP была отклонена администратором.")
        except Exception:
            pass
        await callback.message.edit_text(f"❌ <b>Заявка #{order_id} ({row[1]}) была отклонена.</b>", parse_mode="HTML")
    else:
        await callback.answer("Заявка уже обработана.")

@dp.callback_query(F.data.startswith("adm_confirm_"))
async def admin_confirm_order(callback: CallbackQuery, state: FSMContext):
    user = get_user(user_id=callback.from_user.id)
    if callback.from_user.id not in ADMIN_IDS and user[3] < 8:
        return

    order_id = int(callback.data.split("_")[2])
    cursor.execute("SELECT 1 FROM pending_vip_orders WHERE order_id = ?", (order_id,))
    if not cursor.fetchone():
        return await callback.answer("Заявка не найдена или уже обработана.")

    await state.update_data(current_order_id=order_id)
    await state.set_state(AdminProcessOrder.waiting_for_details)

    await callback.message.answer(
        f"📝 <b>Подтверждение заявки #{order_id}</b>\n\n"
        f"Введите данные в формате:\n<code>СУММА,СРОК ЮЗЕРНЕЙМ</code>\n\n"
        f"📌 Пример: <code>30,1 @username</code>\n"
        f"<i>(где 30 — сумма грн, 1 — срок в месяцах (или 'навсегда'), далее юзернейм/ID)</i>",
        parse_mode="HTML"
    )
    await callback.answer()

@dp.message(AdminProcessOrder.waiting_for_details)
async def process_admin_input(message: Message, state: FSMContext):
    user = get_user(user_id=message.from_user.id)
    if message.from_user.id not in ADMIN_IDS and user[3] < 8:
        return

    data = await state.get_data()
    order_id = data.get("current_order_id")

    try:
        raw_text = message.text.strip()
        parts = raw_text.split(",")
        sum_part = parts[0].strip()

        rest = parts[1].strip().split(" ")
        term_part = rest[0].strip()
        user_part = " ".join(rest[1:]).strip()

        cursor.execute("SELECT user_id, username FROM pending_vip_orders WHERE order_id = ?", (order_id,))
        order = cursor.fetchone()

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        period_str = "Навсегда" if term_part.lower() == "навсегда" else f"{term_part} мес."

        target_uid = order[0] if order else None

        if target_uid:
            add_vip_time(target_uid, term_part)

        cursor.execute("DELETE FROM pending_vip_orders WHERE order_id = ?", (order_id,))
        cursor.execute(
            "INSERT INTO vip_history (user_id, username, price, currency, period, date) VALUES (?, ?, ?, ?, ?, ?)",
            (target_uid or 0, user_part or (order[1] if order else "Н/Д"), sum_part, "грн", period_str, now_str)
        )
        conn.commit()

        if target_uid:
            try:
                await bot.send_message(
                    target_uid,
                    f"🎉 <b>Ваша оплата подтверждена!</b>\nВам успешно зачислен VIP-статус на: <b>{period_str}</b>.",
                    parse_mode="HTML"
                )
            except Exception:
                pass

        await message.answer(
            f"✅ <b>Оплата подтверждена и внесена в реестр!</b>\n\n"
            f"🔹 Сумма: {sum_part} грн\n"
            f"🔹 Срок: {period_str}\n"
            f"🔹 Пользователь: {user_part}",
            parse_mode="HTML"
        )
        await state.clear()

    except Exception:
        await message.answer(
            "⚠️ <b>Ошибка в формате ввода!</b> Попробуйте снова.\nФормат: <code>30,1 @username</code>",
            parse_mode="HTML"
        )

@dp.message(Command("bookvip"))
async def cmd_bookvip(message: Message):
    user = get_user(user_id=message.from_user.id)
    if message.from_user.id not in ADMIN_IDS and user[3] < 8:
        return

    cursor.execute("SELECT username, period, price, currency, date FROM vip_history ORDER BY id DESC LIMIT 50")
    history = cursor.fetchall()

    if not history:
        return await message.answer("📖 <b>Книга покупок VIP пока пуста.</b>", parse_mode="HTML")

    text = "📖 <b>История покупок VIP-статусов:</b>\n\n"
    for item in history:
        text += (
            f"👤 <b>Пользователь:</b> {item[0]}\n"
            f"⏱ <b>Срок:</b> {item[1]}\n"
            f"💰 <b>Сумма:</b> {item[2]} {item[3]}\n"
            f"📅 <b>Дата:</b> {item[4]}\n"
            f"-----------------------------------\n"
        )

    if len(text) > 4000:
        for x in range(0, len(text), 4000):
            await message.answer(text[x : x + 4000], parse_mode="HTML")
    else:
        await message.answer(text, parse_mode="HTML")

# ==========================================
# 9. МОДЕРАЦИЯ И АДМИНИСТРИРОВАНИЕ
# ==========================================

@dp.message(Command("snick"))
async def cmd_snick(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 2: return await message.answer("❌ Доступно с 2 ранга.")
    if not command.args or not message.reply_to_message:
        return await message.answer("⚠️ Ответьте на сообщение: <code>/snick НовыйНик</code>", parse_mode="HTML")
    
    target_id = message.reply_to_message.from_user.id
    update_user(target_id, custom_nickname=command.args)
    await message.answer(f"✅ Пользователю установлен локальный ник: <b>{command.args}</b>", parse_mode="HTML")

@dp.message(Command("rnick"))
async def cmd_rnick(message: Message):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 2: return await message.answer("❌ Доступно с 2 ранга.")
    if not message.reply_to_message: return await message.answer("⚠️ Ответьте на сообщение!")
    
    update_user(message.reply_to_message.from_user.id, custom_nickname="")
    await message.answer("✅ Никнейм сброшен до исходного.")

@dp.message(Command("gnick"))
async def cmd_gnick(message: Message):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 2: return await message.answer("❌ Доступно с 2 ранга.")
    if not message.reply_to_message: return await message.answer("⚠️ Ответьте на сообщение!")
    
    t = get_user(user_id=message.reply_to_message.from_user.id)
    await message.answer(f"👤 Настоящий ник: @{t[1]} | Кастомный: {t[16] or 'Нет'}")

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

@dp.message(Command("mute"))
async def cmd_mute(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 4: return await message.answer("❌ Строго с 4+ ранга.")
    if not message.reply_to_message or not command.args:
        return await message.answer("⚠️ Пример: <code>/mute 10 Спам</code>", parse_mode="HTML")
    
    args = command.args.split(maxsplit=1)
    mins = int(args[0]) if args[0].isdigit() else 10
    reason = args[1] if len(args) > 1 else "Нарушение правил"
    
    until = datetime.now() + timedelta(minutes=mins)
    try:
        await bot.restrict_chat_member(message.chat.id, message.reply_to_message.from_user.id,
                                       ChatPermissions(can_send_messages=False), until_date=until)
        await message.answer(f"🔇 Выдан мут на {mins} мин. Причина: {reason}")
    except Exception as e:
        await message.answer(f"❌ Ошибка прав: {e}")

@dp.message(Command("kick"))
async def cmd_kick(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 4: return await message.answer("❌ Строго с 4+ ранга.")
    if not message.reply_to_message or not command.args:
        return await message.answer("⚠️ Причина обязательна: <code>/kick Причина</code>", parse_mode="HTML")
    
    try:
        await bot.ban_chat_member(message.chat.id, message.reply_to_message.from_user.id)
        await bot.unban_chat_member(message.chat.id, message.reply_to_message.from_user.id)
        await message.answer(f"🚪 Пользователь кикнут! Причина: {command.args}")
    except Exception as e: await message.answer(f"❌ Ошибка: {e}")

@dp.message(Command("ban"))
async def cmd_ban(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 4: return await message.answer("❌ Строго с 4+ ранга.")
    if not message.reply_to_message or not command.args:
        return await message.answer("⚠️ Причина обязательна: <code>/ban Причина</code>", parse_mode="HTML")
    
    try:
        await bot.ban_chat_member(message.chat.id, message.reply_to_message.from_user.id)
        await message.answer(f"⛔ Локальный бан выдан! Причина: {command.args}")
    except Exception as e: await message.answer(f"❌ Ошибка: {e}")

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
            await bot.ban_chat_member(c_id, target_id)
            await bot.unban_chat_member(c_id, target_id)
            success_count += 1
        except Exception:
            pass

    await message.answer(f"🚪 <b>Пользователь @{target_uname} был кикнут из {success_count} групп(ы)!</b>\nПричина: {reason}", parse_mode="HTML")

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
            await bot.ban_chat_member(c_id, target_id)
            success_count += 1
        except Exception:
            pass

    await message.answer(f"⛔ <b>Пользователь @{target_uname} заблокирован в {success_count} группах!</b>\nПричина: {reason}", parse_mode="HTML")

@dp.message(Command("gban"))
async def cmd_gban(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 6: return await message.answer("❌ Заявка доступна с 6+ ранга.")
    if not message.reply_to_message or not command.args:
        return await message.answer("⚠️ Укажите пункт/причину: <code>/gban П1</code>", parse_mode="HTML")
    
    tid = message.reply_to_message.from_user.id
    cursor.execute("INSERT OR REPLACE INTO global_bans VALUES (?, ?, ?)", (tid, command.args, message.from_user.username))
    conn.commit()
    await message.answer("🌐 <b>Заявка на GBAN одобрена и внесена в реестр!</b>", parse_mode="HTML")

@dp.message(Command("pin"))
async def cmd_pin(message: Message):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 6: return await message.answer("❌ Доступно с 6+ ранга.")
    if not message.reply_to_message: return await message.answer("⚠️ Ответьте на сообщение!")
    
    try:
        await bot.pin_chat_message(message.chat.id, message.reply_to_message.message_id)
        await message.answer("📌 Сообщение закреплено!")
    except Exception as e:
        await message.answer(f"❌ Ошибка закрепления: {e}")

@dp.message(Command("unban"))
async def cmd_unban(message: Message):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 5: return await message.answer("❌ Доступно с 5+ ранга.")
    if not message.reply_to_message: return await message.answer("⚠️ Ответьте на сообщение!")
    
    try:
        await bot.unban_chat_member(message.chat.id, message.reply_to_message.from_user.id)
        await message.answer("✅ Бан снят!")
    except Exception as e:
        await message.answer(f"❌ Ошибка снятия бана: {e}")

@dp.message(Command("unmute"))
async def cmd_unmute(message: Message):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 5: return await message.answer("❌ Доступно с 5+ ранга.")
    if not message.reply_to_message: return await message.answer("⚠️ Ответьте на сообщение!")
    
    try:
        await bot.restrict_chat_member(message.chat.id, message.reply_to_message.from_user.id,
                                       ChatPermissions(can_send_messages=True, can_send_media_messages=True))
        await message.answer("🔊 Мут снят!")
    except Exception as e:
        await message.answer(f"❌ Ошибка снятия мута: {e}")

@dp.message(Command("unwarn"))
async def cmd_unwarn(message: Message):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 5: return await message.answer("❌ Доступно с 5+ ранга.")
    if not message.reply_to_message: return await message.answer("⚠️ Ответьте на сообщение!")
    
    tid = message.reply_to_message.from_user.id
    t = get_user(user_id=tid)
    if t[19] > 0:
        update_user(tid, warns=t[19]-1)
    await message.answer("✅ Варн снят!")

# ==========================================
# 10. ЛОГИ И УПРАВЛЕНИЕ ДОСТУПОМ
# ==========================================

@dp.message(Command("Pbook"))
async def cmd_pbook(message: Message):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 5: return await message.answer("❌ Доступ с 5+ ранга.")
    cursor.execute("INSERT OR REPLACE INTO logs_access VALUES (?, 1)", (message.from_user.id,))
    conn.commit()
    await send_log_to_user(message.from_user.id, "Вам одобрен доступ к локальным логам (Pbook)!")
    await message.answer("✅ Заявка отправлена в ЛС бота!")

@dp.message(Command("Pbooks"))
async def cmd_pbooks(message: Message):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 6: return await message.answer("❌ Доступ с 6+ ранга.")
    cursor.execute("INSERT OR REPLACE INTO logs_access VALUES (?, 2)", (message.from_user.id,))
    conn.commit()
    await send_log_to_user(message.from_user.id, "Вам одобрен расширенный доступ к логам (Pbooks)!")
    await message.answer("✅ Расширенный доступ отправлен в ЛС!")

@dp.message(Command("book"))
async def cmd_book(message: Message):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 5: return await message.answer("❌ Доступ с 5+ ранга.")
    await send_log_to_user(message.from_user.id, f"Лог локальных действий группы {message.chat.id}: Действия стабильны.")
    await message.answer("📖 Логи отправлены в ЛС бота!")

@dp.message(Command("books"))
async def cmd_books(message: Message):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 6: return await message.answer("❌ Доступ с 6+ ранга.")
    await send_log_to_user(message.from_user.id, f"Расширенный лог группы {message.chat.id}: Фиксация нарушений и действий модерации активна.")
    await message.answer("📖 Расширенные логи отправлены в ЛС бота!")

@dp.message(Command("book_global"))
async def cmd_book_global(message: Message):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 7: return await message.answer("❌ Доступен с 7+ ранга.")
    await send_log_to_user(message.from_user.id, "🌐 Глобальный лог всех подключенных чатов: Система работает в штатном режиме.")
    await message.answer("🌐 Глобальный лог отправлен в ЛС бота!")

# ==========================================
# 11. УПРАВЛЕНИЕ РАНГАМИ И АДМИНИСТРИРОВАНИЕМ
# ==========================================

@dp.message(Command("setaccess"))
async def cmd_setaccess(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 7: return await message.answer("❌ Доступно с 7+ ранга.")
    if not command.args or len(command.args.split()) < 2:
        return await message.answer("⚠️ Использование: <code>/setaccess @username [ранг 1-10]</code>", parse_mode="HTML")
    
    parts = command.args.split()
    target_un = clean_username(parts[0])
    if not parts[1].isdigit(): return await message.answer("⚠️ Ранг должен быть числом!")
    new_rank = int(parts[1])
    
    if new_rank > user[3] and message.from_user.id != OWNER_ID:
        return await message.answer("❌ Нельзя выдать ранг выше своего!")
        
    t_user = get_user(username=target_un)
    if not t_user: return await message.answer("❌ Пользователь не найден!")
    
    update_user(t_user[0], rank=new_rank)
    await message.answer(f"✅ Пользователю @{target_un} установлен ранг доступа: <b>{new_rank}</b>", parse_mode="HTML")

@dp.message(Command("giverang"))
async def cmd_giverang(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 7: return await message.answer("❌ Доступно с 7+ ранга.")
    if not command.args or len(command.args.split()) < 2:
        return await message.answer("⚠️ Использование: <code>/giverang @username [1-10]</code>", parse_mode="HTML")
    
    parts = command.args.split()
    target_un = clean_username(parts[0])
    new_rank = int(parts[1]) if parts[1].isdigit() else 1
    
    t_user = get_user(username=target_un)
    if t_user:
        update_user(t_user[0], rank=new_rank)
        await message.answer(f"✅ Админ-ранг пользователя @{target_un} повышен до <b>{new_rank}</b>!", parse_mode="HTML")

@dp.message(Command("ungiverang"))
async def cmd_ungiverang(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 7: return await message.answer("❌ Доступно с 7+ ранга.")
    if not command.args: return await message.answer("⚠️ Использование: <code>/ungiverang @username</code>", parse_mode="HTML")
    
    target_un = clean_username(command.args)
    t_user = get_user(username=target_un)
    if t_user:
        update_user(t_user[0], rank=0)
        await message.answer(f"📉 Админ-ранг пользователя @{target_un} сброшен до 0.", parse_mode="HTML")

@dp.message(Command("setzam"))
async def cmd_setzam(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 8: return await message.answer("❌ Доступно с 8+ ранга.")
    if not command.args: return await message.answer("⚠️ Укажите юзернейм: <code>/setzam @username</code>", parse_mode="HTML")
    
    target_un = clean_username(command.args)
    set_role(target_un, "Заместитель")
    t_user = get_user(username=target_un)
    if t_user: update_user(t_user[0], rank=8)
    await message.answer(f"👑 Пользователь @{target_un} назначен Заместителем!", parse_mode="HTML")

@dp.message(Command("unsetzam"))
async def cmd_unsetzam(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 8: return await message.answer("❌ Доступно с 8+ ранга.")
    if not command.args: return await message.answer("⚠️ Укажите юзернейм: <code>/unsetzam @username</code>", parse_mode="HTML")
    
    target_un = clean_username(command.args)
    set_role(target_un, "User")
    t_user = get_user(username=target_un)
    if t_user: update_user(t_user[0], rank=0)
    await message.answer(f"📉 Пользователь @{target_un} снят с должности Заместителя.", parse_mode="HTML")

# ==========================================
# 12. ГЛОБАЛЬНЫЕ РЕЕСТРЫ И РАССЫЛКА
# ==========================================

@dp.message(Command("glist"))
async def cmd_glist(message: Message):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 6: return await message.answer("❌ Доступно с 6+ ранга.")
    
    cursor.execute("SELECT user_id, reason, by_user FROM global_bans")
    rows = cursor.fetchall()
    if not rows: return await message.answer("🌐 Список GBAN пуст.")
    
    text = "🌐 <b>СПИСОК ГЛОБАЛЬНЫХ БАНОВ (GBAN):</b>\n\n"
    for r in rows:
        text += f"• ID: <code>{r[0]}</code> | Причина: {r[1]} | Выдал: @{r[2]}\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("gwlist"))
async def cmd_gwlist(message: Message):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 6: return await message.answer("❌ Доступно с 6+ ранга.")
    
    cursor.execute("SELECT user_id, reason, by_user FROM global_warns")
    rows = cursor.fetchall()
    if not rows: return await message.answer("🌐 Список глобальных предупреждений пуст.")
    
    text = "🌐 <b>СПИСОК ГЛОБАЛЬНЫХ ВАРНОВ (GWARN):</b>\n\n"
    for r in rows:
        text += f"• ID: <code>{r[0]}</code> | Причина: {r[1]} | Выдал: @{r[2]}\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("ungban"))
async def cmd_ungban(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 7: return await message.answer("❌ Доступно с 7+ ранга.")
    if not command.args or not command.args.isdigit():
        return await message.answer("⚠️ Укажите ID пользователя: <code>/ungban 123456789</code>", parse_mode="HTML")
    
    tid = int(command.args)
    cursor.execute("DELETE FROM global_bans WHERE user_id = ?", (tid,))
    conn.commit()
    await message.answer(f"✅ GBAN с пользователя <code>{tid}</code> успешно снят!", parse_mode="HTML")

@dp.message(Command("ungwarn"))
async def cmd_ungwarn(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 7: return await message.answer("❌ Доступно с 7+ ранга.")
    if not command.args or not command.args.isdigit():
        return await message.answer("⚠ Укажите ID пользователя: <code>/ungwarn 123456789</code>", parse_mode="HTML")
    
    tid = int(command.args)
    cursor.execute("DELETE FROM global_warns WHERE user_id = ?", (tid,))
    conn.commit()
    await message.answer(f"✅ GWARN с пользователя <code>{tid}</code> снят!", parse_mode="HTML")

@dp.message(Command("Global_news", prefix="/"))
@dp.message(Command("global_news", prefix="/"))
async def cmd_global_news(message: Message, command: CommandObject):
    user = get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    if user[3] < 8: return await message.answer("❌ Доступно с 8+ ранга.")
    if not command.args:
        return await message.answer("⚠️ Укажите текст новости: <code>/Global news Текст новости</code>", parse_mode="HTML")
    
    cursor.execute("SELECT chat_id FROM known_chats")
    chats = cursor.fetchall()
    
    cnt = 0
    news_text = f"📢 <b>ГЛОБАЛЬНАЯ НОВОСТЬ СИСТЕМЫ:</b>\n\n{command.args}"
    for ch in chats:
        try:
            await bot.send_message(ch[0], news_text, parse_mode="HTML")
            cnt += 1
        except Exception:
            pass
            
    await message.answer(f"✅ Новость успешно отправлена в <b>{cnt}</b> подключенных чатов!", parse_mode="HTML")

# ==========================================
# 13. ЗАПУСК БОТА
# ==========================================

async def main():
    logging.info("Starting Stars Manager Bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped!")
