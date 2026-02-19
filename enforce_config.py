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

        # Enforce Sentinel Plugin - DISABLED (Sentinel is now a Skill)
        plugins = config.get("plugins", {}).get("entries", {})
        if "sentinel" in plugins:
            print("🛡️  Removing legacy Sentinel plugin entry...")
            del plugins["sentinel"]
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

        # Gateway 'bind' is sensitive in recent versions. 
        # We will let OpenClaw manage this or keep loopback as default if needed.
        # Removing enforcement to avoid crashes.
        
        # Enforce Password Auth and remove invalid bind
        gateway = config.get("gateway", {})
        if "bind" in gateway:
            print("🧹 Removing invalid 'bind' key from gateway...")
            del gateway["bind"]
            modified = True
            
        auth_mode = gateway.get("auth", {}).get("mode", "token")
        if auth_mode != "password":
            # We keep 'token' if already configured, but ensure it's secure. 
            # In some previous runs we wanted 'password'.
            pass

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
            workspace_root = Path("/Users/<USER>/taajirah_systems/BOARDROOM")
            agent_dir = Path.home() / ".openclaw" / "agents" / agent_id / "agent"
            agent_dir.mkdir(parents=True, exist_ok=True)
            identity_file = agent_dir / "IDENTITY.md"
            
            # Also sync to workspace if it exists
            if workspace_root.exists():
                ws_identity = workspace_root / "IDENTITY.md"
                if agent_id == "architect": # Architect IS the workspace identity primary
                     with open(ws_identity, "w") as f:
                         f.write(prompt)

            print(f"🆔 Updating identity for {agent_id}...")
            with open(identity_file, "w") as f:
                f.write(prompt)

        # Enforce Architect Agent
        architect_agent = next((a for a in agents_list if a["id"] == "architect"), None)
        if not architect_agent:
            print("🏗️  Adding Architect agent...")
            architect_agent = {"id": "architect", "name": "Architect"}
            agents_list.append(architect_agent)
            modified = True
        
        if architect_agent.get("model") != "google-antigravity/gemini-3-flash":
            print("🏗️  Enforcing gemini-3-flash for Architect...")
            architect_agent["model"] = "google-antigravity/gemini-3-flash"
            modified = True
        
        # TAAJIRAH CORE: Load Sovereign Context for Architect
        boardroom_path = Path("/Users/<USER>/taajirah_systems/BOARDROOM")
        architect_prompt = "You are the System Architect."
        if boardroom_path.exists():
            soul_path = boardroom_path / "SOUL.md"
            consensus_path = boardroom_path / "CONSENSUS.json"
            
            soul_content = ""
            if soul_path.exists():
                with open(soul_path) as f:
                    soul_content = f.read()
            
            red_lines = ""
            if consensus_path.exists():
                try:
                    with open(consensus_path) as f:
                        consensus = json.load(f)
                        
                        # Handle the verified dict structure: red_lines: { "description": "...", "items": [...] }
                        red_lines_block = consensus.get("red_lines", {})
                        if isinstance(red_lines_block, list):
                             rules = red_lines_block
                        else:
                             # Try both 'items' and 'rules' keys
                             rules = red_lines_block.get("items", []) or red_lines_block.get("rules", [])
                             
                        if not rules:
                             # Try root-level governance fallback
                             gov_block = consensus.get("governance", {}).get("red_lines", {})
                             if isinstance(gov_block, list):
                                 rules = gov_block
                             else:
                                 rules = gov_block.get("items", []) or gov_block.get("rules", [])
                             
                        red_lines = "\n".join([f"- {rule.get('id', 'RL')}: {rule.get('rule', 'Restricted Operation')}" for rule in rules if isinstance(rule, dict)])
                        
                        if red_lines:
                            print(f"🔱 Loaded {len(rules)} Red Lines from CONSENSUS.json")
                        else:
                            print("⚠️  No Red Lines found in CONSENSUS.json structure.")
                except Exception as e:
                    print(f"❌ Failed to parse CONSENSUS.json: {e}")
                    red_lines = ""
            
            architect_prompt = (
                f"{soul_content}\n\n"
                f"## CONSTITUTION: THE 7 RED LINES\n"
                f"{red_lines}\n\n"
                f"Operational Directives: You are Tājirah (OpenClaw), the Executive Mobility Partner. "
                f"Maintain zero-trust security and uphold the 7 Red Lines at all times."
            )
            print("🔱 Compiled TAAJIRAH CORE identity for Architect.")
        
        ensure_identity("architect", architect_prompt)
            
        # Enforce Sentinel Agent
        sentinel_agent = next((a for a in agents_list if a["id"] == "sentinel"), None)
        if not sentinel_agent:
             print("🛡️  Adding Sentinel agent...")
             sentinel_agent = {"id": "sentinel", "name": "Sentinel"}
             agents_list.append(sentinel_agent)
             modified = True
             
        if sentinel_agent.get("model") != "google-antigravity/gemini-3-flash":
            print("🛡️  Enforcing gemini-3-flash for Sentinel...")
            sentinel_agent["model"] = "google-antigravity/gemini-3-flash"
            modified = True
        
        # Load AIEOS Identity for Sentinel
        try:
            aieos_path = Path("/Users/<USER>/sentinel/identity/sentinel.aieos.json")
            if aieos_path.exists():
                with open(aieos_path) as f:
                    aieos = json.load(f)
                
                # specific compilation logic
                directives = "\n".join([f"- {d}" for d in aieos["personality"]["directives"]])
                traits = ", ".join(aieos["personality"]["traits"])
                tone = aieos["personality"]["tone"]
                
                prompt = (
                    f"Identity: {aieos['metadata']['name']} ({aieos['metadata']['role']})\n"
                    f"Traits: {traits}\n"
                    f"Tone: {tone}\n\n"
                    f"Directives:\n{directives}\n"
                )
                print("🆔 Compiled AIEOS identity for Sentinel.")
                ensure_identity("sentinel", prompt)
            else:
                 print("⚠️ AIEOS file not found, using default identity.")
                 ensure_identity("sentinel", "You are Sentinel, the security guardian. Your primary role is to audit system state and enforce safety protocols using the 'sentinel' skill.")
        except Exception as e:
                print(f"❌ Failed to load AIEOS identity: {e}")
                ensure_identity("sentinel", "You are Sentinel, the security guardian. Your primary role is to audit system state and enforce safety protocols using the 'sentinel' skill.")
        agents["list"] = agents_list
        config["agents"] = agents

        # Enforce Extra Skills Directory
        skills = config.get("skills", {})
        load_conf = skills.get("load", {})
        extra_dirs = load_conf.get("extraDirs", [])
        sentinel_skill_path = str(Path("/Users/<USER>/sentinel/openclaw-skill").resolve())
        
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

        # Enforce Code Wiki Skill - DISABLED (Potential source of schema errors)
        if "codewiki" in skills_entries:
            print("📖 Disabling Code Wiki skill to resolve schema conflicts...")
            del skills_entries["codewiki"]
            modified = True

        # Custom Telegram configuration is managed manually in openclaw.json
        pass

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
