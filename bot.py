import json
import os
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
import asyncio

# ========== ТОКЕН БЕРЁТСЯ ИЗ ПЕРЕМЕННОЙ ОКРУЖЕНИЯ (НЕ СВЕТИТСЯ В КОДЕ) ==========
TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise Exception("❌ Ошибка: переменная окружения TELEGRAM_TOKEN не задана!")

# Рабочие часы по умолчанию
DEFAULT_START_HOUR = 10
DEFAULT_END_HOUR = 17
STEP_HOURS = 1

DATA_FILE = "bookings.json"
SETTINGS_FILE = "settings.json"
# =============================================================================

def load_data(filename):
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_free_slots(date_str, settings):
    bookings = load_data(DATA_FILE)
    end_hour = settings.get("custom_end_hour", DEFAULT_END_HOUR)
    free = []
    for hour in range(DEFAULT_START_HOUR, end_hour + STEP_HOURS, STEP_HOURS):
        slot = f"{date_str} {hour:02d}:00"
        if slot not in bookings:
            free.append(f"{hour:02d}:00")
    return free

bot = Bot(token=TOKEN)
dp = Dispatcher()

def get_date_buttons():
    builder = InlineKeyboardBuilder()
    today = datetime.now().strftime("%Y-%m-%d")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    day_after = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
    builder.button(text="📅 Сегодня", callback_data=f"date_{today}")
    builder.button(text="📅 Завтра", callback_data=f"date_{tomorrow}")
    builder.button(text="📅 Послезавтра", callback_data=f"date_{day_after}")
    builder.adjust(1)
    return builder.as_markup()

def get_time_buttons(date_str, free_slots):
    builder = InlineKeyboardBuilder()
    for slot in free_slots:
        builder.button(text=slot, callback_data=f"time_{date_str}_{slot}")
    builder.adjust(2)
    return builder.as_markup()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    settings = load_data(SETTINGS_FILE)
    if "master_id" not in settings:
        settings["master_id"] = message.from_user.id
        save_data(SETTINGS_FILE, settings)
        await message.answer(
            "👑 Вы назначены мастером этого бота!\n\n"
            "Команды для управления:\n"
            "/admin - панель управления\n"
            "/stop_today - закрыть запись на сегодня\n"
            "/resume_today - открыть запись на сегодня\n"
            "/work_until 15 - работать до 15:00\n"
            "/all_bookings - все записи\n"
            "/broadcast текст - отправить сообщение всем клиентам"
        )
    master_id = settings.get("master_id")
    status_text = ""
    if not settings.get("is_working", True):
        status_text = "\n⚠️ МАСТЕР ВРЕМЕННО НЕ ПРИНИМАЕТ ЗАПИСИ"
    elif settings.get("stop_today"):
        status_text = "\n⚠️ НА СЕГОДНЯ ЗАПИСЬ ЗАКРЫТА"
    await message.answer(
        f"💅 Маникюрный салон{status_text}\n\n"
        f"⏰ Часы работы: {DEFAULT_START_HOUR}:00 - {settings.get('custom_end_hour', DEFAULT_END_HOUR)}:00\n"
        f"📌 Запись на сегодня, завтра, послезавтра\n\n"
        f"👇 Нажмите, чтобы записаться:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Записаться", callback_data="book")]
        ])
    )

@dp.callback_query(lambda c: c.data == "book")
async def choose_date(callback: types.CallbackQuery):
    settings = load_data(SETTINGS_FILE)
    if not settings.get("is_working", True):
        await callback.answer("❌ Мастер не принимает записи", show_alert=True)
        return
    await callback.message.edit_text("Выберите дату:", reply_markup=get_date_buttons())
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("date_"))
async def choose_time(callback: types.CallbackQuery):
    date_str = callback.data.split("_")[1]
    settings = load_data(SETTINGS_FILE)
    if settings.get("stop_today") and date_str == datetime.now().strftime("%Y-%m-%d"):
        await callback.message.edit_text("❌ Сегодня запись закрыта. Выберите другую дату:", reply_markup=get_date_buttons())
        await callback.answer()
        return
    free_slots = get_free_slots(date_str, settings)
    if not free_slots:
        await callback.message.edit_text("❌ Нет свободных часов. Попробуйте другую дату:", reply_markup=get_date_buttons())
        await callback.answer()
        return
    await callback.message.edit_text(f"📅 {date_str}\nВыберите время:", reply_markup=get_time_buttons(date_str, free_slots))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("time_"))
