"""Pydantic models mirroring contracts/schemas/command-envelope.v1.schema.json."""

from __future__ import annotations

from typing import Any, Literal, Self, get_args
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

ActionId = Literal["ACT-001", "ACT-002", "ACT-003"]
CommandType = Literal["remediation.execute", "diagnostic.run"]
DiagnosticTool = Literal[
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
]

DIAGNOSTIC_TOOLS: frozenset[str] = frozenset(get_args(DiagnosticTool))


class RemediationTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    namespace: str = Field(min_length=1)
    resource_kind: Literal["Deployment"]
    resource_uid: str = Field(min_length=1)


class RemediationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_id: ActionId
    action_version: str = Field(min_length=1)
    target: RemediationTarget
    parameters: dict[str, Any]
    policy_version: str = Field(min_length=1)
    approval_id: UUID | None


class DiagnosticPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: DiagnosticTool
    arguments: dict[str, Any]
    max_bytes: int | None = Field(default=None, ge=1, le=65536)


class CommandEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: UUID
    command_type: CommandType
    site_id: UUID
    issued_at: AwareDatetime
    expires_at: AwareDatetime
    idempotency_key: UUID
    payload: RemediationPayload | DiagnosticPayload

    @model_validator(mode="after")
    def _validate_command(self) -> Self:
        if self.expires_at <= self.issued_at:
            raise ValueError("expires_at must be after issued_at")

        if self.command_type == "remediation.execute":
            if not isinstance(self.payload, RemediationPayload):
                raise ValueError("remediation.execute requires a remediation payload")
            self._validate_remediation(self.payload)
        elif not isinstance(self.payload, DiagnosticPayload):
            raise ValueError("diagnostic.run requires a diagnostic payload")

        return self

    @staticmethod
    def _validate_remediation(payload: RemediationPayload) -> None:
        if payload.action_id == "ACT-002":
            if set(payload.parameters) != {"replicas"}:
                raise ValueError("ACT-002 parameters must contain exactly 'replicas'")
            replicas = payload.parameters["replicas"]
            if isinstance(replicas, bool) or not isinstance(replicas, int):
                raise ValueError("ACT-002 replicas must be an integer")
            if not 0 <= replicas <= 10:
                raise ValueError("ACT-002 replicas must be between 0 and 10")
        elif payload.parameters:
            raise ValueError(f"{payload.action_id} takes no parameters")

        if payload.action_id == "ACT-003" and payload.approval_id is None:
            raise ValueError("ACT-003 is always L2 and requires an approval_id")


__all__ = [
    "DIAGNOSTIC_TOOLS",
    "ActionId",
    "CommandEnvelope",
    "CommandType",
    "DiagnosticPayload",
    "DiagnosticTool",
    "RemediationPayload",
    "RemediationTarget",
]
