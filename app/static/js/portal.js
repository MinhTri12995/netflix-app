/**
 * Netflix Access Member Activation Portal Client Logic
 * Handles i18n, accessible modal interactions, idempotency, and stream activation.
 */

const PORTAL_I18N = {
    en: {
        brand: "Netflix Access Portal",
        badgeActiveSession: "Dedicated Session Security",
        heroTitle: "Instant Member Activation",
        heroSubtitle: "Enter your order Access Code to activate and launch your Netflix session directly without entering account credentials.",
        step1Title: "Direct Network",
        step1Desc: "Disable VPN services. Standard broadband or 4G/5G mobile connection required.",
        step2Title: "Input Code",
        step2Desc: "Paste your unique Access Code from your order confirmation below.",
        step3Title: "Select Device",
        step3Desc: "Choose between PC Browser, Smartphone, or Smart TV authorization.",
        step4Title: "Stream & Enjoy",
        step4Desc: "Session opens automatically. Select your designated profile to watch.",
        labelAccessCode: "Access Code",
        codeLengthHint: "Min 15 characters",
        btnActivateText: "Activate & Launch Stream",
        btnReportText: "Report Issue",
        verifyingText: "Verifying & Connecting...",
        planLabel: "Plan",
        validUntilLabel: "Valid until",
        copyCookieBtn: "Copy JSON Cookie",
        copiedCookieText: "Cookie JSON copied to clipboard!",
        openPc: "Open on PC →",
        openMobile: "Open on Mobile →",
        pairTv: "Pair TV Screen →",
        viewAccount: "View Account →",
        modalTitle: "Submit Replacement Request",
        modalDesc: "Provide your order details and error screenshot. Screen limit issues are verified and replaced automatically 24/7 by AI.",
        labelOrder: "U7BUY Order ID / Purchase ID",
        labelCode: "Access Code",
        labelReason: "Reason / Issue Category",
        reasonScreen: "⚡ Too many people using screen / Screen limit",
        reasonPayment: "💳 Payment error / Membership on hold (Admin review)",
        reasonOther: "📝 Other reason / Different error (Manual review)",
        labelNote: "Additional Note (Optional)",
        labelProof: "Screenshot Proof of Error",
        btnSubmitReport: "Submit for Verification",
        submittingText: "Analyzing with AI Vision...",
        enterCodeFirst: "Please enter your Access Code first.",
        attachProofFirst: "Please attach a screenshot of the error.",
        sessionSuccess: "Session authorization successful! Select your device below.",
        activationFailed: "Activation failed. Please check your access code.",
        connectionError: "Connection error. Please try again.",
        reqQueued: "Request queued for admin verification.",
        reqAutoReplaced: "Error verified! A new active session has been assigned."
    },
    vi: {
        brand: "Cổng Kích Hoạt Netflix",
        badgeActiveSession: "Bảo Mật Phiên Riêng Biệt",
        heroTitle: "Kích Hoạt Tài Khoản Thành Viên",
        heroSubtitle: "Nhập mã Access Code từ đơn hàng để kích hoạt phiên xem phim Netflix tức thì mà không cần nhập mật khẩu.",
        step1Title: "Kết nối trực tiếp",
        step1Desc: "Tắt VPN. Sử dụng mạng Internet thông thường hoặc mạng 4G/5G.",
        step2Title: "Nhập mã Code",
        step2Desc: "Dán mã Access Code nhận được trong đơn hàng U7BUY của bạn.",
        step3Title: "Chọn thiết bị",
        step3Desc: "Lựa chọn xem trên Máy tính, Điện thoại hoặc Tivi thông minh.",
        step4Title: "Bắt đầu xem",
        step4Desc: "Hệ thống tự động đăng nhập. Chọn hồ sơ của bạn để thưởng thức.",
        labelAccessCode: "Mã Access Code",
        codeLengthHint: "Tối thiểu 15 ký tự",
        btnActivateText: "Kích Hoạt & Mở Phim",
        btnReportText: "Báo Lỗi & Bảo Hành",
        verifyingText: "Đang xác thực & kết nối...",
        planLabel: "Gói",
        validUntilLabel: "Hạn dùng",
        copyCookieBtn: "Sao chép Cookie JSON",
        copiedCookieText: "Đã sao chép Cookie vào bộ nhớ tạm!",
        openPc: "Mở trên Máy Tính →",
        openMobile: "Mở trên Điện Thoại →",
        pairTv: "Kết nối Smart TV →",
        viewAccount: "Xem Tài Khoản →",
        modalTitle: "Gửi Yêu Cầu Đổi / Bảo Hành",
        modalDesc: "Cung cấp mã đơn hàng và ảnh chụp màn hình lỗi. Lỗi quá màn hình sẽ được AI kiểm tra và đổi tự động 24/7.",
        labelOrder: "Mã đơn hàng U7BUY (Purchase ID)",
        labelCode: "Mã Access Code",
        labelReason: "Loại lỗi gặp phải",
        reasonScreen: "⚡ Quá số màn hình xem cùng lúc (Tự đổi tức thì)",
        reasonPayment: "💳 Lỗi thanh toán / nợ cước (Admin duyệt)",
        reasonOther: "📝 Lỗi khác / Lý do khác (Duyệt thủ công)",
        labelNote: "Ghi chú thêm (Tùy chọn)",
        labelProof: "Ảnh chụp màn hình thông báo lỗi",
        btnSubmitReport: "Gửi Yêu Cầu Xác Thực",
        submittingText: "Đang phân tích ảnh qua AI...",
        enterCodeFirst: "Vui lòng nhập mã Access Code trước.",
        attachProofFirst: "Vui lòng đính kèm ảnh chụp màn hình lỗi.",
        sessionSuccess: "Cấp quyền phiên thành công! Chọn thiết bị bên dưới.",
        activationFailed: "Kích hoạt thất bại. Vui lòng kiểm tra lại mã code.",
        connectionError: "Lỗi kết nối. Vui lòng thử lại.",
        reqQueued: "Yêu cầu đã được tiếp nhận và đưa vào hàng chờ kiểm tra.",
        reqAutoReplaced: "Xác thực lỗi thành công! Đã cấp tài khoản mới thay thế."
    }
};