async def make_booking(callback: types.CallbackQuery):
    _, date_str, slot_time = callback.data.split("_")
    full_slot = f"{date_str} {slot_time}"
    settings = load_data(SETTINGS_FILE)
    if settings.get("stop_today") and date_str == datetime.now().strftime("%Y-%m-%d"):
        await callback.answer("❌ Сегодня запись закрыта", show_alert=True)
        return
    bookings = load_data(DATA_FILE)
    if full_slot in bookings:
        free_slots = get_free_slots(date_str, settings)
        if free_slots:
            await callback.message.edit_text(
                f"❌ Время {slot_time} уже занято.\n\nДоступные слоты на {date_str}:",
                reply_markup=get_time_buttons(date_str, free_slots)
            )
        else:
            await callback.message.edit_text(f"❌ Время {slot_time} занято. Выберите другую дату:", reply_markup=get_date_buttons())
        await callback.answer("Это время уже занято", show_alert=True)
        return
    bookings[full_slot] = {
        "user_id": callback.from_user.id,
        "username": callback.from_user.full_name,
        "user_tag": f"@{callback.from_user.username}" if callback.from_user.username else "без username",
        "booked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    save_data(DATA_FILE, bookings)
    await callback.message.edit_text(f"✅ Вы записаны на {full_slot}!\nОтменить: /my_bookings")
    master_id = load_data(SETTINGS_FILE).get("master_id")
    if master_id:
        await bot.send_message(
            master_id,
            f"🆕 НОВАЯ ЗАПИСЬ!\n\n"
            f"👤 {callback.from_user.full_name}\n"
            f"🕒 {full_slot}\n"
            f"📱 {callback.from_user.username or 'нет username'}\n"
            f"🆔 ID: {callback.from_user.id}"
        )
    await callback.answer()

@dp.message(Command("my_bookings"))
async def show_my_bookings(message: types.Message):
    bookings = load_data(DATA_FILE)
    my_slots = [slot for slot, info in bookings.items() if info["user_id"] == message.from_user.id]
    if not my_slots:
        await message.answer("У вас нет активных записей.")
        return
    text = "📋 Ваши записи:\n\n"
    kb = InlineKeyboardBuilder()
    for slot in my_slots:
        text += f"• {slot}\n"
        kb.button(text=f"❌ Отменить {slot}", callback_data=f"cancel_{slot}")
    kb.adjust(1)
    await message.answer(text, reply_markup=kb.as_markup())

@dp.callback_query(lambda c: c.data.startswith("cancel_"))
async def cancel_my_booking(callback: types.CallbackQuery):
    slot = callback.data.split("_", 1)[1]
    bookings = load_data(DATA_FILE)
    if slot in bookings and bookings[slot]["user_id"] == callback.from_user.id:
        del bookings[slot]
        save_data(DATA_FILE, bookings)
        await callback.message.edit_text(f"❌ Запись на {slot} отменена.")
        master_id = load_data(SETTINGS_FILE).get("master_id")
        if master_id:
            await bot.send_message(master_id, f"🗑 {callback.from_user.full_name} отменил запись на {slot}")
    else:
        await callback.answer("Запись не найдена", show_alert=True)
    await callback.answer()

def is_master(user_id):
    settings = load_data(SETTINGS_FILE)
    return settings.get("master_id") == user_id

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if not is_master(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора.")
        return
    settings = load_data(SETTINGS_FILE)
    status = "✅ РАБОТАЮ" if settings.get("is_working", True) else "❌ НЕ РАБОТАЮ"
    stop_today = "🛑 СЕГОДНЯ ЗАКРЫТА" if settings.get("stop_today") else "✅ СЕГОДНЯ ОТКРЫТА"
    end_hour = settings.get("custom_end_hour", DEFAULT_END_HOUR)
    await message.answer(
        f"🔧 АДМИН-ПАНЕЛЬ\n\n"
        f"Статус: {status}\n"
        f"Сегодня: {stop_today}\n"
        f"Работаю до: {end_hour}:00\n\n"
        f"📌 Команды:\n"
        f"/stop_today - закрыть запись на сегодня\n"
        f"/resume_today - открыть запись на сегодня\n"
        f"/work_until 15 - работать до 15:00\n"
        f"/off - ВЫКЛЮЧИТЬ бот\n"
        f"/on - ВКЛЮЧИТЬ бот\n"
        f"/all_bookings - список всех записей\n"
        f"/broadcast текст - отправить всем клиентам"
    )

@dp.message(Command("stop_today"))
async def cmd_stop_today(message: types.Message):
    if not is_master(message.from_user.id):
        return
    settings = load_data(SETTINGS_FILE)
    settings["stop_today"] = True
    save_data(SETTINGS_FILE, settings)
    await message.answer("🛑 Запись на СЕГОДНЯ закрыта.")

@dp.message(Command("resume_today"))
async def cmd_resume_today(message: types.Message):
    if not is_master(message.from_user.id):
        return
    settings = load_data(SETTINGS_FILE)
    settings["stop_today"] = False
    save_data(SETTINGS_FILE, settings)
    await message.answer("✅ Запись на сегодня открыта.")

@dp.message(Command("off"))
async def cmd_off(message: types.Message):
    if not is_master(message.from_user.id):
        return
    settings = load_data(SETTINGS_FILE)
    settings["is_working"] = False
    save_data(SETTINGS_FILE, settings)
    await message.answer("❌ Бот выключен. Клиенты не могут записаться.")

@dp.message(Command("on"))
async def cmd_on(message: types.Message):
    if not is_master(message.from_user.id):
        return
    settings = load_data(SETTINGS_FILE)
    settings["is_working"] = True
    save_data(SETTINGS_FILE, settings)
    await message.answer("✅ Бот включён.")

@dp.message(Command("work_until"))
async def cmd_work_until(message: types.Message):
    if not is_master(message.from_user.id):
        return
    try:
        hour = int(message.text.split()[1])
        if hour < DEFAULT_START_HOUR or hour > 23:
            await message.answer(f"Час должен быть от {DEFAULT_START_HOUR} до 23")
            return
        settings = load_data(SETTINGS_FILE)
        settings["custom_end_hour"] = hour
        save_data(SETTINGS_FILE, settings)
        await message.answer(f"✅ Сегодня работаю до {hour}:00")
    except:
        await message.answer("Используйте: /work_until 15")

@dp.message(Command("all_bookings"))
async def cmd_all_bookings(message: types.Message):
    if not is_master(message.from_user.id):
        return
    bookings = load_data(DATA_FILE)
    if not bookings:
        await message.answer("Нет записей")
        return
    text = "📋 ВСЕ ЗАПИСИ:\n\n"
    sorted_slots = sorted(bookings.items())
    for slot, info in sorted_slots:
        text += f"• {slot} — {info['username']} ({info.get('user_tag', '')})\n"
    await message.answer(text)

@dp.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message):
    if not is_master(message.from_user.id):
        return
    text = message.text.replace("/broadcast", "").strip()
    if not text:
        await message.answer("Напишите: /broadcast Текст сообщения")
        return
    bookings = load_data(DATA_FILE)
    unique_users = set()
    for info in bookings.values():
        unique_users.add(info["user_id"])
    success = 0
    for user_id in unique_users:
        try:
            await bot.send_message(user_id, f"📢 Сообщение от мастера:\n\n{text}")
            success += 1
        except:
            pass
    await message.answer(f"✅ Сообщение отправлено {success} клиентам")

async def main():
    print("🤖 Бот запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
