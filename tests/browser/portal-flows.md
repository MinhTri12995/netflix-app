# Browser Test Scenarios & Accessibility Audit Runbook: Portal & Admin

This runbook defines the end-to-end verification workflows and accessibility audit checklists for the Netflix Access Activation Portal and Admin Dashboard.

---

## 1. Environment & Pre-requisites

- **App Server**: Local Flask runtime (`python run.py` / `python wsgi.py`), hermetic test database.
- **Screen Viewports**:
  - Mobile Small: 360 × 740 (Samsung Galaxy S8+)
  - Mobile Standard: 390 × 844 (iPhone 13/14)
  - Tablet: 768 × 1024 (iPad Mini)
  - Desktop: 1280 × 800 and 1920 × 1080
- **Input Modes**:
  - Mouse & Touch
  - Keyboard-only (`Tab`, `Shift+Tab`, `Space`, `Enter`, `Escape`)

---

## 2. Test Scenarios

### Scenario A: Member Direct Activation (PC / Mobile / Smart TV)
1. **Navigate**: Open `/` on desktop browser.
2. **Keyboard Navigation**:
   - Press `Tab` to navigate to language selector (`languageSelect`).
   - Switch language between `English (US)` and `Tiếng Việt (VN)`.
   - Verify all visible labels, step guides, badges, and button texts immediately update without page reload.
   - Verify `document.documentElement.lang` reflects `en` or `vi`.
   - Verify preference persists across browser refreshes via `localStorage`.
3. **Activation Execution**:
   - `Tab` into Access Code input (`accessCodeInput`). Enter a valid 16-character code (e.g., `VALID16CHARCODE1`).
   - Press `Enter` or click **Activate & Launch Stream** (`activateBtn`).
   - Button disables, displays `"Verifying & Connecting..."`.
   - Upon HTTP 200 response:
     - Device Hub unhides (`deviceHub`).
     - Plan Badge shows assigned tier (e.g. `Plan: Premium`).
     - PC link, Mobile link, Smart TV link are populated with signed launch URIs.
     - Toast notification announces successful session authorization.

---

### Scenario B: Warranty Claim Modal & Accessible Interactions
1. **Open Modal**:
   - Click or `Space`/`Enter` on **Report Issue** (`reportBtn`).
   - Verify modal opens with `role="dialog"`, `aria-modal="true"`.
   - Verify focus is automatically moved to the first input: `u7buyOrderId`.
2. **Keyboard Dismissal (Escape Key)**:
   - Press `Escape` key.
   - Verify modal immediately closes.
   - Verify focus returns to **Report Issue** (`reportBtn`).
3. **Double Submission Prevention & Error Handling**:
   - Re-open modal.
   - Fill in Order ID, Access Code, Select `Too many people using screen`.
   - Select a valid screenshot PNG.
   - Click **Submit for Verification** (`modalSubmitBtn`).
   - Verify submit button enters disabled state with loading text (`"Analyzing with AI Vision..."`).
   - Rapid clicking does not generate duplicate requests.
   - If AI returns non-retryable failure or network drops, verify input fields retain entered values so the user does not need to retype.

---

### Scenario C: Out-of-Stock & Manual Review Routing
1. **Submit Claim on Depleted Tier**:
   - Submit a claim when no spare accounts are available in the inventory.
   - Verify user receives message: `"Request queued for verification."` (no false positive claim of auto-rotation).
   - Verify request in database has status `pending_out_of_stock`.
2. **Admin Dashboard Visibility**:
   - Login to `/admin`.
   - Verify the request appears under the **Pending Buyer Replacement Requests** table with badge `Out of Stock`.
   - Click filter button `Out of Stock` -> verify table filters to only out-of-stock items.
   - Click `All` -> verify all pending rows display.

---

### Scenario D: Admin Dashboard Mobile Overflow & Cookie Privacy
1. **Mobile Responsiveness (360px - 390px Viewport)**:
   - Emulate 390 × 844 viewport in DevTools.
   - Inspect page width: verify `document.body.scrollWidth === window.innerWidth` (no horizontal page blowout).
   - Verify data tables scroll smoothly inside their individual wrappers (`overflow-x: auto`).
2. **Cookie Masking & Click-to-Reveal**:
   - Inspect the **Accounts Vault** table.
   - Verify raw Netflix auth tokens (`netflix_id`) are masked by default (`•••••••••••••••• (click to reveal)`).
   - Click the masked span: verify token unmasks and text color changes to indicate active inspection.
   - Click again: verify token returns to masked state.

---

### Scenario E: Admin Login Form Accessibility
1. **Navigate**: Open `/login`.
2. **Inspect Form Fields**:
   - Verify `<label for="admin-email">` and `<label for="admin-password">` exist and have readable contrast against background.
   - Verify `autocomplete="username"` on email input.
   - Verify `autocomplete="current-password"` on password input.
   - Verify CSRF token is embedded in the POST form.

---

## 3. Automated Verification Checklist

| Checkpoint | Target | Status |
|---|---|---|
| i18n English Dictionary | 24 UI keys mapped | PASS |
| i18n Vietnamese Dictionary | 24 UI keys mapped | PASS |
| Modal Accessibility | `role="dialog"`, `aria-modal="true"`, `Escape` trap | PASS |
| Form Idempotency | Operation ID attached, button disabled on submit | PASS |
| Mobile Viewport Protection | 360px / 390px / 768px scroll boundaries enforced | PASS |
| Cookie Privacy | Click-to-reveal mask on admin dashboard | PASS |
| Request Filter Tabs | All / Pending / Out of Stock / Card Mismatch / Unverified | PASS |
