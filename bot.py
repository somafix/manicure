import subprocess
import sys

try:
    import requests
except ModuleNotFoundError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

import json
import os
import threading
import time
from datetime import datetime, timedelta
import db

TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise Exception("❌ TELEGRAM_TOKEN не задан!")

URL = f"https://api.telegram.org/bot{TOKEN}"

START_HOUR = 9
END_HOUR = 20
LUNCH_START = 13
LUNCH_END = 14

user_temp_data = {}
last_update_id = 0

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def is_lunch_time():
    now = datetime.now()
    lunch_disabled = db.get_setting("lunch_disabled", "False") == "True"
    if lunch_disabled:
        return False
    return LUNCH_START <= now.hour < LUNCH_END

def is_working_time():
    now = datetime.now()
    if is_lunch_time():
        return False
    return START_HOUR <= now.hour < END_HOUR

def is_admin(user_id):
    return str(user_id) == db.get_setting("admin_id", "")

def send_message(chat_id, text, keyboard=None):
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if keyboard:
        data["reply_markup"] = json.dumps(keyboard)
    try:
        response = requests.post(f"{URL}/sendMessage", json=data, timeout=5)
        return response.json().get("result", {}).get("message_id")
    except Exception as e:
        print(f"Ошибка отправки: {e}")
        return None

def get_free_slots(date_str, service_duration=60):
    bookings = db.get_all_active_bookings()
    booked_slots = [b["slot"] for b in bookings if b["slot"].startswith(date_str)]
    
    free = []
    current = START_HOUR
    while current + (service_duration // 60) <= END_HOUR:
        if LUNCH_START <= current < LUNCH_END:
            current = LUNCH_END
            continue
        
        slot = f"{date_str} {current:02d}:00"
        conflict = False
        for booked in booked_slots:
            booked_hour = int(booked.split()[1].split(":")[0])
            if abs(booked_hour - current) < (service_duration // 60):
                conflict = True
                break
        
        if not conflict:
            free.append(f"{current:02d}:00")
        current += 1
    return free

def clear_user_temp(chat_id):
    if chat_id in user_temp_data:
        del user_temp_data[chat_id]

# ========== КЛАВИАТУРЫ ==========
def main_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "📅 Записаться", "callback_data": "book"}],
            [{"text": "📋 Мои записи", "callback_data": "my_bookings"}],
            [{"text": "🕒 Свободные часы", "callback_data": "free_slots"}],
            [{"text": "🔴 Занятые часы", "callback_data": "busy_slots"}],
            [{"text": "🛠 Услуги", "callback_data": "services_list"}],
            [{"text": "ℹ️ О боте", "callback_data": "info"}]
        ]
    }

def admin_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "📋 Все записи", "callback_data": "all_bookings"}],
            [{"text": "🍽 Обед (вкл/выкл)", "callback_data": "toggle_lunch"}],
            [{"text": "❌ Отменить запись", "callback_data": "admin_cancel"}],
            [{"text": "🔄 Перенести запись", "callback_data": "admin_reschedule"}],
            [{"text": "📊 Статистика", "callback_data": "stats"}]
        ]
    }

def get_date_buttons():
    today = datetime.now().strftime("%Y-%m-%d")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    after = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
    three = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
    return {
        "inline_keyboard": [
            [{"text": "📅 Сегодня", "callback_data": f"date_{today}"}],
            [{"text": "📅 Завтра", "callback_data": f"date_{tomorrow}"}],
            [{"text": "📅 Послезавтра", "callback_data": f"date_{after}"}],
            [{"text": "📅 +3 дня", "callback_data": f"date_{three}"}],
            [{"text": "◀️ Назад", "callback_data": "back_to_main"}]
        ]
    }