let currentLang = "en";
let currentCookieJson = "";
let lastFocusedElement = null;
let currentOperationId = "";

function generateClientOperationId() {
    return 'req_' + Date.now() + '_' + Math.random().toString(36).substring(2, 9);
}

function initLanguage() {
    const saved = localStorage.getItem('portal_preferred_lang') || 'en';
    setLanguage(saved);
}

function setLanguage(lang) {
    if (!PORTAL_I18N[lang]) lang = 'en';
    currentLang = lang;
    localStorage.setItem('portal_preferred_lang', lang);
    document.documentElement.lang = lang;

    const selectEl = document.getElementById('languageSelect');
    if (selectEl) selectEl.value = lang;

    const t = PORTAL_I18N[lang];
    const map = {
        'heroTitle': t.heroTitle,
        'heroSubtitle': t.heroSubtitle,
        'badgeActiveSession': t.badgeActiveSession,
        'step1Title': t.step1Title,
        'step1Desc': t.step1Desc,
        'step2Title': t.step2Title,
        'step2Desc': t.step2Desc,
        'step3Title': t.step3Title,
        'step3Desc': t.step3Desc,
        'step4Title': t.step4Title,
        'step4Desc': t.step4Desc,
        'labelAccessCode': t.labelAccessCode,
        'codeLengthHint': t.codeLengthHint,
        'btnActivateText': t.btnActivateText,
        'btnReportText': t.btnReportText,
        'modalTitle': t.modalTitle,
        'modalDesc': t.modalDesc,
        'labelOrder': t.labelOrder,
        'labelCode': t.labelCode,
        'labelReason': t.labelReason,
        'labelNote': t.labelNote,
        'labelProof': t.labelProof,
        'modalSubmitBtn': t.btnSubmitReport,
        'pcLaunchLink': t.openPc,
        'mobileLaunchLink': t.openMobile,
        'tvLaunchLink': t.pairTv,
        'generalLaunchLink': t.viewAccount
    };

    for (const [id, val] of Object.entries(map)) {
        const el = document.getElementById(id);
        if (el) {
            if (el.tagName === 'INPUT' || el.tagName === 'BUTTON') {
                el.innerText = val;
            } else {
                el.innerText = val;
            }
        }
    }

    // Update select options
    const optScreen = document.getElementById('optReasonScreen');
    if (optScreen) optScreen.innerText = t.reasonScreen;
    const optPayment = document.getElementById('optReasonPayment');
    if (optPayment) optPayment.innerText = t.reasonPayment;
    const optOther = document.getElementById('optReasonOther');
    if (optOther) optOther.innerText = t.reasonOther;
}

