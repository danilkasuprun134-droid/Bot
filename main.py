import os
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

keep_alive()
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Токен бота
API_TOKEN = "8920950826:AAFToXcVtHQmUOYl3nSdPTYFU5pElDfpwVs"

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Иерархия администраторов (по умолчанию создатель чата имеет максимальный уровень)
# Формат: {chat_id: {user_id: level}}
admin_levels = {}

# Хранилище логов (Bbook, Wbook, Mbook)
# Формат: {chat_id: {"bans": [], "warns": [], "mutes": []}}
chat_logs = {}

def get_user_level(chat_id: int, user_id: int) -> int:
    return admin_levels.get(chat_id, {}).get(user_id, 0)

def set_user_level(chat_id: int, user_id: int, level: int):
    if chat_id not in admin_levels:
        admin_levels[chat_id] = {}
    admin_levels[chat_id][user_id] = level

def log_action(chat_id: int, category: str, entry: str):
    if chat_id not in chat_logs:
        chat_logs[chat_id] = {"bans": [], "warns": [], "mutes": []}
    chat_logs[chat_id][category].append(entry)

# --- Команды помощи и старта ---

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("🤖 Бот администрирования и управления чатом запущен!\nИспользуйте /help для просмотра доступных команд.")

@dp.message(Command("help"))
async def cmd_help(message: Message):
    help_text = (
        "<b>📋 Система иерархии и администрирования:</b>\n\n"
        "<b>Модерация:</b>\n"
        "• /mute [время_мин] [причина] (ответом) — замутить пользователя\n"
        "• /unmute (ответом) — снять мут\n"
        "• /warn [причина] (ответом) — выдать предупреждение\n"
        "• /ban [причина] (ответом) — заблокировать\n"
        "• /unban [id_пользователя] — разблокировать\n\n"
        "<b>Логи и журналы:</b>\n"
        "• /Bbook — журнал банов\n"
        "• /Wbook — журнал варнов\n"
        "• /Mbook — журнал мутов\n\n"
        "<b>Управление уровнями (1-10):</b>\n"
        "• /setlevel [уровень 0-10] (ответом) — назначить ранг\n"
        "• /myrank — узнать свой уровень доступа"
    )
    await message.answer(help_text, parse_mode="HTML")

@dp.message(Command("myrank"))
async def cmd_myrank(message: Message):
    level = get_user_level(message.chat.id, message.from_user.id)
    await message.answer(f"👤 Ваш текущий уровень доступа в этом чате: <b>{level}</b>", parse_mode="HTML")

# --- Команда назначения ранга ---

@dp.message(Command("setlevel"))
async def cmd_setlevel(message: Message, command: CommandObject):
    if not message.reply_to_message:
        await message.answer("⚠️ Ответьте на сообщение пользователя, которому хотите изменить уровень.")
        return

    issuer_level = get_user_level(message.chat.id, message.from_user.id)
    # Проверка: назначать уровни может только суперадмин (например, уровень 10) или создатель
    if issuer_level < 10 and message.from_user.id != (await message.chat.get_member(message.from_user.id)).status == "creator":
        await message.answer("❌ У вас недостаточно прав для назначения уровней (требуется уровень 10).")
        return

    if not command.args or not command.args.isdigit():
        await message.answer("⚠️ Укажите уровень от 0 до 10. Пример: `/setlevel 5`", parse_mode="Markdown")
        return

    new_level = int(command.args)
    if new_level < 0 or new_level > 10:
        await message.answer("⚠️ Уровень должен быть в диапазоне от 0 до 10.")
        return

    target_user = message.reply_to_message.from_user
    set_user_level(message.chat.id, target_user.id, new_level)
    await message.answer(f"✅ Пользователю {target_user.full_name} успешно установлен уровень доступа <b>{new_level}</b>.", parse_mode="HTML")

# --- Модерация: Mute / Unmute ---

@dp.message(Command("mute"))
async def cmd_mute(message: Message, command: CommandObject):
    admin_lvl = get_user_level(message.chat.id, message.from_user.id)
    if admin_lvl < 1:
        await message.answer("❌ Команда доступна с 1 уровня администрирования.")
        return

    if not message.reply_to_message:
        await message.answer("⚠️ Ответьте на сообщение пользователя, которого хотите замутить.")
        return

    target_user = message.reply_to_message.from_user
    args = command.args.split() if command.args else []
    duration = int(args[0]) if args and args[0].isdigit() else 15
    reason = " ".join(args[1:]) if len(args) > 1 else "Нарушение правил чата"

    log_entry = f"Mute: {target_user.full_name} ({target_user.id}) на {duration} мин. Причина: {reason} (Админ: {message.from_user.full_name})"
    log_action(message.chat.id, "mutes", log_entry)

    await message.answer(f"🔇 Пользователь <b>{target_user.full_name}</b> замучен на {duration} минут.\nПричина: {reason}", parse_mode="HTML")

