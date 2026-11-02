"""Pydantic models mirroring contracts/schemas/event-envelope.v1.schema.json."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["info", "warning", "error", "critical"]


class Entity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["site", "node", "namespace", "workload", "pod", "container", "service"]
    id: str


class EventData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    observed_at: datetime
    severity: Severity
    entity: Entity
    payload: dict[str, Any]


class EventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    specversion: Literal["1.0"]
    id: str = Field(min_length=1)
    source: str = Field(pattern=r"^urn:aiops:site:[^:]+:[a-z0-9-]+$")
    type: str
    subject: str
    time: datetime
    datacontenttype: Literal["application/json"] | None = None
    dataschema: str | None = None
    data: EventData
