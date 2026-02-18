import os
import json
from pathlib import Path
from dotenv import load_dotenv
from google import genai
import google.auth
from google.oauth2.credentials import Credentials as GoogleCredentials

def list_vertex_models():
    load_dotenv()
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GOOGLE_CLOUD_LOCATION")
    
    try:
        # Obtain credentials (OpenClaw fallback)
        auth_path = Path.home() / ".openclaw" / "auth-profiles.json"
        auth_data = json.loads(auth_path.read_text())
        profiles = auth_data.get("profiles", {})
        credentials = None
        for p_id, p_data in profiles.items():
            if "google-antigravity" in p_id and p_data.get("access"):
                credentials = GoogleCredentials(token=p_data["access"])
                break

        if not credentials:
            print("❌ Credentials not found.")
            return

        client = genai.Client(
            vertexai=True,
            project=project,
            location=location,
            credentials=credentials
        )
        
        print(f"🔍 Listing models in {project} / {location}...")
        for model in client.models.list():
            print(f"📍 {model.name}")
        
        print("✅ Models listed successfully.")

    except Exception as e:
        print(f"❌ Failed to list models: {e}")

if __name__ == "__main__":
    list_vertex_models()
