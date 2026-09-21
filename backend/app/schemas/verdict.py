from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class VerdictItem(BaseModel):
    ticker: str
    bull_case: str
    bear_case: str
    verdict: Literal["bullish", "bearish", "neutral"]
    confidence: float
    key_risks: str
    key_catalysts: str
    generated_at: datetime

    model_config = {"from_attributes": True}
