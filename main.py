import os
import logging
from threading import Thread
from flask import Flask
import asyncio

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    Message, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    CallbackQuery, 
    LabeledPrice, 
    PreCheckoutQuery
)

# --- 1. ВЕБ-СЕРВЕР FLASK ДЛЯ RENDER (24/7) ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is running online 24/7!"

@app.route('/healthz')
def healthz():
    return "OK", 200

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run, daemon=True)
    t.start()

keep_alive()
# --------------------------------------

logging.basicConfig(level=logging.INFO)

API_TOKEN = os.environ.get("BOT_TOKEN", "8920950826:AAFToXcVtHQmUOYl3nSdPTYFU5pElDfpwVs")
MONOBANK_JAR = "https://send.monobank.ua/jar/8wVnXzoF3f"
OWNER_USERNAME = "nlyxx2686"

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- ХРАНИЛИЩА ДАННЫХ (В ПАМЯТИ) ---
user_ranks = {}           # {user_id: int_rank}
user_roles = {}           # {user_id: [role_ids]} (например: 1, 2, 3, 4)
user_lang = {}            # {user_id: 'ru'|'ua'|'en'}
custom_aliases = {}       # {user_id: {alias: original_cmd}}
chat_rules = {}           # {chat_id: rules_text}
user_rep = {}             # {user_id: rep}
user_coins = {}           # {user_id: coins}
vip_users = {}            # {user_id: dict_info}
used_pleasevip = set()    # {user_id}

# Системы бана и заявок
aban_list = set()         # {user_id} — список заблокированных через /aban
reports_db = []
boost_ideas = []

# Активные заявки: 
# {req_id: {"type": "pvip"|"tc"|"unaban", "user_id": int, "username": str, ...}}
pending_requests = {}
# Голоса за снятие абан для ГА/ТС: {target_id: set(approver_ids)}
unaban_votes = {}


def get_rank(user_id: int, username: str = None) -> int:
    if username and username.lstrip('@').lower() == OWNER_USERNAME.lower():
        return 10
    return user_ranks.get(user_id, 0)

def get_user_roles(user_id: int) -> list:
    return user_roles.get(user_id, [])

def is_ts(user_id: int) -> bool:
    roles = get_user_roles(user_id)
    return 1 in roles or 2 in roles


# --- МИДДЛВАРЬ ДЛЯ БЛОКИРОВКИ ABAN ---
@dp.message.middleware()
async def aban_check_middleware(handler, event: Message, data):
    if event.from_user:
        user_id = event.from_user.id
        if user_id in aban_list:
            # Если пользователь забанен, разрешаем только команду /zadan для подачи заявки
            if event.text and event.text.startswith('/zadan'):
                return await handler(event, data)
            else:
                await event.answer("🚫 <b>Ваш доступ к боту заблокирован системой /aban!</b>\nПодайте заявку на снятие с помощью команды <code>/zadan</code>.", parse_mode="HTML")
                return
    return await handler(event, data)


# --- МИДДЛВАРЬ ДЛЯ КАСТОМНЫХ КОМАНД (/cmd) ---
@dp.message.middleware()
async def alias_middleware(handler, event: Message, data):
    if event.text and event.text.startswith('/'):
        user_id = event.from_user.id
        user_map = custom_aliases.get(user_id, {})
        parts = event.text.split(maxsplit=1)
        cmd_name = parts[0][1:]  # Убираем '/'
        
        if cmd_name in user_map:
            real_cmd = user_map[cmd_name]
            rest_args = " " + parts[1] if len(parts) > 1 else ""
            event.text = f"/{real_cmd}{rest_args}"
            
    return await handler(event, data)


# --- ОБРАБОТЧИК ДОБАВЛЕНИЯ БОТА В ГРУППУ ---
@dp.my_chat_member()
async def bot_added_to_group(event: types.ChatMemberUpdated):
    if event.new_chat_member.status in ["member", "administrator"]:
        inviter = event.from_user
        inviter_id = inviter.id
        inviter_username = inviter.username or inviter.full_name
        
        if get_rank(inviter_id, inviter.username) < 10:
            user_ranks[inviter_id] = 6
            try:
                await bot.send_message(
                    event.chat.id,
                    f"🎉 Спасибо за добавление бота в чат!\n"
                    f"👑 Пользователю @{inviter_username} автоматически выдан <b>6 ранг (ГА)</b>!",
                    parse_mode="HTML"
                )
            except Exception:
                pass


