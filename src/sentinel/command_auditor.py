from __future__ import annotations

import re
import shlex
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable, Optional
from urllib.parse import urlparse

from .models import AuditDecision
from .sentinel_auditor import SentinelAuditor

ENV_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")


@dataclass(frozen=True)
class HardKillConfig:
    blocked_strings: tuple[str, ...]
    blocked_paths: tuple[str, ...]
    blocked_tools: tuple[str, ...]
    blocked_network_tools: tuple[str, ...]
    whitelisted_domains: tuple[str, ...]
    lockdown_mode: bool
    allowed_commands: tuple[str, ...]


class CommandAuditor:
    def __init__(self, constitution: dict[str, Any], llm_auditor: Optional[SentinelAuditor] = None) -> None:
        self.constitution = constitution or {}
        self.llm_auditor = llm_auditor
        self.config = self._load_config(self.constitution)

    def audit(self, command: str) -> AuditDecision:
        normalized_command = self._normalize_command(command)

        deterministic_decision = self._hard_kill_filter(normalized_command)
        if deterministic_decision is not None:
            return deterministic_decision

        if self._is_allowed_in_lockdown(normalized_command):
            return AuditDecision(allowed=True, risk_score=0, reason="Command explicitly allowed by policy.")

        if self.llm_auditor is None:
            return AuditDecision.reject("LLM auditor unavailable; fail-closed policy applied.", risk_score=9)

        return self.llm_auditor.audit_command(normalized_command, constitution=self.constitution)

    def _hard_kill_filter(self, command: str) -> Optional[AuditDecision]:
        if not command.strip():
            return AuditDecision.reject("Empty command is rejected under fail-closed policy.", risk_score=10)

        if self.config.lockdown_mode and not self._is_allowed_in_lockdown(command):
            return AuditDecision.reject("Lockdown mode active: command not in allowed_commands.", risk_score=10)

        lowered_command = command.lower()

        for blocked in self.config.blocked_strings:
            if blocked.lower() in lowered_command:
                return AuditDecision.reject(f"Blocked token detected: {blocked}", risk_score=10)

        for blocked_path in self.config.blocked_paths:
            if blocked_path.lower() in lowered_command:
                return AuditDecision.reject(f"Blocked path access detected: {blocked_path}", risk_score=10)

        blocked_tool = self._match_blocked_tool(command)
        if blocked_tool is not None:
            return AuditDecision.reject(f"Blocked tool detected: {blocked_tool}", risk_score=10)

        if self._contains_base64_shell_exec(lowered_command):
            return AuditDecision.reject("Obfuscated payload execution pattern detected: base64 to shell.", risk_score=10)

        if self._contains_network_tool(command):
            urls = self._extract_urls(command)
            if not urls:
                return AuditDecision.reject(
                    "Network command without explicit URL/domain is rejected.",
                    risk_score=10,
                )

            for url in urls:
                domain = self._extract_domain(url)
                if not domain:
                    return AuditDecision.reject(f"Could not parse domain from network target: {url}", risk_score=10)
                if not self._is_whitelisted_domain(domain):
                    return AuditDecision.reject(
                        f"Outbound network domain not whitelisted: {domain}",
                        risk_score=10,
                    )

        return None

    def _is_allowed_in_lockdown(self, command: str) -> bool:
        if not self.config.allowed_commands:
            return False

        normalized_command = command.strip().lower()
        if self._contains_shell_control(normalized_command):
            return False

        try:
            tokens = shlex.split(command, posix=True)
        except ValueError:
            tokens = command.split()

        first_token = tokens[0].lower() if tokens else ""
        first_basename = first_token.rsplit("/", 1)[-1]

        for allowed in self.config.allowed_commands:
            allowed_normalized = self._normalize_command(allowed).lower()
            if not allowed_normalized:
                continue

            if " " in allowed_normalized:
                if normalized_command == allowed_normalized:
                    return True
                if normalized_command.startswith(allowed_normalized):
                    suffix = normalized_command[len(allowed_normalized):]
                    if self._is_safe_lockdown_suffix(suffix):
                        return True
            elif normalized_command == allowed_normalized or normalized_command.startswith(f"{allowed_normalized} "):
                return True

            if first_token == allowed_normalized or first_basename == allowed_normalized:
                return True

        return False

    @staticmethod
    def _contains_shell_control(command: str) -> bool:
        if "$(" in command or "\n" in command or "\r" in command:
            return True
        return bool(re.search(r"(?:\|\||&&|[;|`<>])", command))

    @staticmethod
    def _is_safe_lockdown_suffix(suffix: str) -> bool:
        if not suffix:
            return True

        stripped = suffix.lstrip()
        if not stripped:
            return True

        return not bool(re.match(r"^(?:[;&|`<>]|\$\()", stripped))

    @staticmethod
    def _normalize_command(command: str) -> str:
        normalized = unicodedata.normalize("NFKC", command or "")
        normalized = normalized.replace("\u200b", "")
        normalized = CommandAuditor._decode_ansi_c_strings(normalized)
        normalized = CommandAuditor._decode_common_escapes(normalized)

        # Join escaped newlines and strip common shell backslash-obfuscation.
        normalized = re.sub(r"\\\r?\n", "", normalized)
        normalized = re.sub(r"\\+([^\s])", r"\1", normalized)
        normalized = re.sub(r"\\+\s+", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized.strip()

    @staticmethod
    def _decode_ansi_c_strings(command: str) -> str:
        def _replace(match: re.Match[str]) -> str:
            payload = match.group(1)
            try:
                return bytes(payload, "utf-8").decode("unicode_escape")
            except Exception:
                return payload

        return re.sub(r"\$'([^']*)'", _replace, command)

    @staticmethod
    def _decode_common_escapes(command: str) -> str:
        if "\\" not in command:
            return command

        decoded = re.sub(r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), command)
        decoded = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), decoded)
        decoded = re.sub(r"\\U([0-9a-fA-F]{8})", lambda m: chr(int(m.group(1), 16)), decoded)
        decoded = re.sub(r"\\([0-7]{1,3})", lambda m: chr(int(m.group(1), 8)), decoded)
        return decoded

    def _contains_network_tool(self, command: str) -> bool:
        executable = self._extract_executable(command)
        if executable is None:
            return False

        for tool in self.config.blocked_network_tools:
            if executable == tool.lower().strip():
                return True
        return False

    def _match_blocked_tool(self, command: str) -> Optional[str]:
        candidate = self._extract_executable(command)
        if candidate is None:
            return None

        for blocked_tool in self.config.blocked_tools:
            blocked = blocked_tool.lower().strip()
            if candidate == blocked:
                return blocked_tool

            if blocked == "python" and re.fullmatch(r"python(?:\d+(?:\.\d+)*)?", candidate):
                return blocked_tool

        return None

    def _extract_executable(self, command: str) -> Optional[str]:
        try:
            tokens = shlex.split(command, posix=True)
        except ValueError:
            tokens = command.split()

        if not tokens:
            return None

        start_index = 0
        first_token = tokens[0].strip().lower().rsplit("/", 1)[-1]
        if first_token == "env":
            start_index = 1
            while start_index < len(tokens):
                token = tokens[start_index].strip()
                if not token:
                    start_index += 1
                    continue
                if token == "--":
                    start_index += 1
                    break
                if token.startswith("-"):
                    start_index += 1
                    continue
                if ENV_ASSIGNMENT_RE.fullmatch(token):
                    start_index += 1
                    continue
                break

        for token in tokens[start_index:]:
            stripped = token.strip()
            if not stripped or ENV_ASSIGNMENT_RE.fullmatch(stripped):
                continue
            return stripped.lower().rsplit("/", 1)[-1]

        return None

    @staticmethod
    def _contains_base64_shell_exec(lowered_command: str) -> bool:
        has_base64_decode = "base64 -d" in lowered_command or "base64 --decode" in lowered_command
        invokes_shell = bool(re.search(r"(?:\||&&|;)\s*(?:bash|sh)\b", lowered_command))
        return has_base64_decode and invokes_shell

    def _extract_urls(self, command: str) -> list[str]:
        urls: list[str] = []

        try:
            tokens = shlex.split(command, posix=True)
        except ValueError:
            return urls

        for token in tokens:
            if token.startswith("http://") or token.startswith("https://"):
                urls.append(token)

        if urls:
            return urls

        # Fallback to raw regex extraction in case of unusual quoting.
        return re.findall(r"https?://[^\s'\"]+", command)

    def _extract_domain(self, url: str) -> Optional[str]:
        parsed = urlparse(url)
        if parsed.hostname:
            return parsed.hostname.lower()
        return None

    def _is_whitelisted_domain(self, domain: str) -> bool:
        for allowed in self.config.whitelisted_domains:
            candidate = allowed.lower().strip()
            if domain == candidate or domain.endswith(f".{candidate}"):
                return True
        return False

    @staticmethod
    def _load_config(constitution: dict[str, Any]) -> HardKillConfig:
        hard_kill = constitution.get("hard_kill", {})
        network_lock = constitution.get("network_lock", {})
        execution_mode = constitution.get("execution_mode", {})

        blocked_strings = _as_tuple(hard_kill.get("blocked_strings"), default=("sudo", "rm -rf", "mkfs"))
        blocked_paths = _as_tuple(hard_kill.get("blocked_paths"), default=("~/.ssh", "~/.env", "/etc/"))
        blocked_tools = _as_tuple(hard_kill.get("blocked_tools"), default=("python", "pip", "npm"))

        blocked_network_tools = _as_tuple(network_lock.get("blocked_tools"), default=("curl", "wget"))

        whitelisted_domains = _as_tuple(
            network_lock.get("whitelisted_domains", constitution.get("whitelisted_domains", ())),
            default=(),
        )
        lockdown_mode = bool(execution_mode.get("lockdown_mode", constitution.get("lockdown_mode", False)))
        allowed_commands = _as_tuple(
            execution_mode.get("allowed_commands", constitution.get("allowed_commands", ())),
            default=(),
        )

        return HardKillConfig(
            blocked_strings=blocked_strings,
            blocked_paths=blocked_paths,
            blocked_tools=blocked_tools,
            blocked_network_tools=blocked_network_tools,
            whitelisted_domains=whitelisted_domains,
            lockdown_mode=lockdown_mode,
            allowed_commands=allowed_commands,
        )


def _as_tuple(value: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return default
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Iterable):
        return tuple(str(item) for item in value)
    return default
