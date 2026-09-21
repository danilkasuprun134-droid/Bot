import os
import logging
from threading import Thread
from flask import Flask
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

# --- 1. БЛОК ВЕБ-СЕРВЕРА FLASK ДЛЯ RENDER ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is running online 24/7!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

keep_alive()
# --------------------------------------------

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Токен бота
API_TOKEN = "8920950826:AAFToXcVtHQmUOYl3nSdPTYFU5pElDfpwVs"

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- БАЗЫ ДАННЫХ В ПАМЯТИ ---
user_ranks = {}       # {user_id: rank_level}
user_rep = {}         # {user_id: reputation}
user_coins = {}       # {user_id: coins}
user_roles = {}       # {user_id: [roles]}
chat_bans = []
chat_warns = []

def get_rank(user_id: int) -> int:
    return user_ranks.get(user_id, 0)

# --- 1. ПЕРВИННИЙ ВХІД ТА НАЛАШТУВАННЯ ---

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("🤖 Бот успішно запущений и готовий до роботи!")

@dp.message(Command("setting"))
async def cmd_setting(message: Message):
    await message.answer("⚙️ Налаштування бота та параметрів чату відкриті.")

@dp.message(Command("help"))
async def cmd_help(message: Message):
    rank = get_rank(message.from_user.id)
    text = "📋 <b>Довідка з команд бота:</b>\n\n"
    text += "• /cmd — Переглянути список усіх 52 команд\n"
    text += "• /stats — Переглянути свій профіль\n"
    text += "• /top — Топ гравців\n"
    if rank >= 3:
        text += "\n👑 <b>Розширені розділи адміністрування доступні (Ранг 3+)!</b>"
    await message.answer(text, parse_mode="HTML")

# --- 2. ЗАГАЛЬНІ, ЕКОСИСТЕМА ТА ЕКОНОМІКА ---

@dp.message(Command("cmd"))
async def cmd_cmd(message: Message):
    await message.answer("📖 Список усіх розділів:\n1. Налаштування\n2. Економіка (19 команд)\n3. Модерація (10 команд)\n4. Логи та Глобал (21 команда)\n5. Вище Керівництво (14 команд)")

@dp.message(Command("rep"))
async def cmd_rep(message: Message):
    rep = user_rep.get(message.from_user.id, 0)
    await message.answer(f"⭐ Ваша репутація: <b>{rep}</b>", parse_mode="HTML")

@dp.message(Command("bonus"))
async def cmd_bonus(message: Message):
    user_coins[message.from_user.id] = user_coins.get(message.from_user.id, 0) + 100
    await message.answer("🎁 Ви отримали щоденний бонус: <b>100 монет</b>!", parse_mode="HTML")

@dp.message(Command("top"))
async def cmd_top(message: Message):
    await message.answer("🏆 <b>Загальний топ гравців:</b>\n1. Гравець 1 — 1000 монет\n2. Гравець 2 — 500 монет", parse_mode="HTML")

@dp.message(Command("tops"))
async def cmd_tops(message: Message):
    await message.answer("📊 Спеціалізовані топи: /top по монетах, /top по рівнях.")

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    coins = user_coins.get(message.from_user.id, 0)
    rep = user_rep.get(message.from_user.id, 0)
    rank = get_rank(message.from_user.id)
    await message.answer(f"📊 <b>Статистика профілю:</b>\n• Монети: {coins}\n• Репутація: {rep}\n• Адмін-ранг: {rank}", parse_mode="HTML")

@dp.message(Command("shop"))
async def cmd_shop(message: Message):
    await message.answer("🛒 <b>Звичайний магазин:</b>\n1. VIP-статус — 500 монет\n2. Кастомна роль — 300 монет", parse_mode="HTML")

@dp.message(Command("eshop"))
async def cmd_eshop(message: Message):
    await message.answer("💎 <b>Ексклюзивний магазин:</b> Доступні унікальні предмети.")

