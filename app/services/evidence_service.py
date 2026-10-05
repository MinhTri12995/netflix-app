import json
from typing import Optional, Dict, Any, Tuple

ALLOWED_ERROR_TYPES = [
    "TOO_MANY_PEOPLE",
    "PAYMENT_ERROR",
    "WRONG_PASSWORD",
    "EXPIRED",
    "OTHER"
]

def parse_and_validate_ai_response(raw_response: Any) -> Tuple[bool, Dict[str, Any], str]:
    """
    Strictly validate AI OCR/Vision JSON response against the authoritative schema:
    - is_netflix: must be a strict boolean (True/False). String 'true' is rejected.
    - error_type: must be one of ALLOWED_ERROR_TYPES.
    - visible_email: string or None.
    - error_description: string.
    - card_last4 / card_digits: string or None.
    """
    if isinstance(raw_response, str):
        try:
            # Strip markdown json code block if present
            cleaned = raw_response.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            data = json.loads(cleaned.strip())
        except Exception as e:
            return False, {}, f"JSON_DECODE_ERROR: {e}"
    elif isinstance(raw_response, dict):
        data = raw_response
    else:
        return False, {}, "INVALID_PAYLOAD_TYPE: Expected dict or JSON string"

    if not isinstance(data, dict):
        return False, {}, "INVALID_JSON_OBJECT: Root must be a dict"

    # 1. Validate is_netflix (must be real bool, not string 'true' or int 1)
    is_netflix_raw = data.get("is_netflix")
    if not isinstance(is_netflix_raw, bool):
        return False, {}, "SCHEMA_ERROR: 'is_netflix' must be a strict boolean (True/False)"

    # 2. Validate error_type
    raw_error_type = str(data.get("error_type") or "").strip().upper()
    desc = str(data.get("error_description") or data.get("reason") or "").strip().lower()
    if raw_error_type in ALLOWED_ERROR_TYPES and raw_error_type != "OTHER":
        error_type = raw_error_type
    elif any(k in desc for k in ["too many", "screen limit", "quá nhiều", "màn hình", "pantallas"]):
        error_type = "TOO_MANY_PEOPLE"
    elif raw_error_type == "OTHER":
        error_type = "OTHER"
    else:
        error_type = "OTHER"

    # 3. Validate visible_email
    raw_email = data.get("visible_email")
    if raw_email and isinstance(raw_email, str) and raw_email.strip():
        visible_email = raw_email.strip().lower()
    else:
        visible_email = None

    # 4. Extract other fields
    card_last4 = str(data.get("card_last4") or "").strip() or None
    card_digits = str(data.get("card_digits") or "").strip() or None

    validated_evidence = {
        "is_netflix": is_netflix_raw,
        "error_type": error_type,
        "visible_email": visible_email,
        "error_description": desc,
        "card_last4": card_last4,
        "card_digits": card_digits
    }

    if not is_netflix_raw:
        return False, validated_evidence, "REJECTED: Screenshot does not show Netflix interface"

    return True, validated_evidence, "VALID"

def evaluate_evidence_for_auto_approval(
    evidence: Dict[str, Any],
    expected_email: str
) -> Tuple[bool, str]:
    """
    Evaluate if validated AI evidence qualifies for automated account replacement.
    For TOO_MANY_PEOPLE (screen limit):
    - is_netflix must be True
    - error_type must be TOO_MANY_PEOPLE
    - Email is NOT mandatory on screen limit overlay because Netflix does not show user emails on this dialog.
      If visible_email is present, it must match expected_email; if not present, it's accepted.
    """
    if not evidence or not isinstance(evidence, dict):
        return False, "EVIDENCE_EMPTY"

    if evidence.get("is_netflix") is not True:
        return False, "NOT_NETFLIX"

    if evidence.get("error_type") != "TOO_MANY_PEOPLE":
        return False, f"ERROR_TYPE_NOT_SCREEN_LIMIT: {evidence.get('error_type')}"

    visible_email = evidence.get("visible_email")
    if visible_email:
        expected = (expected_email or "").strip().lower()
        if expected and visible_email.strip().lower() != expected:
            return False, f"EMAIL_MISMATCH: proof shows '{visible_email}', assigned account is '{expected}'"

    return True, "ELIGIBLE_FOR_AUTO_APPROVAL"
