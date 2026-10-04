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

portal_bp = Blueprint("portal", __name__)

@portal_bp.route("/")
def index():
    database.init_db()
    return render_template("portal/index.html")

@portal_bp.route("/api/generate_nftoken", methods=["POST"])
def api_generate_nftoken():
    def register_fail(err_msg, status_code=400):
        return jsonify({"success": False, "error": err_msg}), status_code

    try:
        data = request.get_json(silent=True) or {}
        cookie_value = data.get("cookie", "").strip()
        if not cookie_value:
            return register_fail("Please enter Access Code")

        database.init_db()

        acc_key_row = None
        if "NetflixId" not in cookie_value and not cookie_value.startswith("FALLBACK:") and not cookie_value.startswith("[") and not cookie_value.startswith("{"):
            try:
                acc_key_row = database.get_access_key(cookie_value)
            except Exception as e:
                print(f"Error querying access key: {e}")

        is_access_code = acc_key_row is not None or (len(cookie_value) in [5, 6, 7, 8, 9, 10, 12, 15, 16] and "NetflixId" not in cookie_value and not cookie_value.startswith("FALLBACK:"))

        if acc_key_row:
            code = acc_key_row[0]
            assigned_email = acc_key_row[1]
            expire_at_str = acc_key_row[2] if len(acc_key_row) > 2 else None

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
            if len(code) == 15:
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

                if not acc:
                    rotated = database.rotate_access_key(code)
                    if not rotated:
                        return jsonify({"success": False, "error": f"Hệ thống đã hết tài khoản dự phòng cho gói {expected_plan}!"}), 500
                    assigned_email = database.get_access_key(code)[1]
                    continue

                netflix_id = acc[2]
                secure_netflix_id = acc[3] if acc[3] else ""
                acc_plan = acc[5] if (acc and len(acc) > 5 and acc[5]) else "Premium"
                acc_expire = acc[1] if (acc and len(acc) > 1 and acc[1]) else (expire_at_str if expire_at_str else "N/A")

                try:
                    token = fetch_netflix_nftoken_api(netflix_id, secure_netflix_id)
                    is_json = token.startswith("FALLBACK:")
                    cookie_json = urllib.parse.unquote(token[9:]) if is_json else ""

                    try:
                        rt_plan, rt_expire = fetch_realtime_account_info(netflix_id, secure_netflix_id)
                        if rt_plan:
                            acc_plan = rt_plan
                            database.update_plan(assigned_email, rt_plan)
                        if rt_expire:
                            acc_expire = rt_expire
                    except CookieError:
                        raise
                    except Exception as meta_err:
                        print(f"Non-critical realtime metadata fetch error: {meta_err}")

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
                    database.delete_account(assigned_email)
                    rotated = database.rotate_access_key(code)
                    if not rotated:
                        return jsonify({"success": False, "error": f"Tài khoản lỗi và kho đã hết Cookie dự phòng cho gói {expected_plan}!"}), 500
                    assigned_email = database.get_access_key(code)[1]
                    continue
                except Exception as e:
                    print(f"Unexpected error: {e}")
                    continue

            return register_fail("Không thể kết nối đến máy chủ Netflix do mạng hoặc Proxy. Vui lòng bấm LOGIN NOW lại!")

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
    acc_key_row = database.get_access_key(cookie_value)

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
            database.delete_account(assigned_email)
            rotated = database.rotate_access_key(code)
            if not rotated:
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
    reason = request.form.get("reason", "").strip()
    image = request.files.get("image")

    if not u7buy_order_id:
        return jsonify({"success": False, "error": "Please enter your U7BUY Purchase ID / Order ID!"}), 400
    if not code:
        return jsonify({"success": False, "error": "Please enter your Access Code!"}), 400
    if not image:
        return jsonify({"success": False, "error": "Please upload a screenshot proof of the error!"}), 400

    database.init_db()
    acc_key_row = database.get_access_key(code)

    if not acc_key_row:
        return jsonify({"success": False, "error": "Invalid or non-existent access code. Please check your code!"}), 400

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
        if len(file_bytes) < 16:
            return jsonify({"success": False, "error": "Invalid or empty image file uploaded."}), 400

        # Validate genuine image headers (PNG, JPEG, WEBP)
        is_png = file_bytes.startswith(b'\x89PNG\r\n\x1a\n')
        is_jpeg = file_bytes.startswith(b'\xff\xd8\xff')
        is_webp = file_bytes.startswith(b'RIFF') and b'WEBP' in file_bytes[:16]
        if not (is_png or is_jpeg or is_webp):
            return jsonify({"success": False, "error": "Unsupported image format. Please upload a real screenshot (PNG, JPG, or WEBP)."}), 400

        file_ext = 'png' if is_png else ('jpg' if is_jpeg else 'webp')
        filename = f"{uuid.uuid4()}.{file_ext}"
        content_type = image.content_type or f"image/{file_ext}"

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
            prompt = """Analyze this Netflix error screenshot. Reply with JSON keys:
            error_type ("PAYMENT_ERROR", "TOO_MANY_PEOPLE", "OTHER"),
            is_netflix (bool), card_digits (str/null), card_last4 (str/null),
            visible_email (str/null), error_description (str)."""

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
                    ai_data = json.loads(r.json()["choices"][0]["message"]["content"])
            except Exception as ocr_err:
                print(f"OCR Vision check notice: {ocr_err}")

        # Tự động duyệt NẾU là lỗi màn hình (TOO_MANY_PEOPLE) VÀ đúng là màn hình Netflix
        error_type = ai_data.get("error_type", "OTHER")
        is_netflix = ai_data.get("is_netflix", False)

        if error_type == "TOO_MANY_PEOPLE" and is_netflix:
            assigned_email = acc_key_row[1]

            # Kiểm tra và thực hiện xoay mã sang tài khoản dự phòng mới TRƯỚC
            rotated = database.rotate_access_key(code)
            if rotated:
                # Xoay thành công mới xóa tài khoản cũ khỏi DB
                database.delete_account(assigned_email)
                mark_code_request_success(code)
                database.save_request(code, u7buy_order_id, image_url, f"Auto-approved: {ai_data.get('error_description')}", "auto_accepted")
                
                # Gửi thông báo Telegram
                send_telegram_alert(f"⚡ <b>Tự động đổi tài khoản thành công!</b>\n- Mã: <code>{code}</code>\n- U7BUY: <code>{u7buy_order_id}</code>\n- Lỗi: Quá số lượng màn hình")

                return jsonify({
                    "success": True,
                    "auto_rotated": True,
                    "message": "AI Verified! Screen limit error detected. The system has automatically changed to a new account for you. Click Login Now!"
                })
            else:
                print(f"[Auto-Rotate Warning] Kho hết tài khoản dự phòng cho mã {code}, chuyển sang hàng đợi Admin duyệt.")

        # Lưu yêu cầu chờ Admin duyệt
        saved = database.save_request(code, u7buy_order_id, image_url, reason or ai_data.get("error_description", ""), "pending")
        if not saved:
            return jsonify({"success": False, "error": "Database error: Could not record your request. Please try again later."}), 500

        mark_code_request_success(code)

        # Gửi thông báo Telegram cho Admin
        send_telegram_alert(f"🔔 <b>Có yêu cầu khiếu nại mới!</b>\n- Mã Code: <code>{code}</code>\n- U7BUY Order: <code>{u7buy_order_id}</code>\n- Lý do: {reason or 'Chờ duyệt'}")

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