def get_service_buttons():
    services = db.get_services()
    buttons = []
    for s in services:
        buttons.append([{"text": f"{s['name']} ({s['duration']} мин, {s['price']}₽)", "callback_data": f"service_{s['id']}"}])
    buttons.append([{"text": "◀️ Назад", "callback_data": "back_to_main"}])
    return {"inline_keyboard": buttons}

def get_time_buttons(date_str, free_slots, service_id):
    buttons = []
    for slot in free_slots:
        buttons.append([{"text": slot, "callback_data": f"time_{date_str}_{slot}_{service_id}"}])
    buttons.append([{"text": "◀️ Назад", "callback_data": "back_to_dates"}])
    return {"inline_keyboard": buttons}

def get_cancel_buttons(user_id):
    bookings = db.get_user_bookings(user_id)
    buttons = []
    for b in bookings:
        if db.can_cancel(b["slot"]):
            buttons.append([{"text": f"❌ {b['slot']} ({b['service']})", "callback_data": f"cancel_{b['slot']}"}])
        else:
            buttons.append([{"text": f"⏰ {b['slot']} (отмена недоступна)", "callback_data": "noop"}])
    if buttons:
        buttons.append([{"text": "◀️ Назад", "callback_data": "back_to_main"}])
    return {"inline_keyboard": buttons}

def get_admin_cancel_buttons():
    bookings = db.get_all_active_bookings()
    buttons = []
    for b in bookings:
        buttons.append([{"text": f"❌ {b['slot']} — {b['name']}", "callback_data": f"admin_cancel_{b['slot']}"}])
    if buttons:
        buttons.append([{"text": "◀️ Назад", "callback_data": "admin_back"}])
    return {"inline_keyboard": buttons}

def get_admin_reschedule_buttons():
    bookings = db.get_all_active_bookings()
    buttons = []
    for b in bookings:
        buttons.append([{"text": f"🔄 {b['slot']} — {b['name']}", "callback_data": f"resched_select_{b['slot']}"}])
    if buttons:
        buttons.append([{"text": "◀️ Назад", "callback_data": "admin_back"}])
    return {"inline_keyboard": buttons}

# ========== НАПОМИНАНИЯ ==========
def reminder_worker():
    while True:
        try:
            now = datetime.now()
            upcoming = db.get_upcoming_bookings(1)
            for b in upcoming:
                slot_time = datetime.strptime(b["slot"], "%Y-%m-%d %H:00")
                diff = (slot_time - now).total_seconds() / 60
                if 30 <= diff <= 70:
                    text = f"🔔 <b>Напоминание!</b>\n\nУ тебя запись через час:\n📅 {b['slot']}\n💅 {b['service']}\n\nЖду тебя!"
                    send_message(b["user_id"], text)
                    db.mark_reminder_sent(b["id"])
        except Exception as e:
            print(f"Ошибка напоминаний: {e}")
        time.sleep(600)

threading.Thread(target=reminder_worker, daemon=True).start()

