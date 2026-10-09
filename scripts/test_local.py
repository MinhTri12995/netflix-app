"""Run the repository suite using temporary databases and blocked service calls."""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def deny_service_call(*args, **kwargs):
    raise AssertionError("Real service calls disabled in local tests")


def main():
    scratch = ROOT / "scratch"
    scratch.mkdir(exist_ok=True)
    original_cwd = Path.cwd()
    original_tempdir = tempfile.tempdir
    tempfile.tempdir = str(scratch)
    try:
        with tempfile.TemporaryDirectory(dir=scratch) as tmp:
            try:
                os.chdir(tmp)
                # Legacy readers check this filename before using the fixture connection.
                Path("accounts.db").touch()
                env = {key: "" for key in (
                    "SUPABASE_KEY", "SUPABASE_SECRET_KEY", "POSTGRES_URL", "DATABASE_URL",
                    "MISTRAL_API_KEY", "TELEGRAM_BOT_TOKEN", "U7BUY_APP_ID", "U7BUY_APP_SECRET")}
                env.update(SECRET_KEY="isolated-test-secret", SQLITE_DB_PATH=str(Path(tmp) / "isolated.db"))
                with patch.dict(os.environ, env), patch("dotenv.load_dotenv", return_value=False), \
                        patch("socket.socket.connect", deny_service_call), \
                        patch("requests.sessions.Session.request", deny_service_call):
                    import pytest
                    return pytest.main([str(ROOT / "tests"), "-c", str(ROOT / "pytest.ini"), *sys.argv[1:]])
            finally:
                # Windows cannot delete the current working directory.
                os.chdir(original_cwd)
    finally:
        os.chdir(original_cwd)
        tempfile.tempdir = original_tempdir


if __name__ == "__main__":
    sys.exit(main())
