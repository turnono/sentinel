from __future__ import annotations

import json
import os

from sentinel_main import SentinelRuntime


def main() -> None:
    model = os.getenv("SENTINEL_MODEL", "gemini-2.0-flash")
    constitution_path = os.getenv("SENTINEL_CONSTITUTION_PATH")
    runtime = SentinelRuntime(constitution_path=constitution_path, model=model)

    if runtime.startup_warning:
        print(f"[sentinel] startup warning: {runtime.startup_warning}")

    print("Sentinel Safe Terminal")
    print("Type a command to audit/execute, or 'exit' to quit.")

    while True:
        try:
            command = input("sentinel> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not command:
            continue

        if command.lower() in {"exit", "quit"}:
            break

        result = runtime.run_intercepted_command(command)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
