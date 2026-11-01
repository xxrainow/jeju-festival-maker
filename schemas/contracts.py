"""Shared contracts: coordinate changes between AI and data developers."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator


class UserRequest(BaseModel):
    region: str | None = None
    purpose: str = Field(min_length=1)
    interest: str | None = None
    budget_max_krw: int | None = Field(default=None, gt=0)


class FestivalCase(BaseModel):
    case_id: str
    title: str
    source_url: HttpUrl
    published_at: date | None = None
    event_date: date | None = None
    evidence_text: str
    evidence_status: Literal["full_text", "snippet_only", "unavailable"]


class FestivalIdea(BaseModel):
    idea_id: str
    title: str
    summary: str
    programs: list[str]
    target_audience: str
    case_ids: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    status: Literal["unreviewed"] = "unreviewed"


class AnalysisRequest(BaseModel):
    idea_id: str
    regions: list[str] = Field(min_length=1)
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def validate_period(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class AnalysisResult(BaseModel):
    result_id: str
    request: AnalysisRequest
    is_synthetic: bool
    metrics: dict[str, float | None] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
