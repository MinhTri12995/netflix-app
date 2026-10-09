import os
import re
import json
import base64
import uuid
import urllib.parse
from datetime import datetime
import requests
from flask import Blueprint, render_template, request, jsonify

import database
import checker
import proxies_list
from app.config import Config
from app.services.token_service import (
    fetch_netflix_nftoken_api,
    generate_json_cookie_token,
    check_code_rate_limit,
    mark_code_request_success,
    check_live_rate_limit,
    ProxyError,
    CookieError
)
from app.services.account_service import fetch_realtime_account_info, is_date_expired
from app.services.vision_service import (
    scrape_netflix_account_payment_card,
    verify_payment_card_match
)
from app.services.notification_service import send_telegram_alert
from app.services.rate_limiter import get_client_ip, check_rate_limit

portal_bp = Blueprint("portal", __name__)

@portal_bp.route("/")
def index():
    database.init_db()
    return render_template("portal/index.html")

@portal_bp.route("/api/generate_nftoken", methods=["POST"])
def api_generate_nftoken():
    def register_fail(err_msg, status_code=400):
        return jsonify({"success": False, "error": err_msg}), status_code

    client_ip = get_client_ip(request)
    allowed, wait_sec = check_rate_limit(f"nftoken:{client_ip}", max_requests=30, window_seconds=60)
    if not allowed:
        return register_fail(f"Too many requests from your IP. Please try again after {wait_sec} seconds.", 429)

    try:
        data = request.get_json(silent=True) or {}
        cookie_value = data.get("cookie", "").strip()
        if not cookie_value:
            return register_fail("Please enter Access Code")

        database.init_db()

        acc_key_row = None
        is_cookie_string = ("NetflixId" in cookie_value) or cookie_value.startswith("FALLBACK:") or cookie_value.startswith("[") or cookie_value.startswith("{")
        if not is_cookie_string:
            clean_code = "".join(cookie_value.split()).upper()
            try:
                acc_key_row = database.get_access_key(clean_code) or database.get_access_key(cookie_value)
            except Exception as e:
                print(f"Error querying access key: {e}")

        is_access_code = acc_key_row is not None or (len("".join(cookie_value.split())) in [5, 6, 7, 8, 9, 10, 12, 15, 16] and not is_cookie_string)

        if acc_key_row:
            code = acc_key_row[0]
            assigned_email = acc_key_row[1]
            expire_at_str = acc_key_row[2] if len(acc_key_row) > 2 else None
            key_plan = acc_key_row[3] if len(acc_key_row) > 3 and acc_key_row[3] else None

            # Check expiration
            if expire_at_str:
                try:
                    expire_date = datetime.strptime(expire_at_str, "%Y-%m-%d")
                    expire_date = expire_date.replace(hour=23, minute=59, second=59)
                    if datetime.now() > expire_date:
                        database.delete_access_key(code)
                        return register_fail("Access code has expired and been disabled!")
                except Exception as e:
                    print(f"Expiration parse error: {e}")

            # Determine expected plan
            if key_plan:
                expected_plan = key_plan
            elif len(code) == 15:
                expected_plan = "Premium"
            elif len(code) == 10:
                expected_plan = "Standard"
            elif len(code) == 8:
                expected_plan = "Standard_Ads"
            elif len(code) == 5:
                expected_plan = "Basic"
            else:
                expected_plan = "Premium"

            max_attempts = 4
            for attempt in range(max_attempts):
                acc = database.get_account_by_email(assigned_email)
                acc_status = str(acc[6] or "").strip().lower() if (acc and len(acc) > 6) else ""

                if not acc or acc_status in ["needs_review", "dead", "blocked_for_new_assignments", "expired", "die"]:
                    print(f"Account {assigned_email} missing or unusable (status='{acc_status}'), rotating...")
                    from app.services.allocation_service import replace
                    rep_res = replace(code=code, actor="system:activation", reason=f"Account status '{acc_status}' unusable", delete_old_account=False, ignore_quota=True)
                    if not rep_res.is_success:
                        return jsonify({"success": False, "error": f"Hệ thống đã hết tài khoản dự phòng cho gói {expected_plan}!"}), 500
                    assigned_email = rep_res.assigned_email
                    continue

                netflix_id = acc[2]
                secure_netflix_id = acc[3] if acc[3] else ""
                acc_plan = acc[5] if (acc and len(acc) > 5 and acc[5]) else expected_plan
                acc_expire = acc[1] if (acc and len(acc) > 1 and acc[1]) else (expire_at_str if expire_at_str else "N/A")

                try:
                    token = fetch_netflix_nftoken_api(netflix_id, secure_netflix_id)
                    is_json = token.startswith("FALLBACK:")
                    if is_json:
                        cookie_json = urllib.parse.unquote(token[9:])
                    else:
                        cookie_json = urllib.parse.unquote(generate_json_cookie_token(netflix_id, secure_netflix_id)[9:])

                    try:
                        rt_plan, rt_expire = fetch_realtime_account_info(netflix_id, secure_netflix_id)
                        if rt_plan:
                            acc_plan = rt_plan
                            database.update_plan(assigned_email, rt_plan)
                        if rt_expire:
                            acc_expire = rt_expire
                    except Exception as meta_err:
                        print(f"[Portal] Realtime metadata lookup skipped: {meta_err}")

                    pc_link = f"https://www.netflix.com/browse?nftoken={token}"
                    mobile_link = f"https://www.netflix.com/unsupported?nftoken={token}"
                    tv_link = f"https://www.netflix.com/tv8?nftoken={token}"
                    general_link = f"https://www.netflix.com/YourAccount?nftoken={token}"

                    return jsonify({
                        "success": True,
                        "pc_link": pc_link,
                        "mobile_link": mobile_link,
                        "tv_link": tv_link,
                        "general_link": general_link,
                        "is_json": is_json,
                        "cookie_json": cookie_json,
                        "plan": acc_plan,
                        "expire_date": acc_expire
                    })
                except ProxyError as e:
                    print(f"Proxy error ({e}), retrying with another proxy...")
                    continue
                except CookieError as e:
                    print(f"Cookie {assigned_email} DIE / PAYMENT ERROR, rotating... (Error: {e})")
                    if database.SUPABASE_KEY:
                        try:
                            database.get_supabase().table("netflix_accounts").update({"status": "needs_review"}).eq("email", assigned_email).execute()
                        except Exception as update_err:
                            print(f"Supabase mark needs_review notice: {update_err}")
                    try:
                        conn = database.get_sqlite_conn()
                        c = conn.cursor()
                        c.execute("UPDATE netflix_accounts SET status = 'needs_review' WHERE email = ?", (assigned_email,))
                        conn.commit()
                        conn.close()
                    except Exception:
                        pass

                    from app.services.allocation_service import replace
                    rep_res = replace(code=code, actor="system:activation", reason=f"CookieError: {e}", delete_old_account=False, ignore_quota=True)
                    if not rep_res.is_success:
                        return jsonify({"success": False, "error": f"Tài khoản lỗi và kho đã hết Cookie dự phòng cho gói {expected_plan}!"}), 500
                    assigned_email = rep_res.assigned_email
                    continue
                except Exception as e:
                    print(f"Unexpected error: {e}")
                    continue

            return register_fail("Không thể tạo link đăng nhập tự động vào lúc này. Vui lòng bấm 'Report Issue' để đổi tài khoản mới hoặc thử lại sau ít phút!")

        elif is_access_code:
            return register_fail("Access Code không tồn tại trong hệ thống. Vui lòng kiểm tra lại mã đã mua!")
        else:
            # Xử lý nhập trực tiếp Cookie string hoặc fallback
            clean_str = cookie_value.replace("\r", " ").replace("\n", " ").strip()
            nid_match = re.search(r'NetflixId=([^; ]+)', clean_str)
            snid_match = re.search(r'SecureNetflixId=([^; ]+)', clean_str)

            if not nid_match:
                return register_fail("Invalid cookie format. Cookie must contain NetflixId.")

            nid = nid_match.group(1).strip()
            snid = snid_match.group(1).strip() if snid_match else ""

            try:
                token = fetch_netflix_nftoken_api(nid, snid)
                is_json = token.startswith("FALLBACK:")
                if is_json:
                    cookie_json = urllib.parse.unquote(token[9:])
                else:
                    cookie_json = urllib.parse.unquote(generate_json_cookie_token(nid, snid)[9:])
                pc_link = f"https://www.netflix.com/browse?nftoken={token}"
                mobile_link = f"https://www.netflix.com/unsupported?nftoken={token}"
                tv_link = f"https://www.netflix.com/tv8?nftoken={token}"
                general_link = f"https://www.netflix.com/YourAccount?nftoken={token}"
                return jsonify({
                    "success": True,
                    "pc_link": pc_link,
                    "mobile_link": mobile_link,
                    "tv_link": tv_link,
                    "general_link": general_link,
                    "is_json": is_json,
                    "cookie_json": cookie_json,
                    "plan": "Premium",
                    "expire_date": "N/A"
                })
            except Exception as e:
                return register_fail(f"Could not generate token: {e}")

    except Exception as e:
        print(f"Error generate token: {e}")
        return register_fail(f"Internal error: {e}", 500)

