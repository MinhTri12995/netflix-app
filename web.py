import os
import sys
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

ADMIN_EMAIL = "concumm2@gmail.com"
ADMIN_PASS = "Nmtyeunnqt1!"

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
        function copyCookie(text, btnElement) {
            navigator.clipboard.writeText(text).then(function() {
                let originalText = btnElement.innerText;
                btnElement.innerText = "Copied!";
                btnElement.style.background = "#27ae60";
                setTimeout(function() {
                    btnElement.innerText = originalText;
                    btnElement.style.background = "rgba(255, 255, 255, 0.2)";
                }, 2000);
            });
        }

        function generateQuickLinks() {

            var rawInput = document.getElementById("rawTokenInput").value.trim();
            if (!rawInput) {
                alert("Please enter a Cookie or Access Code!");
                return;
            }

            var resultDiv = document.getElementById("quickLinksResult");
            var pcLink = document.getElementById("quickPcLink");
            var mobileLink = document.getElementById("quickMobileLink");
            var tvLink = document.getElementById("quickTvLink");
            var statusText = document.getElementById("statusText");
            var btn = document.getElementById("submitBtn");
            var infoBadge = document.getElementById("accountInfoBadge");
            var badgePlan = document.getElementById("badgePlan");
            var badgeExpire = document.getElementById("badgeExpire");

            infoBadge.style.display = "none";
            btn.disabled = true;
            btn.innerHTML = "⏳ Connecting...";
            
            pcLink.innerText = "⏳ Generating link...";
            mobileLink.innerText = "⏳ Generating link...";
            tvLink.innerText = "⏳ Generating link...";
            statusText.innerText = "Generating high-speed link...";
            
            resultDiv.style.display = "flex";
            
            // If user enters code or raw cookie, call API to generate links
            fetch("/api/generate_nftoken", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ cookie: rawInput })
            })
            .then(res => res.json())
            .then(data => {
                btn.disabled = false;
                btn.innerHTML = "🚀 LOGIN NOW (Fast Link)";
                if (data.success) {
                    if (data.plan || data.expire_date) {
                        badgePlan.innerText = "📦 Plan: " + (data.plan || "N/A");
                        badgeExpire.innerText = "📅 Expire Date: " + (data.expire_date || "N/A");
                        infoBadge.style.display = "block";
                    }
                    if (data.is_json) {
                        pcLink.removeAttribute("href");
                        pcLink.removeAttribute("target");
                        pcLink.onclick = function(e) { e.preventDefault(); copyCookie(data.cookie_json, this); };
                        pcLink.innerText = "📋 Copy Cookie (API Failed)";
                        pcLink.style.background = "#2d98da";
                        
                        mobileLink.style.display = "none";
                        tvLink.style.display = "none";
                        
                        statusText.innerText = "Login API unavailable. Please use the Cookie Extension:";
                        statusText.style.color = "#f39c12";
                    } else {
                        pcLink.href = data.pc_link;
                        mobileLink.href = data.mobile_link;
                        tvLink.href = data.tv_link;
                        
                        pcLink.setAttribute("target", "_blank");
                        pcLink.onclick = function() { showLoading(this); };
                        pcLink.style.background = "";
                        
                        pcLink.innerText = "💻 PC / Laptop";
                        mobileLink.innerText = "📱 Mobile (iPhone / Android)";
                        tvLink.innerText = "📺 Smart TV";
                        
                        mobileLink.style.display = "flex";
                        tvLink.style.display = "flex";
                        
                        statusText.innerText = "Success! Please select your device below:";
                        statusText.style.color = "#2ecc71";
                    }
                } else {
                    statusText.innerText = "Error: " + (data.error || "Failed to generate link.");
                    statusText.style.color = "#e74c3c";
                    pcLink.innerText = "❌ Error";
                    mobileLink.innerText = "❌ Error";
                    tvLink.innerText = "❌ Error";
                }
            })
            .catch(err => {
                btn.disabled = false;
                btn.innerHTML = "🚀 LOGIN NOW (Fast Link)";
                statusText.innerText = "Connection to server failed!";
                statusText.style.color = "#e74c3c";
                pcLink.innerText = "❌ Error";
                mobileLink.innerText = "❌ Error";
                tvLink.innerText = "❌ Error";
            });
        }
        
        function openReportModal() {
            let rawInput = document.getElementById("rawTokenInput").value.trim();
            if (!rawInput) {
                alert("Please enter your access code first!");
                return;
            }
            document.getElementById("reportModal").style.display = "flex";
        }
        
        function closeReportModal() {
            document.getElementById("reportModal").style.display = "none";
            document.getElementById("reportForm").reset();
            document.getElementById("reportStatus").innerText = "";
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
                btn.innerHTML = "Submit Report";
                if (data.success) {
                    statusText.innerText = data.message || "Report submitted successfully! The account has been updated.";
                    statusText.style.color = "#2ecc71";
                    setTimeout(closeReportModal, 4000);
                } else {
                    statusText.innerText = "Error: " + data.error;
                    statusText.style.color = "#e74c3c";
                }
            })
            .catch(err => {
                btn.disabled = false;
                btn.innerHTML = "Submit Report";
                statusText.innerText = "Connection error while uploading!";
                statusText.style.color = "#e74c3c";
            });
        }
    </script>
    <style>
        .modal {
            display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%;
            background-color: rgba(0,0,0,0.7); justify-content: center; align-items: center;
        }
        .modal-content {
            background: #222; padding: 20px; border-radius: 8px; width: 90%; max-width: 400px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.5); border: 1px solid #444;
        }
        .close-btn { color: #aaa; float: right; font-size: 28px; font-weight: bold; cursor: pointer; }
        .close-btn:hover { color: white; }
    </style>
</head>
<body>
    <div class="container" style="max-width: 600px; margin-top: 10vh;">
        <div class="header">
            <h1>Netflix Access</h1>
            <p>Automated Fast Login System</p>
        </div>
        <div class="glass-panel">
            <h3 style="margin-top: 0; text-align: center; font-weight: 400;">Enter Access Code</h3>
            <input type="text" id="rawTokenInput" class="search-box" style="text-align: center; font-size: 1.2rem; letter-spacing: 2px;" placeholder="Example: X9K2M1">
            <button id="submitBtn" onclick="generateQuickLinks()" style="width: 100%; margin-top: 10px; padding: 15px; font-size: 1.1rem; background: #27ae60; color: white; border: none; border-radius: 4px; font-weight: bold; cursor: pointer;">🚀 LOGIN NOW (Fast Link)</button>
            <button id="reportBtn" onclick="openReportModal()" style="width: 100%; margin-top: 10px; padding: 12px; font-size: 0.9rem; background: #c0392b; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: bold;">⚠️ REPORT ERROR</button>
            
            <div id="quickLinksResult" style="display: flex; flex-direction: column; gap: 15px; margin-top: 25px; display: none;">
                <div id="accountInfoBadge" style="display: none; background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 8px; padding: 12px 15px; text-align: center; font-size: 0.95rem;">
                    <span id="badgePlan" style="color: #f1c40f; font-weight: bold; margin-right: 20px;">📦 Plan: ---</span>
                    <span id="badgeExpire" style="color: #3498db; font-weight: bold;">📅 Expire Date: ---</span>
                </div>
                <p id="statusText" style="text-align: center; margin: 0; font-weight: bold;"></p>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">
                    <a id="quickPcLink" class="btn-login" href="#" target="_blank" onclick="showLoading(this)" style="padding: 15px !important; text-align: center; font-size: 1rem !important; display: flex; align-items: center; justify-content: center; gap: 8px;">
                        💻 PC / Laptop
                    </a>
                    <a id="quickMobileLink" class="btn-login" href="#" target="_blank" onclick="showLoading(this)" style="padding: 15px !important; text-align: center; font-size: 1rem !important; display: flex; align-items: center; justify-content: center; gap: 8px;">
                        📱 Mobile (iPhone / Android)
                    </a>
                    <a id="quickTvLink" class="btn-login" href="#" target="_blank" onclick="showLoading(this)" style="padding: 15px !important; text-align: center; font-size: 1rem !important; display: flex; align-items: center; justify-content: center; gap: 8px;">
                        📺 Smart TV
                    </a>
                </div>
            </div>
        </div>
        <div style="text-align: center; margin-top: 20px;">
            <a href="/admin" style="color: #666; font-size: 0.8rem; text-decoration: none;">Admin Dashboard</a>
        </div>
    </div>
    
    <div id="reportModal" class="modal">
        <div class="modal-content">
            <span class="close-btn" onclick="closeReportModal()">&times;</span>
            <h3 style="margin-top: 0; margin-bottom: 20px;">Report Dead Account</h3>
            <form id="reportForm" onsubmit="submitReport(event)">
                <p style="margin-top: 0; font-size: 0.9rem; color: #ddd;">Please upload a screenshot of the error. The admin will review it and change your account.</p>
                <input type="file" id="reportImage" accept="image/*" required style="width: 100%; padding: 10px; margin-bottom: 15px; background: rgba(0,0,0,0.2); border: 1px dashed #555; color: #ccc;">
                <button type="submit" id="submitReportBtn" style="width: 100%; background: #c0392b; font-weight: bold; border: none; padding: 12px; color: white; border-radius: 4px; cursor: pointer;">Submit Report</button>
            </form>
            <p id="reportStatus" style="text-align: center; font-weight: bold; margin-top: 15px; margin-bottom: 0;"></p>
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
            
            // 1. Lọc và Đọc File Cục Bộ (Client-side)
            for (let i = 0; i < fileInput.files.length; i++) {
                const file = fileInput.files[i];
                if (file.name.endsWith('.txt')) {
                    try {
                        const text = await file.text();
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
                                    if (n_id) current_netflix_id = decodeURIComponent(n_id[1].trim());
                                    if (s_n_id) current_secure_netflix_id = decodeURIComponent(s_n_id[1].trim());
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
                            if (id_match) { current_netflix_id = id_match[1].trim(); continue; }
                            
                            let sid_match = line.match(/^(?:–|-|#)?\s*SecureNetflixId:\s*(.+)/i);
                            if (sid_match) { current_secure_netflix_id = sid_match[1].trim(); continue; }
                            
                            if (line.startsWith("# ===")) {
                                push_account();
                                continue;
                            }

                            if (line.includes('.netflix.com')) {
                                let parts = line.trim().split(/\s+/);
                                if (parts.length >= 3) {
                                    let c_name = parts[parts.length - 2];
                                    let c_val = decodeURIComponent(parts[parts.length - 1]);
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
                <input type="email" name="email" class="search-box" placeholder="Email" required style="margin-bottom: 0;">
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
@login_required
def check_and_import():
    data = request.json
    netflix_id = data.get("netflix_id")
    secure_netflix_id = data.get("secure_netflix_id", "")
    email = data.get("email", "")
    expire = data.get("expire", "")
    plan = data.get("plan", "")
    
    if not netflix_id:
        return jsonify({"success": False, "error": "Missing NetflixId"})
        
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
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        if email == ADMIN_EMAIL and password == ADMIN_PASS:
            session['logged_in'] = True
            return redirect(url_for("admin"))
        else:
            flash("Incorrect email or password!", "error")
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
    
    import proxies_list
    current_proxy = proxies_list.SINGLE_ROTATING_PROXY.split('@')[-1] if '@' in proxies_list.SINGLE_ROTATING_PROXY else proxies_list.SINGLE_ROTATING_PROXY
    
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
    
    for acc in accounts:
        email = acc[0]
        netflix_id = acc[2]
        plan = acc[5]
        
        if not netflix_id:
            continue
            
        if netflix_id in seen_netflix_ids:
            # Nếu acc hiện tại CÓ plan mà acc trước đó KHÔNG có, ta xóa acc trước đó và giữ acc hiện tại
            existing_email = seen_netflix_ids[netflix_id]['email']
            existing_plan = seen_netflix_ids[netflix_id]['plan']
            
            if plan and not existing_plan:
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
            proxies=proxy_dict, timeout=5, verify=False
        )
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.ProxyError) as e:
        print(f"Lỗi Proxy / Mạng: {e}")
        raise ProxyError("Không thể kết nối qua Proxy")
        
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
        
    # Anti-spam check removed as requested by user
    # if database.has_recent_request(code):
    #     return jsonify({"success": False, "error": "Please try again after 5 minutes."}), 429
        
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
    if not date_str or date_str in ['N/A', 'None']:
        return False
    
    clean_str = date_str.strip()
    
    # 1. ISO format YYYY-MM-DD
    iso_match = re.search(r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})', clean_str)
    if iso_match:
        try:
            dt = datetime(int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3)))
            return dt.date() < datetime.now().date()
        except Exception:
            pass

    # 2. Month name parsing (English, Polish, Spanish, etc.)
    months = {
        'january': 1, 'styczeń': 1, 'stycznia': 1, 'jan': 1, 'enero': 1,
        'february': 2, 'luty': 2, 'lutego': 2, 'feb': 2, 'febrero': 2,
        'march': 3, 'marzec': 3, 'marca': 3, 'mar': 3, 'marzo': 3,
        'april': 4, 'kwiecień': 4, 'kwietnia': 4, 'apr': 4, 'abril': 4,
        'may': 5, 'maj': 5, 'maja': 5, 'mayo': 5,
        'june': 6, 'czerwiec': 6, 'czerwca': 6, 'jun': 6, 'junio': 6,
        'july': 7, 'lipiec': 7, 'lipca': 7, 'jul': 7, 'julio': 7,
        'august': 8, 'sierpień': 8, 'sierpnia': 8, 'agustus': 8, 'aug': 8, 'agosto': 8,
        'september': 9, 'wrzesień': 9, 'września': 9, 'sep': 9, 'septiembre': 9, 'setiembre': 9,
        'october': 10, 'październik': 10, 'października': 10, 'oct': 10, 'octubre': 10,
        'november': 11, 'listopad': 11, 'listopada': 11, 'nov': 11, 'noviembre': 11,
        'december': 12, 'grudzień': 12, 'grudnia': 12, 'dec': 12, 'diciembre': 12
    }

    words = re.findall(r'[a-zA-Záéíóúñąćęłńóśźż]+|\d+', clean_str.lower())
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

    if year and month and day:
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
        html = r.text
        
        plan = None
        plan_m = re.search(r'(?:localizedPlanName|planName)"\s*:\s*\{"fieldType":"String","value":"([^"]+)"\}', html)
        if plan_m:
            plan = plan_m.group(1).replace(r'\x20', ' ').strip()
        else:
            text_lower = html.lower()
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
        
        # 1. Lookup as access key (6 characters)
        acc_key_row = database.get_access_key(cookie_value)
    
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
            max_attempts = 5
            last_error_msg = ""
            for attempt in range(max_attempts):
                acc = database.get_account_by_email(assigned_email)
                
                if not acc:
                    rotated = database.rotate_access_key(code)
                    if not rotated:
                        return jsonify({"success": False, "error": "System ran out of backup Cookies!"}), 500
                    assigned_email = database.get_access_key(code)[1]
                    continue
                    
                netflix_id = acc[2]
                secure_netflix_id = acc[3] if acc[3] else ""
                
                try:
                    token = fetch_netflix_nftoken_api(netflix_id, secure_netflix_id)
                    is_json = token.startswith("FALLBACK:")
                    cookie_json = urllib.parse.unquote(token[9:]) if is_json else ""
                    
                    pc_link = f"https://www.netflix.com/login?nftoken={token}"
                    mobile_link = f"https://www.netflix.com/unsupported?nftoken={token}"
                    tv_link = f"https://www.netflix.com/tv8?nftoken={token}"
                    
                    # Realtime account info check for real plan and next billing date
                    rt_plan, rt_expire = fetch_realtime_account_info(netflix_id, secure_netflix_id)
                    
                    # If date is in the past, account is EXPIRED -> auto delete & rotate
                    acc_expire_check = rt_expire if rt_expire else acc[1]
                    if is_date_expired(acc_expire_check):
                        raise CookieError(f"Account next billing date ({acc_expire_check}) is in the past (Expired).")

                    if rt_plan:
                        database.update_plan(assigned_email, rt_plan)
                        acc_plan = rt_plan
                    else:
                        acc_plan = acc[5] if (acc and len(acc) > 5 and acc[5]) else "Premium"
                        
                    acc_expire = rt_expire if rt_expire else (acc[1] if (acc and len(acc) > 1 and acc[1]) else (expire_at_str if expire_at_str else "N/A"))

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

                    # Plan mismatch check & auto-rotation
                    plan_check_str = str(acc_plan).lower()
                    is_ads = any(kw in plan_check_str for kw in ['ads', 'adverts', 'anuncios', 'pub', 'werbung', 'quảng cáo', 'โฆษณา', '広告', '광고', 'рекламо', 'reklam', 'rek'])
                    
                    should_rotate_mismatch = False
                    if expected_plan == "Premium":
                        if (is_ads or "standard" in plan_check_str or "basic" in plan_check_str) and not ("premium" in plan_check_str or "ultra" in plan_check_str):
                            should_rotate_mismatch = True
                    elif expected_plan == "Standard":
                        if is_ads or "basic" in plan_check_str:
                            should_rotate_mismatch = True

                    if should_rotate_mismatch:
                        print(f"Plan mismatch for code {code}: account {assigned_email} has real plan '{acc_plan}', expected '{expected_plan}'. Auto-rotating to matching account...")
                        rotated = database.rotate_access_key(code)
                        if rotated:
                            assigned_email = database.get_access_key(code)[1]
                            last_error_msg = f"Plan mismatch: {acc_plan} vs {expected_plan}"
                            continue # Retry loop to fetch link for newly assigned matching account!

                    return jsonify({
                        "success": True,
                        "pc_link": pc_link,
                        "mobile_link": mobile_link,
                        "tv_link": tv_link,
                        "is_json": is_json,
                        "cookie_json": cookie_json,
                        "plan": acc_plan,
                        "expire_date": acc_expire
                    })
                except ProxyError as e:
                    last_error_msg = f"Proxy error: {str(e)}"
                    print(f"Proxy error ({e}), retrying...")
                    continue
                except CookieError as e:
                    last_error_msg = f"Cookie died: {str(e)}"
                    print(f"Cookie {assigned_email} DIE, attempting rotation... (Error: {e})")
                    database.delete_account(assigned_email)
                    rotated = database.rotate_access_key(code)
                    if not rotated:
                        return jsonify({"success": False, "error": f"Cookie is broken and system ran out of backup Cookies! Last error: {str(e)}"}), 500
                    assigned_email = database.get_access_key(code)[1]
                    continue
                except Exception as e:
                    last_error_msg = f"Unknown error: {str(e)}"
                    print(f"Lỗi không xác định với tài khoản {assigned_email}: {e}")
                    # Không xóa tài khoản nếu gặp lỗi không xác định (vd: JSONDecodeError do proxy trả HTML)
                    continue
                    
            return jsonify({"success": False, "error": f"Failed to generate link after {max_attempts} attempts. Last error: {last_error_msg}"}), 500

        # If not an access key and length <= 20
        if len(cookie_value) <= 20 and not cookie_value.startswith("B") and not cookie_value.startswith("FALLBACK:"):
            return register_fail("Mã truy cập không hợp lệ hoặc không tồn tại.")

        # 2. Fallback: Parse raw tokens
        netflix_id = None
        secure_netflix_id = ""
        
        unquoted_cookie = urllib.parse.unquote(cookie_value)
        is_already_token = unquoted_cookie.startswith("B") or unquoted_cookie.startswith("FALLBACK:")
        
        if is_already_token:
            token = cookie_value 
            pc_link = f"https://www.netflix.com/login?nftoken={token}"
            mobile_link = f"https://www.netflix.com/unsupported?nftoken={token}"
            tv_link = f"https://www.netflix.com/tv8?nftoken={token}"
            return jsonify({
                "success": True, 
                "pc_link": pc_link, 
                "mobile_link": mobile_link, 
                "tv_link": tv_link,
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
            rt_plan, rt_expire = fetch_realtime_account_info(netflix_id, secure_netflix_id)
            final_plan = rt_plan if rt_plan else (parsed_plan if parsed_plan else "Premium")
            final_expire = rt_expire if rt_expire else (parsed_expire if parsed_expire else "N/A")

            pc_link = f"https://www.netflix.com/login?nftoken={token}"
            mobile_link = f"https://www.netflix.com/unsupported?nftoken={token}"
            tv_link = f"https://www.netflix.com/tv8?nftoken={token}"
            
            return jsonify({
                "success": True,
                "pc_link": pc_link,
                "mobile_link": mobile_link,
                "tv_link": tv_link,
                "is_json": is_json,
                "cookie_json": cookie_json,
                "plan": final_plan,
                "expire_date": final_expire
            })
        except Exception as e:
            return jsonify({"success": False, "error": f"Token generation error: {str(e)}"}), 500
        except Exception as e:
            return register_fail(f"Invalid token: {str(e)}", 500)
            
    except Exception as api_e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": f"Unknown system error: {str(api_e)}"}), 500

if __name__ == "__main__":
    print("🚀 Web interface is running!")
    print("👉 Please open your browser and go to: http://127.0.0.1:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
