# Configuration & Environment Variables Reference

This document provides the authoritative reference for all runtime environment variables, security flags, and infrastructure parameters for the Netflix Access platform.

---

## 1. Environment Variables Catalog

| Variable Name | Type | Default | Production Requirement | Description |
|---|---|---|---|---|
| `FLASK_ENV` / `FLASK_DEBUG` | Boolean | `False` | Must be `False` | Enables or disables debug reloaders and tracebacks. |
| `PORT` | Integer | `5000` | Optional (set by PaaS) | Port for the HTTP server to bind. |
| `SECRET_KEY` | String | Auto-generated `.secret_key` | Mandatory ($\ge 32$ chars) | Key for signing session cookies and HMAC tokens. |
| `SESSION_COOKIE_SECURE` | Boolean | `False` | `True` (under HTTPS) | Marks cookies with the `Secure` flag. |
| `ADMIN_EMAIL` | String | `admin@example.com` | Mandatory | Admin login identifier. |
| `ADMIN_PASSWORD_HASH` | String | None | Recommended | Scrypt hash of admin password. Preempts plain `ADMIN_PASSWORD`. |
| `ADMIN_PASSWORD` | String | None | Disallowed in Prod | Raw password fallback (generates hash in-memory). |
| `ADMIN_API_KEY` | String | None | Mandatory for S2S | Secret token required for server-to-server API endpoints (`X-API-Key`). |
| `TRUSTED_PROXIES` | Comma-separated | `127.0.0.1,::1` | Mandatory behind CDN | Comma-separated allowlist of reverse proxy IPs permitted to set `CF-Connecting-IP` / `X-Forwarded-For`. |
| `AUTO_APPROVAL_ENABLED` | Boolean | `False` | Operator discretion | Feature flag enabling 24/7 AI vision auto-approval for screen limits. |
| `SUPABASE_URL` | URL | `""` | Mandatory for Cloud | Base URL of the Supabase PostgreSQL cluster. |
| `SUPABASE_SECRET_KEY` / `SUPABASE_KEY` | String | `""` | Mandatory for Cloud | Service role key for authoritative storage operations. |
| `MISTRAL_API_KEY` | String | `""` | Mandatory for AI | API key for Mistral OCR Vision screenshot analysis. |
| `MISTRAL_MODEL` | String | `ministral-8b-latest` | Optional | Model identifier for screenshot analysis. |
| `WEBSHARE_USERNAME` | String | `""` | Optional | Username for rotating HTTP residential proxy. |
| `WEBSHARE_PASSWORD` | String | `""` | Optional | Password for rotating HTTP residential proxy. |
| `WEBSHARE_HOST` | String | `p.webshare.io` | Optional | Hostname for residential proxy gateway. |
| `WEBSHARE_PORT` | Integer | `80` | Optional | Port for residential proxy gateway. |
| `TELEGRAM_BOT_TOKEN` | String | `""` | Optional | Bot token for outbox warranty alert notifications. |
| `TELEGRAM_CHAT_ID` | String | `""` | Optional | Target chat ID for admin alerts. |

---

## 2. Trusted Proxy Configuration (F12 Guard)

To prevent IP spoofing attacks where malicious clients forge `CF-Connecting-IP` or `X-Forwarded-For` headers to bypass rate limits:

```env
# Example behind Render / Cloudflare:
TRUSTED_PROXIES=10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,127.0.0.1
```

If a connection arrives from an IP **not** in `TRUSTED_PROXIES`, the system strictly records `request.remote_addr` as the client's identity and ignores any forwarded headers.

---

## 3. Secret Rotation & Hardening Runbook

1. **Flask Session Key**:
   - Generate via CSPRNG:
     ```bash
     python -c "import secrets; print(secrets.token_hex(32))"
     ```
   - Set as `SECRET_KEY` in environment. Existing sessions will invalidate gracefully, requiring admin re-login.
2. **Admin Password Hash**:
   - Generate Scrypt hash:
     ```bash
     python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('StrongSecretPass123!'))"
     ```
   - Store hash as `ADMIN_PASSWORD_HASH`. Unset `ADMIN_PASSWORD`.
3. **Admin API Key**:
   - Generate high-entropy hex:
     ```bash
     python -c "import secrets; print('s2s_' + secrets.token_urlsafe(32))"
     ```
   - Set as `ADMIN_API_KEY`.
