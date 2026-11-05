"""Pydantic models mirroring contracts/schemas/incident.v1.schema.json."""

from __future__ import annotations

from typing import Literal, get_args

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from aiops.contracts.events import EntityKind, Severity

IncidentStatus = Literal[
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
]

INCIDENT_STATUSES: frozenset[str] = frozenset(get_args(IncidentStatus))


class IncidentEntityRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: EntityKind
    id: str = Field(min_length=1)


class Incident(BaseModel):
    model_config = ConfigDict(extra="forbid")
    local_incident_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    fingerprint: str = Field(min_length=1)
    severity: Severity
    status: IncidentStatus
    opened_at: AwareDatetime
    updated_at: AwareDatetime
    resolved_at: AwareDatetime | None = None
    entity_refs: list[IncidentEntityRef] = Field(min_length=1)
    event_ids: list[str] = Field(min_length=1)


__all__ = ["INCIDENT_STATUSES", "Incident", "IncidentEntityRef", "IncidentStatus"]
