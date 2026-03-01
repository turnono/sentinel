from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class AuditDecision:
    allowed: bool
    risk_score: int
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "risk_score": int(max(0, min(10, self.risk_score))),
            "reason": self.reason,
        }

    @classmethod
    def reject(cls, reason: str, risk_score: int = 10) -> "AuditDecision":
        return cls(allowed=False, risk_score=max(0, min(10, risk_score)), reason=reason)
