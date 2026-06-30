import os
from supabase import create_client, Client

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://zzdlmwhmhjofqmhfknbv.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_SECRET_KEY", "sb_secret_wbXnaO_AN5UCJmZoyZzMCw_VjBZDclc")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def init_db():
    # Bảng sẽ được tạo bằng tay trên giao diện Supabase
    print("Sử dụng Supabase REST API (Không cần init local)")

def save_account(email, expire_date, netflix_id, secure_netflix_id=""):
    data = {
        "email": email,
        "expire_date": expire_date,
        "netflix_id": netflix_id,
        "secure_netflix_id": secure_netflix_id
    }
    supabase.table("netflix_accounts").upsert(data).execute()
    
def delete_account(email):
    supabase.table("netflix_accounts").delete().eq("email", email).execute()

def get_all_accounts():
    response = supabase.table("netflix_accounts").select("*").execute()
    # Chuyển đổi list of dicts thành list of tuples cho code cũ tương thích
    rows = []
    for r in response.data:
        rows.append((r["email"], r["expire_date"], r["netflix_id"], r["secure_netflix_id"], r.get("created_at")))
    return rows

def get_random_available_account():
    # Do Supabase không hỗ trợ ORDER BY RANDOM() trực tiếp qua REST API, 
    # ta lấy danh sách và random bằng python
    import random
    response = supabase.table("netflix_accounts").select("email").execute()
    if response.data:
        return random.choice(response.data)["email"]
    return None

def create_access_key(code):
    email = get_random_available_account()
    if not email:
        return False, "Không còn Cookie nào khả dụng trong kho."
    
    # Kiểm tra mã đã tồn tại chưa
    exist = supabase.table("access_keys").select("code").eq("code", code).execute()
    if exist.data:
        return False, "Mã này đã tồn tại."
        
    data = {
        "code": code,
        "assigned_email": email
    }
    supabase.table("access_keys").insert(data).execute()
    return True, "Thành công"

def get_access_key(code):
    response = supabase.table("access_keys").select("*").eq("code", code).execute()
    if response.data:
        r = response.data[0]
        return (r["code"], r["assigned_email"])
    return None

def get_all_access_keys():
    response = supabase.table("access_keys").select("*").order("created_at", desc=True).execute()
    rows = []
    for r in response.data:
        rows.append((r["code"], r["assigned_email"], r.get("created_at")))
    return rows

def rotate_access_key(code):
    email = get_random_available_account()
    if not email:
        return False
    
    data = {"assigned_email": email}
    supabase.table("access_keys").update(data).eq("code", code).execute()
    return True

def delete_access_key(code):
    supabase.table("access_keys").delete().eq("code", code).execute()
