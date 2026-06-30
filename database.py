import sqlite3
import os

DB_FILE = "accounts.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS netflix_accounts (
            email TEXT PRIMARY KEY,
            expire_date TEXT,
            netflix_id TEXT,
            secure_netflix_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS access_keys (
            code TEXT PRIMARY KEY,
            assigned_email TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def save_account(email, expire_date, netflix_id, secure_netflix_id=""):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        REPLACE INTO netflix_accounts (email, expire_date, netflix_id, secure_netflix_id)
        VALUES (?, ?, ?, ?)
    """, (email, expire_date, netflix_id, secure_netflix_id))
    conn.commit()
    conn.close()
    
def delete_account(email):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM netflix_accounts WHERE email = ?", (email,))
    conn.commit()
    conn.close()

def get_all_accounts():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM netflix_accounts")
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_random_available_account():
    # Pick a random account from netflix_accounts
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT email FROM netflix_accounts ORDER BY RANDOM() LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def create_access_key(code):
    email = get_random_available_account()
    if not email:
        return False, "Không còn Cookie nào khả dụng trong kho."
    
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO access_keys (code, assigned_email) VALUES (?, ?)", (code, email))
        conn.commit()
        conn.close()
        return True, "Thành công"
    except sqlite3.IntegrityError:
        return False, "Mã này đã tồn tại."

def get_access_key(code):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT code, assigned_email FROM access_keys WHERE code = ?", (code,))
    row = cursor.fetchone()
    conn.close()
    return row

def get_all_access_keys():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM access_keys ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return rows

def rotate_access_key(code):
    """Assigns a new random cookie to an existing access key."""
    email = get_random_available_account()
    if not email:
        return False # No more cookies available
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE access_keys SET assigned_email = ? WHERE code = ?", (email, code))
    conn.commit()
    conn.close()
    return True

def delete_access_key(code):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM access_keys WHERE code = ?", (code,))
    conn.commit()
    conn.close()
