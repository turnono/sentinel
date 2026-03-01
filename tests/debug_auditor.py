
import os
import json
import logging
import sys
from pathlib import Path

# Add current directory to path so we can import sentinel
sys.path.append(str(Path(__file__).resolve().parent))

from sentinel.sentinel_auditor import SentinelAuditor
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.DEBUG)

print(f"GOOGLE_API_KEY present: {bool(os.getenv('GOOGLE_API_KEY'))}")

try:
    auditor = SentinelAuditor(model="gemini-3-pro-preview")
    print(f"Auditor initialized. Agent: {type(auditor.agent)}")
    print(f"Runner available: {auditor._runner is not None}")

    command = "whoami && id && uname -a"
    print(f"Auditing command: {command}")

    # Manually try the invocation steps to see where it fails
    print("\n--- Testing Method 1 (google.genai) ---")
    try:
        from google import genai
        api_key = os.getenv('GOOGLE_API_KEY')
        client = genai.Client(api_key=api_key)
        print("GenAI client initialized.")
        # Try a simple prompt
        response = client.models.generate_content(
            model="gemini-3-pro-preview",
            contents="test"
        )
        print(f"GenAI response success: {bool(response.text)}")
    except Exception as e:
        print(f"Method 1 failed: {e}")
        import traceback
        traceback.print_exc()

    print("\n--- Testing Method 2 (Runner) ---")
    if auditor._runner:
        try:
            from google.genai import types
            session = auditor._session_service.create_session(
                app_name="sentinel",
                user_id="sentinel_user",
            )
            user_content = types.Content(
                role="user",
                parts=[types.Part(text="test")]
            )
            print("Runner run starting...")
            for event in auditor._runner.run(
                user_id="sentinel_user",
                session_id=session.id,
                new_message=user_content,
            ):
                print(f"Runner event: {event}")
        except Exception as e:
            print(f"Method 2 failed: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("Runner not initialized.")

    print("\n--- Running full audit_command ---")
    decision = auditor.audit_command(command)
    print(f"Decision: {decision.to_dict()}")

except Exception as e:
    print(f"Setup failed: {e}")
    import traceback
    traceback.print_exc()