# ==========================================
# 1. ПЕРВИЧНЫЙ ВХОД И НАСТРОЙКИ
# ==========================================

@dp.message(Command("start"))
async def cmd_start(message: Message):
    chat_id = message.chat.id
    text = "🤖 Бот успешно запущен и готов к работе!"
    if chat_id in chat_rules:
        text += f"\n\n📜 <b>Правила чата:</b>\n{chat_rules[chat_id]}\n\n<i>Используя бота, вы автоматически соглашаетесь с правилами.</i>"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("setting"))
async def cmd_setting(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"),
        InlineKeyboardButton(text="🇺🇦 Українська", callback_data="lang_ua"),
        InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en")
    ]])
    await message.answer("🌐 Выберите язык бота / Оберіть мову бота / Select language:", reply_markup=kb)

@dp.callback_query(F.data.startswith("lang_"))
async def process_lang(callback: CallbackQuery):
    lang = callback.data.split("_")[1]
    user_lang[callback.from_user.id] = lang
    names = {"ru": "Русский", "ua": "Українська", "en": "English"}
    await callback.message.edit_text(f"✅ Язык изменен на: <b>{names[lang]}</b>", parse_mode="HTML")

@dp.message(Command("help"))
async def cmd_help(message: Message):
    text = "📋 <b>Полный список всех команд бота:</b>\n\n"
    text += "<b>1. Настройки:</b> /setting, /help, /help1..10\n"
    text += "<b>2. Защита от слива:</b> /aban (1+), /zadan (1+), /aadan (6+)\n"
    text += "<b>3. Экономика и VIP:</b> /buyvip, /pleasevip, /givesvips (10+), /rep, /bonus, /cmd, /top, /stats, /report\n"
    text += "<b>4. Модерация и ТС:</b> /tc, /zayavka (в ЛС), /giverang (5+)\n"
    text += "<b>5. Высшее руководство:</b> /repgh (8+), /Global news (10)\n\n"
    text += "💡 <i>Узнать доступные команды для уровня:</i> <code>/help1</code> ... <code>/help10</code>"
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text.regexp(r"^/help([1-9]|10)$"))
async def cmd_help_level(message: Message):
    lvl = int(message.text.replace("/help", ""))
    text = f"🛡️ <b>Команды, доступные для {lvl} ранга:</b>\n\n"
    
    if lvl >= 1: text += "• /aban (экстренная блокировка), /zadan (заявка на разбан)\n"
    if lvl >= 5: text += "• /giverang\n"
    if lvl >= 6: text += "• /aadan (просмотр заявок на разбан)\n"
    if lvl >= 8: text += "• /repgh\n"
    if lvl >= 10: text += "• /Global news, /givesvips\n"
    
    await message.answer(text, parse_mode="HTML")


# ==========================================
# 2. ЭКСТРЕННАЯ БЛОКИРОВКА И СНЯТИЕ (/aban, /zadan, /aadan)
# ==========================================

@dp.message(Command("aban"))
async def cmd_aban(message: Message, command: CommandObject):
    sender_id = message.from_user.id
    sender_rank = get_rank(sender_id, message.from_user.username)
    
    if sender_rank < 1:
        return await message.answer("❌ Экстренная блокировка доступна с 1 ранга.")
    
    target_id = None
    target_name = ""
    
    if message.reply_to_message:
        target_id = message.reply_to_message.from_user.id
        target_name = message.reply_to_message.from_user.full_name
    elif command.args:
        arg = command.args.split()[0]
        if arg.isdigit():
            target_id = int(arg)
            target_name = f"ID: {target_id}"
            
    if not target_id:
        return await message.answer("⚠️ <b>Использование:</b> ответьте на сообщение сливщика или введите: <code>/aban [user_id]</code>", parse_mode="HTML")
        
    if target_id == sender_id and sender_rank == 10:
        return await message.answer("❌ Создатель бота не может заблокировать сам себя!")

    aban_list.add(target_id)
    await message.answer(
        f"🚨 <b>СЛЕДСТВЕННАЯ ЗАЩИТА АКТИВИРОВАНА!</b>\n\n"
        f"Пользователю <b>{target_name}</b> (<code>{target_id}</code>) мгновенно заблокирован доступ ко всем функциям бота во избежание слива.\n"
        f"Для разблокировки пользователь должен подать заявку: <code>/zadan</code>.",
        parse_mode="HTML"
    )

