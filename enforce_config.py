import json
import os
import sys
from pathlib import Path

def enforce_config():
    config_path = Path.home() / ".openclaw" / "openclaw.json"
    if not config_path.exists():
        print(f"❌ Config file not found: {config_path}")
        return

    try:
        # Unlock file for writing
        if config_path.exists():
            os.chmod(config_path, 0o644)

        with open(config_path, "r") as f:
            config = json.load(f)

        modified = False

        # Enforce Sentinel Plugin Enabled
        plugins = config.get("plugins", {}).get("entries", {})
        if "sentinel" not in plugins:
            plugins["sentinel"] = {}
        
        sentinel_config = plugins["sentinel"]
        if not sentinel_config.get("enabled", False):
            print("🛡️  Enabling Sentinel plugin...")
            sentinel_config["enabled"] = True
            modified = True

        # Enforce Deny Exec Tool
        tools = config.get("tools", {})
        deny_list = tools.get("deny", [])
        if "exec" not in deny_list:
            print("🛡️  Adding 'exec' to deny list...")
            deny_list.append("exec")
            tools["deny"] = deny_list
            modified = True
        
        # Ensure 'exec' is NOT in allow list
        allow_list = tools.get("allow", [])
        if "exec" in allow_list:
             print("🛡️  Removing 'exec' from allow list...")
             allow_list.remove("exec")
             tools["allow"] = allow_list
             modified = True

        # Enforce Managed Browser (Zero-Config)
        browser = config.get("browser", {})
        if not browser.get("enabled", False) or browser.get("defaultProfile") != "openclaw":
             print("🌐 Enabling OpenClaw Managed Browser...")
             browser["enabled"] = True
             browser["defaultProfile"] = "openclaw"
             config["browser"] = browser
             modified = True

        # Remove stale 'my-chrome' profile if present
        if "my-chrome" in browser.get("profiles", {}):
            print("🧹 Removing stale 'my-chrome' profile...")
            del browser["profiles"]["my-chrome"]
            modified = True

        # Enforce Dynamic Model Selection with Fallback
        agents = config.get("agents", {})
        defaults = agents.get("defaults", {})
        model_config = defaults.get("model", {})
        
        # Use gemini-3-flash as primary (higher quota limits than gemini-3-pro-low)
        valid_models = [
            "google-antigravity/gemini-3-flash",
            "google-antigravity/gemini-3-pro-low", 
            "google-antigravity/claude-opus-4-6-thinking"
        ]
        
        # Default to gemini-3-flash if current is invalid
        # But allow custom/local models (not starting with google-antigravity)
        current_primary = model_config.get("primary", "")
        if current_primary.startswith("google-antigravity/") and current_primary not in valid_models:
            print("🔄 Switching to gemini-3-flash (default fallback)...")
            model_config["primary"] = "google-antigravity/gemini-3-flash"
            defaults["model"] = model_config
            
            # Ensure all models are registered
            models = defaults.get("models", {})
            for model_name in ["google-antigravity/gemini-3-pro-low", 
                             "google-antigravity/gemini-3-flash",
                             "google-antigravity/claude-opus-4-6-thinking"]:
                if model_name not in models:
                    models[model_name] = {}
            defaults["models"] = models
            agents["defaults"] = defaults
            config["agents"] = agents
            modified = True

        if modified:
            with open(config_path, "w") as f:
                json.dump(config, f, indent=2)
            print("✅ Configuration locked: Sentinel Enabled, Exec Denied.")
        else:
            print("✅ Configuration already secure.")

    except Exception as e:
        print(f"❌ Failed to enforce config: {e}")
        sys.exit(1)

    finally:
        # Always ensure file is read-only
        if config_path.exists():
            os.chmod(config_path, 0o444)

if __name__ == "__main__":
    enforce_config()
