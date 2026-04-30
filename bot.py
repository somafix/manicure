import json
import os
import asyncio
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise Exception("TELEGRAM_TOKEN не задан")

START_HOUR = 8
END_HOUR = 18
DATA_FILE = "bookings.json"

bot = Bot(token=TOKEN)
dp = Dispatcher()

def load_bookings():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_bookings(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def is_working_time():
    now = datetime.now()
    return START_HOUR <= now.hour < END_HOUR

def get_free_slots(date_str):
    bookings = load_bookings()
    free = []
    for hour in range(START_HOUR, END_HOUR, 1):
        slot = f"{date_str} {hour:02d}:00"
        if slot not in bookings:
            free.append(f"{hour:02d}:00")
    return free

def get_date_buttons():
    builder = InlineKeyboardBuilder()
    today = datetime.now().strftime("%Y-%m-%d")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    after = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
    builder.button(text="Сегодня", callback_data=f"date_{today}")
    builder.button(text="Завтра", callback_data=f"date_{tomorrow}")
    builder.button(text="Послезавтра", callback_data=f"date_{after}")
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
    if not is_working_time():
        await message.answer(f"⏰ Бот работает с {START_HOUR}:00 до {END_HOUR}:00")
        return
    await message.answer(
        f"💅 Запись на маникюр\n⏰ {START_HOUR}:00-{END_HOUR}:00",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Записаться", callback_data="book")]
        ])
    )

@dp.callback_query(lambda c: c.data == "book")
async def choose_date(callback: types.CallbackQuery):
    if not is_working_time():
        await callback.answer("❌ Нерабочее время")
        return
    await callback.message.edit_text("📅 Выбери дату:", reply_markup=get_date_buttons())
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("date_"))
async def choose_time(callback: types.CallbackQuery):
    if not is_working_time():
        await callback.answer("❌ Нерабочее время")
        return
    date_str = callback.data.split("_")[1]
    free_slots = get_free_slots(date_str)
    if not free_slots:
        await callback.message.edit_text("❌ Нет мест", reply_markup=get_date_buttons())
        return
    await callback.message.edit_text(f"📅 {date_str}\n⏰ Время:", reply_markup=get_time_buttons(date_str, free_slots))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("time_"))
async def make_booking(callback: types.CallbackQuery):
    if not is_working_time():
        await callback.answer("❌ Нерабочее время")
        return
    _, date_str, slot_time = callback.data.split("_")
    full_slot = f"{date_str} {slot_time}"
    bookings = load_bookings()
    if full_slot in bookings:
        await callback.answer("❌ Занято")
        return
    bookings[full_slot] = {
        "user_id": callback.from_user.id,
        "name": callback.from_user.full_name
    }
    save_bookings(bookings)
    await callback.message.edit_text(f"✅ Запись на {full_slot}\n/start - меню")
    await callback.answer()

async def main():
    print("✅ Бот запущен")
    # Получаем обновления и сразу завершаемся
    updates = await bot.get_updates(offset=-1, timeout=5)
    for update in updates:
        await dp.process_update(update)
    await bot.session.close()
    print("✅ Бот завершил работу")

if __name__ == "__main__":
    asyncio.run(main())