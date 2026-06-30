import psycopg2

DB_URL = "postgresql://postgres:Concumm1!@db.zzdlmwhmhjofqmhfknbv.supabase.co:5432/postgres"

def init_db():
    try:
        conn = psycopg2.connect(DB_URL)
        cursor = conn.cursor()
        
        # Create netflix_accounts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS netflix_accounts (
                email TEXT PRIMARY KEY,
                expire_date TEXT,
                netflix_id TEXT,
                secure_netflix_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create access_keys table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS access_keys (
                code TEXT PRIMARY KEY,
                assigned_email TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        cursor.close()
        conn.close()
        print("Bảng dữ liệu đã được tạo thành công trên Supabase!")
    except Exception as e:
        print("Lỗi khi tạo bảng:", e)

if __name__ == "__main__":
    init_db()