@portal_bp.route("/api/check_live_code", methods=["POST"])
def api_check_live_code():
    data = request.get_json(silent=True) or {}
    cookie_value = data.get("cookie", "").strip()
    if not cookie_value:
        return jsonify({"success": False, "error": "Please enter Access Code"}), 400

    database.init_db()
    clean_code = "".join(cookie_value.split()).upper()
    acc_key_row = database.get_access_key(clean_code) or database.get_access_key(cookie_value)

    if not acc_key_row:
        return jsonify({"success": False, "error": "Invalid or non-existent access code."}), 400

    code = acc_key_row[0]
    assigned_email = acc_key_row[1]
    expire_at_str = acc_key_row[2] if len(acc_key_row) > 2 else None

    allowed, err_msg = check_live_rate_limit(code)
    if not allowed:
        return jsonify({"success": False, "error": err_msg}), 429

    if expire_at_str:
        try:
            expire_date = datetime.strptime(expire_at_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            if datetime.now() > expire_date:
                database.delete_access_key(code)
                return jsonify({"success": False, "error": "Access code has expired and been disabled!"}), 400
        except Exception as e:
            print(f"Expiration parse error: {e}")

    acc = database.get_account_by_email(assigned_email)
    if not acc:
        rotated = database.rotate_access_key(code)
        if not rotated:
            return jsonify({"success": False, "error": "System ran out of backup Cookies!"}), 500
        return jsonify({"success": True, "message": "Old account died. The system has AUTOMATICALLY CHANGED to a new account for you. Please click Login Now!"})

    netflix_id = acc[2]
    secure_netflix_id = acc[3] if acc[3] else ""

    try:
        status, plan = checker.check_account_live(netflix_id, secure_netflix_id, check_payment=True)
        if status == "LIVE":
            final_plan = plan if (plan and plan != "VALID") else (acc[5] if (len(acc) > 5 and acc[5]) else "Premium")
            database.update_plan(assigned_email, final_plan)
            return jsonify({"success": True, "message": f"Account is LIVE normally! Plan: {final_plan}."})
        elif status == "DIE":
            from app.services.allocation_service import replace
            rep_res = replace(code=code, actor="system:live_check", reason="DIE detected during live check")
            if not rep_res.is_success:
                return jsonify({"success": False, "error": "Old account died but System ran out of backup Cookies!"}), 500
            return jsonify({"success": True, "message": "Account was faulty and has been AUTOMATICALLY CHANGED to a new account. You can click Login Now!"})
        else:
            return jsonify({"success": True, "message": "Temporary network delay during verification. Account status cannot be confirmed right now. Please try clicking Login Now or re-check in a moment!"})
    except Exception as e:
        return jsonify({"success": False, "error": f"Proxy check error. Please try again later. Details: {e}"}), 500


@portal_bp.route("/api/submit_request", methods=["POST"])
def api_submit_request():
    u7buy_order_id = request.form.get("u7buy_order_id", "").strip()
    code = request.form.get("code", "").strip()
    reason_category = request.form.get("reason_category", "").strip().upper()
    reason = request.form.get("reason", "").strip()
    image = request.files.get("image")

    if not reason_category:
        if "TOO_MANY" in reason.upper() or "SCREEN" in reason.upper():
            reason_category = "TOO_MANY_PEOPLE"
        elif "PAYMENT" in reason.upper() or "HOLD" in reason.upper():
            reason_category = "PAYMENT_ERROR"
        else:
            reason_category = "OTHER"

    if not u7buy_order_id:
        return jsonify({"success": False, "error": "Please enter your U7BUY Purchase ID / Order ID!"}), 400
    if not code:
        return jsonify({"success": False, "error": "Please enter your Access Code!"}), 400
    if not image:
        return jsonify({"success": False, "error": "Please upload a screenshot proof of the error!"}), 400

    database.init_db()
    clean_code = "".join(code.split()).upper()
    acc_key_row = database.get_access_key(clean_code) or database.get_access_key(code)

    if not acc_key_row:
        return jsonify({"success": False, "error": "Invalid or non-existent access code. Please check your code!"}), 400

    code = acc_key_row[0]

    expire_at_str = acc_key_row[2] if len(acc_key_row) > 2 else None
    if expire_at_str:
        try:
            expire_date = datetime.strptime(expire_at_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            if datetime.now() > expire_date:
                database.delete_access_key(code)
                return jsonify({"success": False, "error": "Access code has expired and been disabled!"}), 400
        except Exception:
            pass

    allowed, err_msg = check_code_rate_limit(code)
    if not allowed:
        return jsonify({"success": False, "error": err_msg}), 429

    try:
        file_bytes = image.read()
        from app.services.image_service import validate_image_bytes
        ok, validated_img, val_msg = validate_image_bytes(file_bytes)
        if not ok or not validated_img:
            return jsonify({"success": False, "error": f"Unsupported image format or corrupted file ({val_msg}). Please upload a genuine screenshot."}), 400

        file_ext = validated_img.format.lower()
        filename = f"{uuid.uuid4()}.{file_ext}"
        content_type = f"image/{file_ext if file_ext != 'jpg' else 'jpeg'}"

        image_url = ""
        if database.SUPABASE_KEY:
            try:
                database.get_supabase().storage.from_("requests").upload(
                    filename,
                    file_bytes,
                    file_options={"content-type": content_type}
                )
                image_url = f"{database.SUPABASE_URL}/storage/v1/object/public/requests/{filename}"
            except Exception as upload_err:
                print(f"Supabase upload notice: {upload_err}")

        b64_img = base64.b64encode(file_bytes).decode('utf-8')
        data_uri = f"data:{content_type};base64,{b64_img}"
        if not image_url:
            image_url = data_uri

        # AI Vision Check
        ai_data = {
            "error_type": "OTHER",
            "is_netflix": False,
            "card_digits": None,
            "card_last4": None,
            "visible_email": None,
            "error_description": ""
        }

        if Config.MISTRAL_API_KEY:
            headers = {
                "Authorization": f"Bearer {Config.MISTRAL_API_KEY}",
                "Content-Type": "application/json"
            }
            prompt = """Analyze this Netflix error screenshot carefully.
Detect if there is a screen limit / too many users / too many people error in ANY language:
- English: "Too many people are using your account right now", "Screen limit"
- Vietnamese: "Quá nhiều người đang sử dụng tài khoản", "Đã đạt giới hạn màn hình"
- Spanish: "Demasiadas personas están usando tu cuenta", etc.
- Portuguese, Thai, or other languages.

Reply with a valid JSON object with the following keys:
"error_type": Exactly one of "PAYMENT_ERROR", "TOO_MANY_PEOPLE", or "OTHER",
"is_netflix": boolean (true if this is a genuine Netflix screen, app, TV, or website, false otherwise),
"card_digits": string or null (any credit/debit card numbers or partial digits visible),
"card_last4": string or null (last 4 digits of card visible if any),
"visible_email": string or null (Netflix user email visible in screenshot if any, otherwise null),
"error_description": string (brief summary of error message displayed)."""

            payload = {
                "model": "pixtral-12b-2409",
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_uri}}
                    ]
                }],
                "response_format": {"type": "json_object"}
            }
            try:
                r = requests.post("https://api.mistral.ai/v1/chat/completions", headers=headers, json=payload, timeout=20)
                if r.status_code == 200:
                    raw_content = r.json()["choices"][0]["message"]["content"].strip()
                    if "```" in raw_content:
                        raw_content = re.sub(r"^```(?:json)?\s*", "", raw_content)
                        raw_content = re.sub(r"\s*```$", "", raw_content)
                    ai_data = json.loads(raw_content)
            except Exception as ocr_err:
                print(f"OCR Vision check notice: {ocr_err}")

        assigned_email = acc_key_row[1] if len(acc_key_row) > 1 else ""

        from app.services.evidence_service import parse_and_validate_ai_response, evaluate_evidence_for_auto_approval
        from app.services.order_service import verify_order_for_request

        ai_valid, evidence_data, schema_msg = parse_and_validate_ai_response(ai_data)
        if not ai_valid:
            error_type = evidence_data.get("error_type", "OTHER") if isinstance(evidence_data, dict) else "OTHER"
            error_desc = f"AI validation: {schema_msg}"
            can_auto_approve_screen = False
        else:
            error_type = evidence_data["error_type"]
            error_desc = evidence_data["error_description"]
            visible_email = evidence_data["visible_email"]

            # 1. Bằng chứng AI: is_netflix=True, TOO_MANY_PEOPLE (không bắt buộc email vì Netflix overlay không hiện email)
            is_screen_eligible, eval_reason = evaluate_evidence_for_auto_approval(evidence_data, assigned_email)

            # 2. Đơn hàng U7BUY: hợp lệ nếu có mã đơn và không bị huỷ / trùng mã khác
            is_order_verified, order_reason = verify_order_for_request(code, u7buy_order_id)

            can_auto_approve_screen = (
                getattr(Config, "AUTO_APPROVAL_ENABLED", True)
                and is_screen_eligible
                and is_order_verified
            )
            if is_screen_eligible and not is_order_verified:
                error_desc = f"{error_desc} (Order verification required: {order_reason})"
            elif not is_screen_eligible and error_type == "TOO_MANY_PEOPLE":
                error_desc = f"{error_desc} (Proof verification required: {eval_reason})"

        if can_auto_approve_screen:
            saved = database.save_request(code, u7buy_order_id, image_url, f"[TOO_MANY_PEOPLE] Auto-approved: {error_desc or 'Screen limit verified'}", "pending")
            if not saved:
                return jsonify({"success": False, "error": "Database error: Could not record transaction."}), 500

            recent_reqs = database.get_pending_requests()
            req_id = None
            for r in recent_reqs:
                if r.get("code") == code:
                    req_id = r.get("id")
                    break

            from app.services.allocation_service import replace
            rep_res = replace(
                request_id=req_id,
                code=code,
                actor="ai:screen_limit",
                reason=f"[TOO_MANY_PEOPLE] Auto-approved: {error_desc or 'Screen limit verified'}"
            )

            if rep_res.is_success:
                mark_code_request_success(code)
                return jsonify({
                    "success": True,
                    "auto_rotated": True,
                    "error_type": "TOO_MANY_PEOPLE",
                    "message": "AI Verified! Screen limit error detected. The system has automatically replaced your session with a fresh active account. Click Login Now!"
                })
            elif rep_res.status == "out_of_stock":
                return jsonify({
                    "success": True,
                    "auto_rotated": False,
                    "message": "Screen limit verified! The backup vault is temporarily restocking. Admin has been notified to restock and assign your account shortly."
                })
            else:
                return jsonify({"success": False, "error": f"Auto-replacement error: {rep_res.message}"}), 500

        # -------------------------------------------------------------------------
        # CASE 2 & 3: PAYMENT ERROR VÀ CÁC LỖI KHÁC -> CHUYỂN HÀNG CHỜ ADMIN DUYỆT THỦ CÔNG
        # -------------------------------------------------------------------------
        if reason_category == "OTHER":
            status_to_save = "manual"
            req_reason = f"[OTHER] {reason or error_desc or 'Chờ duyệt thủ công'}"
        elif error_type == "PAYMENT_ERROR" or reason_category == "PAYMENT_ERROR":
            status_to_save = "pending"
            req_reason = f"[PAYMENT_ERROR] {reason or error_desc or 'Lỗi thanh toán / nợ cước chờ duyệt'}"
        else:
            status_to_save = "pending"
            req_reason = f"[{reason_category}] {reason or error_desc or 'Chờ duyệt thủ công'}"

        saved = database.save_request(code, u7buy_order_id, image_url, req_reason, status_to_save)
        if not saved:
            return jsonify({"success": False, "error": "Database error: Could not record your request. Please try again later."}), 500

        mark_code_request_success(code)
        send_telegram_alert(f"🔔 <b>Có yêu cầu khiếu nại mới (Chờ duyệt)!</b>\n- Mã: <code>{code}</code>\n- U7BUY: <code>{u7buy_order_id}</code>\n- Phân loại: {reason_category}\n- Lý do: {req_reason}")

        return jsonify({
            "success": True,
            "auto_rotated": False,
            "message": "Your request has been submitted successfully! Admin will review and process within 1-10 hours."
        })

    except Exception as e:
        print(f"Submit request error: {e}")
        return jsonify({"success": False, "error": f"Error submitting request: {e}"}), 500

