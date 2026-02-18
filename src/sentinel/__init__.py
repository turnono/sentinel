from .command_auditor import CommandAuditor
from .models import AuditDecision
from .sentinel_auditor import SentinelAuditor

__all__ = ["AuditDecision", "CommandAuditor", "SentinelAuditor", "SentinelRuntime"]


def __getattr__(name: str):
    if name == "SentinelRuntime":
        from .main import SentinelRuntime

        return SentinelRuntime
    raise AttributeError(f"module 'src.sentinel' has no attribute {name!r}")
