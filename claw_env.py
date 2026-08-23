"""Runtime resolution of the Claw gateway's paths, CLI and process name.

The tree is mid-rename: commit 0515a5f moved part of it from "openclaw" to
"zeroclaw" and left the rest behind, so a hardcoded spelling in one script is
liable to be the wrong one. Everything here probes for whichever install is
actually present rather than assuming, and the process pattern deliberately
matches both spellings so a kill or a restart cannot silently no-op.

Set CLAW_BRAND=openclaw or CLAW_BRAND=zeroclaw to pin the choice explicitly.
"""

import os
import shutil
from pathlib import Path

# Newest spelling first: when both installs exist, the migrated one wins.
BRANDS = ("zeroclaw", "openclaw")

# ERE for `pkill -f` / `pgrep -f`. Matches either spelling so that healing and
# failover restarts keep working whichever binary is installed.
GATEWAY_PROC_PATTERN = r"(open|zero)claw gateway"


def _pinned():
    """The brand pinned via CLAW_BRAND, or None when unset/unrecognised."""
    brand = os.environ.get("CLAW_BRAND", "").strip().lower()
    return brand if brand in BRANDS else None


def brand():
    """The brand in use: pinned, else whichever install is on disk."""
    pinned = _pinned()
    if pinned:
        return pinned
    for name in BRANDS:
        if (Path.home() / f".{name}").is_dir():
            return name
    return "openclaw"


def _candidates():
    """Brands to probe, in priority order."""
    pinned = _pinned()
    return (pinned,) if pinned else BRANDS


def state_dir():
    """The ~/.<brand> directory, preferring one that exists."""
    for name in _candidates():
        path = Path.home() / f".{name}"
        if path.is_dir():
            return path
    return Path.home() / f".{brand()}"


def config_path():
    """The gateway config file, preferring one that exists.

    Both the JSON and TOML spellings are probed because the rename changed the
    filename without changing the readers/writers that parse it.
    """
    for name in _candidates():
        base = Path.home() / f".{name}"
        for filename in (f"{name}.json", "config.toml", "config.json"):
            candidate = base / filename
            if candidate.is_file():
                return candidate
    return Path.home() / f".{brand()}" / f"{brand()}.json"


def log_dir():
    """The /tmp log directory, preferring one that exists."""
    for name in _candidates():
        path = Path("/tmp") / name
        if path.is_dir():
            return path
    return Path("/tmp") / brand()


def gateway_logs():
    """Every gateway log file on disk, across both spellings."""
    logs = []
    for name in _candidates():
        directory = Path("/tmp") / name
        if directory.is_dir():
            logs.extend(directory.glob(f"{name}-*.log"))
    return logs


def restart_flag():
    """Path the failover monitor touches to request a restart."""
    return Path("/tmp") / f"{brand()}_restart_requested"


def cli_path():
    """Absolute path to the CLI, resolved via PATH rather than assumed.

    Falls back to the Homebrew locations only when PATH lookup fails, so this
    keeps working off a stripped-down launchd/cron environment.
    """
    for name in _candidates():
        found = shutil.which(name)
        if found:
            return found
    for name in _candidates():
        for prefix in ("/opt/homebrew/bin", "/usr/local/bin"):
            candidate = Path(prefix) / name
            if candidate.exists():
                return str(candidate)
    return brand()
