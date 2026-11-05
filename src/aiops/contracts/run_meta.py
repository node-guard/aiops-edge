"""Pydantic models mirroring contracts/schemas/run-meta.v1.schema.json."""

from __future__ import annotations

from typing import Any, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class RunMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str = Field(min_length=1)
    fault_id: str = Field(pattern=r"^F[0-9]{2}$")
    seed: int | None = None
    target: str = Field(min_length=1)
    t_injection: AwareDatetime
    t_impact: AwareDatetime | None = None
    t_detection: AwareDatetime | None = None
    t_verified_recovery: AwareDatetime | None = None
    variant: str | None = None
    config_hash: str = Field(min_length=1)
    component_versions: dict[str, Any] = Field(min_length=1)
    valid: bool
    invalid_reason: str | None = None

    @model_validator(mode="after")
    def _validate_exclusion(self) -> Self:
        if self.valid and self.invalid_reason is not None:
            raise ValueError("invalid_reason must be null when valid=true")
        if not self.valid and not self.invalid_reason:
            raise ValueError("invalid_reason is required when valid=false")
        return self


__all__ = ["RunMeta"]
