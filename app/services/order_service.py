import csv
import io
import re
from datetime import datetime, timezone
from typing import Optional, Tuple, Dict, Any, List
import database as db

VALID_STATUSES = {"verified", "unverified", "cancelled"}

def init_orders_schema(conn=None):
    """Ensure orders and audit tables exist."""
    should_close = False
    if conn is None:
        conn = db.get_sqlite_conn()
        should_close = True
    try:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            code TEXT UNIQUE,
            status TEXT DEFAULT 'unverified',
            verified_by TEXT,
            verified_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS order_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT,
            action TEXT,
            actor TEXT,
            old_code TEXT,
            new_code TEXT,
            old_status TEXT,
            new_status TEXT,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        if should_close:
            conn.commit()
            conn.close()
    except Exception as e:
        print(f"init_orders_schema error: {e}")
        if should_close:
            conn.close()

def get_order(order_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve order by order_id."""
    order_id = (order_id or "").strip()
    if not order_id:
        return None
    init_orders_schema()
    try:
        conn = db.get_sqlite_conn()
        c = conn.cursor()
        c.execute("SELECT order_id, code, status, verified_by, verified_at, created_at, updated_at FROM orders WHERE order_id = ?", (order_id,))
        row = c.fetchone()
        conn.close()
        if row:
            return {
                "order_id": row[0],
                "code": row[1],
                "status": row[2],
                "verified_by": row[3],
                "verified_at": row[4],
                "created_at": row[5],
                "updated_at": row[6],
            }
    except Exception as e:
        print(f"get_order error: {e}")
    return None

def get_order_by_code(code: str) -> Optional[Dict[str, Any]]:
    """Retrieve order linked to an access code."""
    code = (code or "").strip()
    if not code:
        return None
    init_orders_schema()
    try:
        conn = db.get_sqlite_conn()
        c = conn.cursor()
        c.execute("SELECT order_id, code, status, verified_by, verified_at, created_at, updated_at FROM orders WHERE code = ?", (code,))
        row = c.fetchone()
        conn.close()
        if row:
            return {
                "order_id": row[0],
                "code": row[1],
                "status": row[2],
                "verified_by": row[3],
                "verified_at": row[4],
                "created_at": row[5],
                "updated_at": row[6],
            }
    except Exception as e:
        print(f"get_order_by_code error: {e}")
    return None

def create_or_update_order(
    order_id: str,
    code: str,
    status: str = "verified",
    actor: str = "admin",
    details: str = ""
) -> Tuple[bool, str]:
    """
    Create or update an order with strict integrity constraints:
    - order_id cannot be empty
    - code must exist in access_keys
    - one order cannot be linked to multiple codes
    - one code cannot have multiple active orders
    - changes are logged into order_audit_log
    """
    order_id = (order_id or "").strip()
    code = (code or "").strip()
    status = (status or "verified").strip().lower()

    if not order_id:
        return False, "EMPTY_ORDER_ID"
    if not code:
        return False, "EMPTY_CODE"
    if status not in VALID_STATUSES:
        return False, f"INVALID_STATUS_{status}"

    # Verify that code exists in access_keys
    key_row = db.get_access_key(code)
    if not key_row:
        return False, f"CODE_NOT_FOUND: {code}"

    init_orders_schema()
    conn = db.get_sqlite_conn()
    try:
        c = conn.cursor()
        # Check if code is already bound to a different order
        c.execute("SELECT order_id, status FROM orders WHERE code = ? AND order_id != ?", (code, order_id))
        existing_for_code = c.fetchone()
        if existing_for_code:
            conn.close()
            return False, f"CODE_ALREADY_LINKED_TO_ORDER: {existing_for_code[0]}"

        # Check existing order
        c.execute("SELECT order_id, code, status FROM orders WHERE order_id = ?", (order_id,))
        existing_order = c.fetchone()

        now_str = datetime.now(timezone.utc).isoformat()
        verified_by = actor if status == "verified" else None
        verified_at = now_str if status == "verified" else None

        if existing_order:
            old_code = existing_order[1]
            old_status = existing_order[2]
            c.execute("""UPDATE orders SET
                code = ?, status = ?, verified_by = ?, verified_at = ?, updated_at = CURRENT_TIMESTAMP
                WHERE order_id = ?""",
                (code, status, verified_by, verified_at, order_id))
            action = "UPDATE"
        else:
            old_code = None
            old_status = None
            c.execute("""INSERT INTO orders (order_id, code, status, verified_by, verified_at)
                VALUES (?, ?, ?, ?, ?)""",
                (order_id, code, status, verified_by, verified_at))
            action = "CREATE"

        # Record audit log
        c.execute("""INSERT INTO order_audit_log
            (order_id, action, actor, old_code, new_code, old_status, new_status, details)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (order_id, action, actor, old_code, code, old_status, status, details))

        conn.commit()
        conn.close()
        return True, "SUCCESS"
    except Exception as e:
        conn.rollback()
        conn.close()
        return False, f"DATABASE_ERROR: {e}"

