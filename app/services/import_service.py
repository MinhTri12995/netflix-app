import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional
import database
import parser

@dataclass
class ImportResult:
    total: int = 0
    saved_count: int = 0
    duplicate_count: int = 0
    invalid_count: int = 0
    failure_count: int = 0
    details: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def is_complete_success(self) -> bool:
        return self.failure_count == 0 and self.saved_count > 0

def import_accounts(accounts_list: List[Dict[str, Any]]) -> ImportResult:
    """
    Import parsed accounts into the authoritative database with per-row verification:
    - Verifies save_account return value before claiming success (F10 fix)
    - Prevents overwriting valid existing plan with NULL or UNKNOWN
    - Differentiates between saved, duplicate, invalid, and retryable failures
    """
    database.init_db()
    result = ImportResult(total=len(accounts_list))

    for idx, acc in enumerate(accounts_list, start=1):
        netflix_id = (acc.get("netflix_id") or "").strip()
        secure_netflix_id = (acc.get("secure_netflix_id") or "").strip()
        email = (acc.get("email") or "").strip()
        expire = (acc.get("expire") or "2099-12-31").strip()
        plan = (acc.get("plan") or "Premium").strip()

        if not netflix_id:
            result.invalid_count += 1
            result.details.append({
                "row": idx,
                "email": email,
                "status": "invalid",
                "error": "Missing NetflixId"
            })
            continue

        # Check existing account
        existing = database.get_account_by_netflix_id(netflix_id)
        if existing:
            # Preserve existing verified plan if incoming plan is unverified/default
            existing_plan = existing[5] if len(existing) > 5 else "Premium"
            if plan in ["Unknown", "None", "None found", "null"] and existing_plan:
                plan = existing_plan
            existing_email = existing[0]
            if existing_email:
                email = existing_email
            result.duplicate_count += 1

        # Attempt atomic save
        saved = database.save_account(
            email=email,
            expire_date=expire,
            netflix_id=netflix_id,
            secure_netflix_id=secure_netflix_id,
            plan=plan
        )

        if saved:
            result.saved_count += 1
            result.details.append({
                "row": idx,
                "email": email,
                "netflix_id": netflix_id,
                "status": "saved"
            })
        else:
            result.failure_count += 1
            result.details.append({
                "row": idx,
                "email": email,
                "netflix_id": netflix_id,
                "status": "retryable_failure",
                "error": "Database write failed"
            })

    return result

def process_import_file(filepath: str, watch_dir: Optional[str] = None) -> ImportResult:
    """
    Read, parse, and import an account batch file:
    - Moves to Processed ONLY if every valid row was committed to DB
    - Leaves in place or moves to Errors if any save failed
    """
    if not os.path.exists(filepath):
        return ImportResult(details=[{"error": f"File not found: {filepath}"}])

    try:
        with open(filepath, 'rb') as f:
            file_bytes = f.read()

        try:
            content = file_bytes.decode('utf-8-sig')
        except UnicodeDecodeError:
            try:
                content = file_bytes.decode('utf-16')
            except UnicodeDecodeError:
                content = file_bytes.decode('latin-1', errors='replace')

        lines = content.splitlines()
        accounts_list = parser.parse_lines(lines)

        if not accounts_list:
            return ImportResult(details=[{"error": "Empty or unrecognized format"}])

        result = import_accounts(accounts_list)

        # File routing
        if watch_dir and os.path.exists(watch_dir):
            processed_dir = os.path.join(watch_dir, "Processed")
            errors_dir = os.path.join(watch_dir, "Errors")
            os.makedirs(processed_dir, exist_ok=True)
            os.makedirs(errors_dir, exist_ok=True)

            filename = os.path.basename(filepath)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

            if result.is_complete_success:
                dest = os.path.join(processed_dir, f"{timestamp}_{filename}")
                shutil.move(filepath, dest)
            else:
                dest = os.path.join(errors_dir, f"{timestamp}_{filename}")
                shutil.move(filepath, dest)

        return result

    except Exception as e:
        return ImportResult(failure_count=1, details=[{"error": str(e)}])
