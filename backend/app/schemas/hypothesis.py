from datetime import date, datetime

from pydantic import BaseModel


class HypothesisRunSummary(BaseModel):
    run_at: datetime
    data_window_start: date
    data_window_end: date
    sample_size: int
    results: dict


class HypothesisItem(BaseModel):
    name: str
    description: str
    source: str
    params: dict
    latest_run: HypothesisRunSummary | None