@portal_bp.route("/api/chat", methods=["POST"])
def api_chat():
    client_ip = get_client_ip(request)
    allowed, wait_sec = check_rate_limit(f"chat:{client_ip}", max_requests=15, window_seconds=60)
    if not allowed:
        return jsonify({"success": False, "error": f"Too many chat requests. Please wait {wait_sec} seconds."}), 429

    data = request.get_json(silent=True) or {}
    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"success": False, "error": "Message is empty"})

    fallback_reply = (
        "👋 Xin chào! Tôi là trợ lý ảo hỗ trợ dịch vụ Netflix Access Code.\n\n"
        "• **Đăng nhập**: Nhập mã Access Code, bấm **LOGIN NOW** rồi chọn thiết bị (PC, Mobile hoặc TV).\n"
        "• **Báo lỗi & Đổi mã**: Bấm nút **REQUEST CHANGE** và tải ảnh chụp màn hình lỗi lên để được đổi tài khoản.\n"
        "• **Không dùng VPN**: Vui lòng tắt VPN/Wi-Fi nếu bị chặn, chuyển sang 4G/5G để xem mượt mà.\n"
        "Nếu bạn cần thêm hỗ trợ chuyên sâu, vui lòng nhắn tin trực tiếp qua **U7BUY Chat**!"
    )

    if Config.MISTRAL_API_KEY:
        headers = {
            "Authorization": f"Bearer {Config.MISTRAL_API_KEY}",
            "Content-Type": "application/json"
        }
        prompt = (
            "You are a helpful customer support AI for Netflix Access. Answer concisely in the user's language. "
            "Condition 1: Screen limit error is automatically replaced 24/7. "
            "Condition 2: Other errors (Hold/Expired) reviewed in 1-10 hours via REQUEST CHANGE button. "
            "Condition 3: Absolutely NO VPN allowed. Never reveal passwords or technical cookies."
        )
        try:
            payload = {
                "model": Config.MISTRAL_MODEL,
                "messages": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_message}
                ],
                "max_tokens": 300
            }
            r = requests.post("https://api.mistral.ai/v1/chat/completions", headers=headers, json=payload, timeout=12)
            if r.status_code == 200:
                reply = r.json()["choices"][0]["message"]["content"].strip()
                return jsonify({"success": True, "reply": reply})
        except Exception as e:
            print(f"Mistral chat error: {e}")

    return jsonify({"success": True, "reply": fallback_reply})

