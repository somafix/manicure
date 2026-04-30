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
STEP_HOURS = 1
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
    for hour in range(START_HOUR, END_HOUR, STEP_HOURS):
        slot = f"{date_str} {hour:02d}:00"
        if slot not in bookings:
            free.append(f"{hour:02d}:00")
    return free

def get_date_buttons():
    builder = InlineKeyboardBuilder()
    today = datetime.now().strftime("%Y-%m-%d")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    after = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
    builder.button(text="📅 Сегодня", callback_data=f"date_{today}")
    builder.button(text="📅 Завтра", callback_data=f"date_{tomorrow}")
    builder.button(text="📅 Послезавтра", callback_data=f"date_{after}")
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
        await message.answer(f"⏰ Бот работает с {START_HOUR}:00 до {END_HOUR}:00. Приходи завтра!")
        return
    await message.answer(
        f"💅 Маникюрный салон\n⏰ {START_HOUR}:00 - {END_HOUR}:00\n👇 Записаться:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Записаться", callback_data="book")]
        ])
    )

@dp.callback_query(lambda c: c.data == "book")
async def choose_date(callback: types.CallbackQuery):
    if not is_working_time():
        await callback.answer("❌ Нерабочее время", show_alert=True)
        return
    await callback.message.edit_text("📅 Выберите дату:", reply_markup=get_date_buttons())
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("date_"))
async def choose_time(callback: types.CallbackQuery):
    if not is_working_time():
        await callback.answer("❌ Нерабочее время", show_alert=True)
        return
    date_str = callback.data.split("_")[1]
    free_slots = get_free_slots(date_str)
    if not free_slots:
        await callback.message.edit_text("❌ Нет свободных часов", reply_markup=get_date_buttons())
        await callback.answer()
        return
    await callback.message.edit_text(f"📅 {date_str}\nВыберите время:", reply_markup=get_time_buttons(date_str, free_slots))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("time_"))
async def make_booking(callback: types.CallbackQuery):
    if not is_working_time():
        await callback.answer("❌ Нерабочее время", show_alert=True)
        return
    _, date_str, slot_time = callback.data.split("_")
    full_slot = f"{date_str} {slot_time}"
    bookings = load_bookings()
    if full_slot in bookings:
        await callback.answer("❌ Уже занято", show_alert=True)
        return
    bookings[full_slot] = {
        "user_id": callback.from_user.id,
        "name": callback.from_user.full_name
    }
    save_bookings(bookings)
    await callback.message.edit_text(f"✅ Вы записаны на {full_slot}!\n/start - вернуться")
    await callback.answer("✅ Запись подтверждена")

@dp.message(Command("my_bookings"))
async def show_my_bookings(message: types.Message):
    if not is_working_time():
        return
    bookings = load_bookings()
    my_slots = [s for s, i in bookings.items() if i["user_id"] == message.from_user.id]
    if not my_slots:
        await message.answer("У вас нет записей")
        return
    text = "Ваши записи:\n" + "\n".join(my_slots)
    await message.answer(text)

async def main():
    print("🤖 Бот запускается...")
    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
