import os
import sys
from flask import Flask, request, render_template_string, redirect, url_for, flash, jsonify, session
import urllib.parse
import requests
import threading
from urllib3.exceptions import InsecureRequestWarning
import database
import parser
import checker
import secrets
import re
from functools import wraps
import random
import string

requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)
sys.stdout.reconfigure(encoding='utf-8')

app = Flask(__name__)
app.secret_key = "super_secret_key_for_flash_messages_and_sessions_123"

ADMIN_EMAIL = "concumm2@gmail.com"
ADMIN_PASS = "Concumm1!"

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

COMMON_STYLE = r"""
<style>
    :root {
        --bg-color: #0f111a;
        --surface-color: rgba(255, 255, 255, 0.05);
        --primary-color: #E50914;
        --text-color: #f1f1f1;
        --border-color: rgba(255, 255, 255, 0.1);
    }
    body {
        font-family: 'Inter', sans-serif;
        background: linear-gradient(135deg, #0f111a 0%, #1a1c29 100%);
        color: var(--text-color);
        margin: 0; padding: 0; min-height: 100vh;
        display: flex; flex-direction: column; align-items: center;
    }
    .container { position: relative; width: 95%; max-width: 1200px; margin-top: 50px; z-index: 1; }
    .header { text-align: center; margin-bottom: 40px; }
    h1 {
        font-size: 2.5rem; font-weight: 700; margin-bottom: 10px;
        background: linear-gradient(90deg, #fff, #aaa);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }
    .glass-panel {
        background: rgba(30, 32, 45, 0.95);
        border: 1px solid var(--border-color);
        border-radius: 16px; padding: 30px; margin-bottom: 30px;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);
    }
    .search-box {
        width: 100%; padding: 12px 15px; border-radius: 8px;
        border: 1px solid var(--border-color); background: rgba(0,0,0,0.3);
        color: white; font-family: 'Inter', sans-serif; font-size: 1rem;
        box-sizing: border-box;
    }
    .search-box:focus {
        outline: none; border-color: var(--primary-color);
        box-shadow: 0 0 10px rgba(229, 9, 20, 0.2);
    }
    button {
        background: var(--primary-color); color: white; border: none;
        padding: 12px 24px; border-radius: 8px; font-weight: 600; cursor: pointer;
    }
    button:hover { background: #f40612; }
    .btn-copy { background: #2d98da; padding: 6px 12px; font-size: 0.8rem; border-radius: 4px; border: none; color: white; cursor: pointer; }
    .btn-login {
        background: #27ae60 !important; color: white !important; border: none !important;
        padding: 8px 12px !important; font-size: 0.85rem !important; font-weight: bold !important;
        border-radius: 6px !important; cursor: pointer; text-decoration: none; display: inline-block;
    }
    table { width: 100%; border-collapse: collapse; margin-top: 10px; }
    th, td { padding: 15px; text-align: left; border-bottom: 1px solid var(--border-color); }
    th { color: #aaa; text-transform: uppercase; font-size: 0.85rem; }
    tr:hover td { background: rgba(255, 255, 255, 0.03); }
    .flash-message {
        background: rgba(46, 213, 115, 0.1); border: 1px solid rgba(46, 213, 115, 0.3);
        color: #2ed573; padding: 15px; border-radius: 8px; margin-bottom: 20px; text-align: center;
    }
    .flash-error {
        background: rgba(255, 71, 87, 0.1); border: 1px solid rgba(255, 71, 87, 0.3); color: #ff4757;
    }
    .flash-warning {
        background: rgba(255, 159, 67, 0.1); border: 1px solid rgba(255, 159, 67, 0.3); color: #ff9f43;
    }
</style>
<script>
    function copyCookie(text, btn) {
        let originalText = btn.innerHTML;
        btn.innerHTML = '✔ Đã Copy';
        btn.style.background = '#20bf6b';
        setTimeout(() => { btn.innerHTML = originalText; btn.style.background = '#2d98da'; }, 2000);
        if (navigator.clipboard && window.isSecureContext) {
            navigator.clipboard.writeText(text).catch(err => {
                fallbackCopy(text);
            });
        } else {
            fallbackCopy(text);
        }
    }
    function fallbackCopy(text) {
        let textArea = document.createElement("textarea");
        textArea.value = text;
        textArea.style.position = "fixed";
        textArea.style.left = "-999999px";
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        try { document.execCommand('copy'); } catch (err) { }
        textArea.remove();
    }
    function showLoading(btn) {
        btn.innerHTML = '⏳ Đang xử lý...';
        btn.style.pointerEvents = 'none';
        btn.style.opacity = '0.7';
    }
</script>
"""

