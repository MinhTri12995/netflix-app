import os
import tempfile
import atexit

# Global test safety guard: Isolate all unit tests to a temporary database
# so that test suites NEVER wipe or overwrite the production accounts.db!
if not os.environ.get("SQLITE_DB_PATH"):
    test_db = os.path.join(tempfile.gettempdir(), f"netflix_test_{os.getpid()}.db")
    os.environ["SQLITE_DB_PATH"] = test_db
    def _cleanup():
        for ext in ["", "-wal", "-shm"]:
            path = test_db + ext
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
    atexit.register(_cleanup)
