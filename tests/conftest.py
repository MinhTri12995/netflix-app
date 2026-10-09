import os
import sys
os.environ["DISABLE_ADMIN_WORKER"] = "1"
import tempfile
import sqlite3
from unittest.mock import patch

# Ensure project root is in path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import database
from app import create_app
from app.config import Config

import struct
import zlib
import io

TEST_CSRF_TOKEN = "test-csrf-token-abc123xyz"

def create_valid_png_bytes(width=1, height=1):
    sig = b'\x89PNG\r\n\x1a\n'
    ihdr_data = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    ihdr_crc = zlib.crc32(b'IHDR' + ihdr_data) & 0xffffffff
    ihdr = struct.pack('>I', 13) + b'IHDR' + ihdr_data + struct.pack('>I', ihdr_crc)

    raw_pixel = b'\x00\xff\x00\x00' * width
    compressed = zlib.compress(b'\x00' + raw_pixel)
    idat_crc = zlib.crc32(b'IDAT' + compressed) & 0xffffffff
    idat = struct.pack('>I', len(compressed)) + b'IDAT' + compressed + struct.pack('>I', idat_crc)

    iend_crc = zlib.crc32(b'IEND') & 0xffffffff
    iend = struct.pack('>I', 0) + b'IEND' + struct.pack('>I', iend_crc)
    return sig + ihdr + idat + iend

def create_valid_png_file(width=1, height=1):
    return io.BytesIO(create_valid_png_bytes(width, height))

def create_isolated_test_app(db_path=None):
    """Factory creating a hermetic test Flask app with isolated DB and no network."""
    if db_path is None:
        fd, db_path = tempfile.mkstemp(prefix="test_iso_", suffix=".db")
        os.close(fd)

    orig_conn = database.get_sqlite_conn
    database.get_sqlite_conn = lambda p=db_path: sqlite3.connect(db_path)
    database.SUPABASE_KEY = ""

    database.init_db()
    conn = database.get_sqlite_conn(db_path)
    # Ensure requests and access_keys tables exist
    conn.execute("""CREATE TABLE IF NOT EXISTS access_keys (
        code TEXT PRIMARY KEY,
        assigned_email TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expire_at TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT,
        u7buy_order_id TEXT,
        image_url TEXT,
        reason TEXT,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()
    conn.close()

    app = create_app()
    app.config.update(
        TESTING=True,
        SECRET_KEY="hermetic-test-secret-key-32-chars",
        WTF_CSRF_ENABLED=False
    )
    return app, db_path, orig_conn

def setup_admin_session(client):
    """Configures a client with a valid admin session and CSRF token."""
    with client.session_transaction() as sess:
        sess["logged_in"] = True
        sess["_csrf_token"] = TEST_CSRF_TOKEN
    return client

# Optional pytest fixtures if pytest is used:
try:
    import pytest

    @pytest.fixture
    def test_app():
        app, db_path, orig_conn = create_isolated_test_app()
        yield app
        database.get_sqlite_conn = orig_conn
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except Exception:
                pass

    @pytest.fixture
    def client(test_app):
        return test_app.test_client()

    @pytest.fixture
    def admin_client(test_app):
        c = test_app.test_client()
        return setup_admin_session(c)

except ImportError:
    pass