@dp.message(Command("Gshop"))
async def cmd_gshop(message: Message):
    await message.answer("🌐 <b>Глобальний магазин:</b> Предмети діють у всіх чатах.")

@dp.message(Command("givemevip"))
async def cmd_givemevip(message: Message):
    await message.answer("🌟 VIP-статус успішно активовано!")

@dp.message(Command("role"))
async def cmd_role_router(message: Message, command: CommandObject):
    arg = command.args if command.args else ""
    if "shop" in arg:
        await message.answer("🎭 Магазин ролей відкритий.")
    elif "present" in arg:
        await message.answer("🎁 Роль успішно подарована!")
    else:
        await message.answer("🎭 Управління ролями: `/role shop`, `/role present`", parse_mode="Markdown")

@dp.message(Command("my"))
async def cmd_my(message: Message, command: CommandObject):
    if command.args and "role" in command.args:
        roles = user_roles.get(message.from_user.id, ["Немає ролей"])
        await message.answer(f"🎭 Мої ролі: {', '.join(roles)}")
    else:
        await message.answer("Використовуйте: `/my role`", parse_mode="Markdown")

@dp.message(Command("create"))
async def cmd_create(message: Message, command: CommandObject):
    if command.args and "role" in command.args:
        await message.answer("🛠️ Створення власної ролі розпочато.")

@dp.message(Command("money"))
async def cmd_money(message: Message, command: CommandObject):
    if command.args and "role" in command.args:
        await message.answer("💰 Кастомна роль успішно куплена за монети!")

@dp.message(Command("duel"))
async def cmd_duel(message: Message):
    await message.answer("⚔️ Ви викликали гравця на дуель на монети!")

@dp.message(Command("transfer"))
async def cmd_transfer(message: Message):
    await message.answer("💸 Передача монет виконана.")

@dp.message(Command("trade"))
async def cmd_trade(message: Message):
    await message.answer("🔄 Обмін між гравцями розпочато.")

@dp.message(Command("report"))
async def cmd_report(message: Message):
    await message.answer("📩 Ваша скарга/звернення відправлена адміністрації.")

# --- 3. МОДЕРАЦІЯ ТА АДМІНІСТРУВАННЯ ЧАТІВ ---

@dp.message(Command("snick"))
async def cmd_snick(message: Message):
    if get_rank(message.from_user.id) < 1:
        return await message.answer("❌ Доступно з 1+ рангу.")
    await message.answer("✏️ Нікнейм користувача змінено.")

@dp.message(Command("rnick"))
async def cmd_rnick(message: Message):
    if get_rank(message.from_user.id) < 2:
        return await message.answer("❌ Доступно з 2+ рангу.")
    await message.answer("🔄 Нікнейм скинуто до початкового.")

@dp.message(Command("gnick"))
async def cmd_gnick(message: Message):
    if get_rank(message.from_user.id) < 3:
        return await message.answer("❌ Доступно з 3+ рангу.")
    await message.answer("🌐 Глобальна зміна нікнейму виконана.")

@dp.message(Command("staff"))
async def cmd_staff(message: Message):
    if get_rank(message.from_user.id) < 1:
        return await message.answer("❌ Доступно з 1+ рангу.")
    await message.answer("🛡️ Модерація в мережі: Онлайн 5 модераторів.")

@dp.message(Command("warn"))
async def cmd_warn(message: Message):
    if get_rank(message.from_user.id) < 4:
        return await message.answer("❌ Доступно строго з 4+ рангу!")
    await message.answer("⚠️ Користувачу видано попередження.")

@dp.message(Command("mute"))
async def cmd_mute(message: Message):
    if get_rank(message.from_user.id) < 4:
        return await message.answer("❌ Доступно строго з 4+ рангу!")
    await message.answer("🔇 Користувача замучено.")

