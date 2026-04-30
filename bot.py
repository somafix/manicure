import json
import os
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
import asyncio

# ========== НАСТРОЙКИ ==========
TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise Exception("❌ TELEGRAM_TOKEN не задан!")

START_HOUR = 8      # Начало работы в 8:00
END_HOUR = 18       # Конец работы в 18:00
STEP_HOURS = 1      # Шаг записи (1 час)
DATA_FILE = "bookings.json"
# ================================

def load_bookings():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_bookings(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def is_working_time():
    """Проверяет, рабочее ли сейчас время (8:00-18:00)"""
    now = datetime.now()
    return START_HOUR <= now.hour < END_HOUR

def get_free_slots(date_str):
    """Возвращает список свободных часов на конкретную дату"""
    bookings = load_bookings()
    free = []
    for hour in range(START_HOUR, END_HOUR, STEP_HOURS):
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
        f"💅 Маникюрный салон\n"
        f"⏰ Работаю: {START_HOUR}:00 - {END_HOUR}:00\n"
        f"📌 Запись на сегодня, завтра, послезавтра\n\n"
        f"👇 Нажмите, чтобы записаться:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Записаться", callback_data="book")]
        ])
    )

@dp.callback_query(lambda c: c.data == "book")
async def choose_date(callback: types.CallbackQuery):
    if not is_working_time():
        await callback.answer("❌ Сейчас нерабочее время!", show_alert=True)
        return
    await callback.message.edit_text("📅 Выберите дату:", reply_markup=get_date_buttons())
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("date_"))
async def choose_time(callback: types.CallbackQuery):
    if not is_working_time():
        await callback.answer("❌ Сейчас нерабочее время!", show_alert=True)
        return
    
    date_str = callback.data.split("_")[1]
    free_slots = get_free_slots(date_str)
    
    if not free_slots:
        await callback.message.edit_text("❌ На эту дату нет свободных часов. Выберите другую:", reply_markup=get_date_buttons())
        await callback.answer()
        return
    
    await callback.message.edit_text(f"📅 {date_str}\n⏰ Выберите время:", reply_markup=get_time_buttons(date_str, free_slots))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("time_"))
async def make_booking(callback: types.CallbackQuery):
    if not is_working_time():
        await callback.answer("❌ Сейчас нерабочее время!", show_alert=True)
        return
    
    _, date_str, slot_time = callback.data.split("_")
    full_slot = f"{date_str} {slot_time}"
    bookings = load_bookings()
    
    if full_slot in bookings:
        free_slots = get_free_slots(date_str)
        if free_slots:
            await callback.message.edit_text(
                f"❌ Время {slot_time} уже занято.\n\n📅 {date_str}\nДоступные слоты:",
                reply_markup=get_time_buttons(date_str, free_slots)
            )
        else:
            await callback.message.edit_text(f"❌ Время {slot_time} занято. Выберите другую дату:", reply_markup=get_date_buttons())
        await callback.answer("Это время уже занято", show_alert=True)
        return
    
    bookings[full_slot] = {
        "user_id": callback.from_user.id,
        "name": callback.from_user.full_name,
        "username": callback.from_user.username or "без username",
        "booked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    save_bookings(bookings)
    
    await callback.message.edit_text(f"✅ Вы записаны на {full_slot}!\n\nОтменить запись можно через /my_bookings")
    await callback.answer("✅ Запись подтверждена!")

@dp.message(Command("my_bookings"))
async def show_my_bookings(message: types.Message):
    if not is_working_time():
        await message.answer("⏰ Бот работает с 8 до 18. Приходи в рабочее время.")
        return
    
    bookings = load_bookings()
    my_slots = [slot for slot, info in bookings.items() if info["user_id"] == message.from_user.id]
    
    if not my_slots:
        await message.answer("📭 У вас нет активных записей.")
        return
    
    text = "📋 Ваши записи:\n\n"
    kb = InlineKeyboardBuilder()
    for slot in my_slots:
        text += f"• {slot}\n"
        kb.button(text=f"❌ Отменить {slot}", callback_data=f"cancel_{slot}")
    kb.adjust(1)
    await message.answer(text, reply_markup=kb.as_markup())

@dp.callback_query(lambda c: c.data.startswith("cancel_"))
async def cancel_booking(callback: types.CallbackQuery):
    if not is_working_time():
        await callback.answer("❌ Сейчас нерабочее время!", show_alert=True)
        return
    
    slot = callback.data.split("_", 1)[1]
    bookings = load_bookings()
    
    if slot in bookings and bookings[slot]["user_id"] == callback.from_user.id:
        del bookings[slot]
        save_bookings(bookings)
        await callback.message.edit_text(f"❌ Запись на {slot} отменена.")
    else:
        await callback.answer("❌ Запись не найдена", show_alert=True)
    await callback.answer()

async def main():
    print(f"🤖 Бот запущен. Рабочие часы: {START_HOUR}:00 - {END_HOUR}:00")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