@dp.message(Command("zadan"))
async def cmd_zadan(message: Message):
    user_id = message.from_user.id
    
    if user_id not in aban_list:
        return await message.answer("❌ Вы не находитесь в списке заблокированных (/aban).")
        
    req_id = f"unaban_{user_id}"
    if req_id in pending_requests:
        return await message.answer("⏳ Ваша заявка на снятие блокировки уже находится на рассмотрении!")

    rank = get_rank(user_id, message.from_user.username)
    user_is_ts = is_ts(user_id)
    
    pending_requests[req_id] = {
        "type": "unaban",
        "user_id": user_id,
        "username": message.from_user.username or message.from_user.full_name,
        "rank": rank,
        "is_ts": user_is_ts
    }
    
    await message.answer("📩 Ваша заявка на снятие экстренной блокировки создана и передана руководству!")
    
    # Оповещение модераторов
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Снять ABAN", callback_data=f"approve_unaban_{user_id}"),
        InlineKeyboardButton(text="❌ Оставить ABAN", callback_data=f"deny_unaban_{user_id}")
    ]])
    
    text = (
        f"🚨 <b>[ЗАЯВКА НА СНЯТИЕ ABAN]</b>\n\n"
        f"• Пользователь: @{message.from_user.username or 'без_юзернейма'}\n"
        f"• ID: <code>{user_id}</code>\n"
        f"• Ранг: <b>{rank}</b> | ТС: <b>{'Да' if user_is_ts else 'Нет'}</b>"
    )
    
    # Рассылка в зависимости от уровня забаненного
    notified = set()
    if rank < 6 and not user_is_ts:
        # Для <5 лвл: уведомляем ГА (6+) и ТС (роль 1,2)
        for uid, r in user_ranks.items():
            if r >= 6: notified.add(uid)
        for uid, roles in user_roles.items():
            if 1 in roles or 2 in roles: notified.add(uid)
    elif rank in [6, 7] or user_is_ts:
        # Для ГА/ТС: уведомляем роли 3 и 4
        for uid, roles in user_roles.items():
            if 3 in roles or 4 in roles: notified.add(uid)
    else:
        # Для 8+ лвл: уведомляем 8+ лвл
        for uid, r in user_ranks.items():
            if r >= 8: notified.add(uid)

    for admin_id in notified:
        try:
            await bot.send_message(admin_id, text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

@dp.message(Command("aadan"))
async def cmd_aadan(message: Message):
    if message.chat.type != "private":
        return await message.answer("❌ Команда `/aadan` работает <b>строго в ЛС бота</b>!", parse_mode="HTML")
        
    uid = message.from_user.id
    rank = get_rank(uid, message.from_user.username)
    roles = get_user_roles(uid)
    
    if rank < 6 and not is_ts(uid) and 3 not in roles and 4 not in roles:
        return await message.answer("❌ Доступ к проверке заявок на снятие ABAN запрещен.")
        
    count = 0
    await message.answer("🔍 <b>Проверка активных заявок на снятие ABAN...</b>", parse_mode="HTML")
    
    for req_id, req in list(pending_requests.items()):
        if req["type"] == "unaban":
            count += 1
            target_id = req["user_id"]
            votes = len(unaban_votes.get(target_id, set()))
            req_info = f" (Голосов от 3/4 ролей: {votes}/3)" if (req["rank"] in [6, 7] or req["is_ts"]) else ""
            
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅ Снять ABAN", callback_data=f"approve_unaban_{target_id}"),
                InlineKeyboardButton(text="❌ Оставить ABAN", callback_data=f"deny_unaban_{target_id}")
            ]])
            
            await message.answer(
                f"🚨 <b>Заявка от @{req['username']}</b> (ID: <code>{target_id}</code>)\n"
                f"Ранг: {req['rank']}{req_info}",
                reply_markup=kb,
                parse_mode="HTML"
            )
            
    if count == 0:
        await message.answer("🎉 Активных заявок на снятие ABAN нет!")