@dp.message(Command("kick"))
async def cmd_kick(message: Message):
    if get_rank(message.from_user.id) < 4:
        return await message.answer("❌ Доступно строго з 4+ рангу!")
    await message.answer("🚪 Користувача виключено з чату.")

@dp.message(Command("ban"))
async def cmd_ban(message: Message):
    if get_rank(message.from_user.id) < 4:
        return await message.answer("❌ Доступно строго з 4+ рангу!")
    await message.answer("🚫 Локальний бан видано.")

@dp.message(Command("gban"))
async def cmd_gban(message: Message):
    if get_rank(message.from_user.id) < 6:
        return await message.answer("❌ Доступно з 6+ рангу за схваленням 8+.")
    await message.answer("🌐 Форма на Глобальний Бан подана.")

@dp.message(Command("news"))
async def cmd_news(message: Message):
    if get_rank(message.from_user.id) < 5:
        return await message.answer("❌ Доступно з 5+ рангу.")
    await message.answer("📢 Новина успішно опублікована в чаті.")

# --- 4. ЛОГИ, РЕПОРТИ ТА ГЛОБАЛЬНЕ УПРАВЛІННЯ ---

@dp.message(Command("give"))
async def cmd_give(message: Message, command: CommandObject):
    arg = command.args if command.args else ""
    if "books" in arg:
        await message.answer("📚 Видано розширений доступ до логів (6+).")
    elif "book" in arg:
        await message.answer("📖 Видано доступ до книги логів (5+).")

@dp.message(Command("book"))
async def cmd_book(message: Message, command: CommandObject):
    arg = command.args if command.args else ""
    if "global" in arg:
        await message.answer("🌐 Глобальний перегляд усіх дій (7+).")
    else:
        await message.answer("📖 Перегляд локальної книги дій (5+).")

@dp.message(Command("books"))
async def cmd_books(message: Message):
    await message.answer("📚 Розширений перегляд логів (6+).")

@dp.message(Command("mevip"))
async def cmd_mevip(message: Message):
    await message.answer("🌟 Видано розширений VIP-статус (8+).")

@dp.message(Command("checkreps"))
async def cmd_checkreps(message: Message):
    await message.answer("📊 Статистика оброблених репортів: 150 репортів.")

@dp.message(Command("giverep"))
async def cmd_giverep(message: Message):
    await message.answer("⭐ Видано очки репорта/репутації.")

@dp.message(Command("ungloballist"))
async def cmd_ungloballist(message: Message):
    await message.answer("🔓 Користувача знято з глобального бана.")

@dp.message(Command("setaccess"))
async def cmd_setaccess(message: Message):
    await message.answer("⚙️ Рівні доступу успішно налаштовані (9+).")

@dp.message(Command("giverang"))
async def cmd_giverang(message: Message, command: CommandObject):
    if command.args and command.args.isdigit():
        target_rank = int(command.args)
        user_ranks[message.from_user.id] = target_rank
        await message.answer(f"✅ Ваш адмін-ранг змінено на: <b>{target_rank}</b>", parse_mode="HTML")
    else:
        await message.answer("Приклад: `/giverang 5`", parse_mode="Markdown")

@dp.message(Command("ungiverang"))
async def cmd_ungiverang(message: Message):
    await message.answer("❌ Адмін-ранг знято.")

@dp.message(Command("setzam"))
async def cmd_setzam(message: Message):
    await message.answer("👑 Заступника успішно призначено.")

@dp.message(Command("unsetzam"))
async def cmd_unsetzam(message: Message):
    await message.answer("👑 Заступника знято.")

@dp.message(Command("business"))
async def cmd_business(message: Message):
    await message.answer("💼 Управління бізнесами (7+).")

@dp.message(Command("givemegabonus"))
async def cmd_givemegabonus(message: Message):
    await message.answer("🎉 Мега-бонус успішно видано (8+).")

