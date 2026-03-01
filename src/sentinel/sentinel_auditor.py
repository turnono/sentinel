from __future__ import annotations

import ast
import inspect
import json
import re
import time
from collections import deque
from importlib import import_module
from pathlib import Path
from typing import Any, Optional

from .models import AuditDecision

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
    def __init__(self, model: str = "gemini-3-pro-preview", agent_name: str = "sentinel_auditor") -> None:
        llm_agent_cls = self._resolve_llm_agent_class()
        if llm_agent_cls is None:
            raise RuntimeError(
                "Unable to import LlmAgent. Install Google ADK and ensure either "
                "'google.adk.agents' or 'google_adk.agents' is available."
            )

        kwargs = self._build_constructor_kwargs(llm_agent_cls, agent_name, model)
        self.agent = llm_agent_cls(**kwargs)
        
        # Throttling & Cost Control state
        self._request_history: deque[float] = deque()
        self._last_cooldown_time = 0.0
        self._max_requests_per_window = 10
        self._window_seconds = 60
        self._cooldown_seconds = 30
        
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

        # Throttling Check
        now = time.time()
        # Clean old requests from window
        while self._request_history and self._request_history[0] < now - self._window_seconds:
            self._request_history.popleft()

        # Check if in active cool-down
        if now < self._last_cooldown_time + self._cooldown_seconds:
            wait_remaining = int(self._last_cooldown_time + self._cooldown_seconds - now)
            return AuditDecision.reject(f"Sentinel Throttle: Cool-down active. {wait_remaining}s remaining.", risk_score=5)

        # Check limit
        if len(self._request_history) >= self._max_requests_per_window:
            self._last_cooldown_time = now
            return AuditDecision.reject("Sentinel Throttle: Limit exceeded (10 req/60s). Cooling down...", risk_score=5)

        # Record request
        self._request_history.append(now)

        prompt = (
            "Analyze this RAW SHELL STRING as a SINGLE SEMANTIC UNIT under Sentinel policy. "
            "Return JSON only with keys: allowed (bool), risk_score (0-10 int), reason (string). "
            "Apply zero-trust and fail-closed logic. "
            "Treat ambiguity as malicious. "
            "Explicitly detect indirect data exfiltration patterns: reading local files/secrets, "
            "encoding/chunking them, then transmitting via URL params, headers, request bodies, "
            "DNS lookups, webhooks, or chained subprocesses.\n"
            f"{context_str}\n"
            f"RAW SHELL STRING: {command}"
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
        last_exception: Optional[Exception] = None
        max_retries = 3
        
        for attempt in range(max_retries + 1):
            try:
                # Method 1: Try google.genai client directly (most reliable)
                try:
                    import os
                    from dotenv import load_dotenv
                    load_dotenv()
                    
                    from google import genai
                    
                    use_vertex = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "false").lower() == "true"
                    project = os.getenv("GOOGLE_CLOUD_PROJECT")
                    location = os.getenv("GOOGLE_CLOUD_LOCATION")
                    api_key = os.getenv('GOOGLE_API_KEY')

                    client_kwargs = {}
                    if use_vertex and project and location:
                        import google.auth
                        from google.oauth2.credentials import Credentials as GoogleCredentials
                        
                        try:
                            credentials, _ = google.auth.default()
                        except Exception:
                            credentials = None

                        # Fallback: Try to extract token from OpenClaw auth-profiles.json
                        if not credentials or not hasattr(credentials, 'token') or not credentials.token:
                            auth_path = Path.home() / ".openclaw" / "auth-profiles.json"
                            if auth_path.exists():
                                try:
                                    auth_data = json.loads(auth_path.read_text())
                                    profiles = auth_data.get("profiles", {})
                                    for p_id, p_data in profiles.items():
                                        if "google-antigravity" in p_id and p_data.get("access"):
                                            credentials = GoogleCredentials(token=p_data["access"])
                                            break
                                except Exception:
                                    pass

                        if not credentials:
                            raise RuntimeError("No valid credentials found for Vertex AI (ADC failed and no OpenClaw token).")

                        client_kwargs = {
                            "vertexai": True,
                            "project": project,
                            "location": location,
                            "credentials": credentials,
                        }
                    elif api_key:
                        client_kwargs = {"api_key": api_key}
                    else:
                        raise RuntimeError("Neither GOOGLE_API_KEY nor Vertex AI configuration found.")

                    client = genai.Client(**client_kwargs)
                    
                    # Billing Safeguard: Model Lock
                    # Using gemini-3-pro-preview for Vertex AI (cost-efficient, available on project).
                    target_model = "gemini-3-pro-preview" if use_vertex else (self.agent.model if hasattr(self.agent, "model") else "gemini-3-pro-preview")

                    request_kwargs = {
                        "model": target_model,
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
                    if hasattr(response, 'text') and response.text:
                        return response.text
                except Exception as e:
                    last_exception = e
                    if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                        raise e
                    # For other errors, try secondary methods if Vertex failed or was not used
                
                # Method 2: Try InMemoryRunner if available (only if Vertex not used or failed)
                if not (use_vertex and project and location) and self._runner is not None and self._session_service is not None:
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
                            if hasattr(event, 'tool_calls') and event.tool_calls:
                                for call in event.tool_calls:
                                    if hasattr(call, 'function_call') and call.function_call:
                                        response_parts.append(json.dumps(call.function_call.args))

                        if response_parts:
                            return "\n".join(response_parts)
                    except Exception as e:
                        last_exception = e
                        if "429" in str(e):
                            raise e
            
            except Exception as e:
                last_exception = e
                if attempt < max_retries and "429" in str(e):
                    time.sleep((2 ** attempt) + 1)
                    continue
                break

        if last_exception:
            raise last_exception
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
            try:
                data = ast.literal_eval(payload)
            except Exception:
                data = {}
                for key in ("allowed", "risk_score", "reason"):
                    key_match = re.search(f'"{key}"\\s*:\\s*([^,\\s}}]+)', payload)
                    if key_match:
                        val = key_match.group(1).strip().strip('"').strip("'")
                        if key == "allowed":
                            data[key] = val.lower() == "true"
                        elif key == "risk_score":
                            try:
                                data[key] = int(val)
                            except ValueError:
                                data[key] = 5
                        else:
                            data[key] = val

        if not isinstance(data, dict):
            raise ValueError("Auditor output is not a dictionary.")

        # Handle potential type mismatches from regex parser
        if "allowed" in data and not isinstance(data["allowed"], bool):
            data["allowed"] = str(data["allowed"]).lower() == "true"
        
        if "risk_score" in data:
            try:
                data["risk_score"] = int(data["risk_score"])
            except (ValueError, TypeError):
                data["risk_score"] = 5

        # Ensure defaults
        if "allowed" not in data and "risk_score" in data:
            data["allowed"] = data["risk_score"] < 5
        if "reason" not in data:
            data["reason"] = "Semantic analysis completed (implied reason)."

        for field in ("allowed", "risk_score", "reason"):
            if field not in data:
                # Final fail-closed fallback
                if field == "allowed": data[field] = False
                elif field == "risk_score": data[field] = 10
                else: data[field] = "Incomplete auditor response"

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
