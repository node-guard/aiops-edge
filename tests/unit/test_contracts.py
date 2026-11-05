import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import BaseModel, ValidationError

from aiops.common.redact import redact
from aiops.common.time import parse_rfc3339
from aiops.contracts.actions import action_levels, level_for_scale, load_yaml
from aiops.contracts.commands import CommandEnvelope
from aiops.contracts.events import EVENT_TYPES, EventEnvelope
from aiops.contracts.incidents import INCIDENT_STATUSES, Incident
from aiops.contracts.rca import RcaReport
from aiops.contracts.run_meta import RunMeta

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "contracts" / "schemas"
EXAMPLES = ROOT / "contracts" / "examples"
INVALID = ROOT / "tests" / "fixtures" / "contracts" / "invalid"

MODELS: dict[str, type[BaseModel]] = {
    "event-envelope": EventEnvelope,
    "incident": Incident,
    "command-envelope": CommandEnvelope,
    "rca-report": RcaReport,
    "run-meta": RunMeta,
}

# Must match SPEC section 6. If this changes, the schema and this list change together.
EXPECTED_EVENT_TYPES = {
    "com.aiops.node.anomaly.detected.v1",
    "com.aiops.node.resource.exhaustion_predicted.v1",
    "com.aiops.node.health.changed.v1",
    "com.aiops.k8s.pod.state_changed.v1",
    "com.aiops.k8s.deployment.health_degraded.v1",
    "com.aiops.app.health_check.failed.v1",
    "com.aiops.network.probe.degraded.v1",
    "com.aiops.alert.firing.v1",
    "com.aiops.site.connectivity.changed.v1",
    "com.aiops.remediation.execution.completed.v1",
    "com.aiops.remediation.verification.failed.v1",
}

# Must match SPEC section 6 and the incident state machine.
EXPECTED_INCIDENT_STATUSES = {
    "NEW",
    "TRIAGING",
    "INVESTIGATING",
    "AWAITING_APPROVAL",
    "REMEDIATING",
    "VERIFYING",
    "RESOLVED",
    "ESCALATED",
    "FALSE_POSITIVE",
    "FAILED",
}

# Must match SPEC section 7. search_runbooks is P1 and may not be implemented until S8.
EXPECTED_DIAGNOSTIC_TOOLS = {
    "get_node_metrics",
    "get_node_status",
    "get_container_metrics",
    "get_pod_status",
    "get_previous_container_logs",
    "search_application_logs",
    "get_service_health",
    "get_network_metrics",
    "get_dependency_graph",
    "get_recent_deployments",
    "search_runbooks",
    "get_related_incidents",
}


def load(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    assert isinstance(data, dict), path
    return data


def schema_for_base(base: str) -> Path:
    return SCHEMAS / f"{base}.v1.schema.json"


def validator_for(base: str) -> Draft202012Validator:
    schema = load(schema_for_base(base))
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)


def base_for_example(path: Path) -> str:
    stem = path.name.removesuffix(".example.json")
    base, _, _version = stem.rpartition(".")
    return base.split(".")[0]


def test_action_levels_match_autonomy_policy():
    catalogue = action_levels()
    policy = load_yaml("contracts/policies/autonomy.yaml")["actions"]
    assert set(catalogue) == set(policy)
    for action_id, level in catalogue.items():
        assert policy[action_id]["level"] == level, action_id


def test_act002_level_rule():
    assert level_for_scale(1, 2, 4) == "L1"
    assert level_for_scale(1, 3, 4) == "L2"  # larger than +1
    assert level_for_scale(3, 2, 4) == "L2"  # scale-in
    assert level_for_scale(4, 5, 4) == "L2"  # beyond max


def test_naive_time_rejected():
    with pytest.raises(ValueError):
        parse_rfc3339("2026-11-02T10:30:00")


def test_redaction():
    out = redact("Authorization: Bearer abc.def.ghi and password=hunter2")
    assert "abc.def.ghi" not in out and "hunter2" not in out


@pytest.mark.parametrize("path", sorted(SCHEMAS.glob("*.schema.json")), ids=lambda p: p.name)
def test_schema_is_valid(path: Path):
    Draft202012Validator.check_schema(load(path))


@pytest.mark.parametrize("path", sorted(SCHEMAS.glob("*.schema.json")), ids=lambda p: p.name)
def test_schema_metadata_and_boundary(path: Path):
    schema = load(path)

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"].endswith(path.name)
    assert schema["title"]
    assert schema["description"]
    # Every contract object is closed at the boundary; open maps (payload/parameters) are
    # explicit nested exceptions, not a top-level hole.
    assert schema.get("additionalProperties") is False

    secret_words = ("secret", "password", "token", "api_key", "private_key", "credential")
    for name in schema.get("properties", {}):
        assert not any(word in name.lower() for word in secret_words), f"{path.name}: {name}"


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.example.json")), ids=lambda p: p.name)
def test_example_validates(path: Path):
    base = base_for_example(path)
    errors = list(validator_for(base).iter_errors(load(path)))
    assert not errors, f"{path.name}: " + "; ".join(err.message for err in errors)


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.example.json")), ids=lambda p: p.name)
def test_example_round_trips_through_model(path: Path):
    base = base_for_example(path)
    model = MODELS[base]
    parsed = model.model_validate(load(path))
    reparsed = model.model_validate(parsed.model_dump(mode="json"))
    assert reparsed == parsed


@pytest.mark.parametrize("path", sorted(INVALID.glob("*.json")), ids=lambda p: p.name)
def test_invalid_fixture_is_rejected(path: Path):
    base = path.name.split(".")[0]
    data = load(path)

    errors = list(validator_for(base).iter_errors(data))
    assert errors, f"{path.name} unexpectedly passed JSON Schema"

    with pytest.raises(ValidationError):
        MODELS[base].model_validate(data)


def test_event_types_match_spec():
    schema = load(schema_for_base("event-envelope"))
    assert set(schema["properties"]["type"]["enum"]) == EXPECTED_EVENT_TYPES
    assert EVENT_TYPES == EXPECTED_EVENT_TYPES


def test_incident_statuses_match_spec():
    schema = load(schema_for_base("incident"))
    assert set(schema["properties"]["status"]["enum"]) == EXPECTED_INCIDENT_STATUSES
    assert INCIDENT_STATUSES == EXPECTED_INCIDENT_STATUSES


def test_diagnostic_tools_cover_spec():
    schema = load(schema_for_base("command-envelope"))
    tools: set[str] = set()
    for branch in schema["allOf"]:
        tool_schema = (
            branch.get("then", {})
            .get("properties", {})
            .get("payload", {})
            .get("properties", {})
            .get("tool")
        )
        if tool_schema:
            tools = set(tool_schema["enum"])
    assert tools == EXPECTED_DIAGNOSTIC_TOOLS


def test_command_expiry_must_be_after_issue():
    data = load(EXAMPLES / "command-envelope.remediation-l1.v1.example.json")
    data["expires_at"] = "2026-11-02T10:29:00Z"

    with pytest.raises(ValidationError):
        CommandEnvelope.model_validate(data)


def test_act003_requires_approval():
    data = load(EXAMPLES / "command-envelope.remediation-l1.v1.example.json")
    data["payload"]["action_id"] = "ACT-003"

    with pytest.raises(ValidationError):
        CommandEnvelope.model_validate(data)


def test_run_meta_valid_run_cannot_carry_invalid_reason():
    data = load(EXAMPLES / "run-meta.v1.example.json")
    data["invalid_reason"] = "not really"

    with pytest.raises(ValidationError):
        RunMeta.model_validate(data)
