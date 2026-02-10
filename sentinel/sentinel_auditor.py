from __future__ import annotations

import ast
import inspect
import json
import re
from importlib import import_module
from typing import Any, Optional

from sentinel.models import AuditDecision

# ADK imports for runner-based invocation
try:
    from google.adk.runners import InMemoryRunner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types
    _ADK_RUNNER_AVAILABLE = True
except ImportError:
    _ADK_RUNNER_AVAILABLE = False


SENTINEL_AUDITOR_SYSTEM_INSTRUCTION = (
    "You are the Sentinel Command Auditor. Your sole purpose is to analyze shell "
    "commands for malicious intent, obfuscation, or policy violations. You operate "
    "on a Zero-Trust, Fail-Closed basis. If a command is ambiguous, you must "
    "REJECT. You do not explain yourself to the user; you only return a structured "
    "JSON response: {'allowed': boolean, 'risk_score': 0-10, 'reason': string}."
)


class SentinelAuditor:
    def __init__(self, model: str = "gemini-2.0-flash", agent_name: str = "sentinel_auditor") -> None:
        llm_agent_cls = self._resolve_llm_agent_class()
        if llm_agent_cls is None:
            raise RuntimeError(
                "Unable to import LlmAgent. Install Google ADK and ensure either "
                "'google.adk.agents' or 'google_adk.agents' is available."
            )

        kwargs = self._build_constructor_kwargs(llm_agent_cls, agent_name, model)
        self.agent = llm_agent_cls(**kwargs)
        
        # Initialize runner for proper invocation
        self._runner = None
        self._session_service = None
        if _ADK_RUNNER_AVAILABLE:
            try:
                self._session_service = InMemorySessionService()
                self._runner = InMemoryRunner(
                    agent=self.agent,
                    app_name="sentinel",
                    session_service=self._session_service,
                )
            except Exception:
                pass  # Fall back to direct invocation attempts

    def audit_command(self, command: str, constitution: Optional[dict[str, Any]] = None) -> AuditDecision:
        context_str = ""
        if constitution:
            context = constitution.get("strategic_context", {})
            semantic = constitution.get("semantic_instructions", {})
            if context:
                context_str += f"\nSTRATEGIC CONTEXT:\n{json.dumps(context, indent=2)}\n"
            if semantic:
                context_str += f"\nSEMANTIC INSTRUCTIONS:\n{json.dumps(semantic, indent=2)}\n"

        prompt = (
            "Analyze this shell command under Sentinel policy and return JSON only with keys: "
            "allowed (bool), risk_score (0-10 int), reason (string). "
            "Apply zero-trust and fail-closed logic. "
            "Treat ambiguity as malicious. "
            "Explicitly detect indirect data exfiltration patterns: reading local files/secrets, "
            "encoding/chunking them, then transmitting via URL params, headers, request bodies, "
            "DNS lookups, webhooks, or chained subprocesses.\n"
            f"{context_str}\n"
            f"Command: {command}"
        )

        try:
            raw_response = self._invoke_agent(prompt)
            parsed = self._parse_json_response(raw_response)
            return AuditDecision(
                allowed=bool(parsed["allowed"]),
                risk_score=int(max(0, min(10, int(parsed["risk_score"])))),
                reason=str(parsed["reason"]).strip() or "No reason provided",
            )
        except Exception as exc:
            return AuditDecision.reject(f"LLM auditor failure: {exc}", risk_score=10)

    def _invoke_agent(self, prompt: str) -> Any:
        # Method 1: Try google.genai client directly (most reliable)
        try:
            import os
            from dotenv import load_dotenv
            load_dotenv()
            
            from google import genai
            api_key = os.getenv('GOOGLE_API_KEY')
            if api_key:
                client = genai.Client(api_key=api_key)
                request_kwargs = {
                    "model": self.agent.model if hasattr(self.agent, 'model') else "gemini-2.0-flash",
                    "contents": prompt,
                }
                try:
                    request_kwargs["config"] = types.GenerateContentConfig(
                        system_instruction=SENTINEL_AUDITOR_SYSTEM_INSTRUCTION,
                    )
                except Exception:
                    request_kwargs["contents"] = (
                        f"{SENTINEL_AUDITOR_SYSTEM_INSTRUCTION}\n\n{prompt}"
                    )

                response = client.models.generate_content(**request_kwargs)
                if hasattr(response, 'text'):
                    return response.text
        except Exception:
            pass
        
        # Method 2: Try InMemoryRunner if available
        if self._runner is not None:
            try:
                session = self._session_service.create_session(
                    app_name="sentinel",
                    user_id="sentinel_user",
                )
                user_content = types.Content(
                    role="user",
                    parts=[types.Part(text=prompt)]
                )
                response_parts = []
                for event in self._runner.run(
                    user_id="sentinel_user",
                    session_id=session.id,
                    new_message=user_content,
                ):
                    if hasattr(event, 'content') and event.content:
                        for part in event.content.parts:
                            if hasattr(part, 'text') and part.text:
                                response_parts.append(part.text)
                if response_parts:
                    return "\n".join(response_parts)
            except Exception:
                pass
        
        raise RuntimeError("No supported invocation method found on ADK LlmAgent.")

    def _parse_json_response(self, response: Any) -> dict[str, Any]:
        text = self._response_to_text(response)
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise ValueError(f"No JSON object found in response: {text!r}")

        payload = match.group(0)

        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            data = ast.literal_eval(payload)

        if not isinstance(data, dict):
            raise ValueError("Auditor output is not a dictionary.")

        for field in ("allowed", "risk_score", "reason"):
            if field not in data:
                raise ValueError(f"Missing required field: {field}")

        if not isinstance(data["allowed"], bool):
            raise ValueError("Field 'allowed' must be a boolean.")
        if not isinstance(data["risk_score"], int):
            raise ValueError("Field 'risk_score' must be an integer.")
        if not isinstance(data["reason"], str):
            raise ValueError("Field 'reason' must be a string.")

        return data

    def _response_to_text(self, response: Any) -> str:
        if isinstance(response, str):
            return response

        if isinstance(response, dict):
            for key in ("text", "output_text", "response", "content"):
                if key in response and isinstance(response[key], str):
                    return response[key]

        for attr in ("text", "output_text", "response"):
            value = getattr(response, attr, None)
            if isinstance(value, str):
                return value

        return str(response)

    def _build_constructor_kwargs(self, llm_agent_cls: type, agent_name: str, model: str) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        signature = inspect.signature(llm_agent_cls)

        if "name" in signature.parameters:
            kwargs["name"] = agent_name
        if "model" in signature.parameters:
            kwargs["model"] = model
        if "instruction" in signature.parameters:
            kwargs["instruction"] = SENTINEL_AUDITOR_SYSTEM_INSTRUCTION
        elif "system_instruction" in signature.parameters:
            kwargs["system_instruction"] = SENTINEL_AUDITOR_SYSTEM_INSTRUCTION
        else:
            kwargs["instruction"] = SENTINEL_AUDITOR_SYSTEM_INSTRUCTION

        return kwargs

    @staticmethod
    def _resolve_llm_agent_class() -> Optional[type]:
        candidates = (
            ("google.adk.agents", "LlmAgent"),
            ("google_adk.agents", "LlmAgent"),
        )

        for module_name, class_name in candidates:
            try:
                module = import_module(module_name)
                return getattr(module, class_name)
            except Exception:
                continue

        return None