function showToast(message, type = 'success') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.style.cssText = 'position:fixed;bottom:25px;right:25px;z-index:999999;display:flex;flex-direction:column;gap:10px;pointer-events:none;';
        document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    const bg = type === 'success' ? '#10B981' : (type === 'error' ? '#EF4444' : '#0284C7');
    toast.style.cssText = `background:${bg};color:#fff;padding:12px 20px;border-radius:10px;font-size:0.9rem;font-weight:600;box-shadow:0 10px 25px rgba(0,0,0,0.5);display:flex;align-items:center;gap:8px;transform:translateY(16px);opacity:0;transition:all 0.25s ease;pointer-events:auto;`;
    toast.innerText = message;
    container.appendChild(toast);
    setTimeout(() => { toast.style.transform = 'translateY(0)'; toast.style.opacity = '1'; }, 10);
    setTimeout(() => {
        toast.style.transform = 'translateY(16px)';
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 250);
    }, 3500);
}

function getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) return meta.getAttribute('content');
    const inp = document.querySelector('input[name="csrf_token"]');
    return inp ? inp.value : '';
}

function handleActivation() {
    const t = PORTAL_I18N[currentLang];
    const code = document.getElementById('accessCodeInput').value.trim();
    if (!code) {
        showToast(t.enterCodeFirst, 'error');
        return;
    }
    const btn = document.getElementById('activateBtn');
    const btnTextEl = document.getElementById('btnActivateText');
    const originalText = btnTextEl ? btnTextEl.innerText : t.btnActivateText;

    if (btnTextEl) btnTextEl.innerText = t.verifyingText;
    btn.disabled = true;
    btn.style.opacity = '0.7';

    fetch('/api/generate_nftoken', {
        method: 'POST',
        headers: { 
            'Content-Type': 'application/json',
            'X-CSRF-Token': getCsrfToken()
        },
        body: JSON.stringify({ cookie: code })
    })
    .then(res => res.json())
    .then(data => {
        if (btnTextEl) btnTextEl.innerText = originalText;
        btn.disabled = false;
        btn.style.opacity = '1';

        if (data.success) {
            document.getElementById('pcLaunchLink').href = data.pc_link;
            document.getElementById('mobileLaunchLink').href = data.mobile_link;
            document.getElementById('tvLaunchLink').href = data.tv_link;
            if (data.general_link) document.getElementById('generalLaunchLink').href = data.general_link;
            if (data.plan) document.getElementById('planBadge').innerText = `${t.planLabel}: ${data.plan}`;
            if (data.expire_date) document.getElementById('expireBadge').innerText = `${t.validUntilLabel}: ${data.expire_date}`;
            currentCookieJson = data.cookie_json || "";
            document.getElementById('deviceHub').style.display = 'flex';
            showToast(t.sessionSuccess, 'success');
        } else {
            showToast(data.error || t.activationFailed, 'error');
        }
    })
    .catch(() => {
        if (btnTextEl) btnTextEl.innerText = originalText;
        btn.disabled = false;
        btn.style.opacity = '1';
        showToast(t.connectionError, 'error');
    });
}

