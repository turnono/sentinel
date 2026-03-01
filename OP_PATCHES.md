# TAAJIRAH CORE: Operational patches

This document tracks patches applied to external dependencies and system configurations that are NOT captured in the repository.

## OpenClaw Parameter Mismatch Fix

**Target**: `/opt/homebrew/lib/node_modules/openclaw/dist/subagent-registry-DN6TUJw4.js`
**Issue**: Schema conversion for Gemini incorrectly marks `path` as optional when aliasing.
**Patch**: 

Ensure `patchToolSchemaForClaudeCompatibility` preserves `path` in `required` array.

```javascript
// Before
const idx = required.indexOf(original);
if (idx !== -1) {
    required.splice(idx, 1);
    changed = true;
}

// After
const idx = required.indexOf(original);
if (idx !== -1) {
    if (!required.includes(alias)) {
        required.push(alias);
    }
    changed = true;
}
```

## System Workspace State

The following local configuration maps OpenClaw to the TAAJIRAH CORE boardroom:

**File**: `~/.openclaw/openclaw.json`
**Key**: `agents.defaults.workspace`
**Value**: `~/taajirah_systems/BOARDROOM`
