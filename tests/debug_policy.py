import sys
import re
from pathlib import Path
sys.path.append("/Users/<USER>/sentinel")
from sentinel_policy import PolicyEnforcer

def debug():
    enforcer = PolicyEnforcer()
    print("--- Loaded Rules ---")
    for r in enforcer.rules:
        print(f"Rule: {r.get('name')}")
        print(f"  Pattern: {r.get('pattern')}")
        print(f"  Action: {r.get('action')}")
    
    cmd = "python openclaw-skill/sentinel_admin.py list_pending"
    print(f"\n--- Testing Command: '{cmd}' ---")
    result = enforcer.evaluate(cmd)
    print(f"Result: {result}")

    # Manual regex check
    admin_pattern = "^python.*sentinel_admin.py.*"
    print(f"\nManual Regex Check: '{admin_pattern}' vs '{cmd}'")
    match = re.match(admin_pattern, cmd)
    print(f"Match: {match}")

if __name__ == "__main__":
    debug()