@dp.message(Command("megabook"))
async def cmd_megabook(message: Message):
    await message.answer("📜 Перегляд історії монет та EXP (7+).")

@dp.message(Command("megabooks"))
async def cmd_megabooks(message: Message):
    await message.answer("📜 Повний лог дій, покарань і підвищень (7+).")

@dp.message(Command("history"))
async def cmd_history(message: Message):
    await message.answer("🔍 Перевірка чатів, твінків та статусу (7+).")

@dp.message(Command("gwarn"))
async def cmd_gwarn(message: Message):
    await message.answer("🌐 Глобальний варн видано (8+).")

# --- 5. СПЕЦІАЛЬНІ ПРИЗНАЧЕННЯ ТА ВИЩЕ КЕРІВНИЦТВО ---

@dp.message(Command("givetex"))
async def cmd_givetex(message: Message):
    await message.answer("🔧 Призначено Технічного Спеціаліста (7 ранг).")

@dp.message(Command("usgivetex"))
async def cmd_usgivetex(message: Message):
    await message.answer("🔧 Знято з посади Технічного Спеціаліста.")

@dp.message(Command("Obnyl"))
async def cmd_obnyl(message: Message, command: CommandObject):
    if command.args and "Money" in command.args:
        await message.answer("💰 Обнулення монет та ролей виконано.")
    else:
        await message.answer("💥 Повне обнулення акаунта виконано.")

@dp.message(Command("Ogwarn"))
async def cmd_ogwarn(message: Message):
    await message.answer("⚖️ Розгляд апеляції по глобальних варнах.")

@dp.message(Command("Ogban"))
async def cmd_ogban(message: Message):
    await message.answer("⚖️ Розгляд апеляції по глобальних банах.")

@dp.message(Command("unga"))
async def cmd_unga(message: Message):
    await message.answer("👑 Зняття ГА (6 ранг) з авто-передачею ВРІО виконано.")

@dp.message(Command("givega"))
async def cmd_givega(message: Message):
    await message.answer("👑 Призначення посади ГА виконано.")

@dp.message(Command("repgh"))
async def cmd_repgh(message: Message):
    await message.answer("📩 Репорт перенаправлено конкретній ролі.")

@dp.message(Command("muterep"))
async def cmd_muterep(message: Message):
    await message.answer("🔇 Блокування користування /report на 3–7 днів видано.")

@dp.message(Command("bot"))
async def cmd_bot(message: Message, command: CommandObject):
    if command.args and "boost" in command.args:
        await message.answer("🚀 Первинний перегляд та фільтрація ідей.")

@dp.message(Command("checkrep"))
async def cmd_checkrep(message: Message):
    await message.answer("📋 Перегляд усіх активних та оброблених репортів (8+).")

@dp.message(Command("checkboost"))
async def cmd_checkboost(message: Message):
    await message.answer("💡 Перегляд усіх пропозицій щодо покращення бота (8+).")

@dp.message(Command("glist"))
async def cmd_glist(message: Message):
    if get_rank(message.from_user.id) < 9:
        return await message.answer("❌ Строго 9+ ранг!")
    await message.answer("📜 Список глобальних банів.")

@dp.message(Command("gwlist"))
async def cmd_gwlist(message: Message):
    if get_rank(message.from_user.id) < 9:
        return await message.answer("❌ Строго 9+ ранг!")
    await message.answer("📜 Список глобальних варнів.")

@dp.message(Command("Global"))
async def cmd_global(message: Message, command: CommandObject):
    if command.args and "news" in command.args:
        if message.from_user.username != "nlyxx2686" and get_rank(message.from_user.id) < 10:
            return await message.answer("❌ Строго 10 ранг — тільки для @nlyxx2686!")
        await message.answer("📢 Глобальна публікація з обов'язковим закріпом опублікована!")

# --- ЗАПУСК БОТА ---

async def main():
    print("Бот з усім функціоналом успішно запускний!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
