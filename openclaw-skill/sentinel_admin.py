import sys
import json
import argparse

def main():
    parser = argparse.ArgumentParser(description="Sentinel Admin Utility")
    parser.add_argument("action", nargs="?", default="status", help="Action to perform (list_pending, status, etc.)")
    parser.add_argument("--id", help="Target ID for the action")
    
    args = parser.parse_args()
    
    if args.action == "list_pending":
        # Simulating returning no pending items if called during restoration
        print(json.dumps({"pending": []}))
    elif args.action == "status":
        print(json.dumps({"status": "active", "version": "1.0.0"}))
    elif args.action == "pulse":
        # Enhanced Pulse (Mission 007)
        try:
            from pathlib import Path
            import os
            
            log_path = Path(__file__).parent.parent / "logs" / "sentinel_audit.log"
            stats = {"total": 0, "allowed": 0, "blocked": 0, "critical_blocks": 0}
            
            if log_path.exists():
                with open(log_path) as f:
                    for line in f:
                        try:
                            entry = json.loads(line)
                            stats["total"] += 1
                            if entry.get("allowed"):
                                stats["allowed"] += 1
                            else:
                                stats["blocked"] += 1
                                if entry.get("risk_score", 0) >= 8:
                                    stats["critical_blocks"] += 1
                        except: continue
            
            model = os.getenv("SENTINEL_MODEL", "gemini-3-pro-preview")
            
            pulse_data = {
                "status": "Green",
                "stats": stats,
                "active_model": model,
                "integrity": "Sovereign"
            }
            print(json.dumps(pulse_data, indent=2))
        except Exception as e:
            print(json.dumps({"error": str(e)}))
    else:
        print(f"Action '{args.action}' not recognized.")

if __name__ == "__main__":
    main()
