import os
from supabase import create_client, Client

import threading

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://zzdlmwhmhjofqmhfknbv.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_SECRET_KEY", "")

_local = threading.local()

def get_supabase() -> Client:
    if not hasattr(_local, "client"):
        _local.client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _local.client

def init_db():
    # Bảng sẽ được tạo bằng tay trên giao diện Supabase
    print("Sử dụng Supabase REST API (Không cần init local)")

def save_account(email, expire_date, netflix_id, secure_netflix_id="", plan=None):
    data = {
        "email": email,
        "expire_date": expire_date,
        "netflix_id": netflix_id,
        "secure_netflix_id": secure_netflix_id
    }
    if plan:
        data["plan"] = plan
    get_supabase().table("netflix_accounts").upsert(data).execute()
    
def delete_account(email):
    get_supabase().table("netflix_accounts").delete().eq("email", email).execute()

def update_plan(email, plan):
    data = {"plan": plan}
    get_supabase().table("netflix_accounts").update(data).eq("email", email).execute()

def fetch_all_rows(table_name, columns="*"):
    all_data = []
    limit = 1000
    offset = 0
    while True:
        response = get_supabase().table(table_name).select(columns).range(offset, offset + limit - 1).execute()
        data = response.data
        if not data:
            break
        all_data.extend(data)
        if len(data) < limit:
            break
        offset += limit
    return all_data

def get_all_accounts():
    data = fetch_all_rows("netflix_accounts")
    # Chuyển đổi list of dicts thành list of tuples cho code cũ tương thích
    rows = []
    for r in data:
        rows.append((r["email"], r["expire_date"], r["netflix_id"], r["secure_netflix_id"], r.get("created_at"), r.get("plan")))
    return rows

def get_account_by_email(email):
    response = get_supabase().table("netflix_accounts").select("*").eq("email", email).execute()
    if response.data:
        r = response.data[0]
        return (r["email"], r["expire_date"], r["netflix_id"], r["secure_netflix_id"], r.get("created_at"), r.get("plan"))
    return None

def get_random_available_account(plan_type=None):
    import random
    
    # Lấy toàn bộ account có trong kho
    acc_data = fetch_all_rows("netflix_accounts", "email, plan")
    if not acc_data:
        return None
        
    # Lọc tài khoản theo gói cước nếu có yêu cầu
    if plan_type:
        all_emails = [r["email"] for r in acc_data if r.get("plan") and plan_type.lower() in str(r["plan"]).lower()]
    else:
        all_emails = [r["email"] for r in acc_data]
    
    # Lấy toàn bộ email ĐÃ ĐƯỢC GÁN cho các mã truy cập (đang sử dụng)
    keys_data = fetch_all_rows("access_keys", "assigned_email")
    used_emails = [r["assigned_email"] for r in keys_data if r.get("assigned_email")]
    
    # Lọc ra những email CHƯA ĐƯỢC AI XÀI (Tạo mảng riêng biệt, không trùng nhau)
    available_emails = list(set(all_emails) - set(used_emails))
    
    if available_emails:
        return random.choice(available_emails)
        
    # Hết sạch Cookie trống trong kho
    return None

def create_access_key(code):
    # Xác định gói cước dựa trên độ dài mã
    plan_type = "Standard" if len(code) == 10 else "Premium"
    
    email = get_random_available_account(plan_type)
    if not email:
        return False, f"Không còn Cookie {plan_type} nào khả dụng trong kho."
    
    # Kiểm tra mã đã tồn tại chưa
    exist = get_supabase().table("access_keys").select("code").eq("code", code).execute()
    if exist.data:
        return False, "Mã này đã tồn tại."
        
    data = {
        "code": code,
        "assigned_email": email
    }
    try:
        get_supabase().table("access_keys").insert(data).execute()
        return True, "Thành công"
    except Exception as e:
        return False, f"Lỗi Database: {e}"

def get_access_key(code):
    response = get_supabase().table("access_keys").select("*").eq("code", code).execute()
    if response.data:
        r = response.data[0]
        return (r["code"], r["assigned_email"])
    return None

def get_all_access_keys():
    # Fetch all data manually to bypass 1000 limit, then sort
    data = fetch_all_rows("access_keys")
    data.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    
    rows = []
    for r in data:
        rows.append((r["code"], r["assigned_email"], r.get("created_at")))
    return rows

def rotate_access_key(code):
    # Xác định gói cước dựa trên độ dài mã
    plan_type = "Standard" if len(code) == 10 else "Premium"
    
    email = get_random_available_account(plan_type)
    if not email:
        return False
    
    data = {"assigned_email": email}
    try:
        get_supabase().table("access_keys").update(data).eq("code", code).execute()
        return True
    except Exception as e:
        print(f"Lỗi Rotate DB: {e}")
        return False

def delete_access_key(code):
    get_supabase().table("access_keys").delete().eq("code", code).execute()
