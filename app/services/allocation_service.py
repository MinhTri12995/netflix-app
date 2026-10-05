import os
import secrets
import string
import threading
from typing import Optional, Tuple
import database as db
from app.services.business_result import OperationResult

# Lock for thread safety in local SQLite environment
_sqlite_allocation_lock = threading.Lock()

def generate_secure_code(plan: str = "Premium", length: int = 16) -> str:
    """Generate a cryptographically secure random access code (at least 16 chars)."""
    if length < 16:
        length = 16
    chars = string.ascii_uppercase + string.digits
    # Generate random string with CSPRNG
    return "".join(secrets.choice(chars) for _ in range(length))

def get_plan_for_code(code: str) -> str:
    """Determine plan based on explicit rules or legacy length mapping."""
    if not code:
        return "Premium"
    length = len(code)
    if length == 15:
        return "Premium"
    elif length == 10:
        return "Standard"
    elif length == 8:
        return "Standard_Ads"
    elif length == 5:
        return "Basic"
    return "Premium"

def get_max_capacity(plan: str) -> int:
    """Determine max allowed keys per account depending on share mode and plan."""
    is_shared = db.get_config("SHARE_MODE_ENABLED", True)
    if not is_shared:
        return 1
    if plan == "Premium":
        return 4
    return 2

