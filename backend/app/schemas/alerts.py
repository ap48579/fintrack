from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, model_validator

RuleType = Literal[
    "fundamental_threshold", "whale_movement", "price_move", "candidate_flagged", "watchlist_candidate_match"
]


class AlertRuleCreate(BaseModel):
    rule_type: RuleType
    ticker: str | None = None
    subject: str | None = None
    condition: Literal["gt", "lt"] | None = None
    threshold: float | None = None

    @model_validator(mode="after")
    def _check_required_fields(self) -> "AlertRuleCreate":
        ticker_scoped = {"fundamental_threshold", "whale_movement", "price_move"}
        if self.rule_type in ticker_scoped and not self.ticker:
            raise ValueError(f"rule_type={self.rule_type} requires a ticker")
        if self.rule_type in {"fundamental_threshold", "price_move"} and self.threshold is None:
            raise ValueError(f"rule_type={self.rule_type} requires a threshold")
        if self.rule_type == "candidate_flagged" and not self.ticker and not self.subject:
            raise ValueError("candidate_flagged requires a ticker or a subject")
        return self


class AlertRuleResponse(BaseModel):
    id: UUID
    rule_type: str
    ticker: str | None
    subject: str | None
    condition: str | None
    threshold: float | None
    active: bool
    created_at: datetime


class AlertLogItem(BaseModel):
    id: UUID
    rule_type: str
    ticker: str | None
    subject: str | None
    triggered_at: datetime
    message: str
    delivered: bool