# ========== ОБРАБОТКА СООБЩЕНИЙ ==========
def handle_callback_query(call):
    chat_id = call["message"]["chat"]["id"]
    message_id = call["message"]["message_id"]
    data_call = call["data"]

    # Навигация
    if data_call == "back_to_main":
        send_message(chat_id, "💅 Главное меню:", main_keyboard())
        clear_user_temp(chat_id)
        return
    
    elif data_call == "back_to_dates":
        send_message(chat_id, "📅 Выбери дату:", get_date_buttons())
        return
    
    elif data_call == "admin_back" and is_admin(chat_id):
        send_message(chat_id, "🔧 Админ-панель", admin_keyboard())
        return
    
    elif data_call == "noop":
        return
    
    elif data_call == "info":
        info_text = """<b>ℹ️ О боте</b>

👋 Бот для записи на маникюр

⏰ Рабочее время: 9:00 - 20:00
🍽 Обед: 13:00 - 14:00

❌ Отменить запись можно за 2 часа до начала"""
        send_message(chat_id, info_text, main_keyboard())
        return

    # Услуги
    elif data_call == "services_list":
        send_message(chat_id, "💅 <b>Выбери услугу:</b>", get_service_buttons())
        return

    # Запись
    elif data_call == "book":
        if not is_working_time():
            send_message(chat_id, "⏰ Сейчас нерабочее время или обед (13:00-14:00)\nРаботаю с 9:00 до 20:00")
        else:
            send_message(chat_id, "📅 Выбери дату:", get_date_buttons())
        return

    elif data_call == "free_slots":
        date_str = datetime.now().strftime("%Y-%m-%d")
        free = get_free_slots(date_str)
        text = f"🟢 <b>Свободно сегодня ({date_str}):</b>\n\n" + ("\n".join(free) if free else "Нет свободных часов")
        send_message(chat_id, text)
        return

    elif data_call == "busy_slots":
        bookings = db.get_all_active_bookings()
        today = datetime.now().strftime("%Y-%m-%d")
        busy = [b for b in bookings if b["slot"].startswith(today)]
        text = f"🔴 <b>Занято сегодня ({today}):</b>\n\n" + ("\n".join([f"• {b['slot']} — {b['service']} ({b['name']})" for b in busy]) if busy else "Нет занятых часов")
        send_message(chat_id, text)
        return

    elif data_call == "my_bookings":
        bookings = db.get_user_bookings(chat_id)
        if not bookings:
            send_message(chat_id, "📭 У тебя нет активных записей")
        else:
            text = "📋 <b>Твои записи:</b>\n\n"
            for b in bookings:
                cancel_status = "✅ можно отменить" if db.can_cancel(b["slot"]) else "⏰ отмена недоступна (менее 2ч)"
                text += f"• {b['slot']} — {b['service']}\n   ({cancel_status})\n\n"
            send_message(chat_id, text, get_cancel_buttons(chat_id))
        return

    # Выбор услуги
    elif data_call.startswith("service_"):
        service_id = int(data_call.split("_")[1])
        user_temp_data[chat_id] = {"service_id": service_id}
        send_message(chat_id, "📅 Теперь выбери дату:", get_date_buttons())
        return

    # Выбор даты
    elif data_call.startswith("date_"):
        date_str = data_call.split("_")[1]
        temp = user_temp_data.get(chat_id, {})
        service_id = temp.get("service_id")
        
        if not service_id:
            send_message(chat_id, "💅 Сначала выбери услугу:", get_service_buttons())
            return
        
        services = db.get_services()
        service = next((s for s in services if s["id"] == service_id), None)
        if not service:
            return
        
        free = get_free_slots(date_str, service["duration"])
        if not free:
            send_message(chat_id, f"❌ На {date_str} нет свободных окон под услугу {service['duration']} мин")
        else:
            user_temp_data[chat_id]["date"] = date_str
            send_message(chat_id, f"📅 <b>{date_str}</b>\n💅 {service['name']} ({service['duration']} мин)\n\nВыбери время:", 
                       get_time_buttons(date_str, free, service_id))
        return

    # Выбор времени и запись
    elif data_call.startswith("time_"):
        parts = data_call.split("_")
        if len(parts) != 4:
            return
        _, date_str, slot_time, service_id = parts
        full_slot = f"{date_str} {slot_time}"
        service_id = int(service_id)
        
        services = db.get_services()
        service = next((s for s in services if s["id"] == service_id), None)
        if not service:
            return
        
        free = get_free_slots(date_str, service["duration"])
        if slot_time not in free:
            send_message(chat_id, f"❌ Время {slot_time} уже занято. Выбери другое:")
            return
        
        name = call["from"].get("first_name", "Клиент")
        username = call["from"].get("username", "")
        full_name = f"{name} (@{username})" if username else name
        
        result = db.add_booking(full_slot, chat_id, full_name, "", service_id)
        
        if result:
            clear_user_temp(chat_id)
            confirm_text = f"✅ <b>Запись подтверждена!</b>\n\n📅 {full_slot}\n💅 {service['name']}\n💰 {service['price']}₽\n\nПриходите вовремя! ✨"
            send_message(chat_id, confirm_text)
            admin_id = db.get_setting("admin_id")
            if admin_id:
                send_message(int(admin_id), f"📝 <b>Новая запись!</b>\n\n{full_name}\n📅 {full_slot}\n💅 {service['name']}")
        else:
            send_message(chat_id, "❌ Ошибка: время уже занято")
        return

    # Отмена записи
    elif data_call.startswith("cancel_"):
        slot = data_call.replace("cancel_", "")
        if not db.can_cancel(slot):
            send_message(chat_id, "⏰ Отменить запись можно не менее чем за 2 часа до начала")
        else:
            if db.cancel_booking(slot, user_id=chat_id):
                send_message(chat_id, f"✅ Запись на {slot} отменена")
                admin_id = db.get_setting("admin_id")
                if admin_id:
                    send_message(int(admin_id), f"❌ Клиент отменил запись на {slot}")
            else:
                send_message(chat_id, "❌ Запись не найдена")
        return

    # Админские команды
    elif data_call == "all_bookings" and is_admin(chat_id):
        bookings = db.get_all_active_bookings()
        if not bookings:
            send_message(chat_id, "📭 Нет записей")
        else:
            text = "📋 <b>ВСЕ ЗАПИСИ:</b>\n\n"
            for b in bookings:
                text += f"• {b['slot']} — {b['name']} ({b['service']})\n"
            send_message(chat_id, text)
        return

    elif data_call == "stats" and is_admin(chat_id):
        bookings = db.get_all_active_bookings()
        total = len(bookings)
        today_count = len([b for b in bookings if b["slot"].startswith(datetime.now().strftime("%Y-%m-%d"))])
        text = f"<b>📊 Статистика:</b>\n\nВсего активных записей: {total}\nЗаписей на сегодня: {today_count}"
        send_message(chat_id, text)
        return

    elif data_call == "toggle_lunch" and is_admin(chat_id):
        current = db.get_setting("lunch_disabled", "False")
        new = "True" if current == "False" else "False"
        db.set_setting("lunch_disabled", new)
        status = "❌ ВЫКЛЮЧЕН" if new == "True" else "✅ ВКЛЮЧЕН"
        send_message(chat_id, f"🍽 Обед {status} (13:00-14:00)")
        return

    elif data_call == "admin_cancel" and is_admin(chat_id):
        send_message(chat_id, "❌ <b>Выбери запись для отмены:</b>", get_admin_cancel_buttons())
        return

    elif data_call.startswith("admin_cancel_") and is_admin(chat_id):
        slot = data_call.replace("admin_cancel_", "")
        booking = db.get_booking_by_slot(slot)
        if booking:
            db.cancel_booking(slot, is_admin=True)
            send_message(chat_id, f"✅ Отменена: {slot} — {booking['user_name']}")
            send_message(booking["user_id"], f"❌ <b>Твоя запись на {slot} отменена администратором</b>")
        return

    elif data_call == "admin_reschedule" and is_admin(chat_id):
        send_message(chat_id, "🔄 <b>Выбери запись для переноса:</b>", get_admin_reschedule_buttons())
        return

    elif data_call.startswith("resched_select_") and is_admin(chat_id):
        slot = data_call.replace("resched_select_", "")
        db.set_setting("reschedule_slot", slot)
        send_message(chat_id, f"Выбрана: {slot}\nТеперь выбери новую дату:", get_date_buttons())
        return

    elif data_call.startswith("date_") and is_admin(chat_id):
        old_slot = db.get_setting("reschedule_slot")
        if not old_slot:
            return
        date_str = data_call.split("_")[1]
        booking = db.get_booking_by_slot(old_slot)
        if not booking:
            send_message(chat_id, "❌ Запись не найдена")
            db.set_setting("reschedule_slot", "")
            return
        services = db.get_services()
        service = next((s for s in services if s["id"] == booking["service_id"]), None)
        free = get_free_slots(date_str, service["duration"] if service else 60)
        if not free:
            send_message(chat_id, f"❌ На {date_str} нет свободных окон")
        else:
            user_temp_data[chat_id] = {"reschedule_date": date_str, "service_id": booking["service_id"]}
            send_message(chat_id, f"📅 {date_str}\nВыбери новое время:", get_time_buttons(date_str, free, booking["service_id"]))
        return

    elif data_call.startswith("time_") and is_admin(chat_id):
        old_slot = db.get_setting("reschedule_slot")
        if not old_slot:
            return
        parts = data_call.split("_")
        if len(parts) != 4:
            return
        _, date_str, slot_time, service_id = parts
        new_slot = f"{date_str} {slot_time}"
        booking = db.get_booking_by_slot(old_slot)
        
        if booking and db.admin_reschedule_booking(old_slot, new_slot):
            send_message(chat_id, f"✅ Перенос: {old_slot} → {new_slot}")
            send_message(booking["user_id"], f"🔄 <b>Твоя запись перенесена</b>\n\n{old_slot} → {new_slot}")
            db.set_setting("reschedule_slot", "")
            clear_user_temp(chat_id)
        else:
            send_message(chat_id, "❌ Ошибка переноса (возможно, время уже занято)")
        return

    elif data_call == "set_cancel_deadline" and is_admin(chat_id):
        send_message(chat_id, "⏰ <b>Таймер отмены записи</b>\n\nСколько минут до записи можно отменить?\nСейчас: " + 
                    db.get_setting("cancellation_deadline_minutes", "120") + " мин\n\nНапиши число (например, 120)")
        db.set_setting("awaiting_deadline", str(chat_id))
        return

