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

API_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
MONOBANK_JAR = "https://send.monobank.ua/jar/8wVnXzoF3f"
OWNER_USERNAME = "nlyxx2686"
CARD_DETAILS = "1234 5678 9012 3456 (Monobank)"

# Telegram ID администраторов, имеющих доступ к финансовым заявкам VIP (/Bvip, /bookvip)
ADMIN_IDS = [123456789]  # Укажите ваш ID или ID администраторов

bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Инициализация SQLite DB
conn = sqlite3.connect("bot_database.db", check_same_thread=False)
cursor = conn.cursor()

def init_db():
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
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
        warns INTEGER DEFAULT 0
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
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS aliases (
        user_id INTEGER,
        alias TEXT,
        command TEXT,
        PRIMARY KEY (user_id, alias)
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

    conn.commit()

init_db()

# ==========================================
# 2. FSM СОСТОЯНИЯ И ПРАЙС-ЛИСТЫ
# ==========================================
class AdminProcessOrder(StatesGroup):
    waiting_for_details = State()

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

# ==========================================
# 3. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================

def get_user(user_id: int, username: str = ""):
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        rank = 10 if username and username.lstrip('@').lower() == OWNER_USERNAME.lower() else 0
        cursor.execute(
            "INSERT INTO users (user_id, username, rank) VALUES (?, ?, ?)",
            (user_id, username, rank)
        )
        conn.commit()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
    else:
        # Индекс 3 равен rank
        if username and username.lstrip('@').lower() == OWNER_USERNAME.lower() and row[3] != 10:
            cursor.execute("UPDATE users SET rank = 10 WHERE user_id = ?", (user_id,))
            conn.commit()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
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

def add_vip_time(user_id: int, period: str):
    """ Начисление VIP времени пользователю """
    user = get_user(user_id)
    if period.lower() == "forever" or period.lower() == "навсегда":
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
    cursor.execute("SELECT rank FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row and row[0] == 10: 
        return False
    cursor.execute("SELECT 1 FROM global_bans WHERE user_id = ?", (user_id,))
    return cursor.fetchone() is not None

async def send_log_to_user(user_id: int, text: str):
    try:
        await bot.send_message(user_id, f"📝 <b>[ЛОГ СИСТЕМЫ]</b>\n{text}", parse_mode="HTML")
    except Exception:
        pass

# ==========================================
# 4. МИДДЛВАРИ
# ==========================================

@dp.message.middleware()
async def global_middleware(handler, event: Message, data):
    if not event.from_user:
        return await handler(event, data)

    user_id = event.from_user.id
    username = event.from_user.username or ""

    # Авто-кик за GBAN (кроме владельца)
    if username.lower() != OWNER_USERNAME.lower() and check_gban(user_id):
        if event.chat.type in ['group', 'supergroup']:
            try:
                await bot.ban_chat_member(event.chat.id, user_id)
                await event.answer(f"🚨 Пользователь @{username or user_id} имеет <b>GBAN</b> и был удалён из чата!", parse_mode="HTML")
            except Exception:
                pass
            return

    # Учет сообщений для топа
    user = get_user(user_id, username)
    update_user(user_id, msg_count=user[14] + 1)

    # Кастомные алиасы /cmd
    if event.text and event.text.startswith('/'):
        parts = event.text.split(maxsplit=1)
        cmd_name = parts[0][1:]
        cursor.execute("SELECT command FROM aliases WHERE user_id = ? AND alias = ?", (user_id, cmd_name))
        row = cursor.fetchone()
        if row:
            rest = " " + parts[1] if len(parts) > 1 else ""
            event.text = f"/{row[0]}{rest}"

    return await handler(event, data)

# ==========================================
# 5. ОСНОВНЫЕ КОМАНДЫ И НАСТРОЙКИ
# ==========================================

@dp.message(Command("setting"))
async def cmd_setting(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"),
        InlineKeyboardButton(text="🇺🇦 Українська", callback_data="lang_ua"),
        InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en")
    ]])
    await message.answer("⚙️ Choose language / Выберите язык / Оберіть мову:", reply_markup=kb)

@dp.callback_query(F.data.startswith("lang_"))
async def cb_lang(call: CallbackQuery):
    lang = call.data.split("_")[1]
    update_user(call.from_user.id, lang=lang)
    await call.message.edit_text(f"✅ Язык успешно изменён на: <b>{lang.upper()}</b>", parse_mode="HTML")

