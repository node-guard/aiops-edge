"""Pydantic models mirroring contracts/schemas/rca-report.v1.schema.json."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from aiops.contracts.commands import ActionId

RcaStatus = Literal["confirmed", "probable", "inconclusive", "unknown"]


class RootCauseCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_id: str = Field(min_length=1)
    fault_type: str = Field(min_length=1)
    rank: int = Field(ge=1)
    evidence_ids: list[str] = Field(min_length=1)


class ConfirmedFact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    statement: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)


class ProposedAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_id: ActionId
    parameters: dict[str, Any]


class RcaReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    investigation_id: str = Field(min_length=1)
    status: RcaStatus
    summary: str = Field(min_length=1)
    root_cause_candidates: list[RootCauseCandidate]
    confirmed_facts: list[ConfirmedFact]
    hypotheses: list[str]
    alternative_hypotheses: list[str]
    missing_evidence: list[str]
    proposed_action: ProposedAction | None = None
    limitations: list[str]


__all__ = [
    "ConfirmedFact",
    "ProposedAction",
    "RcaReport",
    "RcaStatus",
    "RootCauseCandidate",
]
