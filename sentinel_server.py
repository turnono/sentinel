"""
Sentinel Security Gateway - HTTP Server

FastAPI server that exposes the Sentinel runtime as an HTTP API.
The OpenClaw plugin calls this server to audit commands through the full
ADK/LLM semantic analysis pipeline.

Usage:
    python sentinel_server.py

The server runs on http://localhost:8765 by default.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Import the Sentinel runtime
from sentinel_main import SentinelRuntime
from sentinel_approvals import ApprovalManager, PendingRequest
from sentinel_db import SentinelDB

app = FastAPI(
    title="Sentinel Security Gateway",
    description="HTTP API for command auditing with deterministic + LLM semantic analysis",
    version="2.0.0",
)


def _parse_allowed_origins() -> list[str]:
    raw = os.getenv("SENTINEL_ALLOWED_ORIGINS", "http://localhost,http://127.0.0.1")
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    return origins or ["http://localhost", "http://127.0.0.1"]


def _requires_auth() -> bool:
    return os.getenv("SENTINEL_DISABLE_AUTH", "false").strip().lower() not in {"1", "true", "yes"}


def _get_auth_token() -> Optional[str]:
    token = os.getenv("SENTINEL_AUTH_TOKEN", "").strip()
    return token or None

# Allow CORS for local development (OpenClaw plugin calls from localhost)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_allowed_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize the Sentinel runtime once at startup
runtime: Optional[SentinelRuntime] = None
approval_manager = ApprovalManager()
db: Optional[SentinelDB] = None


class AuditRequest(BaseModel):
    """Request body for command auditing."""
    command: str


class AuditResponse(BaseModel):
    """Response body from command auditing."""
    allowed: bool
    risk_score: int
    reason: str
    stdout: str = ""
    stderr: str = ""
    returncode: Optional[int] = None


def _verify_auth(x_sentinel_token: Optional[str]) -> None:
    if not _requires_auth():
        return

    expected_token = _get_auth_token()
    if not expected_token:
        raise HTTPException(status_code=503, detail="Sentinel auth token is not configured")

    if x_sentinel_token != expected_token:
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.on_event("startup")
async def startup_event():
    """Initialize Sentinel runtime on server startup."""
    global runtime, db
    try:
        db = SentinelDB()
        runtime = SentinelRuntime()
        if runtime.startup_warning:
            print(f"⚠️  Sentinel warning: {runtime.startup_warning}")
        print("🛡️  Sentinel Security Gateway initialized")
    except Exception as e:
        print(f"❌ Failed to initialize Sentinel: {e}")
        raise


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "sentinel"}


@app.post("/audit", response_model=AuditResponse)
def audit_command(request: AuditRequest, x_sentinel_token: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    """
    Audit a shell command through Sentinel's security layers.
    
    Layer 1: Deterministic blocklist (<1ms)
    Layer 2: LLM semantic analysis (~500ms) if available
    
    Returns audit decision with execution results if approved.
    """
    if runtime is None:
        raise HTTPException(status_code=503, detail="Sentinel runtime not initialized")

    _verify_auth(x_sentinel_token)
    
    if not request.command or not request.command.strip():
        return {
            "allowed": False,
            "risk_score": 10,
            "reason": "Empty command",
            "stdout": "",
            "stderr": "",
            "returncode": None,
        }
    
    start_time = time.time()
    try:
        result = runtime.run_intercepted_command(request.command)
        
        # HITL Hook
        if result.get("status") == "review_required":
            req_id = approval_manager.create_request(
                command=request.command, 
                rule_name="Policy Review", # We could extract this if we parsed the reason
                reason=result.get("reason", "Requires approval")
            )
            result["reason"] = f"{result.get('reason')} [Request ID: {req_id}]"
            print(f"⚠️  Review Required. Request ID: {req_id}")

        # Log to DB
        if db:
            db.log_audit(request.command, result)

        duration_ms = (time.time() - start_time) * 1000
        print(f"⏱️  Audit completed in {duration_ms:.2f}ms. Decision: {'✅' if result['allowed'] else '❌'} ({result.get('reason', 'No reason provided')})")
        return result
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        print(f"❌ Audit failed in {duration_ms:.2f}ms: {e}")
        raise


@app.post("/audit-only")
def audit_only(request: AuditRequest, x_sentinel_token: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    """
    Audit a command WITHOUT executing it.
    Returns the audit decision only.
    """
    if runtime is None:
        raise HTTPException(status_code=503, detail="Sentinel runtime not initialized")

    _verify_auth(x_sentinel_token)
    
    # Use the command auditor directly for audit-only
    decision = runtime.command_auditor.audit(request.command)
    return decision.to_dict()


@app.get("/pending", response_model=Dict[str, PendingRequest])
def list_pending_requests(x_sentinel_token: Optional[str] = Header(default=None)):
    """List all pending approval requests."""
    _verify_auth(x_sentinel_token)
    return approval_manager.list_pending()


@app.post("/approve/{request_id}")
def approve_request(request_id: str, x_sentinel_token: Optional[str] = Header(default=None)):
    """Approve and execute a pending request."""
    _verify_auth(x_sentinel_token)
    
    req = approval_manager.get_request(request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    
    if req.status != "pending":
        raise HTTPException(status_code=400, detail=f"Request is already {req.status}")
    
    print(f"✅ Approving request {request_id}: {req.command}")
    
    # Execute with policy bypass
    try:
        if runtime is None:
             raise HTTPException(status_code=503, detail="Sentinel runtime not initialized")
             
        result = runtime.run_intercepted_command(req.command, bypass_policy=True)
        approval_manager.resolve_request(request_id, "approved")
        return result
    except Exception as e:
        print(f"❌ Execution failed for approved request {request_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("SENTINEL_PORT", "8765"))
    host = os.getenv("SENTINEL_HOST", "127.0.0.1").strip() or "127.0.0.1"
    print(f"🛡️  Starting Sentinel Security Gateway on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")