PUBLIC_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Netflix Access</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;900&display=swap" rel="stylesheet">
    """ + COMMON_STYLE + r"""
    <script>
        function generateQuickLinks() {
            let rawInput = document.getElementById("rawTokenInput").value.trim();
            let resultDiv = document.getElementById("quickLinksResult");
            let pcLink = document.getElementById("quickPcLink");
            let mobileLink = document.getElementById("quickMobileLink");
            let tvLink = document.getElementById("quickTvLink");
            let statusText = document.getElementById("statusText");
            let btn = document.getElementById("submitBtn");

            if (rawInput) {
                btn.disabled = true;
                btn.innerHTML = "⏳ Đang kết nối...";
                pcLink.innerText = "⏳ Đang tạo link...";
                mobileLink.innerText = "⏳ Đang tạo link...";
                tvLink.innerText = "⏳ Đang tạo link...";
                statusText.innerText = "Đang kiểm tra kho dữ liệu và kết nối tới Netflix...";
                statusText.style.color = "#f39c12";
                resultDiv.style.display = "flex";

                fetch("/api/generate_nftoken", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ cookie: rawInput })
                })
                .then(res => res.json())
                .then(data => {
                    btn.disabled = false;
                    btn.innerHTML = "Tiến Hành Đăng Nhập";
                    if (data.success) {
                        pcLink.href = data.pc_link;
                        pcLink.innerText = "💻 PC Link (Xem ngay)";
                        mobileLink.href = data.mobile_link;
                        mobileLink.innerText = "📱 Mobile Link (Xem ngay)";
                        tvLink.href = data.tv_link;
                        tvLink.innerText = "📺 TV Link (Xem ngay)";
                        statusText.innerText = "Thành công! Hãy click vào link bên dưới để xem phim.";
                        statusText.style.color = "#2ecc71";
                    } else {
                        statusText.innerText = "Lỗi: " + data.error;
                        statusText.style.color = "#e74c3c";
                    }
                })
                .catch(err => {
                    btn.disabled = false;
                    btn.innerHTML = "Tiến Hành Đăng Nhập";
                    statusText.innerText = "Lỗi kết nối tới Server!";
                    statusText.style.color = "#e74c3c";
                });
            } else {
                resultDiv.style.display = "none";
            }
        }
    </script>
</head>
<body>
    <div class="container" style="max-width: 600px; margin-top: 10vh;">
        <div class="header">
            <h1>Netflix Access</h1>
            <p>Hệ thống Đăng nhập Nhanh Tự Động</p>
        </div>
        <div class="glass-panel">
            <h3 style="margin-top: 0; text-align: center; font-weight: 400;">Nhập Mã Truy Cập</h3>
            <input type="text" id="rawTokenInput" class="search-box" style="text-align: center; font-size: 1.2rem; letter-spacing: 2px;" placeholder="Ví dụ: X9K2M1">
            <button id="submitBtn" onclick="generateQuickLinks()" style="width: 100%; margin-top: 10px; padding: 15px; font-size: 1.1rem;">Tiến Hành Đăng Nhập</button>
            
            <div id="quickLinksResult" style="display: flex; flex-direction: column; gap: 15px; margin-top: 25px; display: none; background: rgba(0,0,0,0.2); padding: 20px; border-radius: 8px;">
                <p id="statusText" style="text-align: center; margin: 0; font-weight: bold;"></p>
                <div style="display: flex; gap: 10px; justify-content: center; align-items: center;">
                    <a id="quickPcLink" href="#" target="_blank" rel="noreferrer" class="btn-login" style="background: #e74c3c !important; font-size: 1rem; padding: 12px 20px !important;">💻 PC Link</a>
                    <button class="btn-copy" onclick="copyCookie(document.getElementById('quickPcLink').href, this)" style="padding: 12px 20px; font-size: 1rem;">📋 Copy</button>
                </div>
                <div style="display: flex; gap: 10px; justify-content: center; align-items: center;">
                    <a id="quickMobileLink" href="#" target="_blank" rel="noreferrer" class="btn-login" style="background: #e74c3c !important; font-size: 1rem; padding: 12px 20px !important;">📱 Mobile Link</a>
                    <button class="btn-copy" onclick="copyCookie(document.getElementById('quickMobileLink').href, this)" style="padding: 12px 20px; font-size: 1rem;">📋 Copy</button>
                </div>
                <div style="display: flex; gap: 10px; justify-content: center; align-items: center;">
                    <a id="quickTvLink" href="#" target="_blank" rel="noreferrer" class="btn-login" style="background: #e74c3c !important; font-size: 1rem; padding: 12px 20px !important;">📺 TV Link</a>
                    <button class="btn-copy" onclick="copyCookie(document.getElementById('quickTvLink').href, this)" style="padding: 12px 20px; font-size: 1rem;">📋 Copy</button>
                </div>
            </div>
        </div>
        <div style="text-align: center; margin-top: 20px;">
            <a href="/admin" style="color: #666; font-size: 0.8rem; text-decoration: none;">Admin Dashboard</a>
        </div>
    </div>