@portal_bp.route("/api/translate_page", methods=["POST"])
def api_translate_page():
    client_ip = get_client_ip(request)
    allowed, wait_sec = check_rate_limit(f"translate:{client_ip}", max_requests=15, window_seconds=60)
    if not allowed:
        return jsonify({"success": False, "error": f"Too many translation requests. Please wait {wait_sec} seconds."}), 429

    data = request.get_json(silent=True) or {}
    target_lang = data.get("language", "").strip()
    texts = data.get("texts", {})
    if not target_lang or not texts:
        return jsonify({"success": False, "error": "Missing target language or texts"}), 400

    if Config.MISTRAL_API_KEY:
        headers = {
            "Authorization": f"Bearer {Config.MISTRAL_API_KEY}",
            "Content-Type": "application/json"
        }
        system_prompt = (
            f"You are an expert website translator. Translate the English JSON values into {target_lang}. "
            "Keep the exact same JSON keys and HTML tags. Output ONLY a valid JSON object."
        )
        try:
            payload = {
                "model": Config.MISTRAL_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(texts, ensure_ascii=False)}
                ],
                "response_format": {"type": "json_object"}
            }
            r = requests.post("https://api.mistral.ai/v1/chat/completions", headers=headers, json=payload, timeout=15)
            if r.status_code == 200:
                translated_json = json.loads(r.json()["choices"][0]["message"]["content"].strip())
                return jsonify({"success": True, "translations": translated_json})
        except Exception as e:
            print(f"Translation API error: {e}")

    return jsonify({"success": False, "error": "AI Translation unavailable"}), 500
