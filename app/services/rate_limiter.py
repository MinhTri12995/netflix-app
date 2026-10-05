import time
import threading
from collections import defaultdict
from typing import Tuple

_lock = threading.Lock()
_ip_buckets = defaultdict(list)
_last_cleanup = time.time()

def get_client_ip(request) -> str:
    """
    Trích xuất địa chỉ IP của client an toàn (F12 fix).
    Chỉ tin cậy header proxy (CF-Connecting-IP, X-Forwarded-For) khi kết nối
    xuất phát từ danh sách TRUSTED_PROXIES được cấu hình rõ ràng.
    Đối với peer không tin cậy, luôn sử dụng trực tiếp request.remote_addr.
    """
    import os
    peer_ip = (request.remote_addr or "127.0.0.1").strip()

    from app.config import Config
    trusted_proxies = getattr(Config, "TRUSTED_PROXIES", None)
    if trusted_proxies is None:
        raw_env = os.environ.get("TRUSTED_PROXIES", "")
        trusted_proxies = [p.strip() for p in raw_env.split(",") if p.strip()]

    if not trusted_proxies or peer_ip not in trusted_proxies:
        return peer_ip

    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()

    x_forwarded = request.headers.get("X-Forwarded-For")
    if x_forwarded:
        return x_forwarded.split(",")[0].strip()

    return peer_ip

def check_rate_limit(key: str, max_requests: int, window_seconds: int) -> Tuple[bool, int]:
    """
    Kiểm tra giới hạn tần suất theo thuật toán sliding window.
    Trả về (allowed, retry_after_seconds).
    """
    global _last_cleanup
    now = time.time()

    with _lock:
        # Định kỳ 10 phút dọn dẹp các IP đã hết hạn để tránh tràn bộ nhớ
        if now - _last_cleanup > 600:
            expired_keys = [k for k, timestamps in _ip_buckets.items() if not timestamps or (now - timestamps[-1] > 3600)]
            for k in expired_keys:
                del _ip_buckets[k]
            _last_cleanup = now

        timestamps = _ip_buckets[key]
        # Lọc bỏ các request đã quá thời gian cửa sổ
        cutoff = now - window_seconds
        valid_timestamps = [t for t in timestamps if t > cutoff]
        _ip_buckets[key] = valid_timestamps

        if len(valid_timestamps) >= max_requests:
            oldest = valid_timestamps[0]
            retry_after = max(1, int(window_seconds - (now - oldest)))
            return False, retry_after

        _ip_buckets[key].append(now)
        return True, 0

def reset_rate_limit(key: str):
    """Xóa bỏ lịch sử rate limit cho key cụ thể (ví dụ khi admin đăng nhập thành công)."""
    with _lock:
        if key in _ip_buckets:
            del _ip_buckets[key]
