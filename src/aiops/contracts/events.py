"""Pydantic models mirroring contracts/schemas/event-envelope.v1.schema.json."""

from __future__ import annotations

from typing import Any, Literal, get_args

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

Severity = Literal["info", "warning", "error", "critical"]
EntityKind = Literal["site", "node", "namespace", "workload", "pod", "container", "service"]
EventType = Literal[
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
]

EVENT_TYPES: frozenset[str] = frozenset(get_args(EventType))


class Entity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: EntityKind
    id: str = Field(min_length=1)


class EventData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    observed_at: AwareDatetime
    severity: Severity
    entity: Entity
    payload: dict[str, Any]


class EventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    specversion: Literal["1.0"]
    id: str = Field(min_length=1)
    source: str = Field(pattern=r"^urn:aiops:site:[^:]+:[a-z0-9-]+$")
    type: EventType
    subject: str = Field(min_length=1)
    time: AwareDatetime
    datacontenttype: Literal["application/json"] | None = None
    dataschema: str | None = None
    data: EventData


__all__ = [
    "EVENT_TYPES",
    "Entity",
    "EntityKind",
    "EventData",
    "EventEnvelope",
    "EventType",
    "Severity",
]
