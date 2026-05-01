import sqlite3
from datetime import datetime, timedelta

DB = "bookings.db"

def get_conn():
    return sqlite3.connect(DB)

def init():
    with get_conn() as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slot TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            user_name TEXT,
            service_id INTEGER,
            reminder_sent INTEGER DEFAULT 0
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            duration INTEGER NOT NULL,
            price INTEGER NOT NULL
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )''')
        
        if c.execute("SELECT COUNT(*) FROM services").fetchone()[0] == 0:
            services = [
                ("Манікюр", 60, 300),
                ("Педикюр", 90, 500),
                ("Манікюр + покриття", 90, 450),
            ]
            c.executemany("INSERT INTO services (name, duration, price) VALUES (?, ?, ?)", services)
        conn.commit()

def get_services():
    with get_conn() as conn:
        return [{"id": r[0], "name": r[1], "duration": r[2], "price": r[3]} 
                for r in conn.execute("SELECT id, name, duration, price FROM services")]

def add_booking(slot, user_id, user_name, phone, service_id):
    try:
        with get_conn() as conn:
            conn.execute("INSERT INTO bookings (slot, user_id, user_name, service_id) VALUES (?, ?, ?, ?)",
                        (slot, user_id, user_name, service_id))
        return True
    except:
        return False

def get_all_active_bookings():
    with get_conn() as conn:
        return [{"slot": r[0], "user_id": r[1], "name": r[2], "service": r[3]}
                for r in conn.execute('''SELECT b.slot, b.user_id, b.user_name, s.name 
                FROM bookings b JOIN services s ON b.service_id = s.id 
                WHERE datetime(b.slot) > datetime('now') ORDER BY b.slot''')]

def get_user_bookings(user_id):
    with get_conn() as conn:
        return [{"slot": r[0], "id": r[1], "service": r[2]}
                for r in conn.execute('''SELECT b.slot, b.id, s.name 
                FROM bookings b JOIN services s ON b.service_id = s.id 
                WHERE b.user_id = ? AND datetime(b.slot) > datetime('now')''', (user_id,))]

def cancel_booking(slot, user_id=None):
    with get_conn() as conn:
        if user_id:
            cur = conn.execute("DELETE FROM bookings WHERE slot = ? AND user_id = ?", (slot, user_id))
        else:
            cur = conn.execute("DELETE FROM bookings WHERE slot = ?", (slot,))
        return cur.rowcount > 0

def can_cancel(slot):
    slot_time = datetime.strptime(slot, "%Y-%m-%d %H:00")
    return slot_time - datetime.now() > timedelta(hours=2)

def get_setting(key, default=""):
    with get_conn() as conn:
        cur = conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cur.fetchone()
        return row[0] if row else default

def set_setting(key, value):
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))

init()