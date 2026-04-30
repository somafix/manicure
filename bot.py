import json
import os
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, request
import requests
import db

TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise Exception("❌ TELEGRAM_TOKEN не задан!")

URL = f"https://api.telegram.org/bot{TOKEN}"
app = Flask(__name__)

START_HOUR = 8
END_HOUR = 18
LUNCH_START = 13
LUNCH_END = 14

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def is_lunch_time():
    now = datetime.now()
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
        requests.post(f"{URL}/sendMessage", json=data, timeout=5)
    except Exception as e:
        print(f"Ошибка: {e}")

def edit_message(chat_id, message_id, text, keyboard=None):
    data = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML"}
    if keyboard:
        data["reply_markup"] = json.dumps(keyboard)
    try:
        requests.post(f"{URL}/editMessageText", json=data, timeout=5)
    except:
        pass

def get_free_slots(date_str, service_duration=60):
    """Получает свободные слоты с учётом длительности услуги"""
    bookings = db.get_all_active_bookings()
    booked_slots = [b["slot"] for b in bookings if b["slot"].startswith(date_str)]
    
    free = []
    current = START_HOUR
    while current + (service_duration // 60) <= END_HOUR:
        if LUNCH_START <= current < LUNCH_END:
            current = LUNCH_END
            continue
        
        slot = f"{date_str} {current:02d}:00"
        # Проверяем, не пересекается ли с занятыми слотами
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

# ========== КЛАВИАТУРЫ ==========
def main_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "📅 Записаться", "callback_data": "book"}],
            [{"text": "📋 Мои записи", "callback_data": "my_bookings"}],
            [{"text": "🕒 Свободные часы", "callback_data": "free_slots"}],
            [{"text": "🔴 Занятые часы", "callback_data": "busy_slots"}],
            [{"text": "🛠 Услуги", "callback_data": "services_list"}]
        ]
    }

def admin_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "📋 Все записи", "callback_data": "all_bookings"}],
            [{"text": "🍽 Обед (вкл/выкл)", "callback_data": "toggle_lunch"}],
            [{"text": "❌ Отменить запись", "callback_data": "admin_cancel"}],
            [{"text": "🔄 Перенести запись", "callback_data": "admin_reschedule"}],
            [{"text": "➕ Забронировать", "callback_data": "admin_book"}],
            [{"text": "⏰ Таймер отмены", "callback_data": "set_cancel_deadline"}]
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
            [{"text": "📅 +3 дня", "callback_data": f"date_{three}"}]
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

# ========== ФОН ПРОЦЕСС ДЛЯ НАПОМИНАНИЙ ==========
def reminder_worker():
    """Фоновый поток, проверяет каждые 10 минут и отправляет напоминания"""
    while True:
        try:
            now = datetime.now()
            # Проверяем только в рабочее время
            if START_HOUR <= now.hour < END_HOUR:
                upcoming = db.get_upcoming_bookings(1)  # за час
                for b in upcoming:
                    slot_time = datetime.strptime(b["slot"], "%Y-%m-%d %H:00")
                    diff = (slot_time - now).total_seconds() / 60
                    if 30 <= diff <= 70:  # примерно за час
                        text = f"🔔 <b>Напоминание!</b>\n\nУ тебя запись через час:\n📅 {b['slot']}\n💅 {b['service']}\n\nЖду тебя!"
                        send_message(b["user_id"], text)
                        db.mark_reminder_sent(b["id"])
        except Exception as e:
            print(f"Ошибка напоминаний: {e}")
        time.sleep(600)  # каждые 10 минут

# Запускаем фоновый поток
threading.Thread(target=reminder_worker, daemon=True).start()

