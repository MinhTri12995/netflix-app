from flask import Blueprint, request, jsonify
from app.blueprints.auth.routes import login_required
import checker
import database

api_bp = Blueprint("api", __name__)

@api_bp.route("/api/health")
def api_health():
    """Kiểm tra tình trạng hoạt động của hệ thống (SQLite, Supabase, kho tài khoản)"""
    # 1. SQLite status & inventory counts
    sqlite_status = "UNKNOWN"
    total_accounts = 0
    total_keys = 0
    try:
        conn = database.get_sqlite_conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM netflix_accounts")
        row = cur.fetchone()
        total_accounts = row[0] if row else 0
        cur.execute("SELECT COUNT(*) FROM access_keys")
        row_k = cur.fetchone()
        total_keys = row_k[0] if row_k else 0
        conn.close()
        sqlite_status = "OK"
    except Exception as e:
        sqlite_status = f"ERROR: {e}"

    # 2. Supabase status
    supabase_status = "DISABLED"
    if database.SUPABASE_KEY:
        try:
            sb = database.get_supabase()
            sb.table("netflix_accounts").select("email").limit(1).execute()
            supabase_status = "OK"
        except Exception as e:
            supabase_status = f"ERROR: {e}"

    is_healthy = (sqlite_status == "OK") and (supabase_status in ["OK", "DISABLED"])

    from flask import session
    if session.get("logged_in"):
        return jsonify({
            "status": "healthy" if is_healthy else "degraded",
            "sqlite": sqlite_status,
            "supabase": supabase_status,
            "inventory": {
                "accounts": total_accounts,
                "access_keys": total_keys
            },
            "version": "2.0.0-pro"
        }), (200 if is_healthy else 503)

    # Public health check returns minimal status without internal metric leaks
    return jsonify({
        "status": "healthy" if is_healthy else "degraded"
    }), (200 if is_healthy else 503)

@api_bp.route("/api/check_and_import", methods=["POST"])
@api_bp.route("/admin/api/check_and_import", methods=["POST"])
@login_required
def check_and_import():
    try:
        data = request.get_json(silent=True) or {}
        email = (data.get("email") or "").strip().lower()
        expire = (data.get("expire") or "").strip()
        plan = (data.get("plan") or "").strip()
        netflix_id = (data.get("netflix_id") or "").strip()
        secure_netflix_id = (data.get("secure_netflix_id") or "").strip()

        if not netflix_id:
            return jsonify({"success": False, "status": "ERROR", "error": "NetflixId is required"}), 400

        status, updated_plan = checker.check_account_live(netflix_id, secure_netflix_id, check_payment=True)

        if status == "LIVE":
            final_plan = updated_plan if updated_plan and updated_plan != "VALID" else (plan if plan and plan not in ["Unknown", "None found", "None"] else "Premium")

            existing_acc = database.get_account_by_netflix_id(netflix_id)
            if existing_acc:
                import_email = existing_acc[0]
            else:
                import_email = email if email else f"bulk_{netflix_id[:8]}@netflix.com"

            import_expire = expire if expire and expire != "N/A" else "2099-12-31"

            saved = database.save_account(import_email, import_expire, netflix_id, secure_netflix_id, final_plan)
            if saved:
                return jsonify({"success": True, "status": "LIVE", "plan": final_plan, "email": import_email})
            else:
                return jsonify({"success": False, "status": "ERROR", "error": "Database write failed."}), 500
        elif status == "UNKNOWN":
            return jsonify({"success": False, "status": "UNKNOWN", "error": "Check inconclusive due to network or server response. Account not imported."})
        elif status == "ERROR":
            return jsonify({"success": False, "status": "ERROR", "error": "Proxy or API error. Retry later."})
        else:
            return jsonify({"success": False, "status": "DIE", "error": "Account is dead or payment issue."})
    except Exception as e:
        print(f"Check and import error: {e}")
        return jsonify({"success": False, "status": "ERROR", "error": str(e)}), 500
