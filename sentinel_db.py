
import sqlite3
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from sentinel_approvals import PendingRequest

class SentinelDB:
    def __init__(self, db_path: str = "data/sentinel.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._get_conn() as conn:
            # Approvals Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS approvals (
                    id TEXT PRIMARY KEY,
                    command TEXT NOT NULL,
                    status TEXT NOT NULL,
                    rule_name TEXT,
                    reason TEXT,
                    created_at REAL NOT NULL,
                    resolved_at REAL
                )
            """)
            
            # Audit Logs Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    command TEXT NOT NULL,
                    allowed BOOLEAN NOT NULL,
                    risk_score INTEGER,
                    reason TEXT,
                    details JSON
                )
            """)
            conn.commit()

    def insert_approval(self, request: PendingRequest):
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO approvals (id, command, status, rule_name, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (request.id, request.command, request.status, request.rule_name, request.reason, request.created_at)
            )
            conn.commit()

    def get_pending_approvals(self) -> Dict[str, PendingRequest]:
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT id, command, status, rule_name, reason, created_at FROM approvals WHERE status = 'pending'")
            results = {}
            for row in cursor.fetchall():
                req = PendingRequest(
                    id=row[0],
                    command=row[1],
                    status=row[2],
                    rule_name=row[3],
                    reason=row[4],
                    created_at=row[5]
                )
                results[req.id] = req
            return results

    def get_approval(self, request_id: str) -> Optional[PendingRequest]:
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT id, command, status, rule_name, reason, created_at FROM approvals WHERE id = ?", (request_id,))
            row = cursor.fetchone()
            if row:
                return PendingRequest(
                    id=row[0],
                    command=row[1],
                    status=row[2],
                    rule_name=row[3],
                    reason=row[4],
                    created_at=row[5]
                )
            return None

    def update_approval_status(self, request_id: str, status: str):
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE approvals SET status = ?, resolved_at = ? WHERE id = ?",
                (status, time.time(), request_id)
            )
            conn.commit()

    def log_audit(self, command: str, result: Dict[str, Any]):
        allowed = result.get("allowed", False)
        risk_score = result.get("risk_score", 0)
        reason = result.get("reason", "")
        details = json.dumps(result)
        
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO audit_logs (timestamp, command, allowed, risk_score, reason, details) VALUES (?, ?, ?, ?, ?, ?)",
                (time.time(), command, allowed, risk_score, reason, details)
            )
            conn.commit()
