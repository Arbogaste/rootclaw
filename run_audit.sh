#!/usr/bin/env bash
# Modes:
#   scan:     ./run_audit.sh scan <target_dir> <sol|rust|ts> [audit_output_dir]
#   simulate: ./run_audit.sh simulate <file> <sol|rust|ts> "<function>" "<goal>"
#
# Examples:
#   ./run_audit.sh scan /path/to/contracts sol ../blockchain/attack/audit_strategy/audit/beanstalk
#   ./run_audit.sh simulate LibWellBdv.sol sol "bdv" "inflate BDV via swap to get more stalk"

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="${1:?Usage: $0 scan|simulate ...}"

if [[ "$MODE" == "simulate" ]]; then
    FILE="${2:?provide file path}"
    PROFILE="${3:?provide profile: sol|rust|ts}"
    FUNCTION="${4:?provide target function}"
    GOAL="${5:?provide attacker goal}"
    CONFIG_FILE="${SCRIPT_DIR}/config_${PROFILE}.json"
    cd "$SCRIPT_DIR"
    python3 root_claw.py simulate "$FILE" "$CONFIG_FILE" "$FUNCTION" "$GOAL"
    exit 0
fi

# scan mode
TARGET_DIR="${2:?provide target dir}"
PROFILE="${3:?provide profile: sol|rust|ts}"
AUDIT_DIR="${4:-}"
CONFIG_FILE="${SCRIPT_DIR}/config_${PROFILE}.json"

if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "ERROR: Config not found: $CONFIG_FILE (available: sol, rust, ts)"
    exit 1
fi

if [[ ! -d "$TARGET_DIR" ]]; then
    echo "ERROR: Target dir not found: $TARGET_DIR"
    exit 1
fi

echo "=== rootclaw scan ==="
echo "Target:  $TARGET_DIR"
echo "Profile: $PROFILE"
echo ""

cd "$SCRIPT_DIR"
python3 root_claw.py scan "$TARGET_DIR" "$CONFIG_FILE"

LATEST_OUTPUT=$(ls -td output/*/ 2>/dev/null | head -1)

if [[ -n "$AUDIT_DIR" && -n "$LATEST_OUTPUT" ]]; then
    ROOTCLAW_OUT="${AUDIT_DIR}/rootclaw_output"
    mkdir -p "$ROOTCLAW_OUT"
    cp -r "${LATEST_OUTPUT}"* "$ROOTCLAW_OUT/"
    echo "Output copied to: $ROOTCLAW_OUT"
fi

echo "=== Done: ${LATEST_OUTPUT:-output/} ==="