def handle_message(chat_id, text):
    if text == "/start":
        send_message(chat_id, "💅 <b>Маникюрный бот</b>\n\nВыбери действие:", main_keyboard())
        if not is_admin(chat_id) and not db.get_setting("admin_id"):
            db.set_setting("admin_id", str(chat_id))
            send_message(chat_id, "👑 Ты назначен <b>администратором</b>!\n/admin — админ-панель")

    elif text == "/admin" and is_admin(chat_id):
        send_message(chat_id, "🔧 <b>Админ-панель</b>", admin_keyboard())
    
    elif text == "/help":
        help_text = """<b>Доступные команды:</b>
/start - Главное меню
/admin - Админ-панель (только для админа)
/help - Эта справка

<b>Как записаться:</b>
1. Нажми "📅 Записаться"
2. Выбери услугу
3. Выбери дату и время
4. Подтверди запись"""
        send_message(chat_id, help_text)
    
    # Обработка ввода таймера
    awaiting_deadline = db.get_setting("awaiting_deadline")
    if awaiting_deadline == str(chat_id) and text.isdigit():
        db.set_setting("cancellation_deadline_minutes", text)
        db.set_setting("awaiting_deadline", "")
        send_message(chat_id, f"✅ Таймер отмены установлен на {text} минут")

# ========== LONG POLLING ==========
def main():
    global last_update_id
    print("🤖 Бот запущен и работает...")
    
    while True:
        try:
            url = f"{URL}/getUpdates"
            params = {"timeout": 30, "offset": last_update_id + 1}
            response = requests.get(url, params=params, timeout=35)
            data = response.json()
            
            if data.get("ok"):
                for update in data.get("result", []):
                    last_update_id = update["update_id"]
                    
                    if "message" in update:
                        msg = update["message"]
                        chat_id = msg["chat"]["id"]
                        text = msg.get("text", "")
                        handle_message(chat_id, text)
                    
                    elif "callback_query" in update:
                        handle_callback_query(update["callback_query"])
                        
        except Exception as e:
            print(f"Ошибка: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()