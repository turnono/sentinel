# 🛡️ Sentinel

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-26%20passing-brightgreen.svg)]()

**Sentinel** is a security gateway for agentic AI frameworks. It intercepts shell commands, applies deterministic guardrails, and only executes commands that pass policy.

> 🔐 **Fail-closed by design**: Ambiguous or non-compliant commands are rejected by default.

---

## The Problem: Agent Autonomy vs. Security

AI agent frameworks are powerful, but unrestricted command execution creates enterprise-risk outcomes:

- 🔴 **Privilege escalation**: `sudo`, `rm -rf`, filesystem formatting
- 🔴 **Credential exposure**: `~/.ssh`, `.env`, `/etc/`
- 🔴 **Data exfiltration**: Unapproved outbound network calls
- 🔴 **Obfuscation attacks**: `s\u\d\o`, base64 decode pipelines

Sentinel solves this with a **two-layer security model**.

---

## Brains Behind the Security: Google ADK

Sentinel isn't just a set of rules; it's an intelligent gateway powered by the **Google Agent Development Kit (ADK)**. 

By leveraging **Gemini 3 Pro** as its semantic core, Sentinel can:
- **Understand Intent**: Distinguish between helpful commands and malicious obfuscation.
- **Enterprise-Grade Reasoning**: Apply sophisticated logic to every command before it reaches your shell.
- **Fail-Safe Privacy**: Ensure that sensitive data remains protected by an industry-leading AI security layer.

Because it's built on Google's world-class AI infrastructure, Sentinel provides a level of security that standard pattern-matching tools simply can't match.

---

## Architecture

```
┌─────────────────┐     ┌───────────────┐     ┌─────────────────┐
│   AI Agent      │ ──► │   SENTINEL    │ ──► │  Shell          │
│  (OpenClaw)     │     │   Gateway     │     │  Executor       │
└─────────────────┘     └───────────────┘     └─────────────────┘
                               │
                    ┌──────────┴──────────┐
                    │ 1. Hard-Kill Filter │  Instant, deterministic
                    │ 2. LLM Auditor      │  Semantic risk analysis
                    │ 3. Fail-Closed      │  Reject if uncertain
                    └─────────────────────┘
```

| Layer | Component | Purpose |
|-------|-----------|---------|
| 1️⃣ | `CommandAuditor` | Blocks known-dangerous patterns, normalizes obfuscation |
| 2️⃣ | `SentinelAuditor` | LLM-backed semantic analysis for complex threats |
| 3️⃣ | `SentinelRuntime` | Orchestrates audit chain, executes approved commands |

---

## Quick Start

### 1. Clone and Setup

```bash
git clone https://github.com/turnono/sentinel.git
cd sentinel
bash setup.sh
```

### 2. Configure Your API Key

```bash
cp .env.example .env
```

Edit `.env` and add your Google API key:

```env
GOOGLE_API_KEY=your_google_api_key_here
SENTINEL_MODEL=gemini-2.0-flash
SENTINEL_AUTH_TOKEN=replace_with_long_random_value
SENTINEL_HOST=127.0.0.1
SENTINEL_ALLOWED_ORIGINS=http://localhost,http://127.0.0.1
SENTINEL_EXEC_TIMEOUT_SEC=15
```

For OpenClaw plugin calls, set the same `SENTINEL_AUTH_TOKEN` in the plugin environment.

### 3. Test the Safe Terminal

```bash
source .venv/bin/activate
python sentinel_shell.py
```

```
sentinel> ls -la
{"allowed": true, "risk_score": 1, ...}

sentinel> sudo rm -rf /
{"allowed": false, "reason": "Blocked token detected: sudo", ...}
```

---

## Integration with OpenClaw

Sentinel provides a **native OpenClaw plugin** that adds the `sentinel_exec` tool to your agent.

### Quick Install (OpenClaw Plugin)

```bash
# 1. Copy plugin to OpenClaw extensions
mkdir -p ~/.openclaw/extensions/sentinel
cp openclaw-plugin/* ~/.openclaw/extensions/sentinel/

# 2. Enable in config (~/.openclaw/openclaw.json)
# Add to plugins.entries:
#   "sentinel": { "enabled": true }
# Add to tools.allow:
#   ["sentinel_exec", "group:plugins"]

# 3. Restart gateway
openclaw gateway
```

### Usage in OpenClaw TUI

```
Use sentinel_exec to run "ls -la"
→ ✅ SENTINEL APPROVED (executes command)

Use sentinel_exec to run "sudo rm -rf /"
→ 🛡️ SENTINEL BLOCKED: Blocked token detected: sudo
```

### HTTP API Hardening Defaults

- API auth is enabled by default via `X-Sentinel-Token` header.
- Server binds to `127.0.0.1` by default (`SENTINEL_HOST` override available).
- CORS defaults to localhost origins (`SENTINEL_ALLOWED_ORIGINS`).
- Command execution timeout defaults to 15s (`SENTINEL_EXEC_TIMEOUT_SEC`).

### Python Integration (Standalone)

```python
from sentinel import SentinelRuntime

runtime = SentinelRuntime()

def safe_execute(cmd: str) -> str:
    """Replace your agent's shell executor with this."""
    result = runtime.run_intercepted_command(cmd)
    
    if not result["allowed"]:
        raise SecurityError(f"Command blocked: {result['reason']}")
    
    return result["stdout"]
```

---

## Constitution (Policy Configuration)

The constitution file (`Sentinel-Constitution.yaml`) defines your security policy:

```yaml
hard_kill:
  blocked_strings:
    - sudo
    - rm -rf
    - mkfs
  blocked_paths:
    - ~/.ssh
    - ~/.env
    - /etc/
  blocked_tools:
    - python
    - pip
    - npm

network_lock:
  blocked_tools:
    - curl
    - wget
  whitelisted_domains:
    - api.openclaw.example

execution_mode:
  lockdown_mode: false        # Set true for strict allowlist
  allowed_commands:
    - ls
    - pwd
    - echo
```

### Lockdown Mode

When `lockdown_mode: true`, **only commands in `allowed_commands` are permitted**. Everything else is rejected.

---

## Running Tests

```bash
# All tests
python -m pytest tests/ -v

# Red-team bypass tests
python tests/red_team_test.py

# Comprehensive unit tests
python tests/test_command_auditor.py
```

**Test coverage**: 26 tests covering success paths, failure paths, edge cases, and obfuscation detection.

---

## Security Features

| Feature | Description |
|---------|-------------|
| **Blocked Strings** | Rejects commands containing dangerous tokens |
| **Blocked Paths** | Prevents access to sensitive directories |
| **Blocked Tools** | Stops execution of dangerous binaries |
| **Domain Allowlist** | Only permits network calls to whitelisted domains |
| **Obfuscation Detection** | Normalizes unicode, backslash escapes, base64 pipelines |
| **Lockdown Mode** | Strict allowlist for maximum security |
| **Audit Logging** | JSON audit trail for compliance |
| **Fail-Closed** | Rejects on any uncertainty or error |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

---

## License

MIT License - see [LICENSE](LICENSE) for details.

---

## Security

If you discover a security vulnerability, please open an issue or contact the maintainers directly. Do not disclose security issues publicly until they are addressed.
