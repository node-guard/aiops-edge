"""Security and correctness checks for the edge-stack Helm chart (S2-B1).

These tests render the chart with Helm and assert the properties that matter
for the security boundary in docs/SPEC.md §12: least-privilege RBAC, pinned
images, no secrets, no privileged workloads, and resource limits everywhere.

They are skipped when Helm is not installed locally. CI installs Helm before
running ``make check``, so the checks are enforced on every pull request.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "deploy" / "helm" / "edge-stack"
NAMESPACE = "aiops-system"
DIGEST = re.compile(r"@sha256:[a-f0-9]{64}$")

pytestmark = pytest.mark.skipif(shutil.which("helm") is None, reason="helm is not installed")


def helm_template(*extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "helm",
            "template",
            "edge-stack",
            str(CHART),
            "--namespace",
            NAMESPACE,
            *extra,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def render(*extra: str) -> list[dict[str, Any]]:
    result = helm_template(*extra)
    assert result.returncode == 0, result.stderr
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def find_containers(node: Any) -> list[dict[str, Any]]:
    containers: list[dict[str, Any]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key in {"containers", "initContainers"} and isinstance(value, list):
                containers.extend(item for item in value if isinstance(item, dict))
            else:
                containers.extend(find_containers(value))
    elif isinstance(node, list):
        for item in node:
            containers.extend(find_containers(item))
    return containers


def workload_documents() -> list[dict[str, Any]]:
    return [doc for doc in render() if doc["kind"] in {"Deployment", "StatefulSet", "DaemonSet"}]


def test_chart_renders_the_expected_workloads():
    kinds = sorted(doc["kind"] for doc in render())
    assert kinds.count("ServiceAccount") == 3
    assert kinds.count("StatefulSet") == 2
    assert kinds.count("DaemonSet") == 1
    assert kinds.count("Deployment") == 1
    assert "Secret" not in kinds
    assert "CustomResourceDefinition" not in kinds


def test_every_container_has_requests_and_limits():
    for doc in workload_documents():
        for container in find_containers(doc["spec"]["template"]["spec"]):
            resources = container.get("resources", {})
            for section in ("requests", "limits"):
                assert resources.get(section, {}).get("cpu"), (
                    doc["metadata"]["name"],
                    container["name"],
                    section,
                )
                assert resources.get(section, {}).get("memory"), (
                    doc["metadata"]["name"],
                    container["name"],
                    section,
                )


def test_every_image_is_pinned_to_a_digest():
    images = [
        container["image"]
        for doc in workload_documents()
        for container in find_containers(doc["spec"]["template"]["spec"])
    ]
    assert images
    for image in images:
        assert "@sha256:" in image, image
        assert DIGEST.search(image), image
        assert ":latest" not in image, image


def test_containers_are_unprivileged_and_read_only():
    for doc in workload_documents():
        for container in find_containers(doc["spec"]["template"]["spec"]):
            security = container.get("securityContext", {})
            assert security.get("allowPrivilegeEscalation") is False
            assert security.get("privileged") is not True
            assert security.get("readOnlyRootFilesystem") is True
            assert security.get("capabilities", {}).get("drop") == ["ALL"]
        pod_security = doc["spec"]["template"]["spec"].get("securityContext", {})
        assert pod_security.get("runAsNonRoot") is True
        assert pod_security.get("seccompProfile", {}).get("type") == "RuntimeDefault"


def test_only_node_exporter_uses_host_namespaces():
    for doc in workload_documents():
        spec = doc["spec"]["template"]["spec"]
        if doc["metadata"]["name"].endswith("node-exporter"):
            assert spec.get("hostNetwork") is True
            assert spec.get("hostPID") is True
        else:
            assert spec.get("hostNetwork") is not True, doc["metadata"]["name"]
            assert spec.get("hostPID") is not True, doc["metadata"]["name"]


def test_rbac_is_read_only_and_never_touches_secrets():
    documents = render()
    roles = [doc for doc in documents if doc["kind"] == "ClusterRole"]
    assert {role["metadata"]["name"].rsplit("-", 1)[-1] for role in roles} == {
        "telemetry",
        "observer",
    }
    for role in roles:
        for rule in role["rules"]:
            assert "*" not in rule.get("apiGroups", []), role["metadata"]["name"]
            assert "*" not in rule.get("resources", []), role["metadata"]["name"]
            assert "*" not in rule.get("verbs", []), role["metadata"]["name"]
            assert set(rule["verbs"]) <= {"get", "list", "watch"}, (
                role["metadata"]["name"],
                rule["verbs"],
            )
            assert "secrets" not in rule.get("resources", []), role["metadata"]["name"]
            assert "configmaps" not in rule.get("resources", []), role["metadata"]["name"]


def test_cluster_roles_are_not_cluster_admin_and_bind_only_known_identities():
    documents = render()
    for binding in [doc for doc in documents if doc["kind"] == "ClusterRoleBinding"]:
        assert binding["roleRef"]["name"] != "cluster-admin"
        assert binding["roleRef"]["kind"] == "ClusterRole"
        for subject in binding["subjects"]:
            assert subject["kind"] == "ServiceAccount"
            assert subject["name"] in {"aiops-telemetry", "aiops-observer"}
            assert subject["namespace"] == NAMESPACE


def test_remediation_executor_has_no_token_and_no_binding():
    documents = render()
    executor = next(
        doc
        for doc in documents
        if doc["kind"] == "ServiceAccount"
        and doc["metadata"]["name"] == "aiops-remediation-executor"
    )
    assert executor["automountServiceAccountToken"] is False
    for binding in [doc for doc in documents if doc["kind"] == "ClusterRoleBinding"]:
        assert all(
            subject["name"] != "aiops-remediation-executor" for subject in binding["subjects"]
        )


def test_prometheus_scrapes_node_and_pod_metrics_without_overwriting_labels():
    config_map = next(
        doc
        for doc in render()
        if doc["kind"] == "ConfigMap" and doc["metadata"]["name"].endswith("prometheus-config")
    )
    config = yaml.safe_load(config_map["data"]["prometheus.yml"])
    jobs = {job["job_name"]: job for job in config["scrape_configs"]}
    assert set(jobs) == {"prometheus", "node-exporter", "kube-state-metrics"}
    assert config["global"]["external_labels"]["site"] == "lab"

    ksm_relabels = jobs["kube-state-metrics"]["relabel_configs"]
    overwritten = {relabel["target_label"] for relabel in ksm_relabels if "target_label" in relabel}
    # kube-state-metrics already exports namespace/pod; overwriting them with
    # the exporter's own namespace silently corrupts every kube_* metric.
    assert overwritten.isdisjoint({"namespace", "pod", "service"})


@pytest.mark.parametrize(
    "override",
    [
        "prometheus.retention=banana",
        "prometheus.image.digest=sha256:abc",
        "prometheus.image.tag=latest",
        "kubeStateMetrics.collectedResources=secrets",
        "bogusKey=1",
    ],
)
def test_values_schema_rejects_invalid_input(override: str):
    result = helm_template("--set", override)
    assert result.returncode != 0, override
    assert "schema" in result.stderr.lower(), result.stderr


def test_alertmanager_can_be_disabled_without_dangling_references():
    documents = render("--set", "alertmanager.enabled=false")
    assert not any(
        doc["kind"] == "StatefulSet" and "alertmanager" in doc["metadata"]["name"]
        for doc in documents
    )
    config_map = next(
        doc
        for doc in documents
        if doc["kind"] == "ConfigMap" and doc["metadata"]["name"].endswith("prometheus-config")
    )
    config = yaml.safe_load(config_map["data"]["prometheus.yml"])
    assert "alerting" not in config
    assert json.dumps(config).count("alertmanager") == 0
