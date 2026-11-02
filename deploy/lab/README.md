# QEMU/libvirt lab (S1-B1)

Target: two VMs on a private libvirt network.

| VM | vCPU | RAM | Disk | Role |
|---|---|---|---|---|
| edge-server | 2 | 3-4 GB | 30-40 GB | K3s server + gateway services |
| edge-worker | 2 | 2-3 GB | ~25 GB | K3s agent + fault workloads |
| (optional) plain-host | 1-2 | ~2 GB | ~20 GB | Linux host without Kubernetes |

Example network 192.168.100.0/24 (gateway .1, server .10, worker .11). Adapt if it conflicts.
Rules: K3s API stays private; pin the K3s version; fault injection only here, namespace `aiops-test`; every script must refuse to run against any other kube context.

To implement: `lab-up.sh`, `lab-down.sh`, cloud-init templates, K3s install, kubeconfig fetch to `deploy/lab/.state/` (git-ignored).
