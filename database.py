import os
import threading
from dotenv import load_dotenv

load_dotenv()

from supabase import create_client, Client

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://zzdlmwhmhjofqmhfknbv.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_KEY") or ""

_local = threading.local()

def get_supabase() -> Client:
    if not hasattr(_local, "client"):
        key = SUPABASE_KEY or "dummy_key_to_prevent_startup_crash"
        _local.client = create_client(SUPABASE_URL, key)
    return _local.client

import json
import sqlite3

def get_sqlite_conn(db_path=None):
    override = os.environ.get("SQLITE_DB_PATH")
    if override:
        db_path = override
    elif not db_path:
        db_path = "accounts.db"
    conn = sqlite3.connect(db_path, timeout=15)
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.execute("PRAGMA synchronous = NORMAL;")
    except Exception:
        pass
    return conn

CONFIG_FILE = "config.json"

def get_config(key, default=None):
    # 1. Thử lấy từ Supabase DB để lưu vĩnh viễn (nếu có SUPABASE_KEY)
    if SUPABASE_KEY:
        try:
            res = get_supabase().table("system_config").select("value").eq("key", key).limit(1).execute()
            if res.data and len(res.data) > 0:
                val = res.data[0].get("value")
                if val is not None:
                    if str(val).lower() == 'true': return True
                    if str(val).lower() == 'false': return False
                    return val
        except Exception:
            pass

    # 2. Fallback lấy từ config.json local
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f).get(key, default)
    except:
        return default

def set_config(key, value):
    # 1. Lưu vào local config.json
    try:
        data = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
        data[key] = value
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f)
    except:
        pass
        
    # 2. Lưu vào Supabase DB (nếu có bảng system_config) để giữ cấu hình vĩnh viễn
    if SUPABASE_KEY:
        try:
            get_supabase().table("system_config").upsert({"key": key, "value": str(value)}).execute()
        except Exception as e:
            print(f"Supabase set_config notice: {e}")

def init_db():
    try:
        import sqlite3
        conn = get_sqlite_conn("accounts.db")
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS netflix_accounts (
            email TEXT PRIMARY KEY,
            expire_date TEXT,
            netflix_id TEXT,
            secure_netflix_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            plan TEXT,
            status TEXT DEFAULT 'usable',
            assignment_version INTEGER DEFAULT 1
        )""")
        for col_def in ["plan TEXT", "status TEXT DEFAULT 'usable'", "assignment_version INTEGER DEFAULT 1"]:
            try:
                c.execute(f"ALTER TABLE netflix_accounts ADD COLUMN {col_def}")
            except Exception:
                pass

        c.execute("""CREATE TABLE IF NOT EXISTS access_keys (
            code TEXT PRIMARY KEY,
            assigned_email TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expire_at TEXT,
            plan TEXT DEFAULT 'Premium',
            assignment_version INTEGER DEFAULT 1
        )""")
        for col_def in ["expire_at TEXT", "plan TEXT DEFAULT 'Premium'", "assignment_version INTEGER DEFAULT 1"]:
            try:
                c.execute(f"ALTER TABLE access_keys ADD COLUMN {col_def}")
            except Exception:
                pass

        c.execute("""CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT,
            u7buy_order_id TEXT,
            image_url TEXT,
            reason TEXT,
            status TEXT DEFAULT 'pending',
            blocked_reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        for col_def in ["u7buy_order_id TEXT", "reason TEXT", "blocked_reason TEXT"]:
            try:
                c.execute(f"ALTER TABLE requests ADD COLUMN {col_def}")
            except Exception:
                pass

        c.execute("""CREATE TABLE IF NOT EXISTS operations (
            operation_id TEXT PRIMARY KEY,
            status TEXT,
            assigned_email TEXT,
            detail_code TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS rotation_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT,
            old_email TEXT,
            new_email TEXT,
            actor TEXT,
            reason TEXT,
            request_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS events_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            retry_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            delivered_at TIMESTAMP
        )""")

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"init_db local SQLite notice: {e}")

    # Đồng bộ schema PostgreSQL nếu có POSTGRES_URL
    pg_url = os.environ.get("POSTGRES_URL") or os.environ.get("DATABASE_URL")
    if pg_url:
        try:
            import psycopg2
            pg_conn = psycopg2.connect(pg_url, connect_timeout=3)
            pg_cur = pg_conn.cursor()
            pg_cur.execute("""
                ALTER TABLE IF EXISTS netflix_accounts ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'usable';
                ALTER TABLE IF EXISTS netflix_accounts ADD COLUMN IF NOT EXISTS assignment_version INTEGER DEFAULT 1;
                ALTER TABLE IF EXISTS netflix_accounts ADD COLUMN IF NOT EXISTS plan TEXT DEFAULT 'Premium';
                ALTER TABLE IF EXISTS access_keys ADD COLUMN IF NOT EXISTS plan TEXT DEFAULT 'Premium';
                ALTER TABLE IF EXISTS access_keys ADD COLUMN IF NOT EXISTS assignment_version INTEGER DEFAULT 1;
                ALTER TABLE IF EXISTS requests ADD COLUMN IF NOT EXISTS u7buy_order_id TEXT;
                ALTER TABLE IF EXISTS requests ADD COLUMN IF NOT EXISTS blocked_reason TEXT;
            """)
            pg_conn.commit()
            pg_cur.close()
            pg_conn.close()
        except Exception:
            pass