</body>
</html>
"""

ADMIN_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;900&display=swap" rel="stylesheet">
    """ + COMMON_STYLE + r"""
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Admin Dashboard</h1>
            <p>Hệ thống Quản lý Tài khoản & Mã Truy Cập</p>
            <a href="/" style="color: #3498db; text-decoration: none; margin-right: 15px;">[Về Trang Chủ]</a>
            <a href="/logout" style="color: #e74c3c; text-decoration: none;">[Đăng xuất]</a>
        </div>

        {% with messages = get_flashed_messages(with_categories=true) %}
          {% if messages %}
            {% for category, message in messages %}
              <div class="flash-message {% if category == 'error' %}flash-error{% elif category == 'warning' %}flash-warning{% endif %}">{{ message }}</div>
            {% endfor %}
          {% endif %}
        {% endwith %}

        <div class="glass-panel">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                <h3 style="margin: 0; font-weight: 400;">Quản lý Mã Truy Cập (License Keys)</h3>
                <div style="display: flex; gap: 10px;">
                    <form action="/admin/generate_key/standard" method="POST" style="margin: 0;" onsubmit="showLoading(this.querySelector('button'))">
                        <button type="submit" style="background: #2980b9; font-size: 0.9rem; padding: 10px 15px;">+ Sinh Mã Standard (10)</button>
                    </form>
                    <form action="/admin/generate_key/premium" method="POST" style="margin: 0;" onsubmit="showLoading(this.querySelector('button'))">
                        <button type="submit" style="background: #27ae60; font-size: 0.9rem; padding: 10px 15px;">+ Sinh Mã Premium 4K (15)</button>
                    </form>
                </div>
            </div>
            
            <form action="/admin" method="GET" style="display: flex; gap: 10px; margin-bottom: 20px;">
                <input type="text" name="search_code" class="search-box" placeholder="Nhập Mã 6 số để tìm..." value="{{ request.args.get('search_code', '') }}">
                <button type="submit" style="background: #3498db; white-space: nowrap;">🔍 Tìm theo Mã</button>
            </form>
            
            {% if search_code or access_keys|length < 20 %}
            <div style="overflow-x: auto;">

                <table>
                    <thead>
                        <tr>
                            <th>Mã (Code)</th>
                            <th>Email Đang Gán</th>
                            <th>Ngày Tạo</th>
                            <th>Hành động</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for key in access_keys %}
                        <tr>
                            <td style="font-weight: bold; font-family: monospace; font-size: 1.3rem; color: #f1c40f; letter-spacing: 2px;">{{ key[0] }}</td>
                            <td>{{ key[1] }}</td>
                            <td style="font-size: 0.85rem; color: #888;">{{ key[2] }}</td>
                            <td style="display: flex; gap: 10px; flex-wrap: wrap;">
                                <button class="btn-copy" onclick="copyCookie('{{ key[0] }}', this)">Copy Mã</button>
                                <form action="/admin/rotate_key/{{ key[0] }}" method="POST" style="margin: 0;" onsubmit="return confirm('Bạn muốn đổi tài khoản mới cho mã này?');">
                                    <button type="submit" style="background: #f39c12; padding: 6px 12px; font-size: 0.8rem;">Đổi Acc</button>
                                </form>
                                <form action="/admin/delete_key/{{ key[0] }}" method="POST" style="margin: 0;" onsubmit="return confirm('Xóa mã này? Khách hàng sẽ không dùng được nữa.');">
                                    <button type="submit" style="background: #e74c3c; padding: 6px 12px; font-size: 0.8rem;">Xóa</button>
                                </form>
                            </td>
                        </tr>
                        {% else %}
                        <tr><td colspan="4" style="text-align: center; color: #666; padding: 20px;">Chưa có mã nào được sinh ra.</td></tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            {% else %}
            <p style="text-align: center; color: #888; margin-top: 10px;">Danh sách mã đang được ẩn. Vui lòng sử dụng ô tìm kiếm phía trên.</p>
            {% endif %}
        </div>

        <div class="glass-panel">
            <h3 style="margin-top: 0; margin-bottom: 20px; font-weight: 400;">Nhập Kho Dữ Liệu (Cookies)</h3>
            <form style="display: flex; gap: 15px; align-items: center;" action="/upload" method="POST" enctype="multipart/form-data" onsubmit="showLoading(this.querySelector('button'))">
                <input type="file" name="account_file" accept=".txt" required style="padding: 10px; background: rgba(0,0,0,0.2); border: 1px dashed var(--border-color); color: #ccc;">
                <button type="submit">Upload Database</button>
            </form>
        </div>

        <div class="glass-panel">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                <h3 style="margin: 0; font-weight: 400;">Kho Cookie Gốc <span style="font-size: 0.9rem; color: #888;">({{ total_accounts }} accounts)</span></h3>
                <div style="display: flex; gap: 10px;">
                    <form action="/force_check_all" method="POST" onsubmit="showLoading(this.querySelector('button'))" style="margin: 0;">
                        <button type="submit" style="background: #e74c3c; padding: 8px 15px; font-size: 0.9rem;" title="Kiểm tra lại toàn bộ kho bất chấp gói cước (Tốn Proxy)">🔥 QUÉT SẠCH KHO (FORCE CHECK)</button>
                    </form>
                    <form action="/check_all" method="POST" onsubmit="showLoading(this.querySelector('button'))" style="margin: 0;">
                        <button type="submit" style="background: #10ac84; padding: 8px 15px; font-size: 0.9rem;" title="Chỉ quét những Acc chưa có tên Gói Cước (Tiết kiệm Proxy)">⚡ CẬP NHẬT GÓI CƯỚC MỚI</button>
                    </form>
                </div>
            </div>
            
            <form action="/admin" method="GET" style="display: flex; gap: 10px; margin-bottom: 20px;">
                <input type="text" name="search_email" class="search-box" placeholder="Nhập Email để tìm Cookie..." value="{{ request.args.get('search_email', '') }}">
                <button type="submit" style="background: #3498db; white-space: nowrap;">🔍 Tìm theo Email</button>
            </form>
            
            {% if search_email or accounts|length < 20 %}
            <div style="overflow-x: auto; max-height: 400px; overflow-y: auto;">
                <table>
                    <thead>
                        <tr>
                            <th>Email</th>
                            <th>Gói Cước</th>
                            <th>Cookie</th>
                            <th>Hành động</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for acc in accounts %}
                        <tr>
                            <td style="font-weight: 600;">{{ acc[0] }}</td>
                            <td style="font-weight: bold; color: {% if 'Premium' in (acc[5] or '') %}#f1c40f{% else %}#bdc3c7{% endif %};">{{ acc[5] if acc[5] else 'Unknown' }}</td>
                            <td style="font-size: 0.8rem; color: #666; font-family: monospace; max-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="{{ acc[2] }}">{{ acc[2] }}</td>
                            <td style="display: flex; gap: 8px;">
                                <form action="/delete/{{ acc[0] }}" method="POST" style="margin: 0;" onsubmit="return confirm('Xóa cookie này?');">
                                    <button type="submit" style="background: #e74c3c; padding: 6px 12px; font-size: 0.8rem;">Xóa</button>
                                </form>
                            </td>
                        </tr>
                        {% else %}
                        <tr><td colspan="4" style="text-align: center; color: #666; padding: 20px;">Chưa có tài khoản nào trong kho. Hãy upload file!</td></tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            {% else %}
            <p style="text-align: center; color: #888; margin-top: 10px;">Danh sách Cookie đang được ẩn để tránh quá tải. Vui lòng sử dụng ô tìm kiếm phía trên.</p>
            {% endif %}
        </div>
    </div>
</body>
</html>
"""