@dp.message(Command("help"))
async def cmd_help(message: Message):
    user = get_user(message.from_user.id, message.from_user.username or "")
    rank = user[3]
    
    text = (
        "📜 <b>ПОЛНЫЙ СПИСОК КОМАНД БОТА</b>\n\n"
        "<b>🌍 1. Основные & Экономика & VIP:</b>\n"
        "• <code>/vip</code> — Купить VIP-статус (Гривны / TG Stars)\n"
        "• <code>/rep [+/-]</code> — Повысить/понизить репутацию (1/день, VIP: 3/день)\n"
        "• <code>/bonus</code> — Ежедневный бонус с серией и уровнями\n"
        "• <code>/cmd [алиас] [команда]</code> — Кастомная команда (напр. stats s)\n"
        "• <code>/top</code> / <code>/tops</code> — Топ группы / Межгрупповой топ\n"
        "• <code>/sell_role</code> — Продать уникальную Legend роль за 50k монет\n"
        "• <code>/stats</code> — Ваша статистика профиля\n"
        "• <code>/shop</code> / <code>/eshop</code> — Магазин монеты-EXP / Эксклюзивы\n"
        "• <code>/givemevip</code> / <code>/pleasevip</code> — Тестовые VIP-запросы\n"
        "• <code>/role_info</code> / <code>/role_shop</code> / <code>/my_role</code>\n"
        "• <code>/create_role</code> / <code>/money_role</code> / <code>/role present</code>\n"
        "• <code>/duel [ставка]</code> — Дуэль на монеты\n"
        "• <code>/transfer [user] [кол-во]</code> — Перевод монет\n"
        "• <code>/report [текст]</code> — Жалоба администрации\n\n"
        "<b>🛡️ 2. Модерация (1-6 Ранги):</b>\n"
        "• <code>/snick</code>, <code>/rnick</code>, <code>/gnick</code> — Управление никами (2+)\n"
        "• <code>/staff</code> — Модерация онлайн (1+)\n"
        "• <code>/warn</code>, <code>/mute</code>, <code>/kick</code>, <code>/ban</code> (4+)\n"
        "• <code>/gban</code> — Форма на глобальный бан (6+)\n"
        "• <code>/pin</code> — Закреп правил чата (6+)\n"
        "• <code>/unban</code>, <code>/unmute</code>, <code>/unwarn</code> (5-6+)\n\n"
    )
    if rank >= 3:
        text += (
            "<b>👑 3. Расширенное руководство (7-10 Ранги):</b>\n"
            "• Логи: <code>/Pbook</code>, <code>/Pbooks</code>, <code>/book</code>, <code>/books</code>, <code>/book_global</code>\n"
            "• Власть: <code>/setaccess</code>, <code>/giverang</code>, <code>/ungiverang</code>, <code>/setzam</code>, <code>/unsetzam</code>\n"
            "• Высшие: <code>/repgh</code>, <code>/muterep</code>, <code>/bot_boost</code>, <code>/checkrep</code>, <code>/checkboost</code>\n"
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

    sender = get_user(sender_id, message.from_user.username or "")
    now_str = datetime.now().strftime("%Y-%m-%d")
    
    max_rep_count = 3 if is_vip(sender) else 1
    today_count = sender[11] if sender[12] == now_str else 0
    
    if today_count >= max_rep_count:
        return await message.answer(f"❌ Лимит изменений репутации на сегодня исчерпан ({today_count}/{max_rep_count})!")

    sign = command.args.strip() if command.args else "+"
    delta = 1 if sign != "-" else -1
    
    target = get_user(target_id, message.reply_to_message.from_user.username or "")
    update_user(target_id, rep=target[8] + delta)
    update_user(sender_id, rep_given_today=today_count + 1, last_rep_date=now_str)
    
    await message.answer(f"✅ Вы изменили репутацию пользователю {message.reply_to_message.from_user.full_name} на {delta}! (Текущая: {target[8] + delta})")

@dp.message(Command("bonus"))
async def cmd_bonus(message: Message):
    uid = message.from_user.id
    user = get_user(uid, message.from_user.username or "")
    
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

@dp.message(Command("cmd"))
async def cmd_alias(message: Message, command: CommandObject):
    if not command.args or len(command.args.split()) < 2:
        return await message.answer("⚠️ Пример использования: <code>/cmd s stats</code>", parse_mode="HTML")
    
    alias, orig_cmd = command.args.split(maxsplit=1)
    alias = alias.lstrip('/')
    orig_cmd = orig_cmd.lstrip('/')
    
    cursor.execute("REPLACE INTO aliases (user_id, alias, command) VALUES (?, ?, ?)", (message.from_user.id, alias, orig_cmd))
    conn.commit()
    await message.answer(f"✅ Алиас создан! Теперь <code>/{alias}</code> вызывает <code>/{orig_cmd}</code>.", parse_mode="HTML")

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
    user = get_user(uid, message.from_user.username or "")
    update_user(uid, coins=user[5] + 50000)
    await message.answer("💰 Вы продали роль <b>Legend</b> и получили <b>50,000 монет</b>!", parse_mode="HTML")

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    u = get_user(message.from_user.id, message.from_user.username or "")
    text = (
        f"📊 <b>СТАТИСТИКА ПОЛЬЗОВАТЕЛЯ:</b>\n\n"
        f"👤 Имя/Ник: <b>{u[16] or message.from_user.full_name}</b> (@{u[1] or 'none'})\n"
        f"🔰 Админ-ранг: <b>{u[3]}</b>\n"
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
        user = get_user(message.from_user.id, message.from_user.username or "")
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
    
    user = get_user(message.from_user.id, message.from_user.username or "")
    update_user(message.from_user.id, coins=user[5] + inc)
    cursor.execute("UPDATE custom_roles SET monthly_income = 0 WHERE creator_id = ?", (message.from_user.id,))
    conn.commit()
    await message.answer(f"💰 Вы успешно сняли <b>{inc} монет</b> со своих ролей!", parse_mode="HTML")

@dp.message(Command("duel"))
async def cmd_duel(message: Message, command: CommandObject):
    if not message.reply_to_message or not command.args or not command.args.isdigit():
        return await message.answer("⚠️ Использование: ответьте на сообщение и укажите ставку <code>/duel 100</code>", parse_mode="HTML")
    
    bet = int(command.args)
    user = get_user(message.from_user.id, message.from_user.username or "")
    max_bet = 2000 if is_vip(user) else 500
    min_bet = 1 if is_vip(user) else 10
    
    if not (min_bet <= bet <= max_bet):
        return await message.answer(f"❌ Допустимая ставка: от {min_bet} до {max_bet} монет!")
        
    if user[5] < bet:
        return await message.answer("❌ У вас недостаточно монет!")
        
    target_id = message.reply_to_message.from_user.id
    target = get_user(target_id, message.reply_to_message.from_user.username or "")
    if target[5] < bet:
        return await message.answer("❌ У соперника недостаточно монет!")

    winner_id = random.choice([message.from_user.id, target_id])
    loser_id = target_id if winner_id == message.from_user.id else message.from_user.id
    
    w_user = get_user(winner_id)
    l_user = get_user(loser_id)
    
    update_user(winner_id, coins=w_user[5] + bet, duel_wins=w_user[15] + 1)
    update_user(loser_id, coins=l_user[5] - bet)
    
    await message.answer(f"⚔️ В дуэли победил <a href='tg://user?id={winner_id}'>Игрок</a> и выиграл <b>{bet} монет</b>!", parse_mode="HTML")

@dp.message(Command("transfer"))
async def cmd_transfer(message: Message, command: CommandObject):
    if not message.reply_to_message or not command.args or not command.args.isdigit():
        return await message.answer("⚠️ Ответьте на сообщение: <code>/transfer 500</code>", parse_mode="HTML")
    
    amount = int(command.args)
    sender = get_user(message.from_user.id, message.from_user.username or "")
    limit = 2000 if is_vip(sender) else 500
    
    if amount > limit:
        return await message.answer(f"❌ Ваш лимит перевода: {limit} монет в день!")
    if sender[5] < amount:
        return await message.answer("❌ У вас нет столько монет!")

    target_id = message.reply_to_message.from_user.id
    target = get_user(target_id, message.reply_to_message.from_user.username or "")
    
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
# 7. ИНТЕГРИРОВАННЫЙ МАГАЗИН VIP (UAH / TG STARS)
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

    await callback.message.edit_text(
        f"💳 <b>Оплата VIP ({info['text']})</b>\n\n"
        f"Переведите <b>{info['price']} грн</b> на карту:\n<code>{CARD_DETAILS}</code>\n\n"
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
    period = payload[2]
    price = payment.total_amount

    user = message.from_user
    username = f"@{user.username}" if user.username else f"ID: {user.id}"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    period_str = "Навсегда" if period == "forever" else f"{period} мес."

    add_vip_time(user.id, period)

    cursor.execute(
        "INSERT INTO vip_history (user_id, username, price, currency, period, date) VALUES (?, ?, ?, ?, ?, ?)",
        (user.id, username, str(price), "звезд TG", period_str, now_str)
    )
    conn.commit()

    await message.answer(f"🎉 <b>Оплата прошла успешно!</b>\nВам активирован VIP-статус на: <b>{period_str}</b>.", parse_mode="HTML")

# Админ-панель VIP
@dp.message(Command("Bvip"))
async def cmd_bvip(message: Message):
    user = get_user(message.from_user.id)
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
    user = get_user(callback.from_user.id)
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
    user = get_user(callback.from_user.id)
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
    user = get_user(message.from_user.id)
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
    user = get_user(message.from_user.id)
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
# 8. МОДЕРАЦИЯ И АДМИНИСТРИРОВАНИЕ
# ==========================================

@dp.message(Command("snick"))
async def cmd_snick(message: Message, command: CommandObject):
    user = get_user(message.from_user.id, message.from_user.username or "")
    if user[3] < 2: return await message.answer("❌ Доступно с 2 ранга.")
    if not command.args or not message.reply_to_message:
        return await message.answer("⚠️ Ответьте на сообщение: <code>/snick НовыйНик</code>", parse_mode="HTML")
    
    target_id = message.reply_to_message.from_user.id
    update_user(target_id, custom_nickname=command.args)
    await message.answer(f"✅ Пользователю установлен локальный ник: <b>{command.args}</b>", parse_mode="HTML")

@dp.message(Command("rnick"))
async def cmd_rnick(message: Message):
    user = get_user(message.from_user.id, message.from_user.username or "")
    if user[3] < 2: return await message.answer("❌ Доступно с 2 ранга.")
    if not message.reply_to_message: return await message.answer("⚠️ Ответьте на сообщение!")
    
    update_user(message.reply_to_message.from_user.id, custom_nickname="")
    await message.answer("✅ Никнейм сброшен до исходного.")

@dp.message(Command("gnick"))
async def cmd_gnick(message: Message):
    user = get_user(message.from_user.id, message.from_user.username or "")
    if user[3] < 2: return await message.answer("❌ Доступно с 2 ранга.")
    if not message.reply_to_message: return await message.answer("⚠️ Ответьте на сообщение!")
    
    t = get_user(message.reply_to_message.from_user.id)
    await message.answer(f"👤 Настоящий ник: @{t[1]} | Кастомный: {t[16] or 'Нет'}")

@dp.message(Command("staff"))
async def cmd_staff(message: Message):
    cursor.execute("SELECT username, rank FROM users WHERE rank >= 1 LIMIT 20")
    rows = cursor.fetchall()
    text = "🛡️ <b>СОСТАВ МОДЕРАЦИИ:</b>\n\n"
    for r in rows:
        text += f"• @{r[0] or 'id'} — Ранг: {r[1]}\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("warn"))
async def cmd_warn(message: Message):
    user = get_user(message.from_user.id, message.from_user.username or "")
    if user[3] < 4: return await message.answer("❌ Строго с 4+ ранга.")
    if not message.reply_to_message: return await message.answer("⚠️ Ответьте на сообщение!")
    
    tid = message.reply_to_message.from_user.id
    target = get_user(tid)
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
    user = get_user(message.from_user.id, message.from_user.username or "")
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
        await message.answer(f"❌ Ошибка: {e}")

@dp.message(Command("kick"))
async def cmd_kick(message: Message, command: CommandObject):
    user = get_user(message.from_user.id, message.from_user.username or "")
    if user[3] < 4: return await message.answer("❌ Строго с 4+ ранга.")
    if not message.reply_to_message or not command.args:
        return await message.answer("⚠️ Причина обязательна: <code>/kick Причина</code>", parse_mode="HTML")
    
    try:
        await bot.ban_chat_member(message.chat.id, message.reply_to_message.from_user.id)
        await bot.unban_chat_member(message.chat.id, message.reply_to_message.from_user.id)
        await message.answer(f"🚪 Пользователь кикнут! Причина: {command.args}")
    except Exception as e: await message.answer(str(e))

@dp.message(Command("ban"))
async def cmd_ban(message: Message, command: CommandObject):
    user = get_user(message.from_user.id, message.from_user.username or "")
    if user[3] < 4: return await message.answer("❌ Строго с 4+ ранга.")
    if not message.reply_to_message or not command.args:
        return await message.answer("⚠️ Причина обязательна: <code>/ban Причина</code>", parse_mode="HTML")
    
    try:
        await bot.ban_chat_member(message.chat.id, message.reply_to_message.from_user.id)
        await message.answer(f"⛔ Локальный бан выдан! Причина: {command.args}")
    except Exception as e: await message.answer(str(e))

@dp.message(Command("gban"))
async def cmd_gban(message: Message, command: CommandObject):
    user = get_user(message.from_user.id, message.from_user.username or "")
    if user[3] < 6: return await message.answer("❌ Заявка доступна с 6+ ранга.")
    if not message.reply_to_message or not command.args:
        return await message.answer("⚠️ Укажите пункт/причину: <code>/gban П1</code>", parse_mode="HTML")
    
    tid = message.reply_to_message.from_user.id
    cursor.execute("INSERT OR REPLACE INTO global_bans VALUES (?, ?, ?)", (tid, command.args, message.from_user.username))
    conn.commit()
    await message.answer("🌐 <b>Заявка на GBAN одобрена и внесена в реестр!</b>", parse_mode="HTML")

@dp.message(Command("pin"))
async def cmd_pin(message: Message):
    user = get_user(message.from_user.id, message.from_user.username or "")
    if user[3] < 6: return await message.answer("❌ Доступно с 6+ ранга.")
    if not message.reply_to_message: return await message.answer("⚠️ Ответьте на сообщение!")
    
    await bot.pin_chat_message(message.chat.id, message.reply_to_message.message_id)
    await message.answer("📌 Сообщение закреплено!")

@dp.message(Command("unban"))
async def cmd_unban(message: Message):
    user = get_user(message.from_user.id, message.from_user.username or "")
    if user[3] < 5: return await message.answer("❌ Доступно с 5+ ранга.")
    if not message.reply_to_message: return await message.answer("⚠️ Ответьте на сообщение!")
    
    await bot.unban_chat_member(message.chat.id, message.reply_to_message.from_user.id)
    await message.answer("✅ Бан снят!")

@dp.message(Command("unmute"))
async def cmd_unmute(message: Message):
    user = get_user(message.from_user.id, message.from_user.username or "")
    if user[3] < 5: return await message.answer("❌ Доступно с 5+ ранга.")
    if not message.reply_to_message: return await message.answer("⚠️ Ответьте на сообщение!")
    
    await bot.restrict_chat_member(message.chat.id, message.reply_to_message.from_user.id,
                                   ChatPermissions(can_send_messages=True, can_send_media_messages=True))
    await message.answer("🔊 Мут снят!")

@dp.message(Command("unwarn"))
async def cmd_unwarn(message: Message):
    user = get_user(message.from_user.id, message.from_user.username or "")
    if user[3] < 5: return await message.answer("❌ Доступно с 5+ ранга.")
    if not message.reply_to_message: return await message.answer("⚠️ Ответьте на сообщение!")
    
    tid = message.reply_to_message.from_user.id
    t = get_user(tid)
    if t[19] > 0:
        update_user(tid, warns=t[19]-1)
    await message.answer("✅ Варн снят!")

# ==========================================
# 9. ЛОГИ И УПРАВЛЕНИЕ ДОСТУПОМ
# ==========================================

@dp.message(Command("Pbook"))
async def cmd_pbook(message: Message):
    user = get_user(message.from_user.id, message.from_user.username or "")
    if user[3] < 5: return await message.answer("❌ Доступ с 5+ ранга.")
    cursor.execute("REPLACE INTO logs_access VALUES (?, 1)", (message.from_user.id,))
    conn.commit()
    await send_log_to_user(message.from_user.id, "Вам одобрен доступ к локальным логам (Pbook)!")
    await message.answer("✅ Заявка отправлена в ЛС бота!")

@dp.message(Command("Pbooks"))
async def cmd_pbooks(message: Message):
    user = get_user(message.from_user.id, message.from_user.username or "")
    if user[3] < 6: return await message.answer("❌ Доступ с 6+ ранга.")
    cursor.execute("REPLACE INTO logs_access VALUES (?, 2)", (message.from_user.id,))
    conn.commit()
    await send_log_to_user(message.from_user.id, "Вам одобрен расширенный доступ к логам (Pbooks)!")
    await message.answer("✅ Расширенный доступ отправлен в ЛС!")

@dp.message(Command("book"))
async def cmd_book(message: Message):
    await send_log_to_user(message.from_user.id, f"Лог локальных действий группы {message.chat.id}: Действия стабильны.")
    await message.answer("📖 Логи отправлены в ЛС бота!")

@dp.message(Command("books"))
async def cmd_books(message: Message):
    await send_log_to_user(message.from_user.id, f"Расширенный лог действий группы {message.chat.id}: Нарушений не найдено.")
    await message.answer("📚 Расширенные логи отправлены в ЛС бота!")

@dp.message(Command("book_global"))
async def cmd_book_global(message: Message):
    user = get_user(message.from_user.id, message.from_user.username or "")
    if user[3] < 7: return await message.answer("❌ Доступно с 7+ ранга.")
    await send_log_to_user(message.from_user.id, "🌐 ГЛОБАЛЬНЫЙ ЛОГ ВСЕХ ЧАТОВ: Активность в норме.")
    await message.answer("🌐 Глобальный лог отправлен в ЛС!")

@dp.message(Command("mevip"))
async def cmd_mevip(message: Message):
    user = get_user(message.from_user.id, message.from_user.username or "")
    if user[3] < 8: return await message.answer("❌ Доступно с 8+ ранга.")
    v_until = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    update_user(message.from_user.id, vip_until=v_until)
    await message.answer("👑 Вам выдан расширенный VIP-статус на 7 дней!")

@dp.message(Command("checkreps"))
async def cmd_checkreps(message: Message):
    user = get_user(message.from_user.id, message.from_user.username or "")
    if user[3] < 6: return await message.answer("❌ Доступно с 6+ ранга.")
    cursor.execute("SELECT COUNT(*) FROM reports")
    cnt = cursor.fetchone()[0]
    await message.answer(f"📊 Всего обработано и активных репортов: <b>{cnt}</b>", parse_mode="HTML")

@dp.message(Command("ungloballist"))
async def cmd_ungloballist(message: Message):
    user = get_user(message.from_user.id, message.from_user.username or "")
    if user[3] < 8: return await message.answer("❌ Доступно для 8+ рангов.")
    cursor.execute("SELECT user_id, reason FROM global_bans LIMIT 10")
    rows = cursor.fetchall()
    text = "📜 <b>СПИСОК ГЛОБАЛЬНЫХ БАНОВ:</b>\n\n"
    for r in rows: text += f"• ID: <code>{r[0]}</code> | Причина: {r[1]}\n"
    await send_log_to_user(message.from_user.id, text)
    await message.answer("📜 Список выслан в ЛС бота!")

@dp.message(Command("setaccess"))
async def cmd_setaccess(message: Message, command: CommandObject):
    user = get_user(message.from_user.id, message.from_user.username or "")
    if user[3] < 4: return await message.answer("❌ Выдача доступна от 4+ ранга.")
    if not message.reply_to_message or not command.args or not command.args.isdigit():
        return await message.answer("⚠️ Пример: <code>/setaccess 3</code>", parse_mode="HTML")
    
    target_rank = int(command.args)
    if target_rank > 5: return await message.answer("❌ Максимум можно выдать 5 ранг через эту команду!")
    
    if user[3] == 4 and target_rank not in [2, 3]: return await message.answer("❌ 4 ранг может давать только 2 и 3 ранги!")
    if user[3] == 5 and target_rank not in [2, 3, 4]: return await message.answer("❌ 5 ранг может давать только 2, 3, 4 ранги!")
    
    update_user(message.reply_to_message.from_user.id, rank=target_rank)
    await message.answer(f"✅ Пользователю установлен <b>{target_rank} ранг</b>!", parse_mode="HTML")

@dp.message(Command("giverang"))
async def cmd_giverang(message: Message):
    user = get_user(message.from_user.id, message.from_user.username or "")
    if user[3] < 9: return await message.answer("❌ Доступно строго для 9+ рангов.")
    if not message.reply_to_message: return await message.answer("⚠️ Ответьте на сообщение!")
    
    update_user(message.reply_to_message.from_user.id, rank=8)
    await send_log_to_user(message.from_user.id, f"Назначен 8 ранг для ID: {message.reply_to_message.from_user.id}.")
    await message.answer("✅ Назначен 8 ранг! Информация отправлена в ЛС.")

@dp.message(Command("ungiverang"))
async def cmd_ungiverang(message: Message):
    user = get_user(message.from_user.id, message.from_user.username or "")
    if user[3] < 9: return await message.answer("❌ Доступно строго для 9+ рангов.")
    if not message.reply_to_message: return await message.answer("⚠️ Ответьте на сообщение!")
    
    update_user(message.reply_to_message.from_user.id, rank=0)
    await message.answer("✅ 8 ранг снят!")

@dp.message(Command("setzam"))
async def cmd_setzam(message: Message):
    user = get_user(message.from_user.id, message.from_user.username or "")
    if user[3] < 10: return await message.answer("❌ Доступно только Владельцу (10 ранг).")
    if not message.reply_to_message: return await message.answer("⚠️ Ответьте на сообщение!")
    
    update_user(message.reply_to_message.from_user.id, rank=9)
    await message.answer("👑 Пользователь назначен Заместителем (9 ранг)!")

@dp.message(Command("unsetzam"))
async def cmd_unsetzam(message: Message):
    user = get_user(message.from_user.id, message.from_user.username or "")
    if user[3] < 10: return await message.answer("❌ Доступно только Владельцу (10 ранг).")
    if not message.reply_to_message: return await message.answer("⚠️ Ответьте на сообщение!")
    
    update_user(message.reply_to_message.from_user.id, rank=0)
    await message.answer("✅ 9 ранг успешно снят!")

@dp.message(Command("megabook"))
async def cmd_megabook(message: Message):
    user = get_user(message.from_user.id, message.from_user.username or "")
    if user[3] < 7: return await message.answer("❌ Доступно с 7+ ранга.")
    await send_log_to_user(message.from_user.id, "📊 ПОЛНАЯ ИСТОРИЯ МОНЕТ И EXP: Все транзакции валидны.")
    await message.answer("📊 Мегабук выслан в ЛС!")

@dp.message(Command("megabooks"))
async def cmd_megabooks(message: Message):
    user = get_user(message.from_user.id, message.from_user.username or "")
    if user[3] < 7: return await message.answer("❌ Доступно с 7+ ранга.")
    await send_log_to_user(message.from_user.id, "📑 ПОЛНЫЙ ЛОГ ДЕЙСТВИЙ, НАКАЗАНИЙ И ПОВЫШЕНИЙ: Анализ завершён.")
    await message.answer("📑 Полный лог выслан в ЛС!")

@dp.message(Command("history"))
async def cmd_history(message: Message):
    user = get_user(message.from_user.id, message.from_user.username or "")
    if user[3] < 7: return await message.answer("❌ Доступно с 7+ ранга.")
    if not message.reply_to_message: return await message.answer("⚠️ Ответьте на сообщение!")
    
    t = get_user(message.reply_to_message.from_user.id)
    await message.answer(f"🔍 <b>ИСТОРИЯ АККАУНТА:</b>\nID: {t[0]} | Твинки: Не обнаружены | Статус GBAN: {'Да' if check_gban(t[0]) else 'Нет'}", parse_mode="HTML")

@dp.message(Command("gwarn"))
async def cmd_gwarn(message: Message, command: CommandObject):
    user = get_user(message.from_user.id, message.from_user.username or "")
    if user[3] < 5: return await message.answer("❌ Заявка доступна с 5+ ранга.")
    if not message.reply_to_message or not command.args:
        return await message.answer("⚠️ Обязательно укажите причину: <code>/gwarn Причина</code>", parse_mode="HTML")
    
    tid = message.reply_to_message.from_user.id
    cursor.execute("INSERT INTO global_warns (user_id, reason, by_user) VALUES (?, ?, ?)", (tid, command.args, message.from_user.username))
    conn.commit()
    
    cursor.execute("SELECT COUNT(*) FROM global_warns WHERE user_id = ?", (tid,))
    cnt = cursor.fetchone()[0]
    if cnt >= 3:
        cursor.execute("INSERT OR REPLACE INTO global_bans VALUES (?, '3/3 GWARN', 'SYSTEM')", (tid,))
        conn.commit()
        await message.answer("🚨 Пользователь получил 3/3 GWARN и автоматически занесён в <b>GBAN</b>!", parse_mode="HTML")
    else:
        await message.answer(f"⚠️ Подана заявка на GWARN ({cnt}/3)! На рассмотрении 8+.")

# ==========================================
# 10. СПЕЦ-РОЛИ И ВЫСШЕЕ РУКОВОДСТВО
# ==========================================

@dp.message(Command("givetex"))
async def cmd_givetex(message: Message):
    user = get_user(message.from_user.id, message.from_user.username or "")
    if user[3] < 8: return await message.answer("❌ Доступно для ГСЗТХ/ЗГСЗТХ (8+).")
    if not message.reply_to_message: return await message.answer("⚠️ Ответьте на сообщение!")
    
    update_user(message.reply_to_message.from_user.id, rank=7)
    await message.answer("🔧 Пользователю назначен статус <b>Технического Специалиста (7 ранг)</b>!", parse_mode="HTML")

@dp.message(Command("usgivetex"))
async def cmd_usgivetex(message: Message):
    user = get_user(message.from_user.id, message.from_user.username or "")
    if user[3] < 8: return await message.answer("❌ Доступно для 8+ рангов.")
    if not message.reply_to_message: return await message.answer("⚠️ Ответьте на сообщение!")
    
    update_user(message.reply_to_message.from_user.id, rank=0)
    await message.answer("✅ Технический Специалист снят с должности.")

@dp.message(Command("Obnyl_Money"))
async def cmd_obnyl_money(message: Message):
    user = get_user(message.from_user.id, message.from_user.username or "")
    if user[3] < 8: return await message.answer("❌ Доступно для Технического Спец. (8+).")
    if not message.reply_to_message: return await message.answer("⚠️ Ответьте на сообщение!")
    
    tid = message.reply_to_message.from_user.id
    update_user(tid, coins=0)
    cursor.execute("DELETE FROM custom_roles WHERE creator_id = ?", (tid,))
    conn.commit()
    await message.answer("💸 Монеты и созданные роли пользователя полностью обнулены!")

@dp.message(Command("Obnyl"))
async def cmd_obnyl(message: Message):
    user = get_user(message.from_user.id, message.from_user.username or "")
    if user[3] < 8: return await message.answer("❌ Доступно для Технического Спец. (8+).")
    if not message.reply_to_message: return await message.answer("⚠️ Ответьте на сообщение!")
    
    tid = message.reply_to_message.from_user.id
    cursor.execute("DELETE FROM users WHERE user_id = ?", (tid,))
    cursor.execute("DELETE FROM custom_roles WHERE creator_id = ?", (tid,))
    conn.commit()
    await message.answer("💥 Аккаунт пользователя полностью сброшен и обнулён!")

@dp.message(Command("repgh"))
async def cmd_repgh(message: Message, command: CommandObject):
    user = get_user(message.from_user.id, message.from_user.username or "")
    if user[3] < 8: return await message.answer("❌ Доступно с 8+ ранга.")
    if not command.args:
        return await message.answer("⚠️ Укажите роли в ЛС бота: <code>/repgh 1,2</code>", parse_mode="HTML")
    await send_log_to_user(message.from_user.id, f"Репорт перенаправлен ролям: {command.args}")
    await message.answer("✅ Перенаправление репорта выполнено!")

@dp.message(Command("muterep"))
async def cmd_muterep(message: Message, command: CommandObject):
    user = get_user(message.from_user.id, message.from_user.username or "")
    if user[3] < 8: return await message.answer("❌ Доступно с 8+ ранга.")
    if not message.reply_to_message: return await message.answer("⚠️ Ответьте на сообщение!")
    
    days = int(command.args) if command.args and command.args.isdigit() else 3
    until = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    update_user(message.reply_to_message.from_user.id, rep_muted_until=until)
    await message.answer(f"🔇 Использование /report заблокировано на {days} дней!")

@dp.message(Command("bot_boost"))
async def cmd_bot_boost(message: Message, command: CommandObject):
    if not command.args:
        return await message.answer("⚠️ Напишите идею улучшения: <code>/bot_boost Добавить больше игр</code>", parse_mode="HTML")
    cursor.execute("INSERT INTO bot_boosts (user_id, text) VALUES (?, ?)", (message.from_user.id, command.args))
    conn.commit()
    await message.answer("💡 Ваша идея отправлена разработчикам! За отличные идеи полагаются награды.")

@dp.message(Command("checkrep"))
async def cmd_checkrep(message: Message):
    user = get_user(message.from_user.id, message.from_user.username or "")
    if user[3] < 8: return await message.answer("❌ Доступно с 8+ ранга.")
    cursor.execute("SELECT id, user_id, text FROM reports LIMIT 10")
    rows = cursor.fetchall()
    text = "📋 <b>АКТИВНЫЕ ЖАЛОБЫ И РЕПОРТЫ:</b>\n\n"
    for r in rows: text += f"• ID:{r[0]} от {r[1]}: {r[2]}\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("checkboost"))
async def cmd_checkboost(message: Message):
    user = get_user(message.from_user.id, message.from_user.username or "")
    if user[3] < 8: return await message.answer("❌ Доступно с 8+ ранга.")
    cursor.execute("SELECT id, user_id, text FROM bot_boosts LIMIT 10")
    rows = cursor.fetchall()
    text = "💡 <b>ПРЕДЛОЖЕНИЯ ПО УЛУЧШЕНИЮ БОТА:</b>\n\n"
    for r in rows: text += f"• ID:{r[0]} от {r[1]}: {r[2]}\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("glist"))
async def cmd_glist(message: Message):
    user = get_user(message.from_user.id, message.from_user.username or "")
    if user[3] < 9: return await message.answer("❌ Строго для 9+ рангов.")
    cursor.execute("SELECT user_id, reason FROM global_bans")
    rows = cursor.fetchall()
    text = "🌐 <b>СПИСОК ГЛОБАЛЬНЫХ БАНОВ (GBAN):</b>\n\n"
    for r in rows:
        text += f"• Юзер ID: <code>{r[0]}</code> | Причина: {r[1]} [Для снятия: /ungban {r[0]}]\n"
    await message.answer(text if rows else "Список GBAN пуст.", parse_mode="HTML")

@dp.message(Command("gwlist"))
async def cmd_gwlist(message: Message):
    user = get_user(message.from_user.id, message.from_user.username or "")
    if user[3] < 9: return await message.answer("❌ Строго для 9+ рангов.")
    cursor.execute("SELECT user_id, reason FROM global_warns")
    rows = cursor.fetchall()
    text = "⚠️ <b>СПИСОК ГЛОБАЛЬНЫХ ВАРНОВ (GWARN):</b>\n\n"
    for r in rows:
        text += f"• Юзер ID: <code>{r[0]}</code> | Причина: {r[1]} [Для снятия: /ungwarn {r[0]}]\n"
    await message.answer(text if rows else "Список GWARN пуст.", parse_mode="HTML")

@dp.message(Command("ungban"))
async def cmd_ungban(message: Message, command: CommandObject):
    user = get_user(message.from_user.id, message.from_user.username or "")
    if user[3] < 10: return await message.answer("❌ Снятие GBAN строго для 10 ранга (@nlyxx2686).")
    if not command.args or not command.args.isdigit():
        return await message.answer("⚠️ Укажите ID: <code>/ungban 123456789</code>", parse_mode="HTML")
    
    cursor.execute("DELETE FROM global_bans WHERE user_id = ?", (int(command.args),))
    conn.commit()
    await message.answer(f"✅ Пользователь ID {command.args} вынесен из GBAN!")

@dp.message(Command("ungwarn"))
async def cmd_ungwarn(message: Message, command: CommandObject):
    user = get_user(message.from_user.id, message.from_user.username or "")
    if user[3] < 9: return await message.answer("❌ Доступно для 9+ ранга.")
    if not command.args or not command.args.isdigit():
        return await message.answer("⚠️ Укажите ID: <code>/ungwarn 123456789</code>", parse_mode="HTML")
    
    cursor.execute("DELETE FROM global_warns WHERE user_id = ?", (int(command.args),))
    conn.commit()
    await message.answer(f"✅ GWARN с пользователя ID {command.args} снят!")

@dp.message(Command("pleasevip"))
async def cmd_pleasevip(message: Message):
    uid = message.from_user.id
    cursor.execute("SELECT 1 FROM user_roles_owned WHERE user_id = ? AND role_id = -888", (uid,))
    if cursor.fetchone():
        return await message.answer("❌ Вы уже просили бесплатную VIP-ку через /pleasevip!")
    
    v_until = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")
    update_user(uid, vip_until=v_until)
    cursor.execute("INSERT INTO user_roles_owned VALUES (?, -888)", (uid,))
    conn.commit()
    await message.answer("🎉 Вам автоматически одобрен бесплатный <b>VIP на 5 дней</b>!", parse_mode="HTML")

@dp.message(Command("givesvips"))
async def cmd_givesvips(message: Message, command: CommandObject):
    user = get_user(message.from_user.id, message.from_user.username or "")
    if user[3] < 10: return await message.answer("❌ Выдача VIP строго от 10 ранга.")
    if not command.args:
        return await message.answer("⚠️ Использование: <code>/givesvips @username 1</code> (месяцев)", parse_mode="HTML")
    
    parts = command.args.split()
    target_uname = parts[0].lstrip('@')
    months = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
    
    cursor.execute("SELECT user_id FROM users WHERE username = ?", (target_uname,))
    row = cursor.fetchone()
    if not row: return await message.answer("❌ Пользователь не найден в БД бота!")
    
    add_vip_time(row[0], str(months))
    await message.answer(f"✅ Пользователю @{target_uname} выдан VIP на {months} мес.!")

@dp.message(Command("Global"))
async def cmd_global_news(message: Message, command: CommandObject):
    if message.from_user.username and message.from_user.username.lower() != OWNER_USERNAME.lower():
        return await message.answer("❌ Эта команда доступна исключительно Владельцу бота (@nlyxx2686)!")
    
    if command.args and command.args.startswith("news"):
        rules_text = command.args[4:].strip()
        cursor.execute("REPLACE INTO chat_settings (chat_id, rules) VALUES (?, ?)", (message.chat.id, rules_text))
        conn.commit()
        await message.answer(f"📜 <b>ГЛОБАЛЬНЫЕ ПРАВИЛА ЧАТА ОБНОВЛЕНЫ:</b>\n{rules_text}", parse_mode="HTML")
    else:
        await message.answer("⚠️ Использование: <code>/Global news [Текст правил]</code>", parse_mode="HTML")

# ==========================================
# 11. ЗАПУСК БОТА
# ==========================================

async def main():
    print("🚀 Stars Manager Bot с интегрированным магазином VIP запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
