import json
import os
from datetime import datetime
from typing import Optional, Dict, Any
import database as db
from app.services.notification_service import send_telegram_alert

def record_outbox_event(event_type: str, payload: Dict[str, Any], conn=None) -> Optional[int]:
    """Record an event into events_outbox table within an existing transaction or standalone."""
    payload_str = json.dumps(payload, ensure_ascii=False) if isinstance(payload, dict) else str(payload)
    
    if db.SUPABASE_KEY and conn is None:
        try:
            res = db.get_supabase().table("events_outbox").insert({
                "event_type": event_type,
                "payload": payload if isinstance(payload, dict) else {"message": str(payload)},
                "status": "pending",
                "retry_count": 0
            }).execute()
            if res.data and len(res.data) > 0:
                return res.data[0].get("id")
            return 1
        except Exception as e:
            print(f"Supabase record_outbox_event error: {e}")
            return None

    # SQLite store
    should_close = False
    if conn is None:
        conn = db.get_sqlite_conn()
        should_close = True

    try:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS events_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            retry_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            delivered_at TIMESTAMP
        )""")
        c.execute("INSERT INTO events_outbox (event_type, payload, status, retry_count) VALUES (?, ?, 'pending', 0)",
                  (event_type, payload_str))
        outbox_id = c.lastrowid
        if should_close:
            conn.commit()
            conn.close()
        return outbox_id
    except Exception as e:
        print(f"SQLite record_outbox_event error: {e}")
        if should_close:
            conn.close()
        return None

def deliver_event(outbox_id: int, event_type: str, payload: Any, conn=None) -> bool:
    """Deliver a specific outbox event (e.g. Telegram alert)."""
    if isinstance(payload, str):
        try:
            payload_data = json.loads(payload)
        except Exception:
            payload_data = {"message": payload}
    else:
        payload_data = payload or {}

    delivered = False
    if event_type == "telegram_alert":
        msg = payload_data.get("message", "")
        if msg:
            delivered = send_telegram_alert(msg)
        else:
            delivered = True  # Nothing to send
    else:
        delivered = True

    # Update delivery status
    from datetime import timezone
    now_str = datetime.now(timezone.utc).isoformat()
    if db.SUPABASE_KEY and conn is None:
        try:
            if delivered:
                db.get_supabase().table("events_outbox").update({
                    "status": "delivered",
                    "delivered_at": now_str
                }).eq("id", outbox_id).execute()
            else:
                db.get_supabase().table("events_outbox").update({
                    "retry_count": 1
                }).eq("id", outbox_id).execute()
        except Exception as e:
            print(f"Supabase update outbox status error: {e}")
    else:
        should_close = False
        if conn is None:
            conn = db.get_sqlite_conn()
            should_close = True
        try:
            c = conn.cursor()
            if delivered:
                c.execute("UPDATE events_outbox SET status = 'delivered', delivered_at = CURRENT_TIMESTAMP WHERE id = ?", (outbox_id,))
            else:
                c.execute("UPDATE events_outbox SET retry_count = retry_count + 1 WHERE id = ?", (outbox_id,))
            if should_close:
                conn.commit()
                conn.close()
        except Exception as e:
            print(f"SQLite update outbox status error: {e}")
            if should_close:
                conn.close()

    return delivered

def process_outbox(limit: int = 10) -> int:
    """Process pending outbox events for retry. Returns count of delivered events."""
    delivered_count = 0
    if db.SUPABASE_KEY:
        try:
            res = db.get_supabase().table("events_outbox").select("*").eq("status", "pending").lt("retry_count", 5).limit(limit).execute()
            rows = res.data or []
            for r in rows:
                if deliver_event(r["id"], r.get("event_type", ""), r.get("payload")):
                    delivered_count += 1
        except Exception as e:
            print(f"Supabase process_outbox error: {e}")
    else:
        try:
            conn = db.get_sqlite_conn()
            c = conn.cursor()
            c.execute("SELECT id, event_type, payload, retry_count FROM events_outbox WHERE status = 'pending' AND retry_count < 5 LIMIT ?", (limit,))
            rows = c.fetchall()
            conn.close()
            for r in rows:
                if deliver_event(r[0], r[1], r[2]):
                    delivered_count += 1
        except Exception as e:
            print(f"SQLite process_outbox error: {e}")

    return delivered_count

def send_notification_outbox(event_type: str, payload: Dict[str, Any], conn=None) -> Optional[int]:
    """
    Enqueues an event in the outbox table and attempts immediate post-commit delivery.
    Never raises on notification failure so primary business transactions stay intact.
    """
    outbox_id = record_outbox_event(event_type, payload, conn=conn)
    if outbox_id and conn is None:
        try:
            deliver_event(outbox_id, event_type, payload)
        except Exception as e:
            print(f"Immediate outbox delivery attempt failed (will retry): {e}")
    return outbox_id