@dp.callback_query(F.data.startswith("approve_unaban_"))
async def process_approve_unaban(callback: CallbackQuery):
    admin_id = callback.from_user.id
    admin_rank = get_rank(admin_id, callback.from_user.username)
    admin_roles = get_user_roles(admin_id)
    
    target_id = int(callback.data.replace("approve_unaban_", ""))
    req_id = f"unaban_{target_id}"
    req = pending_requests.get(req_id)
    
    if not req:
        return await callback.answer("❌ Заявка не найдена или уже обработана.", show_alert=True)
        
    target_rank = req["rank"]
    target_is_ts = req["is_ts"]
    
    # Запрет снимать с себя
    if admin_id == target_id:
        return await callback.answer("❌ Нельзя одобрить снятие бана самому себе!", show_alert=True)

    # Логика 1: Для обычных пользователей (до 5 ранга) -> ГА (6+) или ТС
    if target_rank < 6 and not target_is_ts:
        if admin_rank < 6 and not is_ts(admin_id):
            return await callback.answer("❌ Для снятия требуется одобрение ГА (6+ ранг) или ТС!", show_alert=True)
            
        aban_list.discard(target_id)
        pending_requests.pop(req_id, None)
        try:
            await callback.bot.send_message(target_id, "🎉 <b>Ваш ABAN был успешно снят администратором!</b>", parse_mode="HTML")
        except Exception:
            pass
        return await callback.message.edit_text(f"✅ **ABAN снят** с пользователя <code>{target_id}</code>.", parse_mode="HTML")

    # Логика 2: Для ГА (6-7 ранг) или ТС -> требуется 3 одобрения от ролей 3 или 4
    elif target_rank in [6, 7] or target_is_ts:
        if 3 not in admin_roles and 4 not in admin_roles:
            return await callback.answer("❌ Для снятия ABAN с ГА/ТС требуется одобрение от владельцев 3 или 4 роли!", show_alert=True)
            
        voters = unaban_votes.setdefault(target_id, set())
        voters.add(admin_id)
        
        if len(voters) >= 3:
            aban_list.discard(target_id)
            pending_requests.pop(req_id, None)
            unaban_votes.pop(target_id, None)
            try:
                await callback.bot.send_message(target_id, "🎉 **Ваш ABAN был снят по решению 3 администраторов (3/4 роли)!**", parse_mode="HTML")
            except Exception:
                pass
            return await callback.message.edit_text(f"✅ **ABAN успешно снят!** Получено {len(voters)}/3 необходимых голосов.", parse_mode="HTML")
        else:
            return await callback.answer(f"✅ Ваш голос учтен! Запущено голосов: {len(voters)}/3", show_alert=True)

    # Логика 3: Для Руководства (8+ ранг) -> требуется одобрение 8+
    else:
        if admin_rank < 8:
            return await callback.answer("❌ Снять ABAN с руководства может только админ 8+ ранга!", show_alert=True)
            
        aban_list.discard(target_id)
        pending_requests.pop(req_id, None)
        try:
            await callback.bot.send_message(target_id, "🎉 **Ваш ABAN был снят Руководством!**", parse_mode="HTML")
        except Exception:
            pass
        return await callback.message.edit_text(f"✅ **ABAN снят** с руководителя <code>{target_id}</code>.", parse_mode="HTML")

@dp.callback_query(F.data.startswith("deny_unaban_"))
async def process_deny_unaban(callback: CallbackQuery):
    admin_id = callback.from_user.id
    admin_rank = get_rank(admin_id, callback.from_user.username)
    
    if admin_rank < 6 and not is_ts(admin_id):
        return await callback.answer("❌ У вас недостаточно прав для отклонения этой заявки.", show_alert=True)
        
    target_id = int(callback.data.replace("deny_unaban_", ""))
    req_id = f"unaban_{target_id}"
    
    pending_requests.pop(req_id, None)
    unaban_votes.pop(target_id, None)
    
    try:
        await callback.bot.send_message(target_id, "❌ Ваша заявка на снятие ABAN была отклонена.")
    except Exception:
        pass
        
    await callback.message.edit_text(f"❌ Заявка на снятие ABAN для <code>{target_id}</code> была отклонена.", parse_mode="HTML")


# ==========================================
# 3. ПОКУПКА VIP И СИСТЕМА VIP (/buyvip, /pleasevip, /givesvips)
# ==========================================

def get_buyvip_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇺🇦 За гривни (UAH)", callback_data="buyvip_currency_uah"),
            InlineKeyboardButton(text="⭐️ За звезды (Stars)", callback_data="buyvip_currency_stars")
        ]
    ])

