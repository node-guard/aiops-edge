#!/usr/bin/env bash
# Shared helpers for the QEMU/libvirt lab. Sourced by lab-up.sh / lab-down.sh,
# never executed directly.

# shellcheck shell=bash

log() { printf '[lab] %s\n' "$*"; }
warn() { printf '[lab] WARNING: %s\n' "$*" >&2; }
die() {
  printf '[lab] ERROR: %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  local cmd
  for cmd in "$@"; do
    command -v "$cmd" >/dev/null 2>&1 || die "missing command: $cmd"
  done
}

# libvirt is accessed through the system daemon: that is where the NAT network
# and the KVM/QEMU privileges live. The session daemon cannot create bridges.
virsh_system() { virsh -c qemu:///system "$@"; }

net_exists() { virsh_system net-info "$LAB_NETWORK_NAME" >/dev/null 2>&1; }
net_active() {
  local info
  info=$(virsh_system net-info "$LAB_NETWORK_NAME" 2>/dev/null) || return 1
  grep -qE '^Active:[[:space:]]+yes' <<<"$info"
}
dom_exists() { virsh_system dominfo "$1" >/dev/null 2>&1; }
dom_running() {
  [[ "$(virsh_system domstate "$1" 2>/dev/null || true)" == "running" ]]
}

# Only the variables used by the templates are substituted; `$UPTIME` and other
# guest-side shell variables must survive rendering.
LAB_TEMPLATE_VARS='${LAB_NETWORK_NAME} ${LAB_BRIDGE} ${LAB_GATEWAY} ${LAB_NETWORK_PREFIX} ${LAB_DHCP_START} ${LAB_DHCP_END} ${LAB_SERVER_IP} ${LAB_SERVER_MAC} ${LAB_WORKER_IP} ${LAB_WORKER_MAC} ${LAB_VM_NAME} ${LAB_VM_MEM_MB} ${LAB_VM_VCPUS} ${LAB_VM_DISK} ${LAB_VM_SEED} ${LAB_VM_MAC} ${LAB_VM_IP} ${LAB_VM_HOSTNAME} ${LAB_VM_INSTANCE_ID} ${LAB_SSH_USER} ${LAB_SSH_PUBLIC_KEY_CONTENT} ${LAB_DNS_SERVER}'

render_template() {
  local src=$1 dst=$2
  [[ -f "$src" ]] || die "template not found: $src"
  envsubst "$LAB_TEMPLATE_VARS" <"$src" >"$dst"
}

ensure_dirs() {
  mkdir -p "$LAB_IMAGE_DIR" "$LAB_STATE_DIR/cloud-init" "$LAB_STATE_DIR/ssh"
  chmod 700 "$LAB_STATE_DIR" "$LAB_STATE_DIR/ssh"
}

# libvirt runs QEMU as an unprivileged user. It needs execute permission on
# every ancestor of the disk and seed directories. /home/<user> is often 0710,
# so grant a traverse-only ACL when the world-execute bit is missing. This is
# reversible and grants no read access.
qemu_user() {
  if id -u "$LAB_QEMU_USER" >/dev/null 2>&1; then
    printf '%s' "$LAB_QEMU_USER"
  else
    printf 'qemu'
  fi
}

ensure_qemu_traversal() {
  local root p user
  user=$(qemu_user)
  for root in "$@"; do
    p=$root
    while [[ "$p" != "/" ]]; do
      if [[ "$(stat -c '%a' "$p")" =~ [1357]$ ]]; then
        :
      elif ! setfacl -m "u:$user:x" "$p" 2>/dev/null; then
        warn "cannot grant $user traverse on $p; VM start may fail"
      fi
      p=$(dirname "$p")
    done
  done
}

ensure_ssh_key() {
  if [[ ! -f "$LAB_SSH_PRIVATE_KEY" ]]; then
    log "generating lab SSH key: $LAB_SSH_PRIVATE_KEY"
    ssh-keygen -q -t ed25519 -N '' -C 'aiops-lab' -f "$LAB_SSH_PRIVATE_KEY"
  fi
  chmod 600 "$LAB_SSH_PRIVATE_KEY"
  chmod 644 "$LAB_SSH_PUBLIC_KEY"
}

ensure_base_image() {
  if [[ -f "$LAB_BASE_IMAGE" ]]; then
    "$QEMU_IMG" info "$LAB_BASE_IMAGE" >/dev/null 2>&1 ||
      die "base image is not a valid qcow2: $LAB_BASE_IMAGE"
    return
  fi
  log "downloading base image (once): $LAB_BASE_IMAGE_URL"
  local tmp="$LAB_BASE_IMAGE.part"
  rm -f "$tmp"
  curl -fL --retry 5 --retry-delay 3 -o "$tmp" "$LAB_BASE_IMAGE_URL"
  "$QEMU_IMG" info "$tmp" >/dev/null 2>&1 || die "downloaded file is not a qcow2 image"
  mv "$tmp" "$LAB_BASE_IMAGE"
  chmod 644 "$LAB_BASE_IMAGE"
}

create_disk() {
  local disk=$1 size_gb=$2
  if [[ -f "$disk" ]]; then
    return
  fi
  log "creating disk ${disk} (${size_gb}G sparse)"
  cp --reflink=auto "$LAB_BASE_IMAGE" "$disk"
  "$QEMU_IMG" resize "$disk" "${size_gb}G" >/dev/null
  chmod 644 "$disk"
}

ensure_network() {
  local xml="$LAB_STATE_DIR/network.xml"
  if net_exists; then
    if ! net_active; then
      log "starting existing network $LAB_NETWORK_NAME"
      virsh_system net-start "$LAB_NETWORK_NAME"
    fi
    virsh_system net-autostart "$LAB_NETWORK_NAME" >/dev/null 2>&1 || true
    return
  fi

  log "defining network $LAB_NETWORK_NAME ($LAB_NETWORK_CIDR)"
  render_template "$LAB_TEMPLATE_DIR/network.xml.tmpl" "$xml"
  xmllint --noout "$xml"
  virsh_system net-define "$xml" >/dev/null
  virsh_system net-start "$LAB_NETWORK_NAME"
  virsh_system net-autostart "$LAB_NETWORK_NAME" >/dev/null
}

lab_ssh() {
  local host=$1
  shift
  ssh "${LAB_SSH_OPTS[@]}" -i "$LAB_SSH_PRIVATE_KEY" "$LAB_SSH_USER@$host" "$@"
}

wait_for_ssh() {
  local ip=$1 deadline=$((SECONDS + LAB_SSH_TIMEOUT))
  log "waiting for SSH on $ip"
  while ((SECONDS < deadline)); do
    if lab_ssh "$ip" true >/dev/null 2>&1; then
      return
    fi
    sleep 5
  done
  die "timed out waiting for SSH on $ip"
}

wait_for_cloud_init() {
  local ip=$1 deadline=$((SECONDS + LAB_SSH_TIMEOUT))
  log "waiting for cloud-init on $ip"
  while ((SECONDS < deadline)); do
    if lab_ssh "$ip" 'test -f /var/lib/cloud/instance/boot-finished' >/dev/null 2>&1; then
      return
    fi
    sleep 5
  done
  die "cloud-init did not finish on $ip"
}

prepare_cloud_init() {
  local name=$1 hostname=$2 mac=$3 ip=$4
  local user_data="$LAB_STATE_DIR/cloud-init/$name-user-data.yaml"
  local meta_data="$LAB_STATE_DIR/cloud-init/$name-meta-data.yaml"
  local seed="$LAB_STATE_DIR/cloud-init/$name-seed.iso"

  LAB_VM_HOSTNAME="$hostname" LAB_VM_INSTANCE_ID="$name" \
    LAB_VM_MAC="$mac" LAB_VM_IP="$ip" \
    render_template "$LAB_CLOUD_INIT_DIR/node.yaml.tmpl" "$user_data"
  LAB_VM_HOSTNAME="$hostname" LAB_VM_INSTANCE_ID="$name" \
    render_template "$LAB_CLOUD_INIT_DIR/meta-data.tmpl" "$meta_data"

  rm -f "$seed"
  "$CLOUD_LOCALDS" -f iso "$seed" "$user_data" "$meta_data"
  chmod 644 "$seed"
}

define_domain() {
  local name=$1 hostname=$2 vcpus=$3 mem_mb=$4 disk_gb=$5 mac=$6 ip=$7
  local disk="$LAB_IMAGE_DIR/$name.qcow2"
  local seed="$LAB_STATE_DIR/cloud-init/$name-seed.iso"
  local xml="$LAB_STATE_DIR/$name.xml"

  create_disk "$disk" "$disk_gb"
  prepare_cloud_init "$name" "$hostname" "$mac" "$ip"

  LAB_VM_NAME="$name" LAB_VM_MEM_MB="$mem_mb" LAB_VM_VCPUS="$vcpus" \
    LAB_VM_DISK="$disk" LAB_VM_SEED="$seed" LAB_VM_MAC="$mac" \
    render_template "$LAB_TEMPLATE_DIR/domain.xml.tmpl" "$xml"

  if dom_exists "$name"; then
    # Re-defining without the existing UUID makes libvirt try to create a new
    # domain and fail on the name collision; pin the UUID we already have.
    local uuid
    uuid=$(virsh_system domuuid "$name")
    sed -i "s|<name>$name</name>|<name>$name</name><uuid>$uuid</uuid>|" "$xml"
  fi
  xmllint --noout "$xml"

  if dom_exists "$name"; then
    log "updating definition for $name"
  else
    log "defining $name"
  fi
  virsh_system define "$xml" >/dev/null
}

start_domain() {
  local name=$1
  if dom_running "$name"; then
    log "$name already running"
  else
    log "starting $name"
    virsh_system start "$name" >/dev/null
  fi
  virsh_system autostart "$name" >/dev/null 2>&1 || true
}
