# QEMU/libvirt lab (S1-B1)

A disposable two-node K3s cluster used for development, fault injection and the
experiments in `docs/EXPERIMENTS.md`. Nothing here touches a real site.

```
host (Arch, KVM/libvirt)
└── libvirt NAT network aiops-lab 192.168.100.0/24 (gateway .1)
    ├── aiops-edge-server  192.168.100.10  2 vCPU / 3 GB / 10 GB  K3s server
    └── aiops-edge-worker  192.168.100.11  2 vCPU / 2 GB /  8 GB  K3s agent
```

The K3s API is only reachable from the host and from the lab network; no port
is forwarded to the host's external interfaces. Fault injection is allowed
**only** in this cluster and only in the `aiops-test` namespace.

## Prerequisites

- Linux with KVM (`/dev/kvm`) and libvirt. On Arch the modular daemons
  (`virtqemud.socket`, `virtnetworkd.socket`, `virtstoraged.socket`) are used;
  monolithic `libvirtd` is not required.
- The current user can talk to `qemu:///system` and is in the `kvm` group.
- `virsh`, `qemu-img`, `cloud-localds` (`cloud-image-utils`), `xmllint`,
  `ssh`, `kubectl`, `envsubst` (`gettext`), `curl`.

Check without creating anything:

```bash
make lab-check          # == bash deploy/lab/lab-up.sh --check
```

## Quick start

```bash
make lab-up                              # idempotent; safe to re-run
export KUBECONFIG="$PWD/deploy/lab/.state/kubeconfig"
kubectl get nodes -o wide
bash deploy/lab/lib/lab-guard.sh         # confirms context aiops-lab
```

SSH to a node:

```bash
ssh -i deploy/lab/.state/ssh/id_ed25519 aiops@192.168.100.10
virsh -c qemu:///system console aiops-edge-server
```

Destroy it:

```bash
make lab-down            # stop + undefine VMs and network, keep disks
make lab-down ARGS=--wipe  # also delete disks, seeds, kubeconfig, SSH keys
```

## What `lab-up.sh` does

1. Preflight: KVM, libvirt, tools, free disk, network CIDR conflicts, pinned
   K3s version.
2. Downloads the Debian 12 genericcloud image once to `images/` (git-ignored).
3. Creates two sparse qcow2 disks as copies of the base image and resizes them.
4. Renders cloud-init (`node.yaml.tmpl`, `meta-data.tmpl`) and a NoCloud seed
   ISO per VM, then defines/starts the domains from `templates/domain.xml.tmpl`.
   The node's user-data writes `/etc/systemd/network/10-lab.network` with the
   static lab IP; cloud-init's own network config is disabled because this
   image only runs `netplan generate` and never applies it.
5. Renders `templates/network.xml.tmpl` with DHCP host reservations and NAT.
6. Waits for SSH and cloud-init, installs the pinned K3s server, fetches the
   kubeconfig, then installs the agent and waits for two `Ready` nodes.
7. Writes `deploy/lab/.state/kubeconfig` with mode `600` and context
   `aiops-lab`, and creates the `aiops-test` namespace.

Re-running reconciles an existing lab: it updates definitions, reuses disks and
skips already-installed K3s.

## Disk budget

`docs/SPEC.md` §13 describes 30–40 GB + 25 GB. This host does not have that
free, so the defaults are **10 GB + 8 GB sparse qcow2**. Sparse files only use
what the guest writes, but a full disk will break the lab. Override when more
space is available:

```bash
LAB_SERVER_DISK_GB=30 LAB_WORKER_DISK_GB=25 make lab-up
```

`lab-up.sh --check` requires at least 8 GB free and warns when free space is
below the nominal disk size. The base image and disks live in `deploy/lab/images/`,
which is git-ignored.