def get_stars_tariffs_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 месяц — 30 ⭐️", callback_data="buyvip_stars_1m")],
        [InlineKeyboardButton(text="3 месяца — 60 ⭐️", callback_data="buyvip_stars_3m")],
        [InlineKeyboardButton(text="6 месяцев — 90 ⭐️", callback_data="buyvip_stars_6m")],
        [InlineKeyboardButton(text="12 месяцев — 160 ⭐️", callback_data="buyvip_stars_12m")],
        [InlineKeyboardButton(text="♾ Навсегда — 650 ⭐️", callback_data="buyvip_stars_forever")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="buyvip_back")]
    ])

@dp.message(Command("buyvip"))
async def cmd_buyvip(message: Message):
    text = (
        "🌟 <b>Покупка VIP-статуса</b>\n\n"
        "Выберите удобный способ оплаты:\n"
        "• <b>UAH (Гривны)</b> — перевод на банку Monobank\n"
        "• <b>Stars (Звезды)</b> — оплата напрямую в Telegram"
    )
    await message.answer(text, reply_markup=get_buyvip_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "buyvip_currency_uah")
async def process_vip_uah(callback: CallbackQuery):
    text = (
        "💳 <b>Оплата VIP через Monobank (UAH)</b>\n\n"
        "<b>Тарифы:</b>\n"
        "• 1 месяц — <b>20 грн</b>\n"
        "• 3 месяца — <b>50 грн</b>\n"
        "• 6 месяцев — <b>85 грн</b>\n"
        "• 12 месяцев — <b>140 грн</b>\n"
        "• ♾ Навсегда — <b>500 грн</b>\n\n"
        "⚠️ <b>ОБЯЗАТЕЛЬНО:</b> В комментарии к переводу укажите ваш <b>@username</b>, "
        "иначе вы не сможете получить VIP!\n\n"
        f"🔗 <b>Ссылка на банку Monobank:</b>\n{MONOBANK_JAR}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Перейти в банку Monobank", url=MONOBANK_JAR)],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="buyvip_back")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "buyvip_currency_stars")
async def process_vip_stars(callback: CallbackQuery):
    await callback.message.edit_text("⭐️ <b>Выберите тариф за Telegram Stars:</b>", reply_markup=get_stars_tariffs_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "buyvip_back")
async def process_vip_back(callback: CallbackQuery):
    text = (
        "🌟 <b>Покупка VIP-статуса</b>\n\n"
        "Выберите удобный способ оплаты:"
    )
    await callback.message.edit_text(text, reply_markup=get_buyvip_kb(), parse_mode="HTML")

# --- Оплата звездами ---
STARS_PRICES = {
    "buyvip_stars_1m": ("VIP на 1 месяц", 30),
    "buyvip_stars_3m": ("VIP на 3 месяца", 60),
    "buyvip_stars_6m": ("VIP на 6 месяцев", 90),
    "buyvip_stars_12m": ("VIP на 12 месяцев", 160),
    "buyvip_stars_forever": ("VIP Навсегда", 650)
}

@dp.callback_query(F.data.in_(STARS_PRICES.keys()))
async def process_stars_invoice(callback: CallbackQuery):
    title, stars_amount = STARS_PRICES[callback.data]
    prices = [LabeledPrice(label=title, amount=stars_amount)]
    
    await callback.bot.send_invoice(
        chat_id=callback.from_user.id,
        title=title,
        description=f"Приобретение {title} за {stars_amount} Telegram Stars",
        payload=f"vip_stars_{callback.data}",
        provider_token="",
        currency="XTR",
        prices=prices
    )
    await callback.answer()

@dp.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)

@dp.message(F.successful_payment)
async def process_successful_payment(message: Message):
    vip_users[message.from_user.id] = {"type": "paid"}
    await message.answer("🎉 <b>Оплата прошла успешно! VIP-статус активирован!</b>", parse_mode="HTML")

