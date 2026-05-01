import sqlite3
import json
from datetime import datetime, timedelta

DB_NAME = "bookings.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Таблица записей
    c.execute('''CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        slot TEXT NOT NULL,
        user_id INTEGER NOT NULL,
        user_name TEXT,
        phone TEXT,
        service_id INTEGER,
        reminder_sent INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Таблица услуг
    c.execute('''CREATE TABLE IF NOT EXISTS services (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        duration INTEGER NOT NULL,
        price INTEGER NOT NULL
    )''')
    
    # Таблица настроек
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')
    
    # Добавляем тестовые услуги, если их нет
    c.execute("SELECT COUNT(*) FROM services")
    if c.fetchone()[0] == 0:
        services = [
            ("Маникюр", 60, 1000),
            ("Педикюр", 90, 1500),
            ("Маникюр + покрытие", 90, 2000),
            ("Наращивание", 120, 3000),
        ]
        c.executemany("INSERT INTO services (name, duration, price) VALUES (?, ?, ?)", services)
    
    conn.commit()
    conn.close()

def get_services():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, name, duration, price FROM services")
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "duration": r[2], "price": r[3]} for r in rows]

def add_booking(slot, user_id, user_name, phone, service_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO bookings (slot, user_id, user_name, phone, service_id) VALUES (?, ?, ?, ?, ?)",
                  (slot, user_id, user_name, phone, service_id))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_all_active_bookings():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''SELECT b.slot, b.user_id, b.user_name, s.name as service_name 
                 FROM bookings b 
                 JOIN services s ON b.service_id = s.id 
                 WHERE datetime(b.slot) > datetime('now')
                 ORDER BY b.slot''')
    rows = c.fetchall()
    conn.close()
    return [{"slot": r[0], "user_id": r[1], "name": r[2], "service": r[3]} for r in rows]

def get_user_bookings(user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''SELECT b.slot, b.id, s.name as service_name 
                 FROM bookings b 
                 JOIN services s ON b.service_id = s.id 
                 WHERE b.user_id = ? AND datetime(b.slot) > datetime('now')
                 ORDER BY b.slot''', (user_id,))
    rows = c.fetchall()
    conn.close()
    return [{"slot": r[0], "id": r[1], "service": r[2]} for r in rows]

def cancel_booking(slot, user_id=None, is_admin=False):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    if user_id:
        c.execute("DELETE FROM bookings WHERE slot = ? AND user_id = ?", (slot, user_id))
    else:
        c.execute("DELETE FROM bookings WHERE slot = ?", (slot,))
    affected = c.rowcount
    conn.commit()
    conn.close()
    return affected > 0

def get_booking_by_slot(slot):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''SELECT b.slot, b.user_id, b.user_name, b.service_id, s.name as service_name 
                 FROM bookings b 
                 JOIN services s ON b.service_id = s.id 
                 WHERE b.slot = ?''', (slot,))
    row = c.fetchone()
    conn.close()
    if row:
        return {"slot": row[0], "user_id": row[1], "user_name": row[2], "service_id": row[3], "service": row[4]}
    return None

def admin_reschedule_booking(old_slot, new_slot):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("UPDATE bookings SET slot = ? WHERE slot = ?", (new_slot, old_slot))
        conn.commit()
        return c.rowcount > 0
    except:
        return False
    finally:
        conn.close()

def get_upcoming_bookings(hours=1):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    now = datetime.now()
    future = now + timedelta(hours=hours)
    c.execute('''SELECT b.id, b.slot, b.user_id, s.name as service_name 
                 FROM bookings b 
                 JOIN services s ON b.service_id = s.id 
                 WHERE datetime(b.slot) BETWEEN datetime(?) AND datetime(?) 
                 AND b.reminder_sent = 0''', 
              (now.strftime("%Y-%m-%d %H:%M"), future.strftime("%Y-%m-%d %H:%M")))
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "slot": r[1], "user_id": r[2], "service": r[3]} for r in rows]

def mark_reminder_sent(booking_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE bookings SET reminder_sent = 1 WHERE id = ?", (booking_id,))
    conn.commit()
    conn.close()

def can_cancel(slot):
    slot_time = datetime.strptime(slot, "%Y-%m-%d %H:00")
    deadline_minutes = int(get_setting("cancellation_deadline_minutes", "120"))
    return slot_time - datetime.now() > timedelta(minutes=deadline_minutes)

def get_setting(key, default=""):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else default

def set_setting(key, value):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

# Инициализация БД при импорте
init_db()
