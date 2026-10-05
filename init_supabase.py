import os
import sys
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.environ.get("POSTGRES_URL") or os.environ.get("DATABASE_URL")

def init_db():
    if not DB_URL:
        print("Lỗi: Chưa cấu hình biến môi trường POSTGRES_URL trong file .env.")
        return

    try:
        import psycopg2
        conn = psycopg2.connect(DB_URL)
        cursor = conn.cursor()
        
        # 1. Bảng netflix_accounts
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS netflix_accounts (
                email TEXT PRIMARY KEY,
                expire_date TEXT,
                netflix_id TEXT,
                secure_netflix_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                plan TEXT DEFAULT 'Premium',
                status TEXT DEFAULT 'usable',
                assignment_version INTEGER DEFAULT 1
            );
            ALTER TABLE netflix_accounts ADD COLUMN IF NOT EXISTS plan TEXT DEFAULT 'Premium';
            ALTER TABLE netflix_accounts ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'usable';
            ALTER TABLE netflix_accounts ADD COLUMN IF NOT EXISTS assignment_version INTEGER DEFAULT 1;
        """)
        
        # 2. Bảng access_keys
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS access_keys (
                code TEXT PRIMARY KEY,
                assigned_email TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expire_at TEXT,
                plan TEXT DEFAULT 'Premium',
                assignment_version INTEGER DEFAULT 1
            );
            ALTER TABLE access_keys ADD COLUMN IF NOT EXISTS plan TEXT DEFAULT 'Premium';
            ALTER TABLE access_keys ADD COLUMN IF NOT EXISTS assignment_version INTEGER DEFAULT 1;
        """)

        # 3. Bảng requests (bảo hành / khiếu nại)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS requests (
                id SERIAL PRIMARY KEY,
                code TEXT,
                u7buy_order_id TEXT,
                image_url TEXT,
                reason TEXT,
                status TEXT DEFAULT 'pending',
                blocked_reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            ALTER TABLE requests ADD COLUMN IF NOT EXISTS u7buy_order_id TEXT;
            ALTER TABLE requests ADD COLUMN IF NOT EXISTS blocked_reason TEXT;
        """)
        
        conn.commit()
        cursor.close()
        conn.close()
        print("Bảng dữ liệu đã được khởi tạo/đồng bộ thành công trên Supabase!")
    except Exception as e:
        print("Lỗi khi tạo bảng trên Supabase:", e)

if __name__ == "__main__":
    init_db()
