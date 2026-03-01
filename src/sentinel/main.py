from __future__ import annotations

import inspect
import json
import logging
import os
import shlex
import subprocess
from importlib import import_module
from pathlib import Path
from typing import Any, Optional

from .command_auditor import CommandAuditor
from .sentinel_auditor import SentinelAuditor
from .models import AuditDecision
from .policy import PolicyEnforcer

try:
    import yaml
except ImportError as exc:
    yaml = None
    _YAML_IMPORT_ERROR = exc
else:
    _YAML_IMPORT_ERROR = None


DEFAULT_CONSTITUTION_CANDIDATES = (
    "Sentinel-Constitution.yaml",
)

PROJECT_ROOT = Path(__file__).resolve().parent
AUDIT_LOG_PATH = PROJECT_ROOT / "logs" / "sentinel_audit.log"
DEFAULT_EXEC_TIMEOUT_SECONDS = 15.0


def _autoload_dotenv() -> None:
    """
    Best-effort .env support.
    If python-dotenv is not installed, this is a no-op and runtime will use
    standard OS environment variables only.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    env_paths = (
        Path(".env"),
        PROJECT_ROOT / ".env",
    )
    for env_path in env_paths:
        if env_path.exists():
            load_dotenv(dotenv_path=env_path, override=False)
            return

    load_dotenv(override=False)


_autoload_dotenv()


def _build_audit_logger() -> logging.Logger:
    logger = logging.getLogger("sentinel.audit")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(AUDIT_LOG_PATH, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger


_AUDIT_LOGGER: Optional[logging.Logger] = None


def _get_audit_logger() -> Optional[logging.Logger]:
    global _AUDIT_LOGGER
    if _AUDIT_LOGGER is not None:
        return _AUDIT_LOGGER

    try:
        _AUDIT_LOGGER = _build_audit_logger()
    except Exception:
        _AUDIT_LOGGER = None
    return _AUDIT_LOGGER


def _log_audit_event(command: str, payload: dict[str, Any]) -> None:
    logger = _get_audit_logger()
    if logger is None:
        return

    event = {
        "command": command,
        "allowed": bool(payload.get("allowed", False)),
        "risk_score": int(payload.get("risk_score", 10)),
        "reason": str(payload.get("reason", "")),
        "returncode": payload.get("returncode"),
    }
    try:
        logger.info(json.dumps(event, ensure_ascii=True))
    except Exception:
        # Logging failures must never affect command interception outcomes.
        pass


def _parse_execution_timeout(raw_timeout: str | None) -> float:
    if raw_timeout is None:
        return DEFAULT_EXEC_TIMEOUT_SECONDS

    try:
        parsed = float(raw_timeout)
    except (TypeError, ValueError):
        return DEFAULT_EXEC_TIMEOUT_SECONDS

    if parsed < 1:
        return 1.0
    if parsed > 300:
        return 300.0
    return parsed


class SentinelRuntime:
    def __init__(self, constitution_path: str | Path | None = None, model: str | None = None) -> None:
        if constitution_path is None:
            env_constitution = os.getenv("SENTINEL_CONSTITUTION_PATH", "").strip()
            if env_constitution:
                constitution_path = env_constitution

        resolved_model = (model or os.getenv("SENTINEL_MODEL", "gemini-3-pro-preview")).strip() or "gemini-3-pro-preview"

        self.constitution_path = self._resolve_constitution_path(constitution_path)
        self.constitution = load_constitution(self.constitution_path)
        self.execution_timeout_seconds = _parse_execution_timeout(os.getenv("SENTINEL_EXEC_TIMEOUT_SEC"))
        self.startup_warning: Optional[str] = None
        try:
            self.sentinel_auditor: Optional[SentinelAuditor] = SentinelAuditor(model=resolved_model)
        except Exception as exc:
            # Fail-closed: deterministic layer still runs and anything not deterministically
            # cleared is rejected because no LLM auditor is available.
            self.sentinel_auditor = None
            self.startup_warning = str(exc)
        self.command_auditor = CommandAuditor(self.constitution, llm_auditor=self.sentinel_auditor)
        self.orchestrator = initialize_adk_environment(self.sentinel_auditor)
        self.policy_enforcer = PolicyEnforcer()

    def run_intercepted_command(self, cmd_string: str, bypass_policy: bool = False) -> dict[str, Any]:
        decision = None
        
        # 0. Policy Check (ZeroClaw Hardening)
        if not bypass_policy:
            policy_result = self.policy_enforcer.evaluate(cmd_string)
            action = policy_result.get("action", "block")
            
            if action == "block":
                failed = AuditDecision.reject(
                    f"Policy Violation: {policy_result.get('rule_name', 'Unknown')} - {policy_result.get('reason', 'Blocked by policy')}", 
                    risk_score=10
                )
                payload = failed.to_dict()
                payload.update({"returncode": None, "stdout": "", "stderr": ""})
                _log_audit_event(cmd_string, payload)
                return payload

            if action == "review":
                # TODO: Integrate with HITL system. For now, we block with a specific message.
                failed = AuditDecision.reject(
                    f"Review Required: {policy_result.get('rule_name', 'Unknown')} - {policy_result.get('reason', 'Requires approval')}", 
                    risk_score=5
                )
                payload = failed.to_dict()
                # Mark it as 'review_required' for the API response if we support it in the future
                payload["status"] = "review_required" 
                payload.update({"returncode": None, "stdout": "", "stderr": ""})
                _log_audit_event(cmd_string, payload)
                return payload

            if action == "allow":
                decision = AuditDecision(
                    allowed=True, 
                    risk_score=0, 
                    reason=f"Allowed by policy: {policy_result.get('rule_name', 'Policy Allow')}"
                )
                # Fall through to execution logic
        
        if decision is None:
            if bypass_policy:
                decision = AuditDecision(allowed=True, risk_score=0, reason="User Approved via HITL")
            else:
                # 1. Standard Sentinel Audit
                decision = self.command_auditor.audit(cmd_string)
        
        payload: dict[str, Any] = decision.to_dict()

        if not decision.allowed:
            payload.update({"returncode": None, "stdout": "", "stderr": ""})
            _log_audit_event(cmd_string, payload)
            return payload

        # Shell Execution Patch: Detect shell operators (| , > , &&)
        # If present, use shell=True and pass the full string.
        # Otherwise, keep the safer shell=False with shlex.split.
        shell_operators = {"|", ">", "&&", ";", "<<", ">>"}
        use_shell = any(op in cmd_string for op in shell_operators)

        if use_shell:
            cmd_args = cmd_string
        else:
            try:
                cmd_args = shlex.split(cmd_string, posix=True)
            except ValueError as exc:
                failed = AuditDecision.reject(f"Command parsing failed: {exc}", risk_score=10)
                payload = failed.to_dict()
                payload.update({"returncode": None, "stdout": "", "stderr": ""})
                _log_audit_event(cmd_string, payload)
                return payload

        try:
            completed = subprocess.run(
                cmd_args,
                shell=use_shell,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.execution_timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            failed = AuditDecision.reject(
                f"Command execution timed out after {self.execution_timeout_seconds:g}s.",
                risk_score=10,
            )
            payload = failed.to_dict()
            payload.update(
                {
                    "returncode": None,
                    "stdout": exc.stdout or "",
                    "stderr": exc.stderr or "Execution timeout",
                }
            )
            _log_audit_event(cmd_string, payload)
            return payload
        except Exception as exc:
            failed = AuditDecision.reject(f"Command execution failed: {exc}", risk_score=10)
            payload = failed.to_dict()
            payload.update({"returncode": None, "stdout": "", "stderr": str(exc)})
            _log_audit_event(cmd_string, payload)
            return payload

        payload.update(
            {
                "returncode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
        )
        _log_audit_event(cmd_string, payload)
        return payload

    def _resolve_constitution_path(self, constitution_path: str | Path | None) -> Path:
        if constitution_path is not None:
            path = Path(constitution_path)
            if not path.exists():
                raise FileNotFoundError(f"Constitution file not found: {path}")
            return path

        for candidate in DEFAULT_CONSTITUTION_CANDIDATES:
            path = Path(candidate)
            if path.exists():
                return path
            project_path = PROJECT_ROOT / candidate
            if project_path.exists():
                return project_path

        raise FileNotFoundError(
            "No constitution file found. Expected one of: "
            + ", ".join(DEFAULT_CONSTITUTION_CANDIDATES)
        )


def load_constitution(path: str | Path) -> dict[str, Any]:
    path_obj = Path(path)
    raw_text = path_obj.read_text(encoding="utf-8")

    if yaml is not None:
        data = yaml.safe_load(raw_text) or {}
    else:
        data = _minimal_yaml_load(raw_text)

    if not isinstance(data, dict):
        raise ValueError("Constitution file must deserialize to a mapping/object.")

    return data


def initialize_adk_environment(sentinel_auditor: Optional[SentinelAuditor]) -> Optional[Any]:
    if sentinel_auditor is None:
        return None

    sequential_cls = _resolve_sequential_agent_class()
    if sequential_cls is None:
        return None

    signature = inspect.signature(sequential_cls)
    kwargs: dict[str, Any] = {}

    if "name" in signature.parameters:
        kwargs["name"] = "sentinel_orchestrator"
    if "agents" in signature.parameters:
        kwargs["agents"] = [sentinel_auditor.agent]
    elif "sub_agents" in signature.parameters:
        kwargs["sub_agents"] = [sentinel_auditor.agent]

    try:
        return sequential_cls(**kwargs)
    except Exception:
        return None


def _resolve_sequential_agent_class() -> Optional[type]:
    candidates = (
        ("google.adk.agents", "SequentialAgent"),
        ("google_adk.agents", "SequentialAgent"),
    )

    for module_name, class_name in candidates:
        try:
            module = import_module(module_name)
            return getattr(module, class_name)
        except Exception:
            continue

    return None


def _minimal_yaml_load(raw_text: str) -> dict[str, Any]:
    """
    Minimal YAML parser for Sentinel constitution files when PyYAML is unavailable.
    Supported subset:
    - indentation-based dictionaries
    - lists with '- item'
    - scalar values (string/int/bool)
    """
    lines: list[tuple[int, str]] = []
    for raw_line in raw_text.splitlines():
        stripped_comment = raw_line.split("#", 1)[0].rstrip()
        if not stripped_comment.strip():
            continue
        indent = len(stripped_comment) - len(stripped_comment.lstrip(" "))
        content = stripped_comment.strip()
        lines.append((indent, content))

    index = 0

    def parse_block(expected_indent: int) -> Any:
        nonlocal index

        if index >= len(lines) or lines[index][0] < expected_indent:
            return {}

        mode: Optional[str] = None
        as_dict: dict[str, Any] = {}
        as_list: list[Any] = []

        while index < len(lines):
            indent, content = lines[index]
            if indent < expected_indent:
                break
            if indent > expected_indent:
                raise ValueError(f"Unexpected indentation at: {content!r}")

            if content.startswith("- "):
                if mode is None:
                    mode = "list"
                elif mode != "list":
                    raise ValueError("Invalid YAML: mixed list and mapping at same indentation.")

                item = content[2:].strip()
                index += 1
                if item == "":
                    as_list.append(parse_block(expected_indent + 2))
                else:
                    as_list.append(parse_scalar(item))
                continue

            if mode is None:
                mode = "dict"
            elif mode != "dict":
                raise ValueError("Invalid YAML: mixed mapping and list at same indentation.")

            if ":" not in content:
                raise ValueError(f"Invalid YAML mapping line: {content!r}")

            key, raw_value = content.split(":", 1)
            key = key.strip()
            value = raw_value.strip()
            index += 1

            if value:
                as_dict[key] = parse_scalar(value)
                continue

            if index < len(lines) and lines[index][0] > expected_indent:
                as_dict[key] = parse_block(expected_indent + 2)
            else:
                as_dict[key] = {}

        if mode == "list":
            return as_list
        return as_dict

    def parse_scalar(value: str) -> Any:
        lowered = value.lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        if value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
            return int(value)
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            return value[1:-1]
        return value

    parsed = parse_block(0)
    if not isinstance(parsed, dict):
        raise ValueError("Constitution YAML must be a mapping at the root level.")
    return parsed


_runtime: Optional[SentinelRuntime] = None


def run_intercepted_command(cmd_string: str) -> dict[str, Any]:
    global _runtime
    if _runtime is None:
        _runtime = SentinelRuntime()
    return _runtime.run_intercepted_command(cmd_string, bypass_policy=False)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Sentinel command interception entry point")
    parser.add_argument("command", help="Shell command string to evaluate and optionally execute")
    parser.add_argument(
        "--constitution",
        default=None,
        help="Optional path to constitution YAML. Defaults to Sentinel-Constitution.yaml",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Gemini model for the SentinelAuditor (defaults to SENTINEL_MODEL or gemini-3-pro-preview).",
    )

    args = parser.parse_args()

    runtime = SentinelRuntime(constitution_path=args.constitution, model=args.model)
    result = runtime.run_intercepted_command(args.command)
    print(json.dumps(result, indent=2))
