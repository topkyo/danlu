#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
VAULT_ROOT="${AIWIKI_VAULT:-${1:-}}"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "error: launchd install is only supported on macOS" >&2
  exit 1
fi
if [ -z "$VAULT_ROOT" ]; then
  echo "error: AIWIKI_VAULT is not set" >&2
  echo "  Example: AIWIKI_VAULT=/path/to/vault $0" >&2
  exit 1
fi
for dir in raw wiki schema output .aiwiki; do
  if [ ! -d "$VAULT_ROOT/$dir" ]; then
    echo "error: vault scaffold is missing '$dir': $VAULT_ROOT" >&2
    echo "  Create the vault first: aiwiki advanced new-vault $VAULT_ROOT" >&2
    exit 1
  fi
done

# Resolve a Python >=3.10 once at install time and bake it into the plist env;
# launchd jobs get a minimal PATH where `python3` may be Apple 3.9.
# pick_python.sh honors AIWIKI_PYTHON as its first candidate AND version-checks it.
RESOLVED_PYTHON_BIN="$(/bin/bash "$SCRIPT_DIR/pick_python.sh")"

LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
AIWIKI_CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/aiwiki"
LOG_DIR="$AIWIKI_CONFIG_DIR/logs"
WATCH_LABEL="${AIWIKI_LAUNCHD_WATCH_LABEL:-com.aiwiki.watch}"
NIGHTLY_LABEL="${AIWIKI_LAUNCHD_NIGHTLY_LABEL:-com.aiwiki.nightly}"
WATCH_PLIST="$LAUNCH_AGENTS_DIR/$WATCH_LABEL.plist"
NIGHTLY_PLIST="$LAUNCH_AGENTS_DIR/$NIGHTLY_LABEL.plist"
NIGHTLY_HOUR="${AIWIKI_LAUNCHD_NIGHTLY_HOUR:-0}"
NIGHTLY_MINUTE="${AIWIKI_LAUNCHD_NIGHTLY_MINUTE:-0}"

mkdir -p "$LAUNCH_AGENTS_DIR" "$LOG_DIR"

PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" "$RESOLVED_PYTHON_BIN" -m aiwiki.cli \
  --root "$PROJECT_ROOT" advanced sync-product-shell "$VAULT_ROOT" >/dev/null

"$RESOLVED_PYTHON_BIN" - "$WATCH_PLIST" "$NIGHTLY_PLIST" "$PROJECT_ROOT" "$VAULT_ROOT" "$LOG_DIR" "$WATCH_LABEL" "$NIGHTLY_LABEL" "$NIGHTLY_HOUR" "$NIGHTLY_MINUTE" "$RESOLVED_PYTHON_BIN" <<'PY'
import os
import plistlib
import sys
from pathlib import Path

watch_plist = Path(sys.argv[1])
nightly_plist = Path(sys.argv[2])
project_root = Path(sys.argv[3])
vault_root = Path(sys.argv[4])
log_dir = Path(sys.argv[5])
watch_label = sys.argv[6]
nightly_label = sys.argv[7]
nightly_hour = int(sys.argv[8])
nightly_minute = int(sys.argv[9])
python_bin = sys.argv[10]

base_path = os.environ.get("AIWIKI_LAUNCHD_PATH")
if not base_path:
    home = str(Path.home())
    base_path = ":".join(
        [
            f"{home}/.local/bin",
            f"{home}/.opencode/bin",
            "/opt/homebrew/bin",
            "/usr/local/bin",
            "/usr/bin",
            "/bin",
            "/usr/sbin",
            "/sbin",
        ]
    )

watch_env = {
    "AIWIKI_VAULT": str(vault_root),
    "AIWIKI_PYTHON": python_bin,
    "AIWIKI_WATCH_INTERVAL": os.environ.get("AIWIKI_WATCH_INTERVAL", "5"),
    "AIWIKI_WATCH_COMPILE_LIMIT": os.environ.get("AIWIKI_WATCH_COMPILE_LIMIT", "5"),
    "AIWIKI_WATCH_SKIP_INITIAL": os.environ.get("AIWIKI_WATCH_SKIP_INITIAL", "0"),
    "PATH": base_path,
}
nightly_env = {
    "AIWIKI_VAULT": str(vault_root),
    "AIWIKI_PYTHON": python_bin,
    "AIWIKI_NIGHTLY_COMPILE_LIMIT": os.environ.get("AIWIKI_NIGHTLY_COMPILE_LIMIT", "5"),
    "AIWIKI_AUTONOMY_PROFILE": os.environ.get("AIWIKI_AUTONOMY_PROFILE", "agentic"),
    "PATH": base_path,
}

watch_payload = {
    "Label": watch_label,
    "ProgramArguments": ["/bin/bash", str(project_root / "scripts" / "run_launchd_watch.sh")],
    "EnvironmentVariables": watch_env,
    "RunAtLoad": True,
    "KeepAlive": True,
    "StandardOutPath": str(log_dir / "aiwiki-watch.out.log"),
    "StandardErrorPath": str(log_dir / "aiwiki-watch.err.log"),
    "WorkingDirectory": str(project_root),
}
nightly_payload = {
    "Label": nightly_label,
    "ProgramArguments": ["/bin/bash", str(project_root / "scripts" / "run_launchd_nightly.sh")],
    "EnvironmentVariables": nightly_env,
    "StartCalendarInterval": {"Hour": nightly_hour, "Minute": nightly_minute},
    "StandardOutPath": str(log_dir / "aiwiki-nightly.out.log"),
    "StandardErrorPath": str(log_dir / "aiwiki-nightly.err.log"),
    "WorkingDirectory": str(project_root),
}

for path, payload in [(watch_plist, watch_payload), (nightly_plist, nightly_payload)]:
    with path.open("wb") as handle:
        plistlib.dump(payload, handle, sort_keys=True)
PY

DOMAIN="gui/$(id -u)"
launchctl bootout "$DOMAIN" "$WATCH_PLIST" >/dev/null 2>&1 || true
launchctl bootout "$DOMAIN" "$NIGHTLY_PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "$DOMAIN" "$WATCH_PLIST"
launchctl bootstrap "$DOMAIN" "$NIGHTLY_PLIST"
launchctl enable "$DOMAIN/$WATCH_LABEL"
launchctl enable "$DOMAIN/$NIGHTLY_LABEL"
launchctl kickstart -k "$DOMAIN/$WATCH_LABEL"

echo "[OK] Installed launchd watcher and nightly jobs"
echo "      watch plist:   $WATCH_PLIST"
echo "      nightly plist: $NIGHTLY_PLIST"
echo "      vault:         $VAULT_ROOT"
echo "      python:        $RESOLVED_PYTHON_BIN"
echo "      logs:          $LOG_DIR"
echo "      plugin:        synced Product Shell release files (data.json preserved)"
echo "      note:          LLM secrets are read by the CLI from the vault Product Shell data.json or process env; they are not written to plist files."