@dp.message(Command("givesvips"))
async def cmd_givesvips(message: Message, command: CommandObject):
    if get_rank(message.from_user.id, message.from_user.username) < 10:
        return await message.answer("❌ Выдача VIP вручную доступна только администраторам 10+ ранга.")
    
    if not command.args or len(command.args.split()) < 2:
        return await message.answer(
            "⚠️ <b>Использование:</b>\n"
            "<code>/givesvips @username [месяцев (1-12) или forever]</code>\n\n"
            "Пример: <code>/givesvips @durov 3</code> или <code>/givesvips @durov forever</code>",
            parse_mode="HTML"
        )
    
    args = command.args.split()
    target_username = args[0]
    period = args[1].lower()
    
    if period == "forever":
        duration_str = "навсегда"
    elif period.isdigit() and 1 <= int(period) <= 12:
        duration_str = f"на {period} мес."
    else:
        return await message.answer("❌ Укажите количество месяцев от 1 до 12 или слово <code>forever</code>.", parse_mode="HTML")
    
    await message.answer(f"✅ Пользователю <b>{target_username}</b> успешно выдан VIP-статус {duration_str}!", parse_mode="HTML")

@dp.message(Command("pleasevip"))
async def cmd_pleasevip(message: Message):
    user_id = message.from_user.id
    
    if user_id in used_pleasevip:
        return await message.answer("❌ Вы уже использовали бесплатный пробный VIP-статус!")
    
    req_id = f"pvip_{user_id}"
    pending_requests[req_id] = {
        "type": "pvip",
        "user_id": user_id,
        "username": message.from_user.username or message.from_user.full_name
    }
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Одобрить VIP (5 дней)", callback_data=f"approve_pvip_{user_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"deny_pvip_{user_id}")
    ]])
    
    await message.answer("📩 Ваша заявка на бесплатный VIP (5 дней) отправлена администраторам в ЛС.")
    
    for admin_id, rank in user_ranks.items():
        if rank >= 8:
            try:
                await bot.send_message(
                    admin_id,
                    f"🔔 <b>[Заявка на VIP (5 дней)]</b>\n\n"
                    f"• Пользователь: @{message.from_user.username or 'без_юзернейма'}\n"
                    f"• ID: <code>{user_id}</code>",
                    reply_markup=kb,
                    parse_mode="HTML"
                )
            except Exception:
                pass


# ==========================================
# 4. СИСТЕМА ЗАЯВОК НА ТС (/tc) И КУРАТОРСКАЯ КОМАНДА /zayavka
# ==========================================

@dp.message(Command("tc"))
async def cmd_tc(message: Message, command: CommandObject):
    if not command.args:
        return await message.answer("⚠️ Использование: `/tc @username` (подать заявку на ТС)", parse_mode="Markdown")
    
    target_username = command.args.strip()
    user_id = message.from_user.id
    req_id = f"tc_{user_id}_{target_username.replace('@', '')}"
    
    pending_requests[req_id] = {
        "type": "tc",
        "user_id": user_id,
        "username": message.from_user.username or message.from_user.full_name,
        "target_username": target_username
    }
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Согласиться", callback_data=f"approve_tc_{req_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"deny_tc_{req_id}")
    ]])
    
    await message.answer("📩 Ваша заявка на ТС успешно отправлена руководству в ЛС!")
    
    notified_users = set()
    for uid, rank in user_ranks.items():
        if rank >= 8:
            notified_users.add(uid)
            
    for uid, roles in user_roles.items():
        if 1 in roles or 2 in roles:
            notified_users.add(uid)
            
    for target_id in notified_users:
        try:
            await bot.send_message(
                target_id,
                f"🔔 <b>[Новая заявка на ТС]</b>\n\n"
                f"• Подал: @{message.from_user.username or user_id}\n"
                f"• Назначить ТС для: <b>{target_username}</b>",
                reply_markup=kb,
                parse_mode="HTML"
            )
        except Exception:
            pass

@dp.message(Command("zayavka"))
async def cmd_zayavka(message: Message):
    if message.chat.type != "private":
        return await message.answer("❌ Команда `/zayavka` работает <b>строго в ЛС бота</b>!", parse_mode="HTML")
    
    user_id = message.from_user.id
    rank = get_rank(user_id, message.from_user.username)
    roles = get_user_roles(user_id)
    
    can_review_pvip = (rank >= 8)
    can_review_tc = (rank >= 8 or 1 in roles or 2 in roles or rank in [9, 10])
    
    if not (can_review_pvip or can_review_tc):
        return await message.answer("❌ У вас нет доступа к просмотру активных заявок.")
    
    text = "📥 <b>Список всех доступных заявок на одобрение:</b>\n\n"
    count = 0
    
    for req_id, req in list(pending_requests.items()):
        if req["type"] == "pvip" and can_review_pvip:
            count += 1
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_pvip_{req['user_id']}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"deny_pvip_{req['user_id']}")
            ]])
            await message.answer(f"🔹 <b>VIP (5 дней)</b> от @{req['username']} (ID: <code>{req['user_id']}</code>)", reply_markup=kb, parse_mode="HTML")
            
        elif req["type"] == "tc" and can_review_tc:
            count += 1
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅ Согласиться", callback_data=f"approve_tc_{req_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"deny_tc_{req_id}")
            ]])
            await message.answer(f"🔹 <b>Заявка на ТС</b> от @{req['username']} для <b>{req['target_username']}</b>", reply_markup=kb, parse_mode="HTML")
            
    if count == 0:
        await message.answer("🎉 Нет активных заявок для вашего уровня доступа!")

