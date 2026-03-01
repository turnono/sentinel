try:
    import yaml
except ImportError:
    yaml = None

import re
import os
from pathlib import Path
from typing import Optional, Dict, Any, List

class PolicyEnforcer:
    def __init__(self, policy_path: Optional[str] = None):
        if policy_path:
            self.policy_path = Path(policy_path)
        else:
            # Default to policies/security.yaml relative to this file
            self.policy_path = Path(__file__).parent / "policies" / "security.yaml"
        
        self.policy = self._load_policy()
        self.rules = self.policy.get("rules", [])
        self.default_action = self.policy.get("default_action", "block")

    def _load_policy(self) -> Dict[str, Any]:
        if not self.policy_path.exists():
            print(f"⚠️  Policy file not found at {self.policy_path}. Using safe defaults.")
            return {"default_action": "block", "rules": []}
        
        try:
            with open(self.policy_path, "r") as f:
                if yaml:
                    return yaml.safe_load(f) or {}
                else:
                    return self._minimal_yaml_load(f.read())
        except Exception as e:
            print(f"❌ Failed to load policy: {e}")
            return {"default_action": "block", "rules": []}

    def _minimal_yaml_load(self, raw_text: str) -> Dict[str, Any]:
        """
        Minimal YAML parser for Sentinel policy files when PyYAML is unavailable.
        """
        lines = []
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

            mode = None
            as_dict = {}
            as_list = []

            while index < len(lines):
                indent, content = lines[index]
                if indent < expected_indent:
                    break
                if indent > expected_indent:
                    raise ValueError(f"Unexpected indentation at: {content!r}")

                is_list_start = content.startswith("- ")
                if content == "-":
                    is_list_start = True
                
                if is_list_start:
                    if mode is None: mode = "list"
                    elif mode != "list": raise ValueError("Invalid YAML: mixed list and mapping.")
                    
                    if content == "-":
                        item = ""
                    else:
                        item = content[2:].strip()
                        
                    index += 1
                    if item == "":
                        as_list.append(parse_block(expected_indent + 2))
                    else:
                        as_list.append(parse_scalar(item))
                    continue

                if mode is None: mode = "dict"
                elif mode != "dict": raise ValueError("Invalid YAML: mixed mapping and list.")

                if ":" not in content:
                    raise ValueError(f"Invalid YAML mapping line: {content!r}")

                key, raw_value = content.split(":", 1)
                key = key.strip()
                value = raw_value.strip()
                index += 1

                if value:
                    as_dict[key] = parse_scalar(value)
                else:
                    if index < len(lines) and lines[index][0] > expected_indent:
                        as_dict[key] = parse_block(expected_indent + 2)
                    else:
                        as_dict[key] = {}

            if mode == "list":
                return as_list
            return as_dict

        def parse_scalar(value: str) -> Any:
            lowered = value.lower()
            if lowered == "true": return True
            if lowered == "false": return False
            if value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
                return int(value)
            if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                return value[1:-1]
            return value

        parsed = parse_block(0)
        if not isinstance(parsed, dict):
            return {}
        return parsed

    def evaluate(self, command: str) -> Dict[str, Any]:
        """
        Evaluate a command against the policy.
        Returns a dict with 'action', 'rule_name', and 'reason'.
        """
        # Strip command to basic form for matching (simple heuristic)
        # In a real system, we'd want robust parsing (shlex based)
        cmd_str = command.strip()

        for rule in self.rules:
            pattern = rule.get("pattern", "")
            if not pattern:
                continue
            
            try:
                if re.match(pattern, cmd_str):
                    return {
                        "action": rule.get("action", "block"),
                        "rule_name": rule.get("name", "Unknown Rule"),
                        "reason": rule.get("description", "Matched policy rule")
                    }
            except re.error:
                print(f"⚠️  Invalid regex pattern in rule: {rule.get('name')}")
                continue
        
        return {
            "action": self.default_action,
            "rule_name": "Default Policy",
            "reason": "No specific rule matched, applying default action"
        }