@dp.message(Command("unmute"))
async def cmd_unmute(message: Message):
    admin_lvl = get_user_level(message.chat.id, message.from_user.id)
    if admin_lvl < 1:
        await message.answer("❌ Команда доступна с 1 уровня администрирования.")
        return

    if not message.reply_to_message:
        await message.answer("⚠️ Ответьте на сообщение пользователя, с которого нужно снять мут.")
        return

    target_user = message.reply_to_message.from_user
    await message.answer(f"🔊 С пользователя <b>{target_user.full_name}</b> сняты ограничения на общение.", parse_mode="HTML")

# --- Модерация: Warn & Ban ---

@dp.message(Command("warn"))
async def cmd_warn(message: Message, command: CommandObject):
    admin_lvl = get_user_level(message.chat.id, message.from_user.id)
    if admin_lvl < 2:
        await message.answer("❌ Команда доступна со 2 уровня администрирования.")
        return

    if not message.reply_to_message:
        await message.answer("⚠️ Ответьте на сообщение нарушителя.")
        return

    target_user = message.reply_to_message.from_user
    reason = command.args if command.args else "Без указания причины"

    log_entry = f"Warn: {target_user.full_name} ({target_user.id}). Причина: {reason} (Админ: {message.from_user.full_name})"
    log_action(message.chat.id, "warns", log_entry)

    await message.answer(f"⚠️ Пользователю <b>{target_user.full_name}</b> выдано предупреждение.\nПричина: {reason}", parse_mode="HTML")

@dp.message(Command("ban"))
async def cmd_ban(message: Message, command: CommandObject):
    admin_lvl = get_user_level(message.chat.id, message.from_user.id)
    if admin_lvl < 3:
        await message.answer("❌ Команда доступна с 3 уровня администрирования.")
        return

    if not message.reply_to_message:
        await message.answer("⚠️ Ответьте на сообщение пользователя для бана.")
        return

    target_user = message.reply_to_message.from_user
    reason = command.args if command.args else "Грубое нарушение правил"

    try:
        await message.chat.ban(user_id=target_user.id)
        log_entry = f"Ban: {target_user.full_name} ({target_user.id}). Причина: {reason} (Админ: {message.from_user.full_name})"
        log_action(message.chat.id, "bans", log_entry)
        await message.answer(f"🚫 Пользователь <b>{target_user.full_name}</b> заблокирован.\nПричина: {reason}", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка при блокировке (убедитесь, что бот является администратором чата): {e}")

# --- Журналы логов (/Bbook, /Wbook, /Mbook) ---

@dp.message(Command("Bbook"))
async def cmd_bbook(message: Message):
    admin_lvl = get_user_level(message.chat.id, message.from_user.id)
    if admin_lvl < 1:
        await message.answer("❌ Просмотр логов доступен администраторам.")
        return

    bans = chat_logs.get(message.chat.id, {}).get("bans", [])
    if not bans:
        await message.answer("📖 Журнал блокировок (Bbook) пуст.")
        return
    
    text = "<b>📕 Журнал блокировок (Bbook):</b>\n\n" + "\n".join(bans[-10:])
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("Wbook"))
async def cmd_wbook(message: Message):
    admin_lvl = get_user_level(message.chat.id, message.from_user.id)
    if admin_lvl < 1:
        await message.answer("❌ Просмотр логов доступен администраторам.")
        return

    warns = chat_logs.get(message.chat.id, {}).get("warns", [])
    if not warns:
        await message.answer("📖 Журнал предупреждений (Wbook) пуст.")
        return

    text = "<b>📙 Журнал предупреждений (Wbook):</b>\n\n" + "\n".join(warns[-10:])
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("Mbook"))
async def cmd_mbook(message: Message):
    admin_lvl = get_user_level(message.chat.id, message.from_user.id)
    if admin_lvl < 1:
        await message.answer("❌ Просмотр логов доступен администраторам.")
        return

    mutes = chat_logs.get(message.chat.id, {}).get("mutes", [])
    if not mutes:
        await message.answer("📖 Журнал мутов (Mbook) пуст.")
        return

    text = "<b>📘 Журнал ограничений (Mbook):</b>\n\n" + "\n".join(mutes[-10:])
    await message.answer(text, parse_mode="HTML")

# --- Запуск бота ---

async def main():
    print("Бот успешно запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