@dp.callback_query(F.data.startswith("approve_pvip_"))
async def process_approve_pvip(callback: CallbackQuery):
    if get_rank(callback.from_user.id, callback.from_user.username) < 8:
        return await callback.answer("❌ Одобрять заявки могут только администраторы 8+ ранга!", show_alert=True)
    
    target_id = int(callback.data.replace("approve_pvip_", ""))
    used_pleasevip.add(target_id)
    vip_users[target_id] = {"type": "trial_5d"}
    pending_requests.pop(f"pvip_{target_id}", None)
    
    try:
        await callback.bot.send_message(target_id, "🎉 <b>Ваша заявка одобрена!</b> Вам выдан VIP-статус на 5 дней.", parse_mode="HTML")
    except Exception:
        pass
        
    await callback.message.edit_text(f"✅ <b>Заявка одобрена!</b> Пользователю (ID: <code>{target_id}</code>) выдан VIP на 5 дней.", parse_mode="HTML")

@dp.callback_query(F.data.startswith("deny_pvip_"))
async def process_deny_pvip(callback: CallbackQuery):
    if get_rank(callback.from_user.id, callback.from_user.username) < 8:
        return await callback.answer("❌ Отклонять заявки могут только администраторы 8+ ранга!", show_alert=True)
    
    target_id = int(callback.data.replace("deny_pvip_", ""))
    pending_requests.pop(f"pvip_{target_id}", None)
    
    try:
        await callback.bot.send_message(target_id, "❌ Ваша заявка на бесплатный VIP была отклонена.")
    except Exception:
        pass
        
    await callback.message.edit_text(f"❌ Заявка пользователя (ID: <code>{target_id}</code>) отклонена.", parse_mode="HTML")

@dp.callback_query(F.data.startswith("approve_tc_"))
async def process_approve_tc(callback: CallbackQuery):
    uid = callback.from_user.id
    rank = get_rank(uid, callback.from_user.username)
    roles = get_user_roles(uid)
    
    if not (rank >= 8 or 1 in roles or 2 in roles or rank in [9, 10]):
        return await callback.answer("❌ У вас нет прав для одобрения заявки на ТС!", show_alert=True)
    
    req_id = callback.data.replace("approve_tc_", "")
    req_data = pending_requests.pop(req_id, None)
    
    target_str = req_data['target_username'] if req_data else "пользователя"
    if req_data:
        try:
            await callback.bot.send_message(req_data['user_id'], f"🎉 <b>Ваша заявка на ТС для {target_str} была ОДОБРЕНА!</b>", parse_mode="HTML")
        except Exception:
            pass
            
    await callback.message.edit_text(f"✅ <b>Заявка на ТС для {target_str} СОГЛАСОВАНА!</b>", parse_mode="HTML")

@dp.callback_query(F.data.startswith("deny_tc_"))
async def process_deny_tc(callback: CallbackQuery):
    uid = callback.from_user.id
    rank = get_rank(uid, callback.from_user.username)
    roles = get_user_roles(uid)
    
    if not (rank >= 8 or 1 in roles or 2 in roles or rank in [9, 10]):
        return await callback.answer("❌ У вас нет прав для отклонения заявки на ТС!", show_alert=True)
    
    req_id = callback.data.replace("deny_tc_", "")
    req_data = pending_requests.pop(req_id, None)
    
    target_str = req_data['target_username'] if req_data else "пользователя"
    if req_data:
        try:
            await callback.bot.send_message(req_data['user_id'], f"❌ <b>Ваша заявка на ТС для {target_str} была ОТКЛОНЕНА.</b>", parse_mode="HTML")
        except Exception:
            pass
            
    await callback.message.edit_text(f"❌ <b>Заявка на ТС для {target_str} ОТКЛОНЕНА.</b>", parse_mode="HTML")