LOGIN_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Login</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;900&display=swap" rel="stylesheet">
    """ + COMMON_STYLE + r"""
</head>
<body>
    <div class="container" style="max-width: 400px; margin-top: 15vh;">
        <div class="glass-panel">
            <h2 style="text-align: center; margin-top: 0;">Admin Login</h2>
            {% with messages = get_flashed_messages(with_categories=true) %}
              {% if messages %}
                {% for category, message in messages %}
                  <div class="flash-message {% if category == 'error' %}flash-error{% endif %}" style="padding: 10px; margin-bottom: 15px;">{{ message }}</div>
                {% endfor %}
              {% endif %}
            {% endwith %}
            <form action="/login" method="POST" style="display: flex; flex-direction: column; gap: 15px;">
                <input type="email" name="email" class="search-box" placeholder="Email" required style="margin-bottom: 0;">
                <input type="password" name="password" class="search-box" placeholder="Mật khẩu" required style="margin-bottom: 0;">
                <button type="submit" style="width: 100%;">Đăng nhập</button>
            </form>
        </div>
    </div>
</body>
</html>
"""

@app.route("/")
def index():
    database.init_db()
    return render_template_string(PUBLIC_TEMPLATE)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        if email == ADMIN_EMAIL and password == ADMIN_PASS:
            session['logged_in'] = True
            return redirect(url_for("admin"))
        else:
            flash("Sai email hoặc mật khẩu!", "error")
    return render_template_string(LOGIN_TEMPLATE)

@app.route("/logout")
def logout():
    session.pop('logged_in', None)
    return redirect(url_for("login"))

@app.route("/admin")
@login_required
def admin():
    database.init_db()
    all_accounts = database.get_all_accounts()
    all_access_keys = database.get_all_access_keys()
    
    search_email = request.args.get("search_email", "").strip().lower()
    search_code = request.args.get("search_code", "").strip().upper()
    
    # Filter keys
    if search_code:
        access_keys = [k for k in all_access_keys if search_code in k[0].upper()]
    else:
        access_keys = all_access_keys
        
    # Filter accounts
    if search_email:
        accounts = [a for a in all_accounts if search_email in a[0].lower()]
    else:
        accounts = all_accounts
        
    return render_template_string(
        ADMIN_TEMPLATE, 
        accounts=accounts, 
        access_keys=access_keys,
        total_accounts=len(all_accounts),
        search_email=search_email,
        search_code=search_code
    )

@app.route("/admin/generate_key/<plan_type>", methods=["POST"])
@login_required
def generate_key(plan_type):
    database.init_db()
    
    # 10 chars for standard, 15 chars for premium
    length = 10 if plan_type == 'standard' else 15
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))
    
    success, msg = database.create_access_key(code)
    if success:
        flash(f"Đã tạo mã {plan_type.upper()} thành công: {code}", "success")
    else:
        flash(f"Lỗi tạo mã: {msg}", "error")
    return redirect(url_for("admin"))

@app.route("/admin/rotate_key/<code>", methods=["POST"])
@login_required
def rotate_key(code):
    success = database.rotate_access_key(code)
    if success:
        flash(f"Đã đổi sang Account mới cho mã: {code}", "success")
    else:
        flash(f"Lỗi: Không còn Account nào khả dụng trong kho để đổi.", "error")
    return redirect(url_for("admin"))

@app.route("/admin/delete_key/<code>", methods=["POST"])
@login_required
def delete_key(code):
    database.delete_access_key(code)
    flash(f"Đã xóa mã truy cập: {code}", "success")
    return redirect(url_for("admin"))

@app.route("/upload", methods=["POST"])
@login_required
def upload():
    if "account_file" not in request.files:
        flash("Lỗi: Không tìm thấy file upload.", "error")
        return redirect(url_for("admin"))
        
    file = request.files["account_file"]
    if file.filename == "":
        flash("Lỗi: Chưa chọn file.", "error")
        return redirect(url_for("admin"))
        
    if file:
        file_bytes = file.read()
        try:
            content = file_bytes.decode('utf-8-sig')
        except UnicodeDecodeError:
            try:
                content = file_bytes.decode('utf-16')
            except UnicodeDecodeError:
                content = file_bytes.decode('latin-1', errors='replace')
                
        lines = content.splitlines()
        accounts_list = parser.parse_lines(lines)
            
        if accounts_list:
            database.init_db()
            count = 0
            for acc in accounts_list:
                database.save_account(acc['email'], acc['expire'], acc['netflix_id'], acc['secure_netflix_id'], acc.get('plan'))
                count += 1
            flash(f"🎉 Đã trích xuất và lưu thành công {count} tài khoản vào Database!", "success")
        else:
            debug_info = content[:200] if content else "EMPTY_FILE"
            flash(f"❌ Thất bại: Không tìm thấy tài khoản hợp lệ nào trong file. Debug info: {debug_info}", "error")
            
    return redirect(url_for("admin"))

@app.route("/delete/<email>", methods=["POST"])
@login_required
def delete_acc(email):
    database.delete_account(email)
    flash(f"Đã xoá cookie: {email}", "success")
    return redirect(url_for("admin"))

def background_check_all():
    with app.app_context():
        database.init_db()
        accounts = database.get_all_accounts()
        for acc in accounts:
            email = acc[0]
            current_plan = acc[5]
            
            # Bỏ qua những tài khoản đã có gói cước
            if current_plan:
                continue
                
            netflix_id = acc[2]
            secure_netflix_id = acc[3]
            status, plan = checker.check_account_live(netflix_id, secure_netflix_id)
            if status == "LIVE" and plan:
                database.update_plan(email, plan)
            elif status == "DIE":
                database.delete_account(email)

@app.route("/check_all", methods=["POST"])
@login_required
def check_all():
    database.init_db()
    accounts = database.get_all_accounts()
    
    # Lọc ra các tài khoản chưa có gói cước
    accounts_to_check = [acc for acc in accounts if not acc[5]]
    
    if not accounts_to_check:
        flash("Tất cả tài khoản trong kho đều đã có Gói Cước. Không cần chạy cập nhật thêm.", "warning")
        return redirect(url_for("admin"))
        
    import threading
    t = threading.Thread(target=background_check_all)
    t.daemon = True
    t.start()
    
    estimated_time = len(accounts_to_check) * 2
    flash(f"🔄 Đang cập nhật ngầm cho {len(accounts_to_check)} tài khoản chưa có Gói Cước (khoảng {estimated_time}s). Các cookie DIE sẽ tự xóa.", "warning")
    return redirect(url_for("admin"))


def background_force_check_all():
    with app.app_context():
        database.init_db()
        accounts = database.get_all_accounts()
        for acc in accounts:
            email = acc[0]
            netflix_id = acc[2]
            secure_netflix_id = acc[3]
            status, plan = checker.check_account_live(netflix_id, secure_netflix_id)
            if status == "LIVE" and plan:
                database.update_plan(email, plan)
            elif status == "DIE":
                database.delete_account(email)

@app.route("/force_check_all", methods=["POST"])
@login_required
def force_check_all():
    database.init_db()
    accounts = database.get_all_accounts()
    
    if not accounts:
        flash("Kho không có tài khoản nào để quét.", "warning")
        return redirect(url_for("admin"))
        
    import threading
    t = threading.Thread(target=background_force_check_all)
    t.daemon = True
    t.start()
    
    estimated_time = len(accounts) * 2
    flash(f"🔥 Đang ÉP quét ngầm TOÀN BỘ {len(accounts)} tài khoản trong kho (khoảng {estimated_time}s). Quá trình này sẽ ngốn khá nhiều Proxy.", "warning")
    return redirect(url_for("admin"))



# Constants for Netflix API
NETFLIX_API_URL = "https://ios.prod.ftl.netflix.com/iosui/user/15.48"
NETFLIX_QUERY_PARAMS = {
    "appVersion": "15.48.1",
    "config": '{"gamesInTrailersEnabled":"false","isTrailersEvidenceEnabled":"false","cdsMyListSortEnabled":"true","kidsBillboardEnabled":"true","addHorizontalBoxArtToVideoSummariesEnabled":"false","skOverlayTestEnabled":"false","homeFeedTestTVMovieListsEnabled":"false","baselineOnIpadEnabled":"true","trailersVideoIdLoggingFixEnabled":"true","postPlayPreviewsEnabled":"false","bypassContextualAssetsEnabled":"false","roarEnabled":"false","useSeason1AltLabelEnabled":"false","disableCDSSearchPaginationSectionKinds":["searchVideoCarousel"],"cdsSearchHorizontalPaginationEnabled":"true","searchPreQueryGamesEnabled":"true","kidsMyListEnabled":"true","billboardEnabled":"true","useCDSGalleryEnabled":"true","contentWarningEnabled":"true","videosInPopularGamesEnabled":"true","avifFormatEnabled":"false","sharksEnabled":"true"}',
    "device_type": "NFAPPL-02-",
    "esn": "NFAPPL-02-IPHONE8%3D1-PXA-02026U9VV5O8AUKEAEO8PUJETCGDD4PQRI9DEB3MDLEMD0EACM4CS78LMD334MN3MQ3NMJ8SU9O9MVGS6BJCURM1PH1MUTGDPF4S4200",
    "idiom": "phone",
    "iosVersion": "15.8.5",
    "isTablet": "false",
    "languages": "en-US",
    "locale": "en-US",
    "maxDeviceWidth": "375",
    "model": "saget",
    "modelType": "IPHONE8-1",
    "odpAware": "true",
    "path": '["account","token","default"]',
    "pathFormat": "graph",
    "pixelDensity": "2.0",
    "progressive": "false",
    "responseFormat": "json",
}
NETFLIX_BASE_HEADERS = {
    "User-Agent": "Argo/15.48.1 (iPhone; iOS 15.8.5; Scale/2.00)",
    "x-netflix.request.attempt": "1",
    "x-netflix.request.client.user.guid": "A4CS633D7VCBPE2GPK2HL4EKOE",
    "x-netflix.context.profile-guid": "A4CS633D7VCBPE2GPK2HL4EKOE",
    "x-netflix.request.routing": '{"path":"/nq/mobile/nqios/~15.48.0/user","control_tag":"iosui_argo"}',
    "x-netflix.context.app-version": "15.48.1",
    "x-netflix.argo.translated": "true",
    "x-netflix.context.form-factor": "phone",
    "x-netflix.context.sdk-version": "2012.4",
    "x-netflix.client.appversion": "15.48.1",
    "x-netflix.context.max-device-width": "375",
    "x-netflix.tracing.cl.useractionid": "4DC655F2-9C3C-4343-8229-CA1B003C3053",
    "x-netflix.client.type": "argo",
    "x-netflix.client.ftl.esn": "NFAPPL-02-IPHONE8=1-PXA-02026U9VV5O8AUKEAEO8PUJETCGDD4PQRI9DEB3MDLEMD0EACM4CS78LMD334MN3MQ3NMJ8SU9O9MVGS6BJCURM1PH1MUTGDPF4S4200",
    "x-netflix.context.locales": "en-US",
    "x-netflix.context.top-level-uuid": "90AFE39F-ADF1-4D8A-B33E-528730990FE3",
    "x-netflix.client.iosversion": "15.8.5",
    "accept-language": "en-US;q=1",
    "x-netflix.context.os-version": "15.8.5",
    "x-netflix.request.client.context": '{"appState":"foreground"}',
    "x-netflix.context.ui-flavor": "argo",
    "x-netflix.argo.nfnsm": "9",
    "x-netflix.context.pixel-density": "2.0",
    "x-netflix.request.toplevel.uuid": "90AFE39F-ADF1-4D8A-B33E-528730990FE3",
    "x-netflix.request.client.timezoneid": "Asia/Dhaka",
}

class ProxyError(Exception): pass
class CookieError(Exception): pass

import proxies_list

def fetch_netflix_nftoken_api(netflix_id):
    headers = dict(NETFLIX_BASE_HEADERS)
    headers["Cookie"] = f"NetflixId={netflix_id}"
    
    proxy_dict = proxies_list.get_random_proxy()
    
    try:
        response = requests.get(
            NETFLIX_API_URL, params=NETFLIX_QUERY_PARAMS, headers=headers,
            proxies=proxy_dict, timeout=15, verify=False
        )
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.ProxyError) as e:
        print(f"Lỗi Proxy / Mạng: {e}")
        raise ProxyError("Không thể kết nối qua Proxy")
        
    if response.status_code in [403, 429]:
        raise ProxyError("Proxy bị Netflix block (403/429)")
        
    response.raise_for_status()
    data = response.json()
    token_data = ((((data.get("value") or {}).get("account") or {}).get("token") or {}).get("default") or {})
    token = token_data.get("token")
    if not token:
        raise CookieError("Netflix API không trả về token. Cookie có thể đã DIE.")
    return token

@app.route("/api/generate_nftoken", methods=["POST"])
def api_generate_nftoken():
    try:
        data = request.get_json(silent=True) or {}
        cookie_value = data.get("cookie", "").strip()
        if not cookie_value:
            return jsonify({"success": False, "error": "Vui lòng nhập Mã Truy Cập"}), 400
            
        database.init_db()
        
        # Import checker for realtime check
        import checker
        
        # 1. Lookup as access key (6 characters)
        acc_key_row = database.get_access_key(cookie_value)
    
        if acc_key_row:
            code = acc_key_row[0]
            assigned_email = acc_key_row[1]
            
            # Auto-rotation loop
            max_attempts = 5
            for attempt in range(max_attempts):
                acc = database.get_account_by_email(assigned_email)
                
                if not acc:
                    rotated = database.rotate_access_key(code)
                    if not rotated:
                        return jsonify({"success": False, "error": "Hệ thống đã hết Cookie dự phòng!"}), 500
                    assigned_email = database.get_access_key(code)[1]
                    continue
                    
                netflix_id = urllib.parse.unquote(acc[2])
                secure_netflix_id = urllib.parse.unquote(acc[3]) if acc[3] else ""
                
                try:
                    # --- [MỚI] KIỂM TRA REALTIME TRƯỚC KHI XUẤT LINK ---
                    print(f"Bắt đầu Check Realtime cho tài khoản: {assigned_email}")
                    live_status, live_plan = checker.check_account_live(netflix_id, secure_netflix_id)
                    
                    if live_status == "DIE":
                        # Cookie dính Update Payment hoặc bị văng -> Ném lỗi ra để nó chạy vòng lặp đổi acc mới (Rotation)
                        raise Exception("Cookie dính Update Payment hoặc đã chết (Real-time check failed)")
                    elif live_status == "ERROR":
                        # Lỗi mạng / Proxy trong lúc check live, văng ra để thử lại bằng Proxy khác
                        raise ProxyError("Lỗi Proxy trong quá trình Check Real-time")
                    
                    # Vượt qua bài kiểm tra "Mắt thần" -> Tiếp tục lấy Link
                    token = fetch_netflix_nftoken_api(netflix_id)
                    pc_link = f"https://www.netflix.com/login?nftoken={token}"
                    mobile_link = f"https://www.netflix.com/unsupported?nftoken={token}"
                    tv_link = f"https://www.netflix.com/tv8?nftoken={token}"
                    return jsonify({
                        "success": True,
                        "pc_link": pc_link,
                        "mobile_link": mobile_link,
                        "tv_link": tv_link
                    })
                except ProxyError as e:
                    # Lỗi proxy, ta giữ nguyên Cookie và thử lại ngay lập tức (không rotate Cookie)
                    print(f"Lỗi Proxy ({e}), thử lại...")
                    continue
                except Exception as e:
                    # Các lỗi khác (hoặc CookieError) -> Cookie is dead, delete it and rotate
                    print(f"Cookie {assigned_email} DIE, attempting rotation... (Lỗi: {e})")
                    database.delete_account(assigned_email)
                    rotated = database.rotate_access_key(code)
                    if not rotated:
                        return jsonify({"success": False, "error": "Cookie hỏng và hệ thống đã hết Cookie dự phòng!"}), 500
                    assigned_email = database.get_access_key(code)[1]
                    
            return jsonify({"success": False, "error": "Quá tải máy chủ hoặc toàn bộ Proxy chết. Vui lòng thử lại sau."}), 500

        # 2. Fallback: Parse raw tokens for admin testing
        netflix_id = None
        unquoted_cookie = urllib.parse.unquote(cookie_value)
        is_already_token = unquoted_cookie.startswith("B")
        
        if is_already_token:
            token = cookie_value 
            pc_link = f"https://www.netflix.com/login?nftoken={token}"
            mobile_link = f"https://www.netflix.com/unsupported?nftoken={token}"
            tv_link = f"https://www.netflix.com/tv8?nftoken={token}"
            return jsonify({"success": True, "pc_link": pc_link, "mobile_link": mobile_link, "tv_link": tv_link})
        
        if "NetflixId=" in cookie_value:
            match = re.search(r'NetflixId\s*=\s*([^;]+)', cookie_value)
            if match:
                netflix_id = match.group(1).strip()
        elif ".netflix.com" in cookie_value:
            for line in cookie_value.splitlines():
                parts = line.split("\t")
                if len(parts) >= 7 and parts[5].strip() == "NetflixId":
                    netflix_id = parts[6].strip()
                    break
        else:
            netflix_id = cookie_value.replace('"', '').replace("'", "").strip()
            
        if not netflix_id:
            netflix_id = cookie_value
            
        netflix_id = urllib.parse.unquote(netflix_id)
        
        try:
            token = fetch_netflix_nftoken_api(netflix_id)
            pc_link = f"https://www.netflix.com/login?nftoken={token}"
            mobile_link = f"https://www.netflix.com/unsupported?nftoken={token}"
            tv_link = f"https://www.netflix.com/tv8?nftoken={token}"
            return jsonify({"success": True, "pc_link": pc_link, "mobile_link": mobile_link, "tv_link": tv_link})
        except ProxyError as e:
            return jsonify({"success": False, "error": f"Lỗi Proxy. Vui lòng bấm thử lại. Chi tiết: {str(e)}"}), 500
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500
            
    except Exception as api_e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": f"Lỗi hệ thống không xác định: {str(api_e)}"}), 500

if __name__ == "__main__":
    print("🚀 Web interface is running!")
    print("👉 Please open your browser and go to: http://127.0.0.1:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
