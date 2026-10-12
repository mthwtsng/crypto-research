#!/usr/bin/env bash
# ==============================================================================
# Multi-VM Ghost Forward Telemetry Sync Script
# Pulls ghost_trades.jsonl and ghost_summary.json from GCP VMs into local reports
# ==============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Target local directories
VM1_LOCAL_DIR="$WORKSPACE_ROOT/reports/vm1"
VM2_LOCAL_DIR="$WORKSPACE_ROOT/reports/vm2"
mkdir -p "$VM1_LOCAL_DIR" "$VM2_LOCAL_DIR"

# Remote VM connection variables (configurable via environment)
VM1_HOST="${VM1_HOST:-}"
VM2_HOST="${VM2_HOST:-}"
VM_REMOTE_DIR="${VM_REMOTE_DIR:-code/Crypto/data}"
SSH_KEY="${SSH_KEY:-}"
SSH_OPTS="${SSH_OPTS:--o ConnectTimeout=5 -o StrictHostKeyChecking=no -o BatchMode=yes}"

if [[ -n "$SSH_KEY" ]]; then
    SSH_OPTS="$SSH_OPTS -i $SSH_KEY"
fi

echo "=========================================================================================="
echo "          SOLANA STARTING 5 — MULTI-VM GHOST TELEMETRY SYNCHRONIZER"
echo "=========================================================================================="
echo "Local workspace: $WORKSPACE_ROOT"
echo "Remote data dir: $VM_REMOTE_DIR"
echo "VM1 Host:        ${VM1_HOST:-<not set: export VM1_HOST=user@ip1>}"
echo "VM2 Host:        ${VM2_HOST:-<not set: export VM2_HOST=user@ip2>}"
echo "------------------------------------------------------------------------------------------"

sync_vm() {
    local vm_name="$1"
    local vm_host="$2"
    local dest_dir="$3"

    if [[ -z "$vm_host" ]]; then
        echo "[-] $vm_name: Host not configured. To enable, set ${vm_name^^}_HOST (e.g. export ${vm_name^^}_HOST=user@<gcp-ip>)"
        return 0
    fi

    echo "[*] $vm_name: Connecting to $vm_host..."

    # Check connectivity
    if ! ssh $SSH_OPTS "$vm_host" "true" 2>/dev/null; then
        echo "[!] $vm_name: Cannot reach host $vm_host (connection timeout or SSH auth failed)."
        return 1
    fi

    echo "[+] $vm_name: Connected. Synchronizing telemetry..."

    # Attempt rsync first, fallback to scp
    if command -v rsync >/dev/null 2>&1; then
        rsync -avz -e "ssh $SSH_OPTS" "$vm_host:$VM_REMOTE_DIR/ghost_trades.jsonl" "$dest_dir/ghost_trades.jsonl" 2>/dev/null || true
        rsync -avz -e "ssh $SSH_OPTS" "$vm_host:$VM_REMOTE_DIR/ghost_summary.json" "$dest_dir/ghost_summary.json" 2>/dev/null || true
    else
        scp $SSH_OPTS "$vm_host:$VM_REMOTE_DIR/ghost_trades.jsonl" "$dest_dir/ghost_trades.jsonl" 2>/dev/null || true
        scp $SSH_OPTS "$vm_host:$VM_REMOTE_DIR/ghost_summary.json" "$dest_dir/ghost_summary.json" 2>/dev/null || true
    fi

    # Verify synced files
    if [[ -f "$dest_dir/ghost_trades.jsonl" ]]; then
        local line_count
        line_count=$(wc -l < "$dest_dir/ghost_trades.jsonl" | tr -d ' ')
        echo "[✓] $vm_name: Synced ghost_trades.jsonl ($line_count trade records)"
    else
        echo "[!] $vm_name: ghost_trades.jsonl not found on remote"
    fi

    if [[ -f "$dest_dir/ghost_summary.json" ]]; then
        echo "[✓] $vm_name: Synced ghost_summary.json"
    fi
}

# Run sync for VM1 and VM2
sync_vm "vm1" "$VM1_HOST" "$VM1_LOCAL_DIR"
sync_vm "vm2" "$VM2_HOST" "$VM2_LOCAL_DIR"

echo "------------------------------------------------------------------------------------------"
echo "Sync cycle completed. To view the consolidated forward telemetry dashboard, run:"
echo "  python3 scripts/aggregate_ghost_reports.py"
echo "=========================================================================================="
