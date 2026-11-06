#!/usr/bin/env bash
# Build shop-demo on the host and import it into both lab nodes.
# The lab is disposable: the image is loaded into containerd directly, not
# pushed to a registry. After loading, this script pins the digest in
# deploy/shop-demo/kustomization.yaml unless --no-pin is passed.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHOP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ROOT="$(cd "$SHOP_DIR/../.." && pwd)"

# shellcheck source=../../lab/lab.conf
set -a
source "$ROOT/deploy/lab/lab.conf"
set +a
# shellcheck source=../../lab/lib.sh
source "$ROOT/deploy/lab/lib.sh"

TAG="${TAG:-0.1.0}"
PIN=true
for arg in "$@"; do
  case "$arg" in
    --no-pin) PIN=false ;;
    -h | --help)
      echo "Usage: build-and-load.sh [--no-pin]"
      exit 0
      ;;
    *)
      die "unknown argument: $arg"
      ;;
  esac
done

require_cmd docker ssh scp awk
export KUBECONFIG="${KUBECONFIG:-$LAB_KUBECONFIG}"
bash "$ROOT/deploy/lab/lib/lab-guard.sh"

image="shop-demo:$TAG"
log "building $image"
docker build -t "$image" "$SHOP_DIR/app"

tar="$(mktemp)"
trap 'rm -f "$tar"' EXIT
docker save "$image" -o "$tar"
log "image tar: $(du -h "$tar" | cut -f1)"

for ip in "$LAB_SERVER_IP" "$LAB_WORKER_IP"; do
  log "loading $image on $ip"
  scp "${LAB_SSH_OPTS[@]}" -i "$LAB_SSH_PRIVATE_KEY" \
    "$tar" "$LAB_SSH_USER@$ip:/tmp/shop-demo-image.tar"
  lab_ssh "$ip" 'sudo k3s ctr images import /tmp/shop-demo-image.tar && rm -f /tmp/shop-demo-image.tar'
done

ref="docker.io/library/shop-demo:$TAG"
digest="$(lab_ssh "$LAB_SERVER_IP" 'sudo k3s ctr images ls' |
  awk -v ref="$ref" '$1 == ref {print $3; exit}')"
[[ "$digest" == sha256:* ]] || die "could not read the image digest from the lab"

# A digest reference is a separate key in containerd's image store. Without
# this extra tag the kubelet would try Docker Hub for `shop-demo@sha256:...`
# and fail with "pull access denied".
for ip in "$LAB_SERVER_IP" "$LAB_WORKER_IP"; do
  if ! out=$(lab_ssh "$ip" "sudo k3s ctr images tag 'docker.io/library/shop-demo:$TAG' 'docker.io/library/shop-demo@$digest'" 2>&1); then
    [[ "$out" == *"already exists"* ]] || die "could not tag $digest on $ip: $out"
  fi
done

log "image digest: $digest"

if $PIN; then
  python3 - "$SHOP_DIR/kustomization.yaml" "$SHOP_DIR/app-deployment.yaml" "$digest" <<'PY'
import re
import sys

kustomization, deployment, digest = sys.argv[1:4]

text = open(kustomization, encoding="utf-8").read()
text, count = re.subn(r"(?m)^(\s*)(?:newTag|digest):.*$", rf"\1digest: {digest}", text)
if count != 1:
    raise SystemExit(f"expected one newTag/digest line in {kustomization}, found {count}")
open(kustomization, "w", encoding="utf-8").write(text)

text = open(deployment, encoding="utf-8").read()
text, count = re.subn(
    r'(?m)^(\s*aiops\.io/image-digest:\s*)"[^"]*"$', rf'\1"{digest}"', text
)
if count != 1:
    raise SystemExit(f"expected one aiops.io/image-digest annotation in {deployment}, found {count}")
open(deployment, "w", encoding="utf-8").write(text)
PY
  log "pinned $digest in kustomization.yaml and app-deployment.yaml"
else
  log "not pinning; pass the digest above to kustomization.yaml manually"
fi