def lookup_operation(operation_id: str) -> Optional[OperationResult]:
    """Look up an existing operation by ID for idempotency."""
    if not operation_id:
        return None
    try:
        if db.SUPABASE_KEY:
            try:
                res = db.get_supabase().table("operations").select("*").eq("operation_id", operation_id).limit(1).execute()
                if res.data and isinstance(res.data, list) and len(res.data) > 0 and isinstance(res.data[0], dict):
                    row = res.data[0]
                    status = row.get("status")
                    if status in ["success", "out_of_stock", "already_processed", "limit_exceeded", "temporarily_unavailable", "needs_review", "invalid_input"]:
                        return OperationResult(
                            status=status,
                            operation_id=operation_id,
                            assigned_email=row.get("assigned_email"),
                            detail_code=row.get("detail_code", "")
                        )
            except Exception as e:
                print(f"Supabase lookup_operation error: {e}")
                return None
        else:
            conn = db.get_sqlite_conn()
            c = conn.cursor()
            c.execute("""CREATE TABLE IF NOT EXISTS operations (
                operation_id TEXT PRIMARY KEY,
                status TEXT,
                assigned_email TEXT,
                detail_code TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
            c.execute("SELECT status, assigned_email, detail_code FROM operations WHERE operation_id = ?", (operation_id,))
            row = c.fetchone()
            conn.close()
            if row:
                return OperationResult(
                    status=row[0],
                    operation_id=operation_id,
                    assigned_email=row[1],
                    detail_code=row[2] or ""
                )
    except Exception as e:
        print(f"lookup_operation error: {e}")
    return None

def record_operation(operation_id: str, result: OperationResult):
    """Persist an operation result for idempotency."""
    if not operation_id:
        return
    try:
        data = {
            "operation_id": operation_id,
            "status": result.status,
            "assigned_email": result.assigned_email,
            "detail_code": result.detail_code
        }
        if db.SUPABASE_KEY:
            try:
                db.get_supabase().table("operations").insert(data).execute()
            except Exception as e:
                print(f"Supabase record_operation error: {e}")
        else:
            conn = db.get_sqlite_conn()
            c = conn.cursor()
            c.execute("""CREATE TABLE IF NOT EXISTS operations (
                operation_id TEXT PRIMARY KEY,
                status TEXT,
                assigned_email TEXT,
                detail_code TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
            c.execute("INSERT OR REPLACE INTO operations (operation_id, status, assigned_email, detail_code) VALUES (?, ?, ?, ?)",
                      (operation_id, result.status, result.assigned_email, result.detail_code))
            conn.commit()
            conn.close()
    except Exception as e:
        print(f"record_operation error: {e}")

def allocate(code: str, plan: Optional[str] = None, expire_at: Optional[str] = None, operation_id: Optional[str] = None) -> OperationResult:
    """Atomically allocate an account to an access code with capacity bounds and idempotency."""
    code = (code or "").strip()
    if not code:
        return OperationResult(status="invalid_input", detail_code="EMPTY_CODE", message="Code cannot be empty")

    if not plan:
        plan = get_plan_for_code(code)

    # Idempotency check
    if operation_id:
        cached = lookup_operation(operation_id)
        if cached:
            return cached

    max_cap = get_max_capacity(plan)

    # Authoritative store: Supabase
    if db.SUPABASE_KEY:
        try:
            # Check if code exists
            code_check = db.get_supabase().table("access_keys").select("code").eq("code", code).execute()
            if code_check.data:
                res = OperationResult(status="invalid_input", operation_id=operation_id, detail_code="CODE_EXISTS", message="Access code already exists")
                record_operation(operation_id, res)
                return res

            # Query candidate accounts
            try:
                accs_res = db.get_supabase().table("netflix_accounts").select("email, plan, status").eq("plan", plan).neq("status", "blocked_for_new_assignments").execute()
            except Exception as e:
                err_str = str(e).lower()
                if "status" in err_str or "42703" in err_str:
                    accs_res = db.get_supabase().table("netflix_accounts").select("email, plan").eq("plan", plan).execute()
                else:
                    raise
            if not accs_res.data:
                res = OperationResult(status="out_of_stock", operation_id=operation_id, detail_code="NO_ACCOUNTS", message=f"No {plan} accounts available in vault")
                record_operation(operation_id, res)
                return res

            all_emails = [a["email"] for a in accs_res.data]
            keys_res = db.get_supabase().table("access_keys").select("assigned_email").in_("assigned_email", all_emails).execute()
            
            # Count current usage
            usage = {}
            for k in (keys_res.data or []):
                em = k.get("assigned_email")
                if em:
                    usage[em] = usage.get(em, 0) + 1

            # Filter candidates under max_cap
            candidates = [em for em in all_emails if usage.get(em, 0) < max_cap]
            if not candidates:
                res = OperationResult(status="out_of_stock", operation_id=operation_id, detail_code="CAPACITY_EXCEEDED", message="All accounts at capacity")
                record_operation(operation_id, res)
                return res

            chosen_email = min(candidates, key=lambda e: usage.get(e, 0))

            # Insert key into Supabase
            insert_data = {"code": code, "assigned_email": chosen_email}
            if expire_at:
                insert_data["expire_at"] = expire_at
            db.get_supabase().table("access_keys").insert(insert_data).execute()

            res = OperationResult(status="success", operation_id=operation_id, assigned_email=chosen_email, detail_code="ALLOCATED", message="Allocated successfully")
            record_operation(operation_id, res)
            return res

        except Exception as e:
            print(f"Supabase allocate error: {e}")
            # F04 Rule: NEVER fallback to SQLite when cloud store fails
            return OperationResult(status="temporarily_unavailable", operation_id=operation_id, retryable=True, detail_code="CLOUD_UNAVAILABLE", message=str(e))

    # Local Store: SQLite with atomic transaction lock
    with _sqlite_allocation_lock:
        conn = db.get_sqlite_conn()
        try:
            c = conn.cursor()
            # 1. Check if code already exists
            c.execute("SELECT code FROM access_keys WHERE code = ?", (code,))
            if c.fetchone():
                res = OperationResult(status="invalid_input", operation_id=operation_id, detail_code="CODE_EXISTS", message="Access code already exists")
                record_operation(operation_id, res)
                conn.close()
                return res

            # 2. Select candidates with capacity < max_cap
            c.execute("PRAGMA table_info(netflix_accounts)")
            cols = [col[1] for col in c.fetchall()]
            status_filter = "AND (na.status IS NULL OR na.status = 'usable')" if "status" in cols else ""

            query = f"""
                SELECT na.email, COUNT(ak.code) as current_cnt
                FROM netflix_accounts na
                LEFT JOIN access_keys ak ON ak.assigned_email = na.email
                WHERE (na.plan = ? OR (na.plan IS NULL AND ? = 'Premium'))
                  {status_filter}
                GROUP BY na.email
                HAVING current_cnt < ?
                ORDER BY current_cnt ASC
            """
            c.execute(query, (plan, plan, max_cap))
            candidates = c.fetchall()

            if not candidates:
                res = OperationResult(status="out_of_stock", operation_id=operation_id, detail_code="NO_CAPACITY", message=f"No available {plan} accounts in vault")
                record_operation(operation_id, res)
                conn.close()
                return res

            chosen_email = candidates[0][0]

            # 3. Insert access key
            c.execute("INSERT INTO access_keys (code, assigned_email, expire_at) VALUES (?, ?, ?)",
                      (code, chosen_email, expire_at))
            conn.commit()
            conn.close()

            res = OperationResult(status="success", operation_id=operation_id, assigned_email=chosen_email, detail_code="ALLOCATED", message="Allocated successfully")
            record_operation(operation_id, res)
            return res

        except Exception as e:
            conn.rollback()
            conn.close()
            return OperationResult(status="temporarily_unavailable", operation_id=operation_id, retryable=True, detail_code="SQLITE_ERROR", message=str(e))

def replace(
    request_id: Optional[Any] = None,
    code: Optional[str] = None,
    actor: str = "system",
    operation_id: Optional[str] = None,
    expected_assignment_version: Optional[int] = None,
    reason: str = ""
) -> OperationResult:
    """
    Atomically replace an access key's assigned account with idempotency,
    quota bounds, capacity invariants, and shared-account protection.
    """
    if operation_id:
        cached = lookup_operation(operation_id)
        if cached:
            return cached

    # Cloud Store: Supabase
    if db.SUPABASE_KEY:
        try:
            req_row = None
            if request_id is not None:
                req_res = db.get_supabase().table("requests").select("*").eq("id", request_id).execute()
                if not req_res.data:
                    res = OperationResult(status="invalid_input", operation_id=operation_id, request_id=str(request_id), detail_code="REQUEST_NOT_FOUND", message=f"Request #{request_id} not found")
                    record_operation(operation_id, res)
                    return res
                req_row = req_res.data[0]
                req_status = str(req_row.get("status") or "")
                if req_status in ["accepted", "auto_accepted"]:
                    req_code = (req_row.get("code") or "").strip()
                    k_res = db.get_supabase().table("access_keys").select("assigned_email").eq("code", req_code).execute()
                    assigned_email = k_res.data[0].get("assigned_email") if k_res.data else None
                    res = OperationResult(
                        status="already_processed",
                        operation_id=operation_id,
                        request_id=str(request_id),
                        assigned_email=assigned_email,
                        detail_code="ALREADY_PROCESSED",
                        message=f"Request #{request_id} already processed"
                    )
                    record_operation(operation_id, res)
                    return res
                if not code:
                    code = req_row.get("code")

            code = (code or "").strip()
            if not code:
                res = OperationResult(status="invalid_input", operation_id=operation_id, request_id=str(request_id) if request_id else None, detail_code="EMPTY_CODE", message="Access code cannot be empty")
                record_operation(operation_id, res)
                return res

            key_res = db.get_supabase().table("access_keys").select("*").eq("code", code).execute()
            if not key_res.data:
                res = OperationResult(status="invalid_input", operation_id=operation_id, request_id=str(request_id) if request_id else None, detail_code="CODE_NOT_FOUND", message=f"Access code {code} not found")
                record_operation(operation_id, res)
                return res

            key_data = key_res.data[0]
            old_email = key_data.get("assigned_email")
            expire_at_str = key_data.get("expire_at")
            curr_version = key_data.get("assignment_version", 1)

            if expected_assignment_version is not None and curr_version != expected_assignment_version:
                res = OperationResult(status="already_processed", operation_id=operation_id, request_id=str(request_id) if request_id else None, assigned_email=old_email, detail_code="VERSION_MISMATCH", message="Assignment version mismatch")
                record_operation(operation_id, res)
                return res

            if expire_at_str:
                from datetime import datetime
                try:
                    exp_dt = datetime.strptime(expire_at_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
                    if datetime.now() > exp_dt:
                        res = OperationResult(status="invalid_input", operation_id=operation_id, request_id=str(request_id) if request_id else None, detail_code="EXPIRED_CODE", message="Access code has expired")
                        record_operation(operation_id, res)
                        return res
                except Exception:
                    pass

            today_count = db.get_today_rotation_count(code)
            if today_count >= 5:
                res = OperationResult(status="limit_exceeded", operation_id=operation_id, request_id=str(request_id) if request_id else None, detail_code="QUOTA_EXCEEDED", message="Maximum replacement limit (5 times per 24 hours) reached")
                record_operation(operation_id, res)
                return res

            plan = key_data.get("plan") or get_plan_for_code(code)
            max_cap = get_max_capacity(plan)

            try:
                accs_res = db.get_supabase().table("netflix_accounts").select("email, plan, status").eq("plan", plan).neq("status", "blocked_for_new_assignments").execute()
            except Exception as e:
                err_str = str(e).lower()
                if "status" in err_str or "42703" in err_str:
                    accs_res = db.get_supabase().table("netflix_accounts").select("email, plan").eq("plan", plan).execute()
                else:
                    raise

            all_accs = accs_res.data or []
            candidate_emails = [a["email"] for a in all_accs if a["email"] != old_email]

            if not candidate_emails:
                if request_id is not None:
                    req_id_val = int(request_id) if str(request_id).isdigit() else request_id
                    try:
                        db.get_supabase().table("requests").update({"status": "pending_out_of_stock", "blocked_reason": "OUT_OF_STOCK"}).eq("id", req_id_val).execute()
                    except Exception as e:
                        err_str = str(e).lower()
                        if "blocked_reason" in err_str or "42703" in err_str:
                            db.get_supabase().table("requests").update({"status": "pending_out_of_stock"}).eq("id", req_id_val).execute()
                        else:
                            raise
                res = OperationResult(status="out_of_stock", operation_id=operation_id, request_id=str(request_id) if request_id else None, detail_code="NO_CAPACITY", message="No replacement accounts available in vault")
                record_operation(operation_id, res)
                return res

            keys_res = db.get_supabase().table("access_keys").select("assigned_email").in_("assigned_email", candidate_emails).execute()
            usage = {}
            for k in (keys_res.data or []):
                em = k.get("assigned_email")
                if em:
                    usage[em] = usage.get(em, 0) + 1

            valid_candidates = [em for em in candidate_emails if usage.get(em, 0) < max_cap]
            if not valid_candidates:
                if request_id is not None:
                    req_id_val = int(request_id) if str(request_id).isdigit() else request_id
                    try:
                        db.get_supabase().table("requests").update({"status": "pending_out_of_stock", "blocked_reason": "OUT_OF_STOCK"}).eq("id", req_id_val).execute()
                    except Exception as e:
                        err_str = str(e).lower()
                        if "blocked_reason" in err_str or "42703" in err_str:
                            db.get_supabase().table("requests").update({"status": "pending_out_of_stock"}).eq("id", req_id_val).execute()
                        else:
                            raise
                res = OperationResult(status="out_of_stock", operation_id=operation_id, request_id=str(request_id) if request_id else None, detail_code="CAPACITY_EXCEEDED", message="All accounts at capacity")
                record_operation(operation_id, res)
                return res

            new_email = min(valid_candidates, key=lambda e: usage.get(e, 0))

            # Update access key
            try:
                db.get_supabase().table("access_keys").update({
                    "assigned_email": new_email,
                    "assignment_version": curr_version + 1
                }).eq("code", code).execute()
            except Exception as e:
                err_str = str(e).lower()
                if "assignment_version" in err_str or "42703" in err_str:
                    db.get_supabase().table("access_keys").update({
                        "assigned_email": new_email
                    }).eq("code", code).execute()
                else:
                    raise

            # Protect shared accounts: keep and mark needs_review if shared; delete if solitary
            if old_email:
                if db.is_account_shared_by_others(old_email, exclude_code=code):
                    try:
                        db.get_supabase().table("netflix_accounts").update({"status": "needs_review"}).eq("email", old_email).execute()
                    except Exception as e:
                        print(f"Supabase update status notice (status column might not exist): {e}")
                else:
                    db.get_supabase().table("netflix_accounts").delete().eq("email", old_email).execute()

            # Update request status
            if request_id is not None:
                new_status = "auto_accepted" if actor.startswith("ai") else "accepted"
                req_id_val = int(request_id) if str(request_id).isdigit() else request_id
                db.get_supabase().table("requests").update({"status": new_status}).eq("id", req_id_val).execute()

            # Outbox & events
            from app.services.outbox_service import send_notification_outbox
            alert_msg = f"⚡ <b>Đổi tài khoản thành công!</b>\n- Mã: <code>{code}</code>\n- Tài khoản mới: <code>{new_email}</code>\n- Tác tử: {actor}"
            send_notification_outbox("telegram_alert", {
                "message": alert_msg,
                "code": code,
                "request_id": str(request_id) if request_id else None
            })

            res = OperationResult(
                status="success",
                operation_id=operation_id,
                request_id=str(request_id) if request_id else None,
                assigned_email=new_email,
                detail_code="ROTATED",
                message="Account replaced successfully"
            )
            record_operation(operation_id, res)
            return res

        except Exception as e:
            print(f"Supabase replace error: {e}")
            return OperationResult(status="temporarily_unavailable", operation_id=operation_id, retryable=True, detail_code="CLOUD_UNAVAILABLE", message=str(e))

    # Local Store: SQLite with atomic lock
    with _sqlite_allocation_lock:
        if operation_id:
            cached = lookup_operation(operation_id)
            if cached:
                return cached

        conn = db.get_sqlite_conn()
        try:
            c = conn.cursor()
            req_row = None
            if request_id is not None:
                c.execute("SELECT id, code, status FROM requests WHERE id = ? OR id = ?",
                          (str(request_id), int(request_id) if str(request_id).isdigit() else -1))
                req_row = c.fetchone()
                if not req_row:
                    conn.close()
                    res = OperationResult(status="invalid_input", operation_id=operation_id, request_id=str(request_id), detail_code="REQUEST_NOT_FOUND", message=f"Request #{request_id} not found")
                    record_operation(operation_id, res)
                    return res

                req_status = str(req_row[2] or "")
                if req_status in ["accepted", "auto_accepted"]:
                    req_code = req_row[1]
                    c.execute("SELECT assigned_email FROM access_keys WHERE code = ?", (req_code,))
                    k_row = c.fetchone()
                    assigned_email = k_row[0] if k_row else None
                    conn.close()
                    res = OperationResult(
                        status="already_processed",
                        operation_id=operation_id,
                        request_id=str(request_id),
                        assigned_email=assigned_email,
                        detail_code="ALREADY_PROCESSED",
                        message=f"Request #{request_id} already processed"
                    )
                    record_operation(operation_id, res)
                    return res

                if not code:
                    code = req_row[1]

            code = (code or "").strip()
            if not code:
                conn.close()
                res = OperationResult(status="invalid_input", operation_id=operation_id, request_id=str(request_id) if request_id else None, detail_code="EMPTY_CODE", message="Access code cannot be empty")
                record_operation(operation_id, res)
                return res

            c.execute("PRAGMA table_info(access_keys)")
            ak_cols = [col[1] for col in c.fetchall()]
            v_col = ", assignment_version" if "assignment_version" in ak_cols else ""
            c.execute(f"SELECT code, assigned_email, expire_at{v_col} FROM access_keys WHERE code = ?", (code,))
            key_row = c.fetchone()
            if not key_row:
                conn.close()
                res = OperationResult(status="invalid_input", operation_id=operation_id, request_id=str(request_id) if request_id else None, detail_code="CODE_NOT_FOUND", message=f"Access code {code} not found")
                record_operation(operation_id, res)
                return res

            old_email = key_row[1]
            expire_at_str = key_row[2]
            curr_version = key_row[3] if len(key_row) > 3 else 1

            if expected_assignment_version is not None and curr_version != expected_assignment_version:
                conn.close()
                res = OperationResult(status="already_processed", operation_id=operation_id, request_id=str(request_id) if request_id else None, assigned_email=old_email, detail_code="VERSION_MISMATCH", message="Assignment version mismatch")
                record_operation(operation_id, res)
                return res

            if expire_at_str:
                from datetime import datetime
                try:
                    exp_dt = datetime.strptime(expire_at_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
                    if datetime.now() > exp_dt:
                        conn.close()
                        res = OperationResult(status="invalid_input", operation_id=operation_id, request_id=str(request_id) if request_id else None, detail_code="EXPIRED_CODE", message="Access code has expired")
                        record_operation(operation_id, res)
                        return res
                except Exception:
                    pass

            c.execute("SELECT COUNT(*) FROM requests WHERE code = ? AND (status LIKE '%accepted%' OR status = 'auto_accepted') AND datetime(created_at) > datetime('now', '-24 hours')", (code,))
            quota_row = c.fetchone()
            if quota_row and quota_row[0] >= 5:
                conn.close()
                res = OperationResult(status="limit_exceeded", operation_id=operation_id, request_id=str(request_id) if request_id else None, detail_code="QUOTA_EXCEEDED", message="Maximum replacement limit (5 times per 24 hours) reached")
                record_operation(operation_id, res)
                return res

            plan = get_plan_for_code(code)
            max_cap = get_max_capacity(plan)

            c.execute("PRAGMA table_info(netflix_accounts)")
            na_cols = [col[1] for col in c.fetchall()]
            status_filter = "AND (na.status IS NULL OR na.status = 'usable')" if "status" in na_cols else ""

            query = f"""
                SELECT na.email, COUNT(ak.code) as current_cnt
                FROM netflix_accounts na
                LEFT JOIN access_keys ak ON ak.assigned_email = na.email
                WHERE (na.plan = ? OR (na.plan IS NULL AND ? = 'Premium'))
                  AND na.email != ?
                  {status_filter}
                GROUP BY na.email
                HAVING current_cnt < ?
                ORDER BY current_cnt ASC
            """
            c.execute(query, (plan, plan, old_email or "", max_cap))
            candidates = c.fetchall()

            if not candidates:
                if request_id is not None:
                    c.execute("UPDATE requests SET status = 'pending_out_of_stock', blocked_reason = 'OUT_OF_STOCK' WHERE id = ? OR id = ?",
                              (str(request_id), int(request_id) if str(request_id).isdigit() else -1))
                conn.commit()
                conn.close()
                res = OperationResult(status="out_of_stock", operation_id=operation_id, request_id=str(request_id) if request_id else None, detail_code="NO_CAPACITY", message=f"No available {plan} replacement accounts in vault")
                record_operation(operation_id, res)
                return res

            new_email = candidates[0][0]

            if "assignment_version" in ak_cols:
                c.execute("UPDATE access_keys SET assigned_email = ?, assignment_version = COALESCE(assignment_version, 1) + 1 WHERE code = ?",
                          (new_email, code))
            else:
                c.execute("UPDATE access_keys SET assigned_email = ? WHERE code = ?", (new_email, code))

            if old_email:
                c.execute("SELECT code FROM access_keys WHERE assigned_email = ? AND code != ? LIMIT 1", (old_email, code))
                is_shared = c.fetchone() is not None
                if is_shared:
                    if "status" in na_cols:
                        c.execute("UPDATE netflix_accounts SET status = 'needs_review' WHERE email = ?", (old_email,))
                else:
                    c.execute("DELETE FROM netflix_accounts WHERE email = ?", (old_email,))

            if request_id is not None:
                new_status = "auto_accepted" if actor.startswith("ai") else "accepted"
                c.execute("UPDATE requests SET status = ? WHERE id = ? OR id = ?",
                          (new_status, str(request_id), int(request_id) if str(request_id).isdigit() else -1))

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
            c.execute("INSERT INTO rotation_events (code, old_email, new_email, actor, reason, request_id) VALUES (?, ?, ?, ?, ?, ?)",
                      (code, old_email, new_email, actor, reason, str(request_id) if request_id else None))

            from app.services.outbox_service import record_outbox_event, deliver_event
            alert_msg = f"⚡ <b>Đổi tài khoản thành công!</b>\n- Mã: <code>{code}</code>\n- Tài khoản mới: <code>{new_email}</code>\n- Tác tử: {actor}"
            outbox_id = record_outbox_event(
                "telegram_alert",
                {"message": alert_msg, "code": code, "request_id": str(request_id) if request_id else None},
                conn=conn
            )

            conn.commit()
            conn.close()

            if outbox_id:
                try:
                    deliver_event(outbox_id, "telegram_alert", {"message": alert_msg})
                except Exception as e:
                    print(f"Post-commit outbox delivery notice: {e}")

            res = OperationResult(
                status="success",
                operation_id=operation_id,
                request_id=str(request_id) if request_id else None,
                assigned_email=new_email,
                detail_code="ROTATED",
                message="Account replaced successfully"
            )
            record_operation(operation_id, res)
            return res

        except Exception as e:
            conn.rollback()
            conn.close()
            return OperationResult(status="temporarily_unavailable", operation_id=operation_id, retryable=True, detail_code="SQLITE_ERROR", message=str(e))

