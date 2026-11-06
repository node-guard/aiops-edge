"""Security checks for the shop-demo lab manifests (S1-B2)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
SHOP = ROOT / "deploy" / "shop-demo"


def load_documents() -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for path in sorted(SHOP.glob("*.yaml")):
        documents.extend(doc for doc in yaml.safe_load_all(path.read_text()) if doc)
    return documents


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


def test_kustomization_targets_the_lab_namespace():
    kustomization = yaml.safe_load((SHOP / "kustomization.yaml").read_text())
    assert kustomization["namespace"] == "aiops-test"
    for resource in kustomization["resources"]:
        assert (SHOP / resource).is_file(), resource


def test_no_image_uses_latest_or_no_tag():
    for container in find_containers(load_documents()):
        image = container.get("image", "")
        assert image, container
        assert not image.endswith(":latest"), image
        assert "@sha256:" in image or ":" in image.rsplit("/", 1)[-1], image


def test_containers_are_not_privileged_or_host_namespaced():
    documents = load_documents()
    serialized = yaml.safe_dump_all(documents)
    assert "privileged: true" not in serialized
    assert "hostNetwork: true" not in serialized
    assert "hostPID: true" not in serialized
    for container in find_containers(documents):
        security = container.get("securityContext", {})
        assert security.get("allowPrivilegeEscalation") is not True
        assert security.get("privileged") is not True


def test_database_password_comes_from_a_secret():
    app = next(
        doc
        for doc in load_documents()
        if doc.get("kind") == "Deployment" and doc["metadata"]["name"] == "shop-demo"
    )
    container = app["spec"]["template"]["spec"]["containers"][0]
    env = {item["name"]: item for item in container["env"]}
    password = env["DB_PASSWORD"]
    assert "value" not in password
    assert password["valueFrom"]["secretKeyRef"] == {
        "name": "shop-demo-db",
        "key": "DB_PASSWORD",
    }
    # The secret file is an example: its value must be base64, not plaintext.
    secret = next(doc for doc in load_documents() if doc.get("kind") == "Secret")
    assert "stringData" not in secret
    assert set(secret["data"]) >= {"POSTGRES_PASSWORD", "DB_PASSWORD"}


def test_application_has_health_probes_and_two_replicas():
    app = next(
        doc
        for doc in load_documents()
        if doc.get("kind") == "Deployment" and doc["metadata"]["name"] == "shop-demo"
    )
    assert app["spec"]["replicas"] == 2
    container = app["spec"]["template"]["spec"]["containers"][0]
    assert container["livenessProbe"]["httpGet"]["path"] == "/health/live"
    assert container["readinessProbe"]["httpGet"]["path"] == "/health/ready"
    assert container["ports"][0]["containerPort"] == 8080


def test_service_is_nodeport_and_database_is_private():
    services = {
        doc["metadata"]["name"]: doc for doc in load_documents() if doc.get("kind") == "Service"
    }
    assert services["shop-demo"]["spec"]["type"] == "NodePort"
    assert services["shop-demo"]["spec"]["ports"][0]["nodePort"] == 30080
    assert services["shop-demo-db"]["spec"]["type"] == "ClusterIP"
