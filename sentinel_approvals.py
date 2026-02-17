import uuid
import time
from typing import Dict, Optional, Any, List
from pydantic import BaseModel

# Import DB (delayed import to avoid circular dependency if needed, but here it's fine)
# We need to handle the import carefully. sentinel_db imports PendingRequest.
# So define PendingRequest first.

class PendingRequest(BaseModel):
    id: str
    command: str
    created_at: float
    rule_name: str
    reason: str
    status: str = "pending" # pending, approved, rejected

class ApprovalManager:
    def __init__(self, db_path: str = "data/sentinel.db"):
        # Import inside to avoid circular dependency
        from sentinel_db import SentinelDB
        self.db = SentinelDB(db_path)

    def create_request(self, command: str, rule_name: str, reason: str) -> str:
        req_id = str(uuid.uuid4())[:8]
        request = PendingRequest(
            id=req_id,
            command=command,
            created_at=time.time(),
            rule_name=rule_name,
            reason=reason
        )
        self.db.insert_approval(request)
        return req_id

    def get_request(self, req_id: str) -> Optional[PendingRequest]:
        return self.db.get_approval(req_id)

    def list_pending(self) -> Dict[str, PendingRequest]:
        return self.db.get_pending_approvals()

    def resolve_request(self, req_id: str, status: str) -> bool:
        # Check if exists first
        if self.db.get_approval(req_id):
            self.db.update_approval_status(req_id, status)
            return True
        return False
    
    def cleanup_old_requests(self, max_age_seconds: int = 3600):
        # TODO: Implement DB cleanup
        pass
