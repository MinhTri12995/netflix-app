from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any

VALID_STATUSES = {
    "success",
    "out_of_stock",
    "already_processed",
    "limit_exceeded",
    "temporarily_unavailable",
    "needs_review",
    "invalid_input"
}

@dataclass
class OperationResult:
    status: str
    operation_id: Optional[str] = None
    request_id: Optional[str] = None
    assigned_email: Optional[str] = None
    retryable: bool = False
    detail_code: str = ""
    message: str = ""

    def __post_init__(self):
        if self.status not in VALID_STATUSES:
            raise ValueError(f"Invalid OperationResult status '{self.status}'. Must be one of {VALID_STATUSES}")

    @property
    def is_success(self) -> bool:
        return self.status == "success"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.is_success,
            "status": self.status,
            "operation_id": self.operation_id,
            "request_id": self.request_id,
            "assigned_email": self.assigned_email,
            "retryable": self.retryable,
            "detail_code": self.detail_code,
            "message": self.message
        }
