# 🛡️ Sentinel

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

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
SENTINEL_MODEL=gemini-3-pro-preview
SENTINEL_AUTH_TOKEN=replace_with_long_random_value
SENTINEL_HOST=127.0.0.1
SENTINEL_ALLOWED_ORIGINS=http://localhost,http://127.0.0.1
SENTINEL_EXEC_TIMEOUT_SEC=15
```

Callers of the HTTP API (including the OpenClaw skill) must send this same
`SENTINEL_AUTH_TOKEN` in the `X-Sentinel-Token` header.

### 3. Create Your Constitution

`Sentinel-Constitution.yaml` holds your security policy. It is intentionally
gitignored, so the repo does not ship one -- create it in the project root
before first run, using the sample under
[Constitution (Policy Configuration)](#constitution-policy-configuration)
as a starting point. Without it, the terminal and the red-team script both
exit with `FileNotFoundError`.

### 4. Test the Safe Terminal

```bash
source .venv/bin/activate
python -m src.api.shell
```

```
sentinel> ls -la
{"allowed": true, "risk_score": 1, ...}

sentinel> sudo rm -rf /
{"allowed": false, "reason": "Blocked token detected: sudo", ...}
```

---

## Integration with OpenClaw

> **On the name:** parts of this repo were renamed to "ZeroClaw" in `0515a5f`,
> but that rename was never completed -- the config schema, paths, and CLI
> this project integrates with are all OpenClaw's. The docs below describe
> what the code actually does. `claw_env.py` resolves either spelling at
> runtime, so both installs work; set `CLAW_BRAND` to pin one.

Sentinel ships as an OpenClaw **skill** in `openclaw-skill/`, exposing the
`sentinel_admin` tool. Command auditing itself runs over the HTTP API.

### Install the Skill

`enforce_config.py` registers the skill directory for you, appending it to
`skills.load.extraDirs` in the gateway config:

```bash
python3 enforce_config.py
```

To register it by hand instead, add the absolute path of `openclaw-skill/`
to `skills.load.extraDirs` in your gateway config, then restart the gateway.

### Usage in OpenClaw

The `sentinel_admin` tool takes an `action` (and an optional `target_id`):

| Action | Effect |
|--------|--------|
| `status` | Report Sentinel's current state |
| `list_pending` | List commands awaiting manual approval |
| `approve` / `reject` | Resolve a pending command by `target_id` |

### Auditing Commands over HTTP

Start the API with `python -m src.api.server`. It binds `127.0.0.1:8765`
by default (`SENTINEL_HOST` / `SENTINEL_PORT` override both).

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Liveness check |
| `POST /audit` | Audit a command and execute it if approved |
| `POST /audit-only` | Audit a command without executing it |
| `GET /pending` | List commands awaiting approval |
| `POST /approve/{request_id}` | Approve a pending command |

```bash
curl -X POST http://127.0.0.1:8765/audit-only \
  -H "X-Sentinel-Token: $SENTINEL_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"command": "sudo rm -rf /"}'
# {"allowed": false, "reason": "Blocked token detected: sudo", ...}
```

### HTTP API Hardening Defaults

- API auth is enabled by default via `X-Sentinel-Token` header.
- Server binds to `127.0.0.1` by default (`SENTINEL_HOST` override available).
- CORS defaults to localhost origins (`SENTINEL_ALLOWED_ORIGINS`).
- Command execution timeout defaults to 15s (`SENTINEL_EXEC_TIMEOUT_SEC`).

### Python Integration (Standalone)

```python
from src.sentinel.main import SentinelRuntime

runtime = SentinelRuntime()

def safe_execute(cmd: str) -> str:
    """Replace your agent's shell executor with this."""
    result = runtime.run_intercepted_command(cmd)

    if not result["allowed"]:
        raise PermissionError(f"Command blocked: {result['reason']}")

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

`pytest` is not in `requirements.txt`; install it into the venv first:

```bash
source .venv/bin/activate
pip install pytest
```

```bash
# Unit tests for the deterministic auditor (no API key needed)
python -m pytest tests/test_command_auditor.py -v

# Full suite -- test_api.py and test_monitor.py need the API and
# gateway dependencies installed
python -m pytest tests/ -v

# Red-team bypass checks (a script, not a pytest module)
python tests/red_team_test.py
```

Tests cover success paths, failure paths, edge cases, and obfuscation
detection. Everything except `test_vertex_ai.py` runs offline, but each
suite needs `Sentinel-Constitution.yaml` in the project root (see Quick
Start step 3).

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