def import_orders_csv(csv_content: str, actor: str = "admin") -> Dict[str, Any]:
    """
    Parse CSV content and import orders line-by-line.
    Format: order_id,code,[status]
    Returns dictionary with total, success_count, and row-by-row errors.
    """
    if not csv_content or not csv_content.strip():
        return {"total": 0, "success_count": 0, "errors": [{"row": 0, "error": "CSV content is empty"}]}

    reader = csv.reader(io.StringIO(csv_content.strip()))
    success_count = 0
    errors = []
    row_num = 0

    for row in reader:
        row_num += 1
        if not row or all(not field.strip() for field in row):
            continue

        # Check header row
        first_col = row[0].strip().lower()
        if row_num == 1 and ("order" in first_col or "id" in first_col):
            continue

        if len(row) < 2:
            errors.append({"row": row_num, "order_id": row[0].strip() if row else "", "error": "Missing code column (expected: order_id,code,[status])"})
            continue

        order_id = row[0].strip()
        code = row[1].strip()
        status = row[2].strip().lower() if len(row) > 2 and row[2].strip() else "verified"

        ok, msg = create_or_update_order(order_id=order_id, code=code, status=status, actor=actor, details=f"CSV import row {row_num}")
        if ok:
            success_count += 1
        else:
            errors.append({"row": row_num, "order_id": order_id, "code": code, "error": msg})

    return {
        "total": row_num,
        "success_count": success_count,
        "errors": errors
    }

def verify_order_for_request(code: str, order_id: str) -> Tuple[bool, str]:
    """
    Check if a submitted request's order_id matches the code and is verified.
    Returns (is_verified, reason_code).
    """
    code = (code or "").strip()
    order_id = (order_id or "").strip()

    if not order_id:
        return False, "EMPTY_ORDER_ID"

    order = get_order(order_id)
    if not order:
        return False, "ORDER_NOT_FOUND"

    if order.get("code") != code:
        return False, f"ORDER_CODE_MISMATCH: {order.get('code')} vs {code}"

    status = (order.get("status") or "").lower()
    if status != "verified":
        return False, f"ORDER_NOT_VERIFIED: status is {status}"

    return True, "VERIFIED"

def list_orders(status_filter: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    """List orders with optional status filter for admin dashboard."""
    init_orders_schema()
    try:
        conn = db.get_sqlite_conn()
        c = conn.cursor()
        if status_filter:
            c.execute("SELECT order_id, code, status, verified_by, verified_at, created_at, updated_at FROM orders WHERE status = ? ORDER BY created_at DESC LIMIT ?", (status_filter, limit))
        else:
            c.execute("SELECT order_id, code, status, verified_by, verified_at, created_at, updated_at FROM orders ORDER BY created_at DESC LIMIT ?", (limit,))
        rows = c.fetchall()
        conn.close()
        res = []
        for r in rows:
            res.append({
                "order_id": r[0],
                "code": r[1],
                "status": r[2],
                "verified_by": r[3],
                "verified_at": r[4],
                "created_at": r[5],
                "updated_at": r[6],
            })
        return res
    except Exception as e:
        print(f"list_orders error: {e}")
        return []
