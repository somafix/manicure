#!/usr/bin/env python3
# TELEGRAM БОТ ДЛЯ ЗАПИСИ НА МАНИКЮР
# СОХРАНИ КАК bot.py, ЗАПУСТИ, ВСЁ РАБОТАЕТ

import os
import sqlite3
import json
import time
from datetime import datetime, timedelta
import requests

# ========== НАСТРОЙКИ (МЕНЯЙ ТУТ) ==========
TOKEN = "сюда_свой_токен"           # Токен бота от @BotFather
ADMIN_ID = 123456789                # Твой Telegram ID (узнать у @userinfobot)
# ===========================================

URL = f"https://api.telegram.org/bot{TOKEN}"
DB_NAME = "manicure.db"

# Рабочее время
WORK_START = 9      # с 9 утра
WORK_END = 20       # до 8 вечера
STEP = 60           # шаг записи в минутах

# ========== БАЗА ДАННЫХ (ОДИН ФАЙЛ) ==========
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        time TEXT,
        name TEXT,
        phone TEXT,
        service TEXT,
        user_id INTEGER,
        created_at TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS blocked (
        date TEXT,
        time TEXT,
        PRIMARY KEY (date, time)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS last_id (
        id INTEGER
    )''')
    c.execute("SELECT COUNT(*) FROM last_id")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO last_id (id) VALUES (0)")
    conn.commit()
    conn.close()

def get_last_id():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id FROM last_id")
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def set_last_id(uid):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE last_id SET id = ?", (uid,))
    conn.commit()
    conn.close()

def add_order(date, time, name, phone, service, user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO orders (date, time, name, phone, service, user_id, created_at) VALUES (?,?,?,?,?,?,?)",
              (date, time, name, phone, service, user_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_today_orders():
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT time, name, phone, service FROM orders WHERE date = ? ORDER BY time", (today,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_all_orders():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT date, time, name, phone, service FROM orders ORDER BY date, time")
    rows = c.fetchall()
    conn.close()
    return rows

def cancel_order(date, time):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM orders WHERE date = ? AND time = ?", (date, time))
    deleted = c.rowcount
    conn.commit()
    conn.close()
    return deleted > 0

def is_time_blocked(date, time):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT 1 FROM blocked WHERE date = ? AND time = ?", (date, time))
    row = c.fetchone()
    conn.close()
    return row is not None

def is_time_booked(date, time):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT 1 FROM orders WHERE date = ? AND time = ?", (date, time))
    row = c.fetchone()
    conn.close()
    return row is not None

def get_free_slots(date):
    free = []
    hour = WORK_START
    while hour < WORK_END:
        time_str = f"{hour:02d}:00"
        if not is_time_booked(date, time_str) and not is_time_blocked(date, time_str):
            free.append(time_str)
        hour += STEP // 60
    return free

# ========== КНОПКИ (КРАСИВЫЕ) ==========
def main_menu():
    return {
        "inline_keyboard": [
            [{"text": "💅 ЗАПИСАТЬСЯ", "callback_data": "book"}],
            [{"text": "📋 МОИ ЗАПИСИ", "callback_data": "my_orders"}],
            [{"text": "🕒 СВОБОДНЫЕ ОКНА", "callback_data": "free"}],
            [{"text": "👸 АДМИН", "callback_data": "admin"}]
        ]
    }

def date_buttons():
    buttons = []
    for i in range(5):
        d = (datetime.now() + timedelta(days=i)).strftime("%Y-%m-%d")
        day_name = ["СЕГОДНЯ", "ЗАВТРА", "ПОСЛЕЗАВТРА", f"+3 ДНЯ", f"+4 ДНЯ"][i]
        buttons.append([{"text": f"📅 {day_name} {d}", "callback_data": f"date_{d}"}])
    buttons.append([{"text": "◀️ НАЗАД", "callback_data": "back"}])
    return {"inline_keyboard": buttons}

def service_buttons():
    return {
        "inline_keyboard": [
            [{"text": "💅 МАНИКЮР", "callback_data": "service_manicure"}],
            [{"text": "🦶 ПЕДИКЮР", "callback_data": "service_pedicure"}],
            [{"text": "✨ МАНИКЮР + ПЕДИКЮР", "callback_data": "service_both"}],
            [{"text": "🎨 ПОКРЫТИЕ ГЕЛЬ-ЛАК", "callback_data": "service_gel"}],
            [{"text": "◀️ НАЗАД", "callback_data": "back"}]
        ]
    }

def time_buttons(date, slots):
    buttons = []
    for s in slots:
        buttons.append([{"text": f"🕐 {s}", "callback_data": f"time_{date}_{s}"}])
    buttons.append([{"text": "◀️ ДРУГАЯ ДАТА", "callback_data": "back_date"}])
    return {"inline_keyboard": buttons}

def confirm_buttons(date, time, service, name, phone):
    return {
        "inline_keyboard": [
            [{"text": "✅ ПОДТВЕРДИТЬ", "callback_data": f"confirm_{date}_{time}_{service}_{name}_{phone}"}],
            [{"text": "❌ ОТМЕНИТЬ", "callback_data": "back"}]
        ]
    }

def admin_menu():
    return {
        "inline_keyboard": [
            [{"text": "📋 СЕГОДНЯШНИЕ ЗАПИСИ", "callback_data": "admin_today"}],
            [{"text": "📜 ВСЕ ЗАПИСИ", "callback_data": "admin_all"}],
            [{"text": "❌ ОТМЕНИТЬ ЗАПИСЬ", "callback_data": "admin_cancel"}],
            [{"text": "🚫 ЗАБЛОКИРОВАТЬ ВРЕМЯ", "callback_data": "admin_block"}],
            [{"text": "◀️ НАЗАД", "callback_data": "back"}]
        ]
    }

def cancel_select_buttons():
    orders = get_all_orders()
    if not orders:
        return None
    buttons = []
    for date, time, name, phone, service in orders[:20]:
        buttons.append([{"text": f"❌ {date} {time} — {name}", "callback_data": f"admin_del_{date}_{time}"}])
    buttons.append([{"text": "◀️ НАЗАД", "callback_data": "admin"}])
    return {"inline_keyboard": buttons}

def block_buttons():
    today = datetime.now().strftime("%Y-%m-%d")
    free = get_free_slots(today)
    if not free:
        return None
    buttons = []
    for t in free[:12]:
        buttons.append([{"text": f"🚫 ЗАБЛОКИРОВАТЬ {t}", "callback_data": f"admin_block_{today}_{t}"}])
    buttons.append([{"text": "◀️ НАЗАД", "callback_data": "admin"}])
    return {"inline_keyboard": buttons}

# ========== ЛОГИКА БОТА ==========
user_data = {}

def send(chat_id, text, keyboard=None):
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if keyboard:
        data["reply_markup"] = json.dumps(keyboard)
    try:
        requests.post(f"{URL}/sendMessage", json=data, timeout=5)
    except:
        pass

def handle_callback(chat_id, callback):
    # НАЗАД
    if callback == "back":
        send(chat_id, "⭐️ ГЛАВНОЕ МЕНЮ ⭐️", main_menu())
        user_data.pop(chat_id, None)
        return
    
    if callback == "back_date":
        send(chat_id, "📅 ВЫБЕРИ ДАТУ", date_buttons())
        return
    
    # ГЛАВНОЕ МЕНЮ
    if callback == "book":
        send(chat_id, "💅 ВЫБЕРИ УСЛУГУ", service_buttons())
        return
    
    if callback == "my_orders":
        orders = []
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT date, time, service FROM orders WHERE user_id = ? ORDER BY date", (chat_id,))
        orders = c.fetchall()
        conn.close()
        
        if not orders:
            send(chat_id, "📭 У ВАС НЕТ АКТИВНЫХ ЗАПИСЕЙ", main_menu())
        else:
            text = "📋 <b>ВАШИ ЗАПИСИ:</b>\n\n"
            for d, t, s in orders:
                text += f"🗓 {d} {t}\n💅 {s}\n\n"
            send(chat_id, text, main_menu())
        return
    
    if callback == "free":
        today = datetime.now().strftime("%Y-%m-%d")
        free = get_free_slots(today)
        if not free:
            send(chat_id, "⚠️ НА СЕГОДНЯ СВОБОДНЫХ ОКОН НЕТ", main_menu())
        else:
            text = "🕒 <b>СВОБОДНО СЕГОДНЯ:</b>\n\n" + "\n".join(f"• {f}" for f in free)
            send(chat_id, text, main_menu())
        return
    
    if callback == "admin":
        if chat_id == ADMIN_ID:
            send(chat_id, "👸 <b>АДМИН-ПАНЕЛЬ</b>", admin_menu())
        else:
            send(chat_id, "⛔ ДОСТУП ЗАПРЕЩЕН", main_menu())
        return
    
    # ВЫБОР УСЛУГИ
    if callback.startswith("service_"):
        service = callback.replace("service_", "").replace("_", " ").upper()
        user_data[chat_id] = {"service": service}
        send(chat_id, "📅 ВЫБЕРИ ДАТУ", date_buttons())
        return
    
    # ВЫБОР ДАТЫ
    if callback.startswith("date_"):
        date = callback.replace("date_", "")
        if chat_id not in user_data or "service" not in user_data[chat_id]:
            send(chat_id, "⚠️ СНАЧАЛА ВЫБЕРИ УСЛУГУ", service_buttons())
            return
        
        free = get_free_slots(date)
        if not free:
            send(chat_id, f"❌ НА {date} НЕТ СВОБОДНЫХ ОКОН\nВЫБЕРИ ДРУГУЮ ДАТУ", date_buttons())
        else:
            user_data[chat_id]["date"] = date
            send(chat_id, f"📅 {date}\n💅 {user_data[chat_id]['service']}\n\nВЫБЕРИ ВРЕМЯ:", time_buttons(date, free))
        return
    
    # ВЫБОР ВРЕМЕНИ
    if callback.startswith("time_"):
        parts = callback.split("_")
        date = parts[1]
        time_slot = parts[2]
        
        if is_time_booked(date, time_slot) or is_time_blocked(date, time_slot):
            send(chat_id, "❌ ЭТО ВРЕМЯ УЖЕ ЗАНЯТО ИЛИ ЗАБЛОКИРОВАНО\nВЫБЕРИ ДРУГОЕ", date_buttons())
            return
        
        user_data[chat_id]["order_date"] = date
        user_data[chat_id]["order_time"] = time_slot
        send(chat_id, "✏️ ВВЕДИТЕ ВАШЕ ИМЯ\n(как к вам обращаться)")
        return
    
    # ПОДТВЕРЖДЕНИЕ
    if callback.startswith("confirm_"):
        parts = callback.split("_")
        date = parts[1]
        time_slot = parts[2]
        service = parts[3]
        name = parts[4]
        phone = user_data.get(chat_id, {}).get("phone", "не указан")
        
        if is_time_booked(date, time_slot):
            send(chat_id, "❌ ОШИБКА! ЭТО ВРЕМЯ УЖЕ ЗАНЯТО\nПОПРОБУЙТЕ СНОВА", main_menu())
            return
        
        add_order(date, time_slot, name, phone, service, chat_id)
        send(chat_id, f"✅ <b>ВЫ ЗАПИСАНЫ!</b>\n\n🗓 {date} {time_slot}\n💅 {service}\n👤 {name}\n\nЖДЕМ ВАС ❤️", main_menu())
        
        # Уведомление админу
        send(ADMIN_ID, f"🆕 <b>НОВАЯ ЗАПИСЬ!</b>\n\n📅 {date} {time_slot}\n💅 {service}\n👤 {name}\n📞 {phone}")
        user_data.pop(chat_id, None)
        return
    
    # АДМИН: СЕГОДНЯ
    if callback == "admin_today" and chat_id == ADMIN_ID:
        orders = get_today_orders()
        if not orders:
            send(chat_id, "📭 НА СЕГОДНЯ ЗАПИСЕЙ НЕТ", admin_menu())
        else:
            text = "📋 <b>ЗАПИСИ НА СЕГОДНЯ:</b>\n\n"
            for t, n, p, s in orders:
                text += f"🕐 {t} | {n} | {s}\n📞 {p}\n\n"
            send(chat_id, text, admin_menu())
        return
    
    # АДМИН: ВСЕ ЗАПИСИ
    if callback == "admin_all" and chat_id == ADMIN_ID:
        orders = get_all_orders()
        if not orders:
            send(chat_id, "📭 ЗАПИСЕЙ НЕТ", admin_menu())
        else:
            text = "📜 <b>ВСЕ ЗАПИСИ:</b>\n\n"
            for d, t, n, p, s in orders:
                text += f"🗓 {d} {t}\n👤 {n} | {s}\n📞 {p}\n\n"
                if len(text) > 3500:
                    send(chat_id, text)
                    text = ""
            if text:
                send(chat_id, text, admin_menu())
        return
    
    # АДМИН: ОТМЕНИТЬ ЗАПИСЬ
    if callback == "admin_cancel" and chat_id == ADMIN_ID:
        kb = cancel_select_buttons()
        if kb:
            send(chat_id, "❌ ВЫБЕРИ ЗАПИСЬ ДЛЯ ОТМЕНЫ", kb)
        else:
            send(chat_id, "📭 НЕТ ЗАПИСЕЙ ДЛЯ ОТМЕНЫ", admin_menu())
        return
    
    if callback.startswith("admin_del_") and chat_id == ADMIN_ID:
        parts = callback.split("_")
        date = parts[2]
        time_slot = parts[3]
        if cancel_order(date, time_slot):
            send(chat_id, f"✅ ЗАПИСЬ НА {date} {time_slot} ОТМЕНЕНА", admin_menu())
        else:
            send(chat_id, "❌ НЕ УДАЛОСЬ ОТМЕНИТЬ", admin_menu())
        return
    
    # АДМИН: ЗАБЛОКИРОВАТЬ ВРЕМЯ
    if callback == "admin_block" and chat_id == ADMIN_ID:
        kb = block_buttons()
        if kb:
            send(chat_id, "🚫 ВЫБЕРИ ВРЕМЯ ДЛЯ БЛОКИРОВКИ", kb)
        else:
            send(chat_id, "⚠️ НЕТ СВОБОДНЫХ ОКОН ДЛЯ БЛОКИРОВКИ", admin_menu())
        return
    
    if callback.startswith("admin_block_") and chat_id == ADMIN_ID:
        parts = callback.split("_")
        date = parts[2]
        time_slot = parts[3]
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO blocked (date, time) VALUES (?,?)", (date, time_slot))
        conn.commit()
        conn.close()
        send(chat_id, f"🚫 ВРЕМЯ {date} {time_slot} ЗАБЛОКИРОВАНО", admin_menu())
        return

def handle_message(chat_id, text):
    # Если ждем имя
    if chat_id in user_data and "order_date" in user_data[chat_id] and "order_time" in user_data[chat_id]:
        user_data[chat_id]["name"] = text
        send(chat_id, "📞 ВВЕДИТЕ ВАШ ТЕЛЕФОН\n(для связи)")
        return
    
    # Если ждем телефон
    if chat_id in user_data and "name" in user_data[chat_id] and "phone" not in user_data[chat_id]:
        user_data[chat_id]["phone"] = text
        order = user_data[chat_id]
        send(chat_id, f"✅ <b>ПРОВЕРЬТЕ ДАННЫЕ:</b>\n\n🗓 {order['order_date']} {order['order_time']}\n💅 {order['service']}\n👤 {order['name']}\n📞 {text}\n\nВСЕ ВЕРНО?", 
             confirm_buttons(order['order_date'], order['order_time'], order['service'], order['name'], text))
        return
    
    # Команды
    if text == "/start":
        send(chat_id, "✨ <b>МАНИКЮР-БОТ</b> ✨\n\nЗапись на маникюр и педикюр\n\n👇 ВЫБЕРИТЕ ДЕЙСТВИЕ", main_menu())
    else:
        send(chat_id, "ИСПОЛЬЗУЙТЕ КНОПКИ МЕНЮ 👆", main_menu())

# ========== ЗАПУСК ==========
def main():
    init_db()
    print(f"✅ БОТ ЗАПУЩЕН {datetime.now()}")
    print(f"👸 АДМИН ID: {ADMIN_ID}")
    
    last_id = get_last_id()
    
    while True:
        try:
            resp = requests.get(f"{URL}/getUpdates", params={"offset": last_id + 1, "timeout": 30}, timeout=35)
            data = resp.json()
            
            if data.get("ok"):
                for update in data["result"]:
                    last_id = update["update_id"]
                    set_last_id(last_id)
                    
                    if "message" in update:
                        msg = update["message"]
                        chat_id = msg["chat"]["id"]
                        text = msg.get("text", "")
                        handle_message(chat_id, text)
                    
                    elif "callback_query" in update:
                        cb = update["callback_query"]
                        chat_id = cb["message"]["chat"]["id"]
                        handle_callback(chat_id, cb["data"])
                        
                        # Ответ на callback (убирает часики)
                        requests.post(f"{URL}/answerCallbackQuery", json={"callback_query_id": cb["id"]})
            
            time.sleep(0.5)
            
        except Exception as e:
            print(f"Ошибка: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()