# ========== ОБРАБОТЧИКИ ==========
@app.route(f"/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    if not data:
        return "OK", 200

    if "message" in data:
        msg = data["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "")

        if text == "/start":
            send_message(chat_id, "💅 <b>Маникюрный бот</b>\n\nВыбери действие:", main_keyboard())
            if not is_admin(chat_id) and not db.get_setting("admin_id"):
                db.set_setting("admin_id", str(chat_id))
                send_message(chat_id, "👑 Ты назначен <b>администратором</b>!\n/admin — админ-панель")

        elif text == "/admin" and is_admin(chat_id):
            send_message(chat_id, "🔧 <b>Админ-панель</b>", admin_keyboard())

    elif "callback_query" in data:
        call = data["callback_query"]
        chat_id = call["message"]["chat"]["id"]
        msg_id = call["message"]["message_id"]
        data_call = call["data"]

        # Навигация
        if data_call == "back_to_main":
            edit_message(chat_id, msg_id, "💅 Главное меню:", main_keyboard())
        elif data_call == "back_to_dates":
            edit_message(chat_id, msg_id, "📅 Выбери дату:", get_date_buttons())
        elif data_call == "admin_back" and is_admin(chat_id):
            edit_message(chat_id, msg_id, "🔧 Админ-панель", admin_keyboard())
        elif data_call == "noop":
            pass

        # Услуги
        elif data_call == "services_list":
            edit_message(chat_id, msg_id, "💅 <b>Выбери услугу:</b>", get_service_buttons())

        # Запись
        elif data_call == "book":
            if not is_working_time():
                edit_message(chat_id, msg_id, "⏰ Сейчас нерабочее время или обед (13:00-14:00)\nРаботаю с 8:00 до 18:00")
            else:
                edit_message(chat_id, msg_id, "📅 Выбери дату:", get_date_buttons())

        elif data_call == "free_slots":
            date_str = datetime.now().strftime("%Y-%m-%d")
            free = get_free_slots(date_str)
            text = f"🟢 <b>Свободно сегодня ({date_str}):</b>\n\n" + ("\n".join(free) if free else "Нет свободных часов")
            send_message(chat_id, text)

        elif data_call == "busy_slots":
            bookings = db.get_all_active_bookings()
            today = datetime.now().strftime("%Y-%m-%d")
            busy = [b for b in bookings if b["slot"].startswith(today)]
            text = f"🔴 <b>Занято сегодня ({today}):</b>\n\n" + ("\n".join([f"• {b['slot']} — {b['service']} ({b['name']})" for b in busy]) if busy else "Нет занятых часов")
            send_message(chat_id, text)

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

        # Выбор услуги
        elif data_call.startswith("service_"):
            service_id = int(data_call.split("_")[1])
            db.set_setting(f"temp_service_{chat_id}", str(service_id))
            edit_message(chat_id, msg_id, "📅 Теперь выбери дату:", get_date_buttons())

        # Выбор даты
        elif data_call.startswith("date_"):
            date_str = data_call.split("_")[1]
            service_id = db.get_setting(f"temp_service_{chat_id}")
            if not service_id:
                edit_message(chat_id, msg_id, "💅 Сначала выбери услугу:", get_service_buttons())
                return
            services = db.get_services()
            service = next((s for s in services if s["id"] == int(service_id)), None)
            if not service:
                return
            free = get_free_slots(date_str, service["duration"])
            if not free:
                edit_message(chat_id, msg_id, f"❌ На {date_str} нет свободных окон под услугу {service['duration']} мин")
            else:
                edit_message(chat_id, msg_id, f"📅 <b>{date_str}</b>\n💅 {service['name']} ({service['duration']} мин)\n\nВыбери время:", 
                           get_time_buttons(date_str, free, service_id))

        # Выбор времени и запись
        elif data_call.startswith("time_"):
            _, date_str, slot_time, service_id = data_call.split("_")
            full_slot = f"{date_str} {slot_time}"
            service_id = int(service_id)
            
            services = db.get_services()
            service = next((s for s in services if s["id"] == service_id), None)
            if not service:
                return
            
            # Проверяем, свободно ли время
            free = get_free_slots(date_str, service["duration"])
            if slot_time not in free:
                edit_message(chat_id, msg_id, f"❌ Время {slot_time} уже занято. Выбери другое:")
                return
            
            name = call["from"].get("first_name", "Клиент")
            result = db.add_booking(full_slot, chat_id, name, "", service_id)
            
            if result:
                db.set_setting(f"temp_service_{chat_id}", "")  # очищаем
                edit_message(chat_id, msg_id, f"✅ <b>Запись подтверждена!</b>\n\n📅 {full_slot}\n💅 {service['name']}\n💰 {service['price']}₽\n\n/start — в меню")
            else:
                edit_message(chat_id, msg_id, "❌ Ошибка: время уже занято")

        # Отмена записи
        elif data_call.startswith("cancel_"):
            slot = data_call.replace("cancel_", "")
            if not db.can_cancel(slot):
                send_message(chat_id, "⏰ Отменить запись можно не менее чем за 2 часа до начала")
            else:
                if db.cancel_booking(slot, user_id=chat_id):
                    send_message(chat_id, f"✅ Запись на {slot} отменена")
                    edit_message(chat_id, msg_id, "📋 Твои записи обновлены", get_cancel_buttons(chat_id))
                else:
                    send_message(chat_id, "❌ Запись не найдена")

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

        elif data_call == "toggle_lunch" and is_admin(chat_id):
            current = db.get_setting("lunch_disabled", "False")
            new = "True" if current == "False" else "False"
            db.set_setting("lunch_disabled", new)
            status = "❌ ВЫКЛЮЧЕН" if new == "True" else "✅ ВКЛЮЧЕН"
            send_message(chat_id, f"🍽 Обед {status} (13:00-14:00)")

        elif data_call == "admin_cancel" and is_admin(chat_id):
            send_message(chat_id, "❌ <b>Выбери запись для отмены:</b>", get_admin_cancel_buttons())

        elif data_call.startswith("admin_cancel_") and is_admin(chat_id):
            slot = data_call.replace("admin_cancel_", "")
            booking = db.get_booking_by_slot(slot)
            if booking:
                db.cancel_booking(slot, is_admin=True)
                send_message(chat_id, f"✅ Отменена: {slot} — {booking['user_name']}")
                send_message(booking["user_id"], f"❌ <b>Твоя запись на {slot} отменена администратором</b>")

        elif data_call == "admin_reschedule" and is_admin(chat_id):
            send_message(chat_id, "🔄 <b>Выбери запись для переноса:</b>", get_admin_reschedule_buttons())

        elif data_call.startswith("resched_select_") and is_admin(chat_id):
            slot = data_call.replace("resched_select_", "")
            db.set_setting("reschedule_slot", slot)
            send_message(chat_id, f"Выбрана: {slot}\nТеперь выбери новую дату:", get_date_buttons())

        elif data_call.startswith("date_") and is_admin(chat_id) and db.get_setting("reschedule_slot"):
            date_str = data_call.split("_")[1]
            old_slot = db.get_setting("reschedule_slot")
            booking = db.get_booking_by_slot(old_slot)
            if not booking:
                send_message(chat_id, "❌ Запись не найдена")
                return
            services = db.get_services()
            service = next((s for s in services if s["id"] == booking["service_id"]), None)
            free = get_free_slots(date_str, service["duration"] if service else 60)
            if not free:
                send_message(chat_id, f"❌ На {date_str} нет свободных окон")
            else:
                db.set_setting(f"temp_new_slot_{chat_id}", date_str)
                send_message(chat_id, f"📅 {date_str}\nВыбери новое время:", get_time_buttons(date_str, free, booking["service_id"]))

        elif data_call.startswith("time_") and is_admin(chat_id) and db.get_setting("reschedule_slot"):
            _, date_str, slot_time, service_id = data_call.split("_")
            new_slot = f"{date_str} {slot_time}"
            old_slot = db.get_setting("reschedule_slot")
            booking = db.get_booking_by_slot(old_slot)
            
            if booking and db.admin_reschedule_booking(old_slot, new_slot):
                send_message(chat_id, f"✅ Перенос: {old_slot} → {new_slot}")
                send_message(booking["user_id"], f"🔄 <b>Твоя запись перенесена</b>\n{old_slot} → {new_slot}")
                db.set_setting("reschedule_slot", "")
            else:
                send_message(chat_id, "❌ Ошибка переноса (возможно, время уже занято)")

        elif data_call == "set_cancel_deadline" and is_admin(chat_id):
            send_message(chat_id, "⏰ <b>Таймер отмены записи</b>\n\nСколько минут до записи можно отменить?\nСейчас: " + 
                        db.get_setting("cancellation_deadline_minutes", "120") + " мин\n\nНапиши число (например, 120)")
            db.set_setting("awaiting_deadline", str(chat_id))

    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