def save_account(email, expire_date, netflix_id, secure_netflix_id="", plan=None):
    data = {
        "email": email,
        "expire_date": expire_date,
        "netflix_id": netflix_id,
        "secure_netflix_id": secure_netflix_id
    }
    if plan:
        data["plan"] = plan
    success = False
    if SUPABASE_KEY:
        try:
            get_supabase().table("netflix_accounts").upsert(data).execute()
            success = True
        except Exception as e:
            print(f"Supabase save_account error: {e}")
    try:
        import sqlite3
        conn = get_sqlite_conn("accounts.db")
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS netflix_accounts (
            email TEXT PRIMARY KEY,
            expire_date TEXT,
            netflix_id TEXT,
            secure_netflix_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            plan TEXT
        )""")
        try:
            c.execute("ALTER TABLE netflix_accounts ADD COLUMN plan TEXT")
        except Exception:
            pass
        c.execute("INSERT OR REPLACE INTO netflix_accounts (email, expire_date, netflix_id, secure_netflix_id, plan) VALUES (?, ?, ?, ?, ?)",
                  (email, expire_date, netflix_id, secure_netflix_id, plan or "Premium"))
        conn.commit()
        conn.close()
        success = True
    except Exception as e:
        print(f"SQLite save_account error: {e}")
    return success
    
def is_account_shared_by_others(email, exclude_code=None):
    """Kiểm tra xem tài khoản email còn được các Access Code khác tham chiếu không (Shared Mode)"""
    if not email:
        return False
    if SUPABASE_KEY:
        try:
            q = get_supabase().table("access_keys").select("code").eq("assigned_email", email)
            if exclude_code:
                q = q.neq("code", exclude_code)
            res = q.limit(1).execute()
            if res.data:
                return True
        except Exception as e:
            print(f"Supabase is_account_shared_by_others error: {e}")
    try:
        import sqlite3
        db_path = "accounts.db" if os.path.exists("accounts.db") else None
        if db_path:
            conn = get_sqlite_conn(db_path)
            c = conn.cursor()
            if exclude_code:
                c.execute("SELECT code FROM access_keys WHERE assigned_email = ? AND code != ? LIMIT 1", (email, exclude_code))
            else:
                c.execute("SELECT code FROM access_keys WHERE assigned_email = ? LIMIT 1", (email,))
            row = c.fetchone()
            conn.close()
            return row is not None
    except Exception as e:
        print(f"SQLite is_account_shared_by_others error: {e}")
    return False

def delete_account(email, exclude_code=None, force=False):
    if not email:
        return False
    # Bảo vệ tài khoản dùng chung: Không xóa nếu vẫn còn mã khác tham chiếu
    if not force and is_account_shared_by_others(email, exclude_code):
        print(f"Shared account protected: Keeping {email} because other access key(s) still reference it.")
        return True

    success = False
    if SUPABASE_KEY:
        try:
            get_supabase().table("netflix_accounts").delete().eq("email", email).execute()
            success = True
        except Exception as e:
            print(f"Supabase delete error: {e}")
    try:
        import sqlite3
        if os.path.exists("accounts.db"):
            conn = get_sqlite_conn("accounts.db")
            c = conn.cursor()
            c.execute("DELETE FROM netflix_accounts WHERE email = ?", (email,))
            conn.commit()
            conn.close()
            success = True
    except Exception as e:
        print(f"SQLite delete error: {e}")
    return success

def update_plan(email, plan):
    data = {"plan": plan}
    success = False
    if SUPABASE_KEY:
        try:
            get_supabase().table("netflix_accounts").update(data).eq("email", email).execute()
            success = True
        except Exception as e:
            print(f"Supabase update_plan error: {e}")
    try:
        import sqlite3
        if os.path.exists("accounts.db"):
            conn = get_sqlite_conn("accounts.db")
            c = conn.cursor()
            c.execute("UPDATE netflix_accounts SET plan = ? WHERE email = ?", (plan, email))
            conn.commit()
            conn.close()
            success = True
    except Exception as e:
        print(f"SQLite update_plan error: {e}")
    return success

def fetch_all_rows(table_name, columns="*"):
    all_data = []
    limit = 1000
    offset = 0
    if SUPABASE_KEY:
        try:
            while True:
                response = get_supabase().table(table_name).select(columns).range(offset, offset + limit - 1).execute()
                data = response.data
                if not data:
                    break
                all_data.extend(data)
                if len(data) < limit:
                    break
                offset += limit
            # Supabase query succeeded. Return authoritative cloud data (even if empty).
            return all_data
        except Exception as e:
            print(f"Supabase fetch error for {table_name}: {e}")

    # Fallback to local SQLite ONLY if Supabase credentials are missing or API transport failed
    try:
        import sqlite3
        db_path = "accounts.db" if os.path.exists("accounts.db") else ("netflix.db" if os.path.exists("netflix.db") else None)
        if db_path:
            conn = get_sqlite_conn(db_path)
            c = conn.cursor()
            if table_name == "netflix_accounts":
                c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='netflix_accounts'")
                if c.fetchone():
                    c.execute("SELECT email, expire_date, netflix_id, secure_netflix_id, created_at, plan FROM netflix_accounts")
                    rows = c.fetchall()
                    conn.close()
                    result = []
                    for r in rows:
                        result.append({
                            "email": r[0] if len(r) > 0 else "",
                            "expire_date": r[1] if len(r) > 1 else "",
                            "netflix_id": r[2] if len(r) > 2 else "",
                            "secure_netflix_id": r[3] if len(r) > 3 else "",
                            "created_at": r[4] if len(r) > 4 else "",
                            "plan": r[5] if len(r) > 5 else "Premium",
                        })
                    return result
            elif table_name == "access_keys":
                c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='access_keys'")
                if c.fetchone():
                    c.execute("SELECT code, assigned_email, created_at, expire_at FROM access_keys")
                    rows = c.fetchall()
                    conn.close()
                    result = []
                    for r in rows:
                        result.append({
                            "code": r[0] if len(r) > 0 else "",
                            "assigned_email": r[1] if len(r) > 1 else "",
                            "created_at": r[2] if len(r) > 2 else "",
                            "expire_at": r[3] if len(r) > 3 else None,
                        })
                    return result
            elif table_name == "requests":
                c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='requests'")
                if c.fetchone():
                    c.execute("SELECT id, code, u7buy_order_id, image_url, reason, status, created_at FROM requests")
                    rows = c.fetchall()
                    conn.close()
                    result = []
                    for r in rows:
                        result.append({
                            "id": r[0],
                            "code": r[1],
                            "u7buy_order_id": r[2] or "N/A",
                            "image_url": r[3],
                            "reason": r[4] or "",
                            "status": r[5],
                            "created_at": r[6]
                        })
                    return result
            conn.close()
    except Exception as e:
        print(f"SQLite fallback error: {e}")
    return all_data

def get_all_accounts():
    data = fetch_all_rows("netflix_accounts")
    # Chuyển đổi list of dicts thành list of tuples cho code cũ tương thích
    rows = []
    for r in data:
        rows.append((r.get("email"), r.get("expire_date"), r.get("netflix_id"), r.get("secure_netflix_id"), r.get("created_at"), r.get("plan", "Premium")))
    return rows

def get_dashboard_aggregates(all_accounts=None, all_access_keys=None):
    """Calculates stock and code counts directly from database or pre-loaded rows."""
    stats = {
        'accounts': {'total': 0, 'Premium': 0, 'Standard': 0, 'Standard_Ads': 0, 'Basic': 0},
        'codes': {'total': 0, 'Premium': 0, 'Standard': 0, 'Standard_Ads': 0, 'Basic': 0}
    }

    # 1. Fast-path: calculate from in-memory objects if provided
    if all_accounts is not None and all_access_keys is not None:
        for acc in all_accounts:
            plan = str(acc[5]).strip() if len(acc) > 5 and acc[5] else "Premium"
            if plan in stats['accounts']:
                stats['accounts'][plan] += 1
            else:
                stats['accounts']['Premium'] += 1
            stats['accounts']['total'] += 1

        for k in all_access_keys:
            code = k[0] if isinstance(k, (list, tuple)) else (k.get("code") or "")
            length = len(code)
            if length == 15: stats['codes']['Premium'] += 1
            elif length == 10: stats['codes']['Standard'] += 1
            elif length == 8: stats['codes']['Standard_Ads'] += 1
            elif length == 5: stats['codes']['Basic'] += 1
            else: stats['codes']['Premium'] += 1
            stats['codes']['total'] += 1
        return stats

    # 2. Supabase aggregation
    if SUPABASE_KEY:
        try:
            acc_rows = fetch_all_rows("netflix_accounts", "plan")
            for r in acc_rows:
                p = str(r.get("plan") or "Premium").strip()
                if p in stats['accounts']:
                    stats['accounts'][p] += 1
                else:
                    stats['accounts']['Premium'] += 1
                stats['accounts']['total'] += 1

            key_rows = fetch_all_rows("access_keys", "code")
            for r in key_rows:
                code = r.get("code") or ""
                length = len(code)
                if length == 15: stats['codes']['Premium'] += 1
                elif length == 10: stats['codes']['Standard'] += 1
                elif length == 8: stats['codes']['Standard_Ads'] += 1
                elif length == 5: stats['codes']['Basic'] += 1
                else: stats['codes']['Premium'] += 1
                stats['codes']['total'] += 1
            return stats
        except Exception as e:
            print(f"Supabase aggregation error: {e}")

    # 3. Direct SQLite query
    try:
        conn = get_sqlite_conn()
        c = conn.cursor()
        c.execute("SELECT plan, COUNT(*) FROM netflix_accounts GROUP BY plan")
        for plan_name, count in c.fetchall():
            p = str(plan_name or "Premium")
            if p in stats['accounts']:
                stats['accounts'][p] += count
            else:
                stats['accounts']['Premium'] += count
            stats['accounts']['total'] += count

        c.execute("SELECT LENGTH(code), COUNT(*) FROM access_keys GROUP BY LENGTH(code)")
        for length, count in c.fetchall():
            if length == 15: stats['codes']['Premium'] += count
            elif length == 10: stats['codes']['Standard'] += count
            elif length == 8: stats['codes']['Standard_Ads'] += count
            elif length == 5: stats['codes']['Basic'] += count
            else: stats['codes']['Premium'] += count
            stats['codes']['total'] += count
        conn.close()
    except Exception as e:
        print(f"Aggregation query notice: {e}")
    return stats

def get_account_by_email(email):
    if SUPABASE_KEY:
        try:
            response = get_supabase().table("netflix_accounts").select("*").eq("email", email).execute()
            if response.data and len(response.data) > 0:
                r = response.data[0]
                return (r["email"], r["expire_date"], r["netflix_id"], r["secure_netflix_id"], r.get("created_at"), r.get("plan"), r.get("status"))
            # Succeeded without exception, but record not found in Supabase -> Definitive Not Found!
            return None
        except Exception as e:
            print(f"Supabase get_account_by_email transport notice: {e}")
    try:
        import sqlite3
        if os.path.exists("accounts.db"):
            conn = get_sqlite_conn("accounts.db")
            c = conn.cursor()
            c.execute("PRAGMA table_info(netflix_accounts)")
            cols = [col[1] for col in c.fetchall()]
            status_sel = ", status" if "status" in cols else ""
            c.execute(f"SELECT email, expire_date, netflix_id, secure_netflix_id, created_at, plan{status_sel} FROM netflix_accounts WHERE email = ?", (email,))
            r = c.fetchone()
            conn.close()
            if r:
                return (r[0], r[1], r[2], r[3], r[4], r[5] if len(r)>5 else "Premium", r[6] if len(r)>6 else None)
    except Exception:
        pass
    return None

def get_account_by_netflix_id(netflix_id):
    if not netflix_id:
        return None
    if SUPABASE_KEY:
        try:
            response = get_supabase().table("netflix_accounts").select("*").eq("netflix_id", netflix_id).limit(1).execute()
            if response.data and len(response.data) > 0:
                r = response.data[0]
                return (r["email"], r["expire_date"], r["netflix_id"], r["secure_netflix_id"], r.get("created_at"), r.get("plan"), r.get("status"))
            return None
        except Exception as e:
            print(f"Supabase get_account_by_netflix_id transport notice: {e}")
    try:
        import sqlite3
        if os.path.exists("accounts.db"):
            conn = get_sqlite_conn("accounts.db")
            c = conn.cursor()
            c.execute("PRAGMA table_info(netflix_accounts)")
            cols = [col[1] for col in c.fetchall()]
            status_sel = ", status" if "status" in cols else ""
            c.execute(f"SELECT email, expire_date, netflix_id, secure_netflix_id, created_at, plan{status_sel} FROM netflix_accounts WHERE netflix_id = ? LIMIT 1", (netflix_id,))
            r = c.fetchone()
            conn.close()
            if r:
                return (r[0], r[1], r[2], r[3], r[4], r[5] if len(r)>5 else "Premium", r[6] if len(r)>6 else None)
    except Exception:
        pass
    return None

def get_random_available_account(plan_type=None, exclude_email=None):
    import random
    
    # Lấy toàn bộ account có trong kho
    acc_data = fetch_all_rows("netflix_accounts", "email, plan")
    if not acc_data:
        return None
        
    premium_kws = ['premium', 'ultra', 'премиум', 'özel', 'ozel', 'cao cấp', 'พรีเมียม', 'مميز', '高級', '高级', 'プレミアム', '프리미엄']
    standard_kws = ['standard', 'tiêu chuẩn', 'стандартный', 'standart', '標準', '标准', 'estándar', 'padrão', 'มาตรฐาน', 'قياسي', 'スタンダード', '스탠다드']
    basic_kws = ['basic', 'cơ bản', 'базовый', 'temel', 'básico', 'พื้นฐาน', 'أساسي', '基本', 'ベーシック', '베이직']
    ads_kws = [
        'ads', 'advert', 'anuncio', 'anúncio', 'pub ', 'pub.', 'pub,', 'avec pub', 
        'con pub', 'publicit', 'pubblicit', 'werbung', 'quảng cáo', 'quang cao', 
        'โฆษณา', '広告', '광고', '廣告', '广告', 'реклам', 'reklam', 'publicidad', 'with ads', 'with_ads'
    ]

    def has_any_kw(text, kws):
        for kw in kws:
            if kw in text:
                return True
        return False

    invalid_plan_markers = ["die", "error", "expired", "payment_error", "hold", "paused", "susp"]

    def is_acc_premium(plan_str):
        if not plan_str or plan_str in ["none", "n/a"]:
            return True
        if any(marker in plan_str for marker in invalid_plan_markers):
            return False
        return has_any_kw(plan_str, premium_kws) or "premium" in plan_str

    def is_acc_standard_no_ads(plan_str):
        if not plan_str or any(marker in plan_str for marker in invalid_plan_markers):
            return False
        # Nếu có bất kỳ dấu hiệu nào của quảng cáo (Ads) -> Loại bỏ ngay lập tức 100%
        if has_any_kw(plan_str, ads_kws) or "standard_ads" in plan_str:
            return False
        # Phải có từ khóa của gói Standard
        return has_any_kw(plan_str, standard_kws) or "standard" in plan_str

    def is_acc_standard_ads(plan_str):
        if not plan_str or any(marker in plan_str for marker in invalid_plan_markers):
            return False
        return (has_any_kw(plan_str, standard_kws) and has_any_kw(plan_str, ads_kws)) or "standard_ads" in plan_str or "with ads" in plan_str

    def is_acc_basic(plan_str):
        if not plan_str or any(marker in plan_str for marker in invalid_plan_markers):
            return False
        return has_any_kw(plan_str, basic_kws) or "basic" in plan_str

    keys_data = fetch_all_rows("access_keys", "assigned_email")
    from collections import Counter
    email_counts = Counter()
    for r in keys_data:
        if r.get("assigned_email"):
            for e in r["assigned_email"].split(","):
                email = e.strip()
                if email:
                    email_counts[email] += 1

    # Cấu hình giới hạn sức chứa (Capacity Bounds)
    share_mode_enabled = get_config("SHARE_MODE_ENABLED", False)

    def get_max_cap(plan_str):
        if not share_mode_enabled:
            return 1
        return 4 if is_acc_premium(plan_str) else 2

    # Lọc các tài khoản hợp lệ, chưa đầy tải và không trùng tài khoản cần loại trừ (exclude_email)
    valid_accs = []
    for r in acc_data:
        email = r.get("email")
        if not email:
            continue
        if exclude_email and email == exclude_email:
            continue
        raw_plan = r.get("plan")
        plan_str = str(raw_plan).lower() if raw_plan else ""
        if any(marker in plan_str for marker in invalid_plan_markers):
            continue
        max_cap = get_max_cap(plan_str)
        if email_counts.get(email, 0) < max_cap:
            valid_accs.append(r)

    if not valid_accs:
        return None

    # Kiểm tra chế độ Mix Plan (Premium + Standard không Ads cho code 15 ký tự / Premium)
    mix_plan_enabled = get_config("MIX_PREMIUM_STANDARD", False)

    if plan_type == "Premium" and mix_plan_enabled:
        premium_emails = []
        standard_no_ads_emails = []

        for r in valid_accs:
            raw_plan = r.get("plan")
            plan_str = str(raw_plan).lower() if raw_plan else ""
            if is_acc_premium(plan_str):
                premium_emails.append(r["email"])
            elif is_acc_standard_no_ads(plan_str):
                standard_no_ads_emails.append(r["email"])

        # 1. Ưu tiên cao nhất: Tài khoản Premium mới tinh (0 code)
        prem_0 = [e for e in premium_emails if email_counts.get(e, 0) == 0]
        if prem_0:
            return random.choice(prem_0)

        # 2. Ưu tiên thứ 2: Tài khoản Standard không ads mới tinh (0 code)
        std_0 = [e for e in standard_no_ads_emails if email_counts.get(e, 0) == 0]
        if std_0:
            return random.choice(std_0)

        # 3. Khi hết tài khoản mới: Ưu tiên tài khoản Premium có 1 code
        prem_1 = [e for e in premium_emails if email_counts.get(e, 0) == 1]
        if prem_1:
            return random.choice(prem_1)

        # 4. Ưu tiên kế tiếp: Tài khoản Standard không ads có 1 code
        std_1 = [e for e in standard_no_ads_emails if email_counts.get(e, 0) == 1]
        if std_1:
            return random.choice(std_1)

        # 5. Fallback trong tập mix (chỉ các tài khoản còn slot < max_cap)
        mix_emails = premium_emails + standard_no_ads_emails
        if mix_emails:
            return min(mix_emails, key=lambda e: (email_counts.get(e, 0), 0 if e in premium_emails else 1))

        return None

    # Logic phân phối mặc định
    if plan_type:
        all_emails = []
        for r in valid_accs:
            raw_plan = r.get("plan")
            plan_str = str(raw_plan).lower() if raw_plan else ""
            
            is_match = False
            if plan_type == "Premium":
                if is_acc_premium(plan_str):
                    is_match = True
            elif plan_type == "Standard_Ads":
                if is_acc_standard_ads(plan_str):
                    is_match = True
            elif plan_type == "Standard":
                if is_acc_standard_no_ads(plan_str):
                    is_match = True
            elif plan_type == "Basic":
                if is_acc_basic(plan_str):
                    is_match = True
                    
            if is_match or plan_type.lower() == plan_str:
                all_emails.append(r["email"])
                
        if not all_emails:
            if plan_type in ["Premium", "Standard"]:
                return None
            all_emails = [r["email"] for r in valid_accs]
    else:
        all_emails = [r["email"] for r in valid_accs]
    
    if not all_emails:
        return None

    available_emails_0 = [email for email in all_emails if email_counts.get(email, 0) == 0]
    available_emails_1 = [email for email in all_emails if email_counts.get(email, 0) == 1]
    
    # 1. Luôn ưu tiên dùng tài khoản mới tinh chưa gán cho code nào (1 code = 1 acc riêng biệt)
    if available_emails_0:
        return random.choice(available_emails_0)
        
    # 2. Khi hết tài khoản mới, gán vào tài khoản có 1 code (nếu nằm trong giới hạn)
    if available_emails_1:
        return random.choice(available_emails_1)
        
    # 3. Fallback: Chọn tài khoản có số lượng code gán ít nhất trong danh sách gói (vẫn đảm bảo < max_cap)
    return min(all_emails, key=lambda e: email_counts.get(e, 0))

def save_request(code, u7buy_order_id, image_url, reason="", status="pending"):
    data = {
        "code": code,
        "u7buy_order_id": u7buy_order_id,
        "image_url": image_url,
        "reason": reason,
        "status": status
    }
    success = False
    if SUPABASE_KEY:
        try:
            get_supabase().table("requests").insert(data).execute()
            success = True
        except Exception as e:
            print(f"Supabase save_request error: {e}")
    try:
        import sqlite3
        conn = get_sqlite_conn("accounts.db")
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT,
            u7buy_order_id TEXT,
            image_url TEXT,
            reason TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("INSERT INTO requests (code, u7buy_order_id, image_url, reason, status) VALUES (?, ?, ?, ?, ?)",
                  (code, u7buy_order_id, image_url, reason, status))
        conn.commit()
        conn.close()
        success = True
    except Exception as e:
        print(f"SQLite save_request error: {e}")
    return success

def create_request(code, image_url, u7buy_order_id="", reason="", status="pending"):
    return save_request(code=code, u7buy_order_id=u7buy_order_id, image_url=image_url, reason=reason, status=status)

def has_recent_request(code, minutes=5):
    import datetime
    if SUPABASE_KEY:
        try:
            time_ago = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=minutes)).isoformat()
            response = get_supabase().table("requests").select("id").eq("code", code).gt("created_at", time_ago).limit(1).execute()
            if response.data is not None:
                return bool(response.data)
        except Exception as e:
            print(f"Supabase has_recent_request notice: {e}")
    try:
        import sqlite3
        if os.path.exists("accounts.db"):
            conn = get_sqlite_conn("accounts.db")
            c = conn.cursor()
            c.execute("SELECT id FROM requests WHERE code = ? AND datetime(created_at) > datetime('now', ?) LIMIT 1", (code, f"-{minutes} minutes"))
            r = c.fetchone()
            conn.close()
            return bool(r)
    except Exception:
        pass
    return False

def get_today_rotation_count(code):
    import datetime
    if SUPABASE_KEY:
        try:
            twenty_four_hours_ago = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)).isoformat()
            response = get_supabase().table("requests") \
                .select("id, status") \
                .eq("code", code) \
                .gt("created_at", twenty_four_hours_ago) \
                .execute()
            if response.data is not None:
                rows = response.data
                accepted_count = sum(1 for r in rows if "accepted" in str(r.get("status", "")))
                return accepted_count
        except Exception as e:
            print(f"Supabase get_today_rotation_count notice: {e}")

    try:
        import sqlite3
        if os.path.exists("accounts.db"):
            conn = get_sqlite_conn("accounts.db")
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM requests WHERE code = ? AND (status LIKE '%accepted%' OR status = 'auto_accepted') AND datetime(created_at) > datetime('now', '-24 hours')", (code,))
            r = c.fetchone()
            conn.close()
            if r:
                return r[0]
    except Exception as e:
        print(f"SQLite get_today_rotation_count error: {e}")
    return 0

def get_pending_requests():
    if SUPABASE_KEY:
        try:
            response = get_supabase().table("requests").select("*").not_.in_("status", ["accepted", "rejected", "deleted"]).order("created_at", desc=True).execute()
            if response.data is not None:
                return response.data
        except Exception as e:
            print(f"Supabase get_pending_requests error: {e}")
    try:
        conn = get_sqlite_conn()
        c = conn.cursor()
        c.execute("SELECT id, code, u7buy_order_id, image_url, reason, status, created_at FROM requests WHERE status NOT IN ('accepted', 'rejected', 'deleted') ORDER BY created_at DESC")
        rows = c.fetchall()
        conn.close()
        res = []
        for r in rows:
            res.append({
                "id": r[0],
                "code": r[1],
                "u7buy_order_id": r[2] if r[2] else "N/A",
                "image_url": r[3],
                "reason": r[4] if r[4] else "",
                "status": r[5],
                "created_at": r[6]
            })
        return res
    except Exception as e:
        print(f"SQLite get_pending_requests error: {e}")
    return []

def update_request_status(req_id, status, code=None):
    data = {"status": status}
    req_id_str = str(req_id).strip()
    success = False
    if SUPABASE_KEY:
        try:
            if req_id_str.isdigit():
                get_supabase().table("requests").update(data).eq("id", int(req_id_str)).execute()
            else:
                get_supabase().table("requests").update(data).eq("id", req_id_str).execute()
            success = True
        except Exception as e:
            print(f"Supabase update_request_status error: {e}")
    try:
        import sqlite3
        if os.path.exists("accounts.db"):
            conn = get_sqlite_conn("accounts.db")
            c = conn.cursor()
            c.execute("UPDATE requests SET status = ? WHERE id = ? OR id = ?",
                      (status, req_id_str, int(req_id_str) if req_id_str.isdigit() else -1))
            conn.commit()
            conn.close()
            success = True
    except Exception as e:
        print(f"SQLite update_request_status error: {e}")
    return success

def delete_request(req_id, code=None):
    req_id_str = str(req_id).strip()
    success = False
    if SUPABASE_KEY:
        try:
            if req_id_str.isdigit():
                get_supabase().table("requests").delete().eq("id", int(req_id_str)).execute()
            else:
                get_supabase().table("requests").delete().eq("id", req_id_str).execute()
            success = True
        except Exception as e:
            print(f"Supabase delete_request error: {e}")
    try:
        import sqlite3
        if os.path.exists("accounts.db"):
            conn = get_sqlite_conn("accounts.db")
            c = conn.cursor()
            c.execute("DELETE FROM requests WHERE id = ? OR id = ?",
                      (req_id_str, int(req_id_str) if req_id_str.isdigit() else -1))
            conn.commit()
            conn.close()
            success = True
    except Exception as e:
        print(f"SQLite delete_request error: {e}")
    return success

def get_request_by_id(req_id):
    req_id_str = str(req_id).strip()
    if SUPABASE_KEY:
        try:
            if req_id_str.isdigit():
                response = get_supabase().table("requests").select("*").eq("id", int(req_id_str)).execute()
                if response.data and len(response.data) > 0:
                    return response.data[0]
            response = get_supabase().table("requests").select("*").eq("id", req_id_str).execute()
            if response.data and len(response.data) > 0:
                return response.data[0]
            return None
        except Exception as e:
            print(f"Supabase get_request_by_id notice: {e}")
    try:
        import sqlite3
        if os.path.exists("accounts.db"):
            conn = get_sqlite_conn("accounts.db")
            c = conn.cursor()
            c.execute("SELECT id, code, u7buy_order_id, image_url, reason, status, created_at FROM requests WHERE id = ? OR id = ?",
                      (req_id_str, int(req_id_str) if req_id_str.isdigit() else -1))
            r = c.fetchone()
            conn.close()
            if r:
                return {
                    "id": r[0],
                    "code": r[1],
                    "u7buy_order_id": r[2] if r[2] else "N/A",
                    "image_url": r[3],
                    "reason": r[4] if r[4] else "",
                    "status": r[5],
                    "created_at": r[6]
                }
    except Exception:
        pass
    return None

def cleanup_old_requests():
    import datetime
    try:
        old_date = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)).isoformat()
        if SUPABASE_KEY:
            response = get_supabase().table("requests").select("*").lt("created_at", old_date).execute()
            old_requests = response.data if response.data else []
            for req in old_requests:
                if req.get("image_url") and "supabase.co/storage/v1/object/public/requests/" in req["image_url"]:
                    try:
                        filename = req["image_url"].split("/")[-1]
                        get_supabase().storage.from_("requests").remove([filename])
                    except Exception:
                        pass
                get_supabase().table("requests").delete().eq("id", req["id"]).execute()
    except Exception as e:
        print(f"Lỗi cleanup requests: {e}")

def create_access_key(code, expire_at=None, plan_type=None):
    from app.services.allocation_service import allocate
    res = allocate(code, plan=plan_type, expire_at=expire_at)
    if res.is_success:
        return True, "Success"
    return False, res.message or f"No available {plan_type or 'Premium'} cookies left in the vault."

def get_access_key(code):
    if SUPABASE_KEY:
        try:
            response = get_supabase().table("access_keys").select("*").eq("code", code).execute()
            if response.data and len(response.data) > 0:
                r = response.data[0]
                return (r["code"], r["assigned_email"], r.get("expire_at"), r.get("plan"))
            # Succeeded without exception, but record not found -> Definitive Not Found!
            return None
        except Exception as e:
            print(f"Supabase get_access_key transport notice: {e}")
    try:
        conn = get_sqlite_conn()
        c = conn.cursor()
        c.execute("PRAGMA table_info(access_keys)")
        cols = [col[1] for col in c.fetchall()]
        p_col = ", plan" if "plan" in cols else ""
        c.execute(f"SELECT code, assigned_email, expire_at{p_col} FROM access_keys WHERE code = ?", (code,))
        r = c.fetchone()
        conn.close()
        if r:
            return (r[0], r[1], r[2], r[3] if len(r) > 3 else None)
    except Exception:
        pass
    return None

def get_all_access_keys():
    data = fetch_all_rows("access_keys")
    data.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    
    rows = []
    for r in data:
        rows.append((r.get("code", ""), r.get("assigned_email", ""), r.get("created_at"), r.get("expire_at")))
    return rows

def rotate_access_key(code):
    from app.services.allocation_service import replace
    res = replace(code=code, actor="legacy:rotate_access_key", delete_old_account=False, ignore_quota=True)
    return res.is_success

def delete_access_key(code):
    success = False
    if SUPABASE_KEY:
        try:
            get_supabase().table("access_keys").delete().eq("code", code).execute()
            success = True
        except Exception as e:
            print(f"Supabase delete_access_key error: {e}")
    try:
        import sqlite3
        if os.path.exists("accounts.db"):
            conn = get_sqlite_conn("accounts.db")
            c = conn.cursor()
            c.execute("DELETE FROM access_keys WHERE code = ?", (code,))
            conn.commit()
            conn.close()
            success = True
    except Exception:
        pass
    return success

def delete_all_lifetime_keys():
    """Xóa tất cả các mã Access Code có thời hạn vĩnh viễn (expire_at is NULL hoặc rỗng hoặc Lifetime)"""
    deleted_count = 0
    try:
        if SUPABASE_KEY:
            # 1. Null expire_at
            get_supabase().table("access_keys").delete().is_("expire_at", "null").execute()
            # 2. Empty string or Lifetime
            get_supabase().table("access_keys").delete().eq("expire_at", "").execute()
            get_supabase().table("access_keys").delete().eq("expire_at", "Lifetime").execute()
    except Exception as e:
        print(f"Supabase delete_all_lifetime_keys error: {e}")
    try:
        import sqlite3
        if os.path.exists("accounts.db"):
            conn = get_sqlite_conn("accounts.db")
            c = conn.cursor()
            c.execute("DELETE FROM access_keys WHERE expire_at IS NULL OR expire_at = '' OR expire_at = 'Lifetime' OR expire_at = 'None'")
            deleted_count = c.rowcount
            conn.commit()
            conn.close()
    except Exception as e:
        print(f"SQLite delete_all_lifetime_keys error: {e}")
    return deleted_count

def cleanup_expired_keys():
    """Tự động xóa các Access Code đã hết hạn (quá 23:59:59 của ngày expire_at)"""
    from datetime import datetime
    today_str = datetime.now().strftime("%Y-%m-%d")
    deleted_count = 0
    try:
        if SUPABASE_KEY:
            res = get_supabase().table("access_keys").select("code").lt("expire_at", today_str).execute()
            if res.data:
                deleted_count = len(res.data)
                get_supabase().table("access_keys").delete().lt("expire_at", today_str).execute()
    except Exception as e:
        print(f"Supabase cleanup_expired_keys error: {e}")
    try:
        import sqlite3
        if os.path.exists("accounts.db"):
            conn = get_sqlite_conn("accounts.db")
            c = conn.cursor()
            c.execute("DELETE FROM access_keys WHERE expire_at IS NOT NULL AND expire_at != '' AND expire_at != 'Lifetime' AND expire_at != 'None' AND expire_at < ?", (today_str,))
            if deleted_count == 0:
                deleted_count = c.rowcount
            conn.commit()
            conn.close()
    except Exception as e:
        print(f"SQLite cleanup_expired_keys error: {e}")
    return deleted_count
