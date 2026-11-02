import json
from pathlib import Path

from aiops.common.redact import redact
from aiops.common.time import parse_rfc3339
from aiops.contracts.actions import action_levels, level_for_scale, load_yaml
from aiops.contracts.events import EventEnvelope

ROOT = Path(__file__).resolve().parents[2]


def test_event_example_parses_into_model():
    data = json.loads((ROOT / "contracts/examples/event-envelope.v1.example.json").read_text())
    ev = EventEnvelope.model_validate(data)
    assert ev.data.payload["feature_schema_version"] == "1"
    assert len(ev.data.payload["top_features"]) == 3


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
    import pytest

    with pytest.raises(ValueError):
        parse_rfc3339("2026-11-02T10:30:00")


def test_redaction():
    out = redact("Authorization: Bearer abc.def.ghi and password=hunter2")
    assert "abc.def.ghi" not in out and "hunter2" not in out
