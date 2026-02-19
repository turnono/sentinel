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
    else:
        print(f"Action '{args.action}' not recognized.")

if __name__ == "__main__":
    main()
