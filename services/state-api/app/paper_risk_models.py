"""Request bodies for the paper risk routes.

Every change names its operator and gives a reason. The kill switch and resuming
after it also require an explicit confirmation in the body, so a replayed or
hand-written request without it is refused before anything is read.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from tradesync_core.paper_limits import LIMIT_KEYS


class Audited(BaseModel):
    operator: str = Field(min_length=1, max_length=80)
    reason: str = Field(min_length=5, max_length=240)

    @model_validator(mode="after")
    def _meaningful(self) -> "Audited":
        self.operator, self.reason = self.operator.strip(), self.reason.strip()
        if not self.operator or len(self.reason) < 5:
            raise ValueError("An operator name and a meaningful reason are required")
        return self


class PauseRequest(Audited):
    entries_paused: bool


class KillRequest(Audited):
    confirm: Literal[True]


class ResumeAfterKillRequest(Audited):
    confirm: Literal[True]


class LimitsRequest(Audited):
    daily_loss_limit_usdc: float | None = Field(None, gt=0, le=1_000_000, allow_inf_nan=False)
    max_drawdown_fraction: float | None = Field(None, gt=0, lt=1, allow_inf_nan=False)
    max_gross_exposure_fraction: float | None = Field(None, gt=0, le=10, allow_inf_nan=False)
    max_symbol_exposure_fraction: float | None = Field(None, gt=0, le=10, allow_inf_nan=False)
    max_bucket_exposure_fraction: float | None = Field(None, gt=0, le=10, allow_inf_nan=False)
    correlation_threshold: float | None = Field(None, gt=0, le=1, allow_inf_nan=False)
    max_concurrent_positions: int | None = Field(None, ge=1, le=50)
    max_entry_quote_age_s: float | None = Field(None, gt=0, le=30, allow_inf_nan=False)
    max_mark_age_s: float | None = Field(None, gt=0, le=600, allow_inf_nan=False)

    def changes(self) -> dict[str, Any]:
        return {key: getattr(self, key) for key in LIMIT_KEYS if getattr(self, key) is not None}
