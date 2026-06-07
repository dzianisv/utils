#!/usr/bin/env bash
#
# Resize an Azure VM's OS disk (deallocate → resize → start → grow filesystem).
#
# Usage:
#   azure-vm-resize.sh [--size SIZE_GB] [--rg RESOURCE_GROUP] [--vm VM_NAME]
#
# Defaults are set for the openclaw-dev-1 VM.

# Resize to 512GB (defaults to openclaw-dev-1)
# azure-vm-resize.sh --size 512
# Different VM
# azure-vm-resize.sh --size 256 --rg my-rg --vm my-vm --host user@host

set -euo pipefail

SIZE=256
RG="openclaw-dev-rg"
VM="openclaw-dev-1"
SSH_HOST="azureuser@100.108.64.76"

while [[ $# -gt 0 ]]; do
  case $1 in
    --size) SIZE="$2"; shift 2 ;;
    --rg)   RG="$2";   shift 2 ;;
    --vm)   VM="$2";   shift 2 ;;
    --host) SSH_HOST="$2"; shift 2 ;;
    -h|--help)
      sed -n '2,/^$/{ s/^# //; s/^#//; p }' "$0"
      exit 0
      ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

# Resolve the OS disk name from the VM
DISK=$(az vm show --resource-group "$RG" --name "$VM" \
  --query "storageProfile.osDisk.managedDisk.id" -o tsv | xargs basename)

if [[ -z "$DISK" ]]; then
  echo "ERROR: Could not resolve OS disk for VM $VM in $RG" >&2
  exit 1
fi

CURRENT=$(az disk show --resource-group "$RG" --name "$DISK" \
  --query "diskSizeBytes" -o tsv)
CURRENT_GB=$(( CURRENT / 1073741824 ))

echo "VM:           $VM"
echo "Resource grp: $RG"
echo "OS disk:      $DISK"
echo "Current size: ${CURRENT_GB}GB"
echo "Target size:  ${SIZE}GB"
echo ""

if (( SIZE <= CURRENT_GB )); then
  echo "Target size must be larger than current size (${CURRENT_GB}GB). Aborting." >&2
  exit 1
fi

read -rp "Proceed? This will deallocate the VM. [y/N] " confirm
[[ "$confirm" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }

echo ""
echo "==> Deallocating VM..."
az vm deallocate --resource-group "$RG" --name "$VM" -o none
az vm wait --resource-group "$RG" --name "$VM" \
  --custom "instanceView.statuses[?code=='PowerState/deallocated']" 2>/dev/null
echo "    Deallocated."

echo "==> Resizing disk to ${SIZE}GB..."
az disk update --resource-group "$RG" --name "$DISK" --size-gb "$SIZE" -o none
echo "    Disk resized."

echo "==> Starting VM..."
az vm start --resource-group "$RG" --name "$VM" -o none
echo "    VM started."

echo "==> Waiting for SSH..."
for i in $(seq 1 30); do
  if ssh -o ConnectTimeout=3 -o BatchMode=yes "$SSH_HOST" true 2>/dev/null; then
    break
  fi
  sleep 2
done

echo "==> Growing partition and filesystem..."
ssh "$SSH_HOST" '
  sudo growpart /dev/sda 1 2>/dev/null || true
  sudo resize2fs /dev/sda1 2>/dev/null || true
  echo ""
  echo "=== Disk status ==="
  df -h /
  lsblk /dev/sda
'

echo ""
echo "Done. Disk resized to ${SIZE}GB."