`/home/<user>` is often mode `0710`, so QEMU cannot traverse it even though it
can read the disk. `lab-up.sh` adds a traverse-only ACL for the libvirt QEMU
user on the missing ancestors (`setfacl -m u:libvirt-qemu:x`). This grants no
read access and can be removed with
`setfacl -x u:libvirt-qemu /home/<user>`. Set `LAB_QEMU_USER=qemu` on hosts
where libvirt uses the `qemu` account instead.

## Configuration

Everything lives in `lab.conf` and can be overridden from the environment:

| Variable | Default | Notes |
|---|---|---|
| `LAB_NETWORK_NAME` | `aiops-lab` | Dedicated NAT network; `labnet` is untouched |
| `LAB_NETWORK_CIDR` / `LAB_GATEWAY` | `192.168.100.0/24` / `.1` | `lab-up --check` rejects conflicts |
| `LAB_SERVER_IP` / `LAB_WORKER_IP` | `.10` / `.11` | Static addresses written by cloud-init; also DHCP reservations by MAC |
| `LAB_SERVER_MEM_MB` / `LAB_WORKER_MEM_MB` | `3072` / `2048` | |
| `LAB_SERVER_DISK_GB` / `LAB_WORKER_DISK_GB` | `10` / `8` | Sparse |
| `K3S_VERSION` | `v1.31.4+k3s1` | Pinned; `--check` rejects unpinned values |
| `K3S_SERVER_ARGS` | `--disable traefik --write-kubeconfig-mode 600 --tls-san <server IP>` | |
| `LAB_SSH_USER` | `aiops` | Passwordless sudo, key-only login |
| `LAB_QEMU_USER` | `libvirt-qemu` | Host user QEMU runs as under `qemu:///system` |
| `LAB_NAMESPACE` | `aiops-test` | Fault-injection namespace |

## Context guard

`deploy/lab/lib/lab-guard.sh` exits non-zero unless:

- the current kube context is exactly `aiops-lab`, **and**
- that context points at `https://192.168.100.10:6443`.

Use it at the start of any script that talks to Kubernetes:

```bash
KUBECONFIG=deploy/lab/.state/kubeconfig bash deploy/lab/lib/lab-guard.sh
```

It deliberately does not accept "looks like a lab" heuristics: a different
cluster must never receive fault injection by accident.

## Troubleshooting

| Symptom | Check |
|---|---|
| `cannot talk to qemu:///system` | `systemctl status virtqemud.socket virtnetworkd.socket`; connect with `virsh -c qemu:///system list` |
| VM starts then shuts down | `virsh -c qemu:///system console aiops-edge-server`; disk/permission errors are in `/var/log/libvirt/qemu/<name>.log` |
| SSH never comes up | `virsh domifaddr aiops-edge-server --source lease`; inspect the console for cloud-init errors |
| No internet in the VM | `virsh net-dhcp-leases aiops-lab`; the VMs use static IPs, so check `systemctl status systemd-networkd` inside the guest and the `10-lab.network` file |
| K3s server not ready | `ssh ... 'sudo journalctl -u k3s -n 100 --no-pager'` |
| Worker not joining | `ssh ... 'sudo journalctl -u k3s-agent -n 100 --no-pager'`; re-check the node token |
| Wrong `qemu-img` | On this host `PATH` resolves to an old Android SDK copy; `lab.conf` uses `/usr/bin/qemu-img` |
| Network conflict | `virsh net-list --all`; change `LAB_NETWORK_NAME`/`LAB_GATEWAY` or remove the stale network |

Logs and state are under `deploy/lab/.state/` (git-ignored): rendered XML,
cloud-init user-data/meta-data/seed ISOs, the SSH key and the kubeconfig.

## Not implemented yet

- The optional plain Linux VM (no Kubernetes) from the original target table.
- ARM/Raspberry Pi images; the lab is x86_64 only.
- Automatic host reboot recovery: `virsh` autostart is set on the network and
  domains, but a reboot has not been exercised in this task.
- `shellcheck` is not installed on this host, so the scripts are checked with
  `bash -n` and the unit tests, not shellcheck.
