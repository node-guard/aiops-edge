#!/usr/bin/env bash
# Refuse to run against anything except the disposable aiops-lab context.
#
# Usage:
#   KUBECONFIG=deploy/lab/.state/kubeconfig bash deploy/lab/lib/lab-guard.sh
#
# Every script that talks to Kubernetes in this repo should call this first.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../lab.conf
set -a
source "$SCRIPT_DIR/lab.conf"
set +a

QUIET=false
if [[ "${1:-}" == "--quiet" ]]; then
  QUIET=true
elif [[ $# -gt 0 ]]; then
  printf '[lab-guard] ERROR: unknown argument: %s\n' "$1" >&2
  exit 2
fi

command -v kubectl >/dev/null 2>&1 || {
  printf '[lab-guard] ERROR: kubectl is not installed\n' >&2
  exit 2
}

export KUBECONFIG="${KUBECONFIG:-$LAB_KUBECONFIG}"

context=$(kubectl config current-context 2>/dev/null || true)
if [[ "$context" != "aiops-lab" ]]; then
  printf '[lab-guard] refusing: current context is "%s", not "aiops-lab"\n' "${context:-<none>}" >&2
  exit 1
fi

server=$(kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}' 2>/dev/null || true)
if [[ "$server" != "https://${LAB_SERVER_IP}:6443" ]]; then
  printf '[lab-guard] refusing: context "aiops-lab" points at "%s", not the lab API https://%s:6443\n' \
    "${server:-<none>}" "$LAB_SERVER_IP" >&2
  exit 1
fi

if ! $QUIET; then
  printf '[lab-guard] ok: context aiops-lab (%s)\n' "$server"
fi
