"""Static checks for the QEMU/libvirt lab (S1-B1).

These do not need libvirt or KVM: they check that the shell scripts parse and
that every template renders to valid XML/YAML with no unsubstituted variables.
"""

from __future__ import annotations

import string
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
LAB = ROOT / "deploy" / "lab"

SHELL_FILES = [
    LAB / "lab.conf",
    LAB / "lib.sh",
    LAB / "lab-up.sh",
    LAB / "lab-down.sh",
    LAB / "lib" / "lab-guard.sh",
]

TEMPLATE_VALUES = {
    "LAB_NETWORK_NAME": "aiops-lab",
    "LAB_BRIDGE": "virbr-aiops",
    "LAB_GATEWAY": "192.168.100.1",
    "LAB_DNS_SERVER": "192.168.1.254",
    "LAB_NETWORK_PREFIX": "24",
    "LAB_DHCP_START": "192.168.100.100",
    "LAB_DHCP_END": "192.168.100.199",
    "LAB_SERVER_IP": "192.168.100.10",
    "LAB_SERVER_MAC": "52:54:00:10:00:01",
    "LAB_WORKER_IP": "192.168.100.11",
    "LAB_WORKER_MAC": "52:54:00:10:00:02",
    "LAB_VM_NAME": "aiops-edge-server",
    "LAB_VM_MEM_MB": "3072",
    "LAB_VM_VCPUS": "2",
    "LAB_VM_DISK": "/tmp/aiops-edge-server.qcow2",
    "LAB_VM_SEED": "/tmp/aiops-edge-server-seed.iso",
    "LAB_VM_MAC": "52:54:00:10:00:01",
    "LAB_VM_IP": "192.168.100.10",
    "LAB_VM_HOSTNAME": "aiops-edge-server",
    "LAB_VM_INSTANCE_ID": "aiops-edge-server",
    "LAB_SSH_USER": "aiops",
    "LAB_SSH_PUBLIC_KEY_CONTENT": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITEST aiops-lab",
}


def render(path: Path) -> str:
    text = path.read_text()
    out = string.Template(text).safe_substitute(TEMPLATE_VALUES)
    assert "${LAB_" not in out, f"{path.name}: unsubstituted variable"
    return out


@pytest.mark.parametrize("path", SHELL_FILES, ids=lambda p: p.name)
def test_shell_files_parse(path: Path):
    result = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_network_template_is_valid_xml():
    root = ET.fromstring(render(LAB / "templates" / "network.xml.tmpl"))
    assert root.tag == "network"
    assert root.find("bridge").get("name") == "virbr-aiops"
    assert root.find("ip").get("address") == "192.168.100.1"
    hosts = root.findall("./ip/dhcp/host")
    assert {h.get("ip") for h in hosts} == {"192.168.100.10", "192.168.100.11"}


def test_domain_template_is_valid_xml():
    root = ET.fromstring(render(LAB / "templates" / "domain.xml.tmpl"))
    assert root.tag == "domain"
    assert root.get("type") == "kvm"
    assert root.findtext("memory") == "3072"
    disks = root.findall("./devices/disk")
    assert len(disks) == 2
    assert disks[0].find("source").get("file") == "/tmp/aiops-edge-server.qcow2"
    assert disks[1].find("source").get("file") == "/tmp/aiops-edge-server-seed.iso"
    assert root.find("./devices/interface/source").get("network") == "aiops-lab"


def test_cloud_init_is_valid_yaml():
    data = yaml.safe_load(render(LAB / "cloud-init" / "node.yaml.tmpl"))
    assert data["hostname"] == "aiops-edge-server"
    assert data["ssh_pwauth"] is False
    assert data["network"]["config"] == "disabled"
    assert data["users"][0]["name"] == "aiops"
    assert data["users"][0]["ssh_authorized_keys"][0].startswith("ssh-ed25519 ")
    assert "qemu-guest-agent" in data["packages"]

    network_file = data["write_files"][0]
    assert network_file["path"] == "/etc/systemd/network/10-lab.network"
    assert "MACAddress=52:54:00:10:00:01" in network_file["content"]
    assert "Address=192.168.100.10/24" in network_file["content"]

    # $UPTIME belongs to the guest shell and must not be rendered away.
    assert "$UPTIME" in data["final_message"]


def test_meta_data_is_valid_yaml():
    data = yaml.safe_load(render(LAB / "cloud-init" / "meta-data.tmpl"))
    assert data == {
        "instance-id": "aiops-edge-server",
        "local-hostname": "aiops-edge-server",
    }


def test_prepare_cloud_init_writes_the_node_network(tmp_path: Path):
    """Regression: cloud-init must receive the node MAC and IP, not empty values."""
    stub = tmp_path / "cloud-localds"
    stub.write_text('#!/usr/bin/env bash\ntouch "$3"\n')
    stub.chmod(0o755)

    state = tmp_path / "state"
    script = f"""
set -euo pipefail
set -a
source "{LAB / "lab.conf"}"
set +a
source "{LAB / "lib.sh"}"
LAB_STATE_DIR="{state}"
LAB_CLOUD_INIT_DIR="{LAB / "cloud-init"}"
LAB_TEMPLATE_DIR="{LAB / "templates"}"
CLOUD_LOCALDS="{stub}"
LAB_SSH_USER=aiops
LAB_SSH_PUBLIC_KEY_CONTENT="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITEST aiops-lab"
mkdir -p "$LAB_STATE_DIR/cloud-init"
prepare_cloud_init aiops-edge-server aiops-edge-server 52:54:00:10:00:01 192.168.100.10
cat "$LAB_STATE_DIR/cloud-init/aiops-edge-server-user-data.yaml"
"""
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    data = yaml.safe_load(result.stdout)
    content = data["write_files"][0]["content"]
    assert "MACAddress=52:54:00:10:00:01" in content
    assert "Address=192.168.100.10/24" in content
    assert '""' not in result.stdout


def test_lab_conf_defaults_are_sane():
    result = subprocess.run(
        [
            "bash",
            "-c",
            f'source "{LAB / "lab.conf"}"; '
            'printf "%s|%s|%s|%s\\n" "$LAB_NETWORK_NAME" "$LAB_SERVER_IP" '
            '"$LAB_SERVER_DISK_GB" "$K3S_VERSION"',
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "aiops-lab|192.168.100.10|10|v1.31.4+k3s1"
