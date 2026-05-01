import os
import json
import requests
from datetime import datetime, timedelta
import db

TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise Exception("TELEGRAM_TOKEN не задан!")

URL = f"https://api.telegram.org/bot{TOKEN}"

WORK_START = 8
WORK_END = 18
LUNCH_START = 13
LUNCH_END = 14

temp = {}

# ========== УТИЛИТЫ ==========

def is_working_hour():
    now = datetime.now()
    if LUNCH_START <= now.hour < LUNCH_END:
        return False
    return WORK_START <= now.hour < WORK_END

def is_admin(user_id):
    return str(user_id) == db.get_setting("admin_id")

def send(chat_id, text, keyboard=None):
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if keyboard:
        data["reply_markup"] = json.dumps(keyboard)
    try:
        requests.post(f"{URL}/sendMessage", json=data, timeout=5)
    except:
        pass

def get_free_slots(date, duration=60):
    booked = [b["slot"] for b in db.get_all_active_bookings() if b["slot"].startswith(date)]
    free = []
    hour = WORK_START
    
    while hour + (duration // 60) <= WORK_END:
        if LUNCH_START <= hour < LUNCH_END:
            hour = LUNCH_END
            continue
        
        taken = False
        for b in booked:
            bh = int(b.split()[1].split(":")[0])
            if abs(bh - hour) < (duration // 60):
                taken = True
                break
        
        if not taken:
            free.append(f"{hour:02d}:00")
        hour += 1
    
    return free

# ========== КЛАВИАТУРЫ ==========

MENU = {
    "inline_keyboard": [
        [{"text": "📅 Записаться", "callback_data": "book"}],
        [{"text": "📋 Мои записи", "callback_data": "my"}],
        [{"text": "🕒 Свободно", "callback_data": "free"}],
        [{"text": "🔴 Занято", "callback_data": "busy"}],
        [{"text": "🛠 Услуги", "callback_data": "services"}]
    ]
}

def date_buttons():
    buttons = []
    for i in range(4):
        d = (datetime.now() + timedelta(days=i)).strftime("%Y-%m-%d")
        name = ["Сегодня", "Завтра", "Послезавтра", "+3 дня"][i]
        buttons.append([{"text": f"📅 {name}", "callback_data": f"date_{d}"}])
    buttons.append([{"text": "◀️ Назад", "callback_data": "back"}])
    return {"inline_keyboard": buttons}

def service_buttons():
    buttons = [[{"text": f"{s['name']} ({s['duration']}мин)", "callback_data": f"service_{s['id']}"}] 
               for s in db.get_services()]
    buttons.append([{"text": "◀️ Назад", "callback_data": "back"}])
    return {"inline_keyboard": buttons}

def time_buttons(date, slots, service_id):
    buttons = [[{"text": s, "callback_data": f"time_{date}_{s}_{service_id}"}] for s in slots]
    buttons.append([{"text": "◀️ Назад", "callback_data": "back_date"}])
    return {"inline_keyboard": buttons}

def cancel_buttons(user_id):
    buttons = []
    for b in db.get_user_bookings(user_id):
        if db.can_cancel(b["slot"]):
            buttons.append([{"text": f"❌ {b['slot']}", "callback_data": f"cancel_{b['slot']}"}])
    if buttons:
        buttons.append([{"text": "◀️ Назад", "callback_data": "back"}])
    return {"inline_keyboard": buttons}

# ========== ОБРАБОТЧИКИ ==========

def handle_message(chat_id, text):
    if text == "/start":
        send(chat_id, "💅 Маникюрный бот\n\nВыбери действие:", MENU)
        if not db.get_setting("admin_id"):
            db.set_setting("admin_id", str(chat_id))
            send(chat_id, "👑 Ты администратор! Используй /admin для панели")
    
    elif text == "/admin":
        if is_admin(chat_id):
            admin_menu = {
                "inline_keyboard": [
                    [{"text": "📋 Все записи", "callback_data": "all_bookings"}],
                    [{"text": "🍽 Обед (вкл/выкл)", "callback_data": "toggle_lunch"}],
                    [{"text": "❌ Отменить запись", "callback_data": "admin_cancel"}],
                    [{"text": "📊 Статистика", "callback_data": "stats"}],
                    [{"text": "◀️ Назад", "callback_data": "back"}]
                ]
            }
            send(chat_id, "🔧 Админ-панель", admin_menu)
        else:
            send(chat_id, "⛔ У вас нет прав администратора")
    
    elif text == "/help":
        send(chat_id, "Доступные команды:\n/start - Главное меню\n/admin - Админ-панель\n/help - Справка")

def handle_callback(chat_id, data):
    # Навигация
    if data == "back":
        send(chat_id, "💅 Главное меню:", MENU)
        temp.pop(chat_id, None)
        return
    if data == "back_date":
        send(chat_id, "📅 Выбери дату:", date_buttons())
        return
    
    # ========== АДМИН-ПАНЕЛЬ ==========
    if data == "all_bookings" and is_admin(chat_id):
        bookings = db.get_all_active_bookings()
        if not bookings:
            send(chat_id, "📭 Нет записей")
        else:
            text = "📋 <b>ВСЕ ЗАПИСИ:</b>\n\n"
            for b in bookings:
                text += f"• {b['slot']} — {b['name']} ({b['service']})\n"
            send(chat_id, text)
        return
    
    if data == "stats" and is_admin(chat_id):
        bookings = db.get_all_active_bookings()
        today = datetime.now().strftime("%Y-%m-%d")
        today_count = len([b for b in bookings if b["slot"].startswith(today)])
        text = f"📊 <b>Статистика:</b>\n\nВсего записей: {len(bookings)}\nНа сегодня: {today_count}"
        send(chat_id, text)
        return
    
    if data == "toggle_lunch" and is_admin(chat_id):
        current = db.get_setting("lunch_disabled", "False")
        new = "True" if current == "False" else "False"
        db.set_setting("lunch_disabled", new)
        status = "❌ ВЫКЛЮЧЕН" if new == "True" else "✅ ВКЛЮЧЕН"
        send(chat_id, f"🍽 Обед {status} (13:00-14:00)")
        return
    
    if data == "admin_cancel" and is_admin(chat_id):
        bookings = db.get_all_active_bookings()
        if not bookings:
            send(chat_id, "📭 Нет записей")
            return
        buttons = []
        for b in bookings:
            buttons.append([{"text": f"❌ {b['slot']} — {b['name']}", "callback_data": f"admin_cancel_{b['slot']}"}])
        buttons.append([{"text": "◀️ Назад", "callback_data": "back"}])
        send(chat_id, "❌ Выбери запись для отмены:", {"inline_keyboard": buttons})
        return
    
    if data.startswith("admin_cancel_") and is_admin(chat_id):
        slot = data.replace("admin_cancel_", "")
        booking = db.get_booking_by_slot(slot)
        if booking:
            db.cancel_booking(slot, is_admin=True)
            send(chat_id, f"✅ Отменена: {slot} — {booking['user_name']}")
            send(booking["user_id"], f"❌ <b>Твоя запись на {slot} отменена администратором</b>")
        return
    # =====================================
    
    # Инфо
    if data == "services":
        send(chat_id, "💅 Услуги:", service_buttons())
        return
    
    # Запись
    if data == "book":
        if is_working_hour():
            send(chat_id, "📅 Выбери дату:", date_buttons())
        else:
            send(chat_id, "⏰ Работаю с 8:00 до 18:00, обед 13:00-14:00")
        return
    
    if data == "free":
        today = datetime.now().strftime("%Y-%m-%d")
        free = get_free_slots(today)
        text = f"🟢 Свободно сегодня ({today}):\n" + ("\n".join(free) if free else "Нет свободных часов")
        send(chat_id, text)
        return
    
    if data == "busy":
        today = datetime.now().strftime("%Y-%m-%d")
        busy = [b for b in db.get_all_active_bookings() if b["slot"].startswith(today)]
        text = f"🔴 Занято сегодня ({today}):\n" + ("\n".join([f"{b['slot']} — {b['service']}" for b in busy]) if busy else "Нет записей")
        send(chat_id, text)
        return
    
    if data == "my":
        bookings = db.get_user_bookings(chat_id)
        if not bookings:
            send(chat_id, "📭 Нет активных записей")
        else:
            text = "📋 Твои записи:\n\n"
            for b in bookings:
                status = "✅ можно отменить" if db.can_cancel(b["slot"]) else "⏰ отмена недоступна"
                text += f"{b['slot']} — {b['service']}\n({status})\n\n"
            send(chat_id, text, cancel_buttons(chat_id))
        return
    
    # Выбор услуги
    if data.startswith("service_"):
        sid = int(data.split("_")[1])
        temp[chat_id] = {"service_id": sid}
        send(chat_id, "📅 Выбери дату:", date_buttons())
        return
    
    # Выбор даты
    if data.startswith("date_"):
        date = data.split("_")[1]
        if chat_id not in temp or "service_id" not in temp[chat_id]:
            send(chat_id, "💅 Сначала выбери услугу:", service_buttons())
            return
        
        sid = temp[chat_id]["service_id"]
        service = next((s for s in db.get_services() if s["id"] == sid), None)
        if not service:
            return
        
        free = get_free_slots(date, service["duration"])
        if not free:
            send(chat_id, f"❌ На {date} нет свободных окон под {service['duration']} мин")
        else:
            temp[chat_id]["date"] = date
            send(chat_id, f"📅 {date}\n💅 {service['name']} ({service['duration']}мин)\n\nВыбери время:", 
                 time_buttons(date, free, sid))
        return
    
    # Выбор времени
    if data.startswith("time_"):
        parts = data.split("_")
        if len(parts) != 4:
            return
        _, date, slot_time, sid = parts
        sid = int(sid)
        full_slot = f"{date} {slot_time}"
        
        service = next((s for s in db.get_services() if s["id"] == sid), None)
        if not service:
            return
        
        free = get_free_slots(date, service["duration"])
        if slot_time not in free:
            send(chat_id, f"❌ Время {slot_time} уже занято")
            return
        
        name = f"Клиент"
        if db.add_booking(full_slot, chat_id, name, "", sid):
            temp.pop(chat_id, None)
            send(chat_id, f"✅ Запись подтверждена!\n\n📅 {full_slot}\n💅 {service['name']}\n💰 {service['price']} грн")
            admin = db.get_setting("admin_id")
            if admin:
                send(int(admin), f"📝 Новая запись!\n{full_slot}\n{service['name']}")
        else:
            send(chat_id, "❌ Ошибка: время уже занято")
        return
    
    # Отмена
    if data.startswith("cancel_"):
        slot = data.replace("cancel_", "")
        if not db.can_cancel(slot):
            send(chat_id, "⏰ Отменить можно за 2 часа до начала")
        elif db.cancel_booking(slot, user_id=chat_id):
            send(chat_id, f"✅ Запись на {slot} отменена")

# ========== ЗАПУСК ==========

def main():
    if not is_working_hour():
        print(f"Нерабочее время {datetime.now()}")
        return
    
    print(f"Запуск {datetime.now()}")
    last_id = int(db.get_setting("last_update_id", "0"))
    
    try:
        resp = requests.get(f"{URL}/getUpdates", params={"offset": last_id + 1, "timeout": 30}, timeout=35)
        data = resp.json()
        
        if not data.get("ok"):
            return
        
        for update in data["result"]:
            db.set_setting("last_update_id", str(update["update_id"]))
            
            if "message" in update:
                msg = update["message"]
                chat_id = msg["chat"]["id"]
                text = msg.get("text", "")
                handle_message(chat_id, text)
            
            elif "callback_query" in update:
                cb = update["callback_query"]
                chat_id = cb["message"]["chat"]["id"]
                handle_callback(chat_id, cb["data"])
                
    except Exception as e:
        print(f"Ошибка: {e}")

if __name__ == "__main__":
    main()