# ==========================================
# 5. ЭКОНОМИКА, МОДЕРАЦИЯ И ДРУГИЕ КОМАНДЫ
# ==========================================

@dp.message(Command("cmd"))
async def cmd_custom_alias(message: Message, command: CommandObject):
    if not command.args or len(command.args.split()) < 2:
        return await message.answer("⚠️ Персональная настройка команды.\nПример: `/cmd stats s` (теперь `/s` вызовет `/stats`)", parse_mode="Markdown")
    
    orig_cmd, new_alias = command.args.split()[:2]
    custom_aliases.setdefault(message.from_user.id, {})[new_alias.lstrip('/')] = orig_cmd.lstrip('/')
    await message.answer(f"✅ Успешно! Теперь команда `/{new_alias.lstrip('/')}` вызывает `/{orig_cmd.lstrip('/')}`.", parse_mode="Markdown")

@dp.message(Command("rep"))
async def cmd_rep(message: Message):
    rep = user_rep.get(message.from_user.id, 0)
    await message.answer(f"⭐ Ваша репутация: <b>{rep}</b>", parse_mode="HTML")

@dp.message(Command("bonus"))
async def cmd_bonus(message: Message):
    user_coins[message.from_user.id] = user_coins.get(message.from_user.id, 0) + 100
    await message.answer("🎁 Вы получили ежедневный бонус: <b>100 монет</b>!", parse_mode="HTML")

@dp.message(Command("top"))
async def cmd_top(message: Message):
    await message.answer("🏆 <b>Общий топ игроков:</b>\n1. Игрок 1 — 1000 монет", parse_mode="HTML")

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    coins = user_coins.get(message.from_user.id, 0)
    rep = user_rep.get(message.from_user.id, 0)
    rank = get_rank(message.from_user.id, message.from_user.username)
    await message.answer(f"📊 <b>Статистика профиля:</b>\n• Монеты: {coins}\n• Репутация: {rep}\n• Админ-ранг: {rank}", parse_mode="HTML")

@dp.message(Command("report"))
async def cmd_report(message: Message, command: CommandObject):
    if command.args:
        reports_db.append({"user": message.from_user.id, "text": command.args})
        await message.answer("📩 Ваша жалоба/обращение отправлено администрации.")
    else:
        await message.answer("Используйте: `/report [текст жалобы]`", parse_mode="Markdown")

@dp.message(Command("giverang"))
async def cmd_giverang(message: Message, command: CommandObject):
    if command.args and command.args.isdigit():
        target_rank = int(command.args)
        user_ranks[message.from_user.id] = target_rank
        await message.answer(f"✅ Ваш админ-ранг изменен на: <b>{target_rank}</b>", parse_mode="HTML")
    else:
        await message.answer("Пример: `/giverang 5`", parse_mode="Markdown")

@dp.message(Command("repgh"))
async def cmd_repgh(message: Message, command: CommandObject):
    if get_rank(message.from_user.id, message.from_user.username) < 8: 
        return await message.answer("❌ Доступно с 8+ ранга.")
    if command.args and command.args.isdigit():
        role_id = int(command.args)
        user_roles.setdefault(message.from_user.id, []).append(role_id)
        await message.answer(f"📩 Вам выдана специальная роль <b>({role_id})</b>.", parse_mode="HTML")
    else:
        await message.answer("Пример: `/repgh 1` (выдать себе роль 1)", parse_mode="Markdown")

@dp.message(Command("Global"))
async def cmd_global(message: Message, command: CommandObject):
    if command.args and "news" in command.args:
        if get_rank(message.from_user.id, message.from_user.username) < 10:
            return await message.answer("❌ Строго 10 ранг!")
        
        rules_text = command.args.replace("news", "").strip() or "Создание твинков — Глобальный бан."
        chat_rules[message.chat.id] = rules_text
        await message.answer(f"⚙️ <b>Глобальные правила установлены:</b>\n\n{rules_text}", parse_mode="HTML")


# ==========================================
# ЗАПУСК БОТА
# ==========================================

async def main():
    print("🤖 Бот успешно запущен и готов обрабатывать заявки!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
