#!/usr/bin/env bash
# Create (or reconcile) the disposable two-node K3s lab on QEMU/libvirt.
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
Usage: lab-up.sh [--check]

  --check   run preflight checks only, do not create anything
EOF
}

CHECK_ONLY=false
for arg in "$@"; do
  case "$arg" in
    --check) CHECK_ONLY=true ;;
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

preflight() {
  require_cmd virsh "$QEMU_IMG" "$CLOUD_LOCALDS" ssh ssh-keygen curl envsubst xmllint kubectl

  [[ -r /dev/kvm && -w /dev/kvm ]] ||
    die "/dev/kvm is not readable/writable; add the current user to the kvm group"
  virsh_system version >/dev/null 2>&1 ||
    die "cannot talk to qemu:///system; is virtqemud running?"

  [[ "$K3S_VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+\+k3s[0-9]+$ ]] ||
    die "K3S_VERSION must be a pinned release like v1.31.4+k3s1 (got: $K3S_VERSION)"

  mkdir -p "$LAB_IMAGE_DIR" "$LAB_STATE_DIR"

  local free_gb
  free_gb=$(df -Pk "$LAB_IMAGE_DIR" | awk 'NR==2 {print int($4 / 1024 / 1024)}')
  ((free_gb >= 8)) ||
    die "need at least 8 GB free where the images live ($LAB_IMAGE_DIR), have ${free_gb} GB"

  local nominal_gb=$((LAB_SERVER_DISK_GB + LAB_WORKER_DISK_GB))
  if ((free_gb < nominal_gb)); then
    warn "disks are ${nominal_gb} GB nominal but only ${free_gb} GB free; qcow2 is sparse, but a full disk will break the lab"
  fi

  if net_exists; then
    local xml
    xml=$(virsh_system net-dumpxml "$LAB_NETWORK_NAME")
    if ! grep -q "$LAB_GATEWAY" <<<"$xml"; then
      die "network $LAB_NETWORK_NAME exists but is not on $LAB_NETWORK_CIDR; remove it or set LAB_NETWORK_NAME"
    fi
  else
    local name net_xml
    while read -r name; do
      [[ -n "$name" && "$name" != "$LAB_NETWORK_NAME" ]] || continue
      net_xml=$(virsh_system net-dumpxml "$name" 2>/dev/null || true)
      if grep -q "$LAB_GATEWAY" <<<"$net_xml"; then
        die "libvirt network '$name' already uses $LAB_GATEWAY; set LAB_NETWORK_CIDR/LAB_GATEWAY"
      fi
    done < <(virsh_system net-list --all --name)
  fi

  log "preflight ok (free ${free_gb} GB, K3s ${K3S_VERSION}, network ${LAB_NETWORK_CIDR})"
}

wait_for_kubeconfig() {
  local deadline=$((SECONDS + LAB_BOOT_TIMEOUT))
  log "waiting for the K3s server API"
  while ((SECONDS < deadline)); do
    if lab_ssh "$LAB_SERVER_IP" 'sudo test -f /etc/rancher/k3s/k3s.yaml' >/dev/null 2>&1; then
      return
    fi
    sleep 5
  done
  die "K3s server did not write its kubeconfig; check 'virsh console $LAB_SERVER_NAME'"
}

install_k3s_server() {
  if lab_ssh "$LAB_SERVER_IP" 'test -x /usr/local/bin/k3s' >/dev/null 2>&1; then
    log "K3s server already installed"
    return
  fi
  log "installing K3s ${K3S_VERSION} on the server"
  lab_ssh "$LAB_SERVER_IP" \
    "curl -fsSL --retry 5 -o /tmp/k3s-install.sh https://get.k3s.io && sudo env INSTALL_K3S_VERSION='$K3S_VERSION' INSTALL_K3S_EXEC='$K3S_SERVER_ARGS' sh /tmp/k3s-install.sh"
}

fetch_kubeconfig() {
  local tmp="$LAB_STATE_DIR/kubeconfig.tmp"
  log "fetching kubeconfig as context 'aiops-lab'"
  lab_ssh "$LAB_SERVER_IP" 'sudo cat /etc/rancher/k3s/k3s.yaml' >"$tmp"
  chmod 600 "$tmp"

  KUBECONFIG="$tmp" kubectl config set-cluster default \
    --server="https://${LAB_SERVER_IP}:6443" >/dev/null
  KUBECONFIG="$tmp" kubectl config rename-context default aiops-lab >/dev/null
  KUBECONFIG="$tmp" kubectl config use-context aiops-lab >/dev/null
  KUBECONFIG="$tmp" kubectl config view --flatten >"$LAB_KUBECONFIG"
  rm -f "$tmp"
  chmod 600 "$LAB_KUBECONFIG"
}

install_k3s_worker() {
  if lab_ssh "$LAB_WORKER_IP" 'test -x /usr/local/bin/k3s' >/dev/null 2>&1; then
    log "K3s agent already installed"
    return
  fi
  local token
  token=$(lab_ssh "$LAB_SERVER_IP" 'sudo cat /var/lib/rancher/k3s/server/node-token')
  [[ -n "$token" ]] || die "could not read the K3s node token"
  log "installing K3s ${K3S_VERSION} agent on the worker"
  lab_ssh "$LAB_WORKER_IP" \
    "curl -fsSL --retry 5 -o /tmp/k3s-install.sh https://get.k3s.io && sudo env INSTALL_K3S_VERSION='$K3S_VERSION' K3S_URL='https://${LAB_SERVER_IP}:6443' K3S_TOKEN='$token' sh /tmp/k3s-install.sh"
}

wait_for_nodes() {
  local want=$1 deadline=$((SECONDS + LAB_BOOT_TIMEOUT))
  log "waiting for ${want} Ready node(s)"
  while ((SECONDS < deadline)); do
    local ready
    ready=$(KUBECONFIG="$LAB_KUBECONFIG" kubectl get nodes --no-headers 2>/dev/null |
      awk '$2 == "Ready" {n++} END {print n + 0}')
    if ((ready >= want)); then
      return
    fi
    sleep 5
  done
  KUBECONFIG="$LAB_KUBECONFIG" kubectl get nodes || true
  die "timed out waiting for ${want} Ready node(s)"
}

ensure_namespace() {
  KUBECONFIG="$LAB_KUBECONFIG" kubectl create namespace "$LAB_NAMESPACE" \
    --dry-run=client -o yaml |
    KUBECONFIG="$LAB_KUBECONFIG" kubectl apply -f - >/dev/null
}

summary() {
  cat <<EOF

[lab] lab is ready.

  kubeconfig : $LAB_KUBECONFIG (mode 600, context aiops-lab)
  server     : $LAB_SSH_USER@$LAB_SERVER_IP   (virsh console $LAB_SERVER_NAME)
  worker     : $LAB_SSH_USER@$LAB_WORKER_IP   (virsh console $LAB_WORKER_NAME)
  namespace  : $LAB_NAMESPACE

  export KUBECONFIG="$LAB_KUBECONFIG"
  kubectl get nodes -o wide
  bash deploy/lab/lib/lab-guard.sh

  Destroy VMs: make lab-down   (add --wipe to delete disks and state)
EOF
}

preflight
if $CHECK_ONLY; then
  exit 0
fi

ensure_dirs
ensure_qemu_traversal "$LAB_IMAGE_DIR" "$LAB_STATE_DIR"
ensure_ssh_key
export LAB_SSH_PUBLIC_KEY_CONTENT
LAB_SSH_PUBLIC_KEY_CONTENT="$(cat "$LAB_SSH_PUBLIC_KEY")"
ensure_base_image
ensure_network

define_domain "$LAB_SERVER_NAME" "$LAB_SERVER_NAME" "$LAB_SERVER_VCPUS" \
  "$LAB_SERVER_MEM_MB" "$LAB_SERVER_DISK_GB" "$LAB_SERVER_MAC" "$LAB_SERVER_IP"
start_domain "$LAB_SERVER_NAME"
wait_for_ssh "$LAB_SERVER_IP"
wait_for_cloud_init "$LAB_SERVER_IP"
install_k3s_server
wait_for_kubeconfig
fetch_kubeconfig
wait_for_nodes 1

define_domain "$LAB_WORKER_NAME" "$LAB_WORKER_NAME" "$LAB_WORKER_VCPUS" \
  "$LAB_WORKER_MEM_MB" "$LAB_WORKER_DISK_GB" "$LAB_WORKER_MAC" "$LAB_WORKER_IP"
start_domain "$LAB_WORKER_NAME"
wait_for_ssh "$LAB_WORKER_IP"
wait_for_cloud_init "$LAB_WORKER_IP"
install_k3s_worker
wait_for_nodes 2

ensure_namespace
summary
