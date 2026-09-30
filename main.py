import asyncio
import logging
import os
import random
import re
from datetime import datetime, timedelta
from threading import Thread

import aiosqlite
from flask import Flask

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ==========================================
# 0. ВЕБ-СЕРВЕР ДЛЯ РАЗВЕРТЫВАНИЯ (RENDER/REPLIT 24/7)
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
# 1. КОНФИГУРАЦИЯ И НАСТРОЙКА
# ==========================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
DB_PATH = "bot_database.db"

MONOBANK_JAR = "https://send.monobank.ua/jar/8wVnXzoF3f"
CARD_DETAILS = "4441 0000 0000 0000"
OWNER_USERNAME = "nlyxx2686"
OWNER_ID = 123456789  # Укажите ваш настоящий Telegram ID
ADMIN_IDS = [123456789]  # Список ID администраторов

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ==========================================
# 2. ИНИЦИАЛИЗАЦИЯ И РАБОТА С БАЗОЙ ДАННЫХ
# ==========================================
def clean_username(username: str) -> str:
    if not username:
        return ""
    return username.replace("@", "").strip().lower()

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
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
                role TEXT DEFAULT 'User',
                referrer_id INTEGER DEFAULT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS global_bans (
                user_id INTEGER PRIMARY KEY,
                reason TEXT,
                by_user TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS custom_roles (
                role_id INTEGER PRIMARY KEY AUTOINCREMENT,
                creator_id INTEGER,
                chat_id INTEGER,
                text TEXT,
                color_code TEXT,
                price INTEGER DEFAULT 0,
                monthly_income INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS known_chats (
                chat_id INTEGER PRIMARY KEY,
                chat_title TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pending_vip_orders (
                order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                period TEXT,
                price TEXT,
                currency TEXT,
                date TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS vip_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                price TEXT,
                currency TEXT,
                period TEXT,
                date TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS donats_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                type TEXT,
                amount TEXT,
                currency TEXT,
                date TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_settings (
                chat_id INTEGER PRIMARY KEY,
                rules TEXT DEFAULT '',
                shop_exp_rate INTEGER DEFAULT 10
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                user_id INTEGER,
                target_id INTEGER,
                text TEXT,
                status TEXT DEFAULT 'pending'
            )
        """)
        await db.commit()

async def get_user(user_id: int = None, username: str = ""):
    u_clean = clean_username(username)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        row = None
        if user_id:
            async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
        elif u_clean:
            async with db.execute("SELECT * FROM users WHERE LOWER(username) = ?", (u_clean,)) as cursor:
                row = await cursor.fetchone()

        if not row and user_id:
            rank = 10 if user_id == OWNER_ID or (u_clean and u_clean == OWNER_USERNAME.lower()) else 0
            await db.execute(
                "INSERT INTO users (user_id, username, rank, coins) VALUES (?, ?, ?, 100)",
                (user_id, u_clean, rank)
            )
            await db.commit()
            async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
        elif row and u_clean and row['username'] != u_clean:
            await db.execute("UPDATE users SET username = ? WHERE user_id = ?", (u_clean, row['user_id']))
            await db.commit()
            
        return row

async def update_user(user_id: int, **kwargs):
    async with aiosqlite.connect(DB_PATH) as db:
        fields = [f"{k} = ?" for k in kwargs.keys()]
        values = list(kwargs.values()) + [user_id]
        await db.execute(f"UPDATE users SET {', '.join(fields)} WHERE user_id = ?", values)
        await db.commit()

async def check_gban(user_id: int) -> bool:
    if user_id == OWNER_ID:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT 1 FROM global_bans WHERE user_id = ?", (user_id,)) as cursor:
            return (await cursor.fetchone()) is not None

def is_vip(user_row) -> bool:
    if not user_row or not user_row['vip_until']: 
        return False
    if user_row['vip_until'] == 'forever': 
        return True
    try:
        until = datetime.strptime(user_row['vip_until'], "%Y-%m-%d %H:%M:%S")
        return datetime.now() < until
    except Exception:
        return False

async def add_vip_time(user_id: int, period: str):
    user = await get_user(user_id=user_id)
    if period.lower() in ["forever", "навсегда"]:
        await update_user(user_id, vip_until="forever")
        return

    days_to_add = int(period) * 30
    now = datetime.now()

    if is_vip(user) and user['vip_until'] != 'forever':
        current_until = datetime.strptime(user['vip_until'], "%Y-%m-%d %H:%M:%S")
        new_until = current_until + timedelta(days=days_to_add)
    else:
        new_until = now + timedelta(days=days_to_add)

    await update_user(user_id, vip_until=new_until.strftime("%Y-%m-%d %H:%M:%S"))

async def add_donat_record(user_id: int, username: str, type_str: str, amount: str, currency: str):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO donats_history (user_id, username, type, amount, currency, date) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, clean_username(username), type_str, amount, currency, now_str)
        )
        await db.commit()

async def send_log_to_user(user_id: int, text: str):
    try:
        await bot.send_message(user_id, f"📝 <b>[ЛОГ СИСТЕМЫ]</b>\n{text}", parse_mode="HTML")
    except Exception as e:
        logging.error(f"Не удалось отправить лог пользователю {user_id}: {e}")

# ==========================================
# 3. FSM И ПРАЙС-ЛИСТЫ
# ==========================================
class BroadcastStates(StatesGroup):
    waiting_for_text = State()

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
# 4. МИДДЛВАРЬ ГЛОБАЛЬНОЙ ПРОВЕРКИ
# ==========================================
@dp.message.middleware()
async def global_middleware(handler, event: Message, data):
    if not event.from_user:
        return await handler(event, data)

    user_id = event.from_user.id
    username = event.from_user.username or ""

    if event.chat.type in ['group', 'supergroup']:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT OR REPLACE INTO known_chats (chat_id, chat_title) VALUES (?, ?)", 
                             (event.chat.id, event.chat.title or "Group"))
            await db.commit()

    if user_id != OWNER_ID and await check_gban(user_id):
        if event.chat.type in ['group', 'supergroup']:
            try:
                await bot.ban_chat_member(event.chat.id, user_id)
                await event.answer(f"🚨 Пользователь @{username or user_id} имеет <b>GBAN</b> и был удалён из чата!", parse_mode="HTML")
            except Exception:
                pass
            return

    user = await get_user(user_id=user_id, username=username)
    await update_user(user_id, msg_count=user['msg_count'] + 1)

    return await handler(event, data)

# ==========================================
# 5. ОСНОВНЫЕ И ИГРОВЫЕ КОМАНДЫ
# ==========================================
@dp.message(Command("start"))
async def cmd_start(message: Message, command: CommandObject):
    user_id = message.from_user.id
    username = message.from_user.username

    if not username:
        return await message.answer("⚠️ У вас не установлен **Username** в Настройках Telegram!", parse_mode="Markdown")

    user = await get_user(user_id, username)

    # Реферальная система
    if command.args and command.args.isdigit():
        ref_id = int(command.args)
        if ref_id != user_id and user['referrer_id'] is None:
            ref_user = await get_user(ref_id)
            if ref_user:
                await update_user(user_id, referrer_id=ref_id)
                await update_user(ref_id, coins=ref_user['coins'] + 500)
                await message.answer("🎉 Вы зарегистрировались по реферальной ссылке! Ваш пригласитель получил 🪙 500 монет.")

    kb = InlineKeyboardBuilder()
    kb.button(text="🛍 Магазин ролей", callback_data="open_shop")
    kb.button(text="⭐ VIP / Stars / Донаты", callback_data="open_donate")
    kb.adjust(1)

    vip_status = "Да" if is_vip(user) else "Отсутствует"
    await message.answer(
        f"👋 <b>Привет, {message.from_user.full_name}!</b> (@{clean_username(username)})\n\n"
        f"💳 Твой баланс: 🪙 {user['coins']} монет\n"
        f"🔰 Твой ранг администрирования: {user['rank']}\n"
        f"⭐️ VIP статус: {vip_status}\n\n"
        f"Используй меню или команды для управления!",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )

@dp.message(Command("profile", "me"))
async def cmd_profile(message: Message):
    args = message.text.split()
    if len(args) > 1:
        target_username = args[1]
        user = await get_user(username=target_username)
    else:
        user = await get_user(user_id=message.from_user.id, username=message.from_user.username or "")

    if user:
        vip_str = "Да" if is_vip(user) else "Нет"
        await message.answer(
            f"👤 <b>ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ:</b>\n\n"
            f"🆔 ID: <code>{user['user_id']}</code>\n"
            f"👤 Юзернейм: @{user['username'] or 'отсутствует'}\n"
            f"🏷 Локальная роль: {user['role']}\n"
            f"🪙 Баланс: {user['coins']} монет\n"
            f"⚡ Уровень: {user['level']} ({user['exp']} EXP)\n"
            f"🔰 Админ-ранг: {user['rank']}\n"
            f"⭐ VIP-статус: {vip_str}\n"
            f"🏆 Репутация: {user['rep']}\n"
            f"💬 Сообщений: {user['msg_count']} | ⚔️ Побед в дуэлях: {user['duel_wins']}",
            parse_mode="HTML"
        )
    else:
        await message.answer("❌ Пользователь не найден в базе.")

@dp.message(Command("rep"))
async def cmd_rep(message: Message, command: CommandObject):
    if not message.reply_to_message or message.reply_to_message.from_user.is_bot:
        return await message.answer("⚠️️ Ответьте на сообщение пользователя.")
    
    target_id = message.reply_to_message.from_user.id
    sender_id = message.from_user.id
    if target_id == sender_id:
        return await message.answer("❌ Нельзя изменять репутацию самому себе!")

    sender = await get_user(user_id=sender_id, username=message.from_user.username or "")
    now_str = datetime.now().strftime("%Y-%m-%d")
    
    max_rep_count = 3 if is_vip(sender) else 1
    today_count = sender['rep_given_today'] if sender['last_rep_date'] == now_str else 0
    
    if today_count >= max_rep_count:
        return await message.answer(f"❌ Лимит изменений репутации на сегодня исчерпан ({today_count}/{max_rep_count})!")

    sign = command.args.strip() if command and command.args else "+"
    delta = 1 if sign != "-" else -1
    
    target = await get_user(user_id=target_id, username=message.reply_to_message.from_user.username or "")
    await update_user(target_id, rep=target['rep'] + delta)
    await update_user(sender_id, rep_given_today=today_count + 1, last_rep_date=now_str)
    
    await message.answer(f"👍 Вы изменили репутацию пользователю {message.reply_to_message.from_user.full_name} на {delta}! Теперь у него: {target['rep'] + delta}")

@dp.message(Command("bonus"))
async def cmd_bonus(message: Message):
    uid = message.from_user.id
    user = await get_user(user_id=uid, username=message.from_user.username or "")
    
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    
    if user['last_bonus'] == today_str:
        return await message.answer("❌ Вы уже забирали сегодняшний бонус! Приходите завтра.")
    
    yesterday_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    streak = user['streak'] + 1 if user['last_bonus'] == yesterday_str else 1
    
    coins_add = 100 + (streak - 1) * (25 if streak < 20 else 150)
    exp_add = 50 + (streak - 1) * (10 if streak < 20 else 100)
        
    coins_add = min(coins_add, 1500000)
    exp_add = min(exp_add, 500)
    
    new_coins = user['coins'] + coins_add
    new_exp = user['exp'] + exp_add
    new_level = user['level']
    
    req_exp = 100 + (new_level * 50)
    lvl_up_text = ""
    if new_exp >= req_exp:
        new_level += 1
        new_coins += 50
        lvl_up_text = f"\n🎉 <b>Новый уровень: {new_level}! (+50 монет)</b>"

    await update_user(uid, coins=new_coins, exp=new_exp, level=new_level, rep=user['rep'] + 1, streak=streak, last_bonus=today_str)
    
    await message.answer(
        f"🎁 <b>Ежедневный бонус забран!</b>\n"
        f"🔥 Серия: <b>{streak} дней</b>\n"
        f"💰 Получено: +{coins_add} монет, +{exp_add} EXP, +1 Репутация\n"
        f"{lvl_up_text}", parse_mode="HTML"
    )

@dp.message(Command("top", "tops"))
async def cmd_tops(message: Message):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id, username, coins, level, rep FROM users ORDER BY coins DESC LIMIT 10") as cursor:
            top_users = await cursor.fetchall()
            
    text = "🏆 <b>ТОП-10 ПОЛЬЗОВАТЕЛЕЙ ПО БАЛАНСУ:</b>\n\n"
    for idx, r in enumerate(top_users, start=1):
        uid, uname, bal, lvl, rep = r
        name = f"@{uname}" if uname else f"ID: {uid}"
        text += f"{idx}. {name} — 🪙 {bal} монет | ⚡ {lvl} лвл | ⭐ {rep} реп\n"
        
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("duel"))
async def cmd_duel(message: Message, command: CommandObject):
    if not message.reply_to_message or not command.args or not command.args.isdigit():
        return await message.answer("⚠️ Использование: ответьте на сообщение и укажите ставку <code>/duel 100</code>", parse_mode="HTML")
    
    bet = int(command.args)
    user = await get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    max_bet = 2000 if is_vip(user) else 500
    
    if not (1 <= bet <= max_bet):
        return await message.answer(f"❌ Допустимая ставка: от 1 до {max_bet} монет!")
        
    if user['coins'] < bet:
        return await message.answer("❌ У вас недостаточно монет!")
        
    target_id = message.reply_to_message.from_user.id
    target = await get_user(user_id=target_id, username=message.reply_to_message.from_user.username or "")
    if target['coins'] < bet:
        return await message.answer("❌ У соперника недостаточно монет!")

    winner_id = random.choice([message.from_user.id, target_id])
    loser_id = target_id if winner_id == message.from_user.id else message.from_user.id
    
    w_user = await get_user(user_id=winner_id)
    l_user = await get_user(user_id=loser_id)
    
    await update_user(winner_id, coins=w_user['coins'] + bet, duel_wins=w_user['duel_wins'] + 1)
    await update_user(loser_id, coins=l_user['coins'] - bet)
    
    await message.answer(f"⚔️ В дуэли победил игрок <a href='tg://user?id={winner_id}'>Победитель</a> и выиграл <b>{bet} монет</b>!", parse_mode="HTML")

@dp.message(Command("transfer"))
async def cmd_transfer(message: Message, command: CommandObject):
    if not message.reply_to_message or not command.args or not command.args.isdigit():
        return await message.answer("⚠️ Ответьте на сообщение: <code>/transfer 500</code>", parse_mode="HTML")
    
    amount = int(command.args)
    sender = await get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    
    if sender['coins'] < amount:
        return await message.answer("❌ У вас нет столько монет!")

    target_id = message.reply_to_message.from_user.id
    target = await get_user(user_id=target_id, username=message.reply_to_message.from_user.username or "")
    
    await update_user(message.from_user.id, coins=sender['coins'] - amount)
    await update_user(target_id, coins=target['coins'] + amount)
    await message.answer(f"💸 Успешно переведено <b>{amount} монет</b> пользователю {message.reply_to_message.from_user.full_name}!", parse_mode="HTML")

# ==========================================
# 6. МОДЕРАЦИЯ И АДМИНИСТРИРОВАНИЕ
# ==========================================
@dp.message(Command("mute"))
async def cmd_mute(message: Message, command: CommandObject):
    user = await get_user(message.from_user.id)
    if user['rank'] < 3:
        return await message.answer("❌ Мут доступен только модераторам (3+ ранг).")
    
    if not message.reply_to_message:
        return await message.answer("⚠️ Ответьте на сообщение нарушителя.")
    
    duration = int(command.args) if command.args and command.args.isdigit() else 5
    until_time = datetime.now() + timedelta(minutes=duration)
    
    try:
        await message.chat.restrict(
            user_id=message.reply_to_message.from_user.id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until_time
        )
        await message.answer(f"🔇 Пользователь {message.reply_to_message.from_user.full_name} замучен на {duration} минут.")
    except Exception as e:
        await message.answer(f"❌ Ошибка ограничения прав: {e}")

@dp.message(Command("unmute"))
async def cmd_unmute(message: Message):
    user = await get_user(message.from_user.id)
    if user['rank'] < 3:
        return await message.answer("❌ Доступно с 3+ ранга.")
    
    if not message.reply_to_message:
        return await message.answer("⚠️ Ответьте на сообщение пользователя.")
        
    try:
        await message.chat.restrict(
            user_id=message.reply_to_message.from_user.id,
            permissions=ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True)
        )
        await message.answer(f"🔊 С пользователя {message.reply_to_message.from_user.full_name} сняты ограничения.")
    except Exception as e:
        await message.answer(f"❌ Не удалось снять мут: {e}")

@dp.message(Command("setadmin"))
async def cmd_setadmin(message: Message, command: CommandObject):
    user = await get_user(user_id=message.from_user.id)
    if user['rank'] < 9 and message.from_user.id != OWNER_ID:
        return await message.answer("❌ Недостаточно прав.")

    if not command.args:
        return await message.answer("⚠️ Использование: <code>/setadmin @username</code>", parse_mode="HTML")

    target_username = clean_username(command.args.split()[0])
    target_user = await get_user(username=target_username)

    if target_user:
        await update_user(target_user['user_id'], rank=5, role="Admin")
        await message.answer(f"✅ Пользователю <b>@{target_username}</b> успешно выдана роль <b>Admin</b> (5 ранг)!", parse_mode="HTML")
    else:
        await message.answer(f"❌ Пользователь @{target_username} не найден в базе.", parse_mode="HTML")

@dp.message(Command("setrank"))
async def cmd_setrank(message: Message, command: CommandObject):
    user = await get_user(message.from_user.id)
    if user['rank'] < 9:
        return await message.answer("❌ Выдача рангов доступна только Главной Администрации (9+ ранг).")
    
    if not command.args:
        return await message.answer("⚠️ Использование: <code>/setrank [ID] [Ранг 1-10]</code>", parse_mode="HTML")
        
    args = command.args.split()
    if len(args) < 2 or not args[0].isdigit() or not args[1].isdigit():
        return await message.answer("❌ Укажите корректный ID и ранг (числа).")
        
    target_id, new_rank = int(args[0]), int(args[1])
    if not (1 <= new_rank <= 10):
        return await message.answer("❌ Ранг может быть от 1 до 10.")
        
    await update_user(target_id, rank=new_rank)
    await message.answer(f"✅ Пользователю <code>{target_id}</code> успешно установлен ранг {new_rank}!", parse_mode="HTML")

@dp.message(Command("give_money"))
async def cmd_give_money(message: Message, command: CommandObject):
    user = await get_user(user_id=message.from_user.id)
    if user['rank'] < 10:
        return await message.answer("❌ Команда доступна исключительно Владельцу (10 ранг).")

    if not command.args or len(command.args.split()) < 2:
        return await message.answer("⚠️ Использование: <code>/give_money @username 1000</code>", parse_mode="HTML")

    parts = command.args.split()
    target_username = clean_username(parts[0])
    
    if not parts[1].isdigit():
        return await message.answer("⚠️️ Укажите число монет цифрами.")
        
    amount = int(parts[1])
    row = await get_user(username=target_username)

    if not row:
        return await message.answer(f"❌ Пользователь @{target_username} не найден в базе данных!")

    target_id = row['user_id']
    new_coins = row['coins'] + amount
    await update_user(target_id, coins=new_coins)
    await add_donat_record(target_id, f"@{target_username}", "Покупка монет", f"+{amount} монет", "Админ Выдача")

    await message.answer(f"✅ Успешно выдано <b>{amount} монет</b> пользователю @{target_username}! (Новый баланс: {new_coins})", parse_mode="HTML")

# ==========================================
# 7. КАСТОМНЫЕ РОЛИ И МАГАЗИН
# ==========================================
@dp.message(Command("create_role"))
async def cmd_create_role(message: Message, command: CommandObject):
    user = await get_user(message.from_user.id)
    if user['rank'] < 5:
        return await message.answer("❌ Создание ролей доступно с 5+ ранга.")
        
    if not command.args:
        return await message.answer("⚠️ Использование: <code>/create_role [Текст роли] [#HEX_цвет] [Цена]</code>", parse_mode="HTML")
    
    pattern = r"\[(.*?)\]\s*\[(.*?)\]\s*\[(\d+)\]"
    match = re.search(pattern, command.args)
    
    if not match:
        return await message.answer("❌ Ошибка формата! Пример: <code>/create_role [VIP] [#FF0000] [5000]</code>", parse_mode="HTML")
        
    text, color, price = match.group(1), match.group(2), int(match.group(3))
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO custom_roles (creator_id, chat_id, text, color_code, price) VALUES (?, ?, ?, ?, ?)",
            (message.from_user.id, message.chat.id, text, color, price)
        )
        await db.commit()
        
    await message.answer(f"✅ Кастомная роль <b>{text}</b> создана и добавлена в магазин (/role_shop)!", parse_mode="HTML")

@dp.message(Command("role_shop", "shop"))
async def cmd_role_shop(message: Message):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT role_id, text, color_code, price FROM custom_roles WHERE chat_id = ?", (message.chat.id,)) as cursor:
            roles = await cursor.fetchall()
            
    if not roles:
        return await message.answer("🛍 В этом чате пока нет кастомных ролей.")
        
    text = "🛍 <b>Магазин кастомных ролей чата:</b>\n\n"
    kb = InlineKeyboardBuilder()
    
    for r in roles:
        role_id, r_text, r_color, r_price = r
        text += f"🔹 <b>{r_text}</b> (Цвет: <code>{r_color}</code>) — 🪙 {r_price} монет\n"
        kb.button(text=f"Купить: {r_text}", callback_data=f"buy_role_{role_id}")
        
    kb.adjust(1)
    await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("buy_role_"))
async def process_buy_role(callback: CallbackQuery):
    role_id = int(callback.data.split("_")[2])
    user = await get_user(callback.from_user.id)
    
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT text, price FROM custom_roles WHERE role_id = ?", (role_id,)) as cursor:
            role = await cursor.fetchone()
            
    if not role:
        return await callback.answer("❌ Роль больше не существует.", show_alert=True)
        
    r_text, r_price = role
    if user['coins'] < r_price:
        return await callback.answer(f"❌ Недостаточно монет! Нужен {r_price}, а у вас {user['coins']}.", show_alert=True)
        
    await update_user(callback.from_user.id, coins=user['coins'] - r_price, role=r_text)
    await callback.answer(f"🎉 Вы успешно купили роль '{r_text}'!", show_alert=True)
    await callback.message.answer(f"✅ Пользователь @{callback.from_user.username} приобрел роль <b>{r_text}</b>!", parse_mode="HTML")

# ==========================================
# 8. TELEGRAM STARS И ОПЛАТА ДОНАТОВ
# ==========================================
@dp.callback_query(F.data == "open_donate")
@dp.message(Command("vip"))
async def cmd_vip(event: Message | CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 VIP за ГРН", callback_data="buy_vip_uah")],
        [InlineKeyboardButton(text="⭐️ VIP за TG Stars", callback_data="buy_vip_stars")],
        [InlineKeyboardButton(text="💰 Купить монеты", callback_data="buy_money_menu")],
        [InlineKeyboardButton(text="❤️ Поддержать проект (/blago)", callback_data="blago_menu")]
    ])
    text = "✨ <b>Выберите категорию доната или покупки:</b>"
    if isinstance(event, CallbackQuery):
        await event.message.answer(text, reply_markup=kb, parse_mode="HTML")
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "buy_vip_stars")
async def process_vip_stars_menu(callback: CallbackQuery):
    buttons = []
    for key, data in PRICES_STARS.items():
        buttons.append([InlineKeyboardButton(text=data["text"], callback_data=f"select_stars_{key}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="open_donate")])
    await callback.message.edit_text("⭐️ <b>Выберите период VIP (Оплата TG Stars):</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

@dp.callback_query(F.data.startswith("select_stars_"))
async def process_stars_selection(callback: CallbackQuery):
    period = callback.data.split("_")[2]
    info = PRICES_STARS[period]

    title = f"VIP Подписка ({period} мес.)" if period != "forever" else "VIP Навсегда"
    prices = [LabeledPrice(label="VIP", amount=info["price"])]

    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title=title,
        description=f"Активация VIP-статуса в боте: {info['text']}",
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
        period_str = "Навсегда" if period == "forever" else f"{period} мес."
        await add_vip_time(user.id, period)

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO vip_history (user_id, username, price, currency, period, date) VALUES (?, ?, ?, ?, ?, ?)",
                (user.id, username, str(payment.total_amount), "звезд TG", period_str, now_str)
            )
            await db.commit()

        await message.answer(f"🎉 <b>Оплата прошла успешно!</b>\nВам активирован VIP-статус: <b>{period_str}</b>.", parse_mode="HTML")

    elif payload[0] == "buy" and payload[1] == "coins":
        coins_amt = int(payload[2])
        u = await get_user(user_id=user.id, username=user.username or "")
        await update_user(user.id, coins=u['coins'] + coins_amt)
        
        await add_donat_record(user.id, username, "Покупка монет", f"+{coins_amt} монет", f"{payment.total_amount} Stars")
        await message.answer(f"🎉 <b>Оплата прошла успешно!</b>\nВам начислено <b>{coins_amt} монет</b>.", parse_mode="HTML")

# ==========================================
# 9. РАССЫЛКА И МАССОВЫЕ УВЕДОМЛЕНИЯ
# ==========================================
@dp.message(Command("broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    if user['rank'] < 8:
        return await message.answer("❌ Рассылка доступна с 8+ ранга.")
        
    await state.set_state(BroadcastStates.waiting_for_text)
    await message.answer("📝 Отправьте сообщение (текст/фото/медиа) для рассылки всем пользователям.")

@dp.message(BroadcastStates.waiting_for_text)
async def process_broadcast_text(message: Message, state: FSMContext):
    await state.clear()
    
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users") as cursor:
            users = await cursor.fetchall()
            
    count = 0
    await message.answer("🚀 Запуск массовой рассылки...")
    for u in users:
        try:
            await message.copy_to(chat_id=u[0])
            count += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
            
    await message.answer(f"✅ Рассылка завершена! Сообщение получили {count} пользователей.")

# ==========================================
# 10. ЛОГИ И ИНФОРМАЦИЯ (/help, /books)
# ==========================================
@dp.message(Command("help"))
async def cmd_help(message: Message):
    user = await get_user(user_id=message.from_user.id, username=message.from_user.username or "")
    rank = user['rank']
    
    text = (
        "📜 <b>ПОЛНЫЙ СПИСОК КОМАНД БОТА</b>\n\n"
        "<b>🌍 1. Основные & Экономика & VIP:</b>\n"
        "• <code>/profile [@username]</code> — Просмотр профиля\n"
        "• <code>/vip</code> — Купить VIP-статус\n"
        "• <code>/bonus</code> — Ежедневный бонус\n"
        "• <code>/top</code> — Топ по монетам\n"
        "• <code>/duel [ставка]</code> — Дуэль на монеты\n"
        "• <code>/transfer [user] [кол-во]</code> — Перевод монет\n\n"
        "<b>🛡️ 2. Модерация:</b>\n"
        "• <code>/mute [мин]</code>, <code>/unmute</code> — Мут/Размут\n"
    )
    if rank >= 3:
        text += (
            "\n<b>👑 3. Руководство:</b>\n"
            "• <code>/setadmin @username</code> — Выдать права админа\n"
            "• <code>/setrank [ID] [Ранг]</code> — Выдать ранг\n"
            "• <code>/give_money @username [кол-во]</code> — Выдать монеты\n"
            "• <code>/broadcast</code> — Массовая рассылка\n"
            "• <code>/books</code>, <code>/book_global</code> — Системные логи\n"
        )
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("books"))
async def cmd_books(message: Message):
    user = await get_user(message.from_user.id)
    if user['rank'] < 6:
        return await message.answer("❌ Доступ к расширенным логам только с 6+ ранга.")
    
    await send_log_to_user(
        message.from_user.id, 
        f"📊 <b>РАСШИРЕННЫЙ ЛОГ ГРУППЫ {message.chat.title} ({message.chat.id}):</b>\nВсе системы работают штатно."
    )
    await message.answer("📖 Расширенные логи успешно отправлены вам в ЛС!")

@dp.message(Command("book_global"))
async def cmd_book_global(message: Message):
    user = await get_user(message.from_user.id)
    if user['rank'] < 8:
        return await message.answer("❌ Глобальные логи доступны с 8+ ранга.")
    
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as c1:
            total_users = (await c1.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM known_chats") as c2:
            total_chats = (await c2.fetchone())[0]
    
    log_text = (
        f"🌐 <b>ГЛОБАЛЬНЫЙ ЛОГ СИСТЕМЫ:</b>\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"💬 Чатов под контролем: {total_chats}\n"
        f"⏰ Время сервера: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    await send_log_to_user(message.from_user.id, log_text)
    await message.answer("🌐 Глобальный лог отправлен в ЛС!")

# ==========================================
# 11. ЗАПУСК БОТА (MAIN LOOP)
# ==========================================
async def main():
    await init_db()
    logging.info("🚀 Запуск Stars Manager Bot...")
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("🤖 Бот остановлен.")
