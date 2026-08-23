#!/bin/bash
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"

# Try to use the version we know works, or default
nvm use v22.14.0 > /dev/null 2>&1 || nvm use default > /dev/null 2>&1

# Resolve the CLI: the tree is mid-rename from openclaw to zeroclaw.
for name in zeroclaw openclaw; do
  if command -v "$name" >/dev/null 2>&1; then
    echo "🦞 Launching ${name} TUI..."
    exec "$name" tui "$@"
  fi
done

echo "❌ No zeroclaw/openclaw CLI found on PATH." >&2
exit 1
