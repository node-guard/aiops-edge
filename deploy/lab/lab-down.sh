#!/usr/bin/env bash
# Stop and undefine the lab. Disks and the base image are kept unless --wipe.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lab.conf
set -a
source "$SCRIPT_DIR/lab.conf"
set +a
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

usage() {
  cat <<'EOF'
Usage: lab-down.sh [--wipe] [--keep-network]

  --wipe          also delete disks, cloud-init seeds, kubeconfig and SSH keys
  --keep-network  leave the libvirt network defined and running
EOF
}

WIPE=false
KEEP_NETWORK=false
for arg in "$@"; do
  case "$arg" in
    --wipe) WIPE=true ;;
    --keep-network) KEEP_NETWORK=true ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      die "unknown argument: $arg"
      ;;
  esac
done

require_cmd virsh

stop_domain() {
  local name=$1
  if ! dom_exists "$name"; then
    log "$name is not defined"
    return
  fi
  if dom_running "$name"; then
    log "destroying $name"
    virsh_system destroy "$name" >/dev/null
  fi
  log "undefining $name"
  virsh_system undefine "$name" >/dev/null
}

remove_network() {
  if ! net_exists; then
    log "network $LAB_NETWORK_NAME is not defined"
    return
  fi
  if net_active; then
    log "stopping network $LAB_NETWORK_NAME"
    virsh_system net-destroy "$LAB_NETWORK_NAME" >/dev/null
  fi
  log "undefining network $LAB_NETWORK_NAME"
  virsh_system net-undefine "$LAB_NETWORK_NAME" >/dev/null
}

stop_domain "$LAB_WORKER_NAME"
stop_domain "$LAB_SERVER_NAME"

if $KEEP_NETWORK; then
  log "keeping network $LAB_NETWORK_NAME"
else
  remove_network
fi

if $WIPE; then
  log "deleting disks, seeds, kubeconfig and SSH keys"
  rm -rf "$LAB_IMAGE_DIR" "$LAB_STATE_DIR"
else
  log "kept disks and state under $LAB_IMAGE_DIR and $LAB_STATE_DIR (use --wipe to delete)"
fi

log "lab down"
