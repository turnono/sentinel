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
        
        # Default to gemini-3-flash if current is invalid or not an antigravity model
        current_primary = model_config.get("primary", "")
        if current_primary not in valid_models:
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
            defaults["models"] = models
            agents["defaults"] = defaults
            config["agents"] = agents
            modified = True

        # Enforce Specialized Agents
        agents_list = agents.get("list", [])
        agent_ids = {a["id"] for a in agents_list}
        
        # Helper to create identity file
        def ensure_identity(agent_id, prompt):
            agent_dir = Path.home() / ".openclaw" / "agents" / agent_id / "agent"
            agent_dir.mkdir(parents=True, exist_ok=True)
            identity_file = agent_dir / "IDENTITY.md"
            if not identity_file.exists():
                print(f"🆔 Creating identity for {agent_id}...")
                with open(identity_file, "w") as f:
                    f.write(prompt)

        if "architect" not in agent_ids:
            print("🏗️  Adding Architect agent...")
            agents_list.append({
                "id": "architect",
                "name": "Architect",
                "model": "google-antigravity/claude-opus-4-6-thinking"
            })
            modified = True
        
        ensure_identity("architect", "You are the System Architect. You think deeply about system design, security implications, and long-term strategy.")
            
        if "sentinel" not in agent_ids:
             print("🛡️  Adding Sentinel agent...")
             agents_list.append({
                "id": "sentinel",
                "name": "Sentinel",
                "model": "google-antigravity/gemini-3-pro-low"
             })
             modified = True
        
        # SANITIZATION: Remove 'prompt' keys if they exist (invalid in JSON)
        for agent in agents_list:
            if "prompt" in agent:
                print(f"🧹 Removing invalid 'prompt' key from agent {agent.get('id')}...")
                del agent["prompt"]
                modified = True

        ensure_identity("sentinel", "You are Sentinel, the security guardian. Your primary role is to audit system state and enforce safety protocols using the 'sentinel' skill.")

        agents["list"] = agents_list
        config["agents"] = agents

        # Enforce Extra Skills Directory
        skills = config.get("skills", {})
        load_conf = skills.get("load", {})
        extra_dirs = load_conf.get("extraDirs", [])
        sentinel_skill_path = "/Users/<USER>/sentinel/openclaw-skill"
        
        if sentinel_skill_path not in extra_dirs:
            print("➕ Registering Sentinel skill directory...")
            extra_dirs.append(sentinel_skill_path)
            load_conf["extraDirs"] = extra_dirs
            skills["load"] = load_conf
            config["skills"] = skills
            modified = True

        # Enforce Voice-Call Plugin (Mock Provider)
        plugins = config.get("plugins", {}).get("entries", {})
        if "voice-call" not in plugins:
            print("📞 Adding Voice-Call plugin (Mock)...")
            plugins["voice-call"] = {
                "enabled": True,
                "config": {
                    "provider": "mock",
                    "fromNumber": "+15550001234",
                    "toNumber": "+15550005678",
                    "outbound": {
                        "defaultMode": "notify"
                    }
                }
            }
            config["plugins"]["entries"] = plugins
            modified = True

        # Enforce Voice-Call Skill
        skills_entries = config.get("skills", {}).get("entries", {})
        if "voice-call" not in skills_entries:
            print("📞 Enabling Voice-Call skill...")
            skills_entries["voice-call"] = {
                "enabled": True
            }
            config["skills"]["entries"] = skills_entries
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