function handleCopyCookie() {
    const t = PORTAL_I18N[currentLang];
    if (!currentCookieJson) {
        showToast(t.enterCodeFirst, 'error');
        return;
    }
    if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(currentCookieJson).then(() => {
            showToast(t.copiedCookieText, 'success');
        }).catch(() => fallbackCopy(currentCookieJson));
    } else {
        fallbackCopy(currentCookieJson);
    }
}

function fallbackCopy(text) {
    const t = PORTAL_I18N[currentLang];
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.left = '-9999px';
    document.body.appendChild(ta);
    ta.select();
    try {
        document.execCommand('copy');
        showToast(t.copiedCookieText, 'success');
    } catch (e) {
        showToast('Unable to copy automatically.', 'error');
    }
    ta.remove();
}

function openWarrantyModal() {
    lastFocusedElement = document.activeElement;
    currentOperationId = generateClientOperationId();

    const code = document.getElementById('accessCodeInput').value.trim();
    if (code) document.getElementById('modalAccessCode').value = code;

    const modal = document.getElementById('warrantyModal');
    if (modal) {
        modal.style.display = 'flex';
        modal.setAttribute('aria-hidden', 'false');
        const firstInput = document.getElementById('u7buyOrderId');
        if (firstInput) firstInput.focus();
    }
}

function closeWarrantyModal() {
    const modal = document.getElementById('warrantyModal');
    if (modal) {
        modal.style.display = 'none';
        modal.setAttribute('aria-hidden', 'true');
    }
    if (lastFocusedElement && typeof lastFocusedElement.focus === 'function') {
        lastFocusedElement.focus();
    }
}

function submitWarrantyRequest(e) {
    e.preventDefault();
    const t = PORTAL_I18N[currentLang];
    const orderId = document.getElementById('u7buyOrderId').value.trim();
    const code = document.getElementById('modalAccessCode').value.trim();
    const categorySelect = document.getElementById('modalReasonCategory');
    const category = categorySelect ? categorySelect.value : 'TOO_MANY_PEOPLE';
    const noteInput = document.getElementById('modalReasonNote');
    const note = noteInput ? noteInput.value.trim() : '';
    const combinedReason = note ? `[${category}] ${note}` : `[${category}]`;

    const fileInput = document.getElementById('modalProofImage');
    if (!fileInput.files.length) {
        showToast(t.attachProofFirst, 'error');
        return;
    }

    const submitBtn = document.getElementById('modalSubmitBtn');
    submitBtn.innerText = t.submittingText;
    submitBtn.disabled = true;

    const formData = new FormData();
    formData.append('u7buy_order_id', orderId);
    formData.append('code', code);
    formData.append('reason_category', category);
    formData.append('reason', combinedReason);
    formData.append('image', fileInput.files[0]);
    formData.append('operation_id', currentOperationId);

    fetch('/api/submit_request', {
        method: 'POST',
        headers: { 'X-CSRF-Token': getCsrfToken() },
        body: formData
    })
    .then(res => res.json())
    .then(data => {
        submitBtn.innerText = t.btnSubmitReport;
        submitBtn.disabled = false;

        if (data.success) {
            closeWarrantyModal();
            // Clear inputs on success
            document.getElementById('u7buyOrderId').value = '';
            document.getElementById('modalProofImage').value = '';
            if (noteInput) noteInput.value = '';

            if (data.auto_rotated) {
                showToast(data.message || t.reqAutoReplaced, 'success');
                document.getElementById('accessCodeInput').value = code;
                handleActivation();
            } else {
                showToast(data.message || t.reqQueued, 'success');
            }
        } else {
            // Keep user inputs preserved on failure!
            showToast(data.error || 'Failed to submit request.', 'error');
        }
    })
    .catch(() => {
        submitBtn.innerText = t.btnSubmitReport;
        submitBtn.disabled = false;
        showToast(t.connectionError, 'error');
    });
}

// Keyboard navigation & accessibility event listeners
document.addEventListener('keydown', function(event) {
    if (event.key === 'Escape') {
        const modal = document.getElementById('warrantyModal');
        if (modal && modal.style.display === 'flex') {
            closeWarrantyModal();
        }
    }
});

document.addEventListener('DOMContentLoaded', function() {
    initLanguage();
});
