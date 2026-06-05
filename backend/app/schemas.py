from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: str
    project_name: str
    target: str
    therapeutic_area: str
    primary_goal: str


class ProjectSummary(ProjectRead):
    measured_compounds: int
    design_count: int
    feedback_count: int
    active_models: int


class CompoundMeasurement(BaseModel):
    compound_id: str
    smiles: str
    canonical_smiles: str
    series: str | None
    properties: dict[str, float]


class PredictionRead(BaseModel):
    property_name: str
    predicted_value: float
    confidence: float | None = None
    applicability_domain: str | None = None
    model_version: str


class RankRead(BaseModel):
    total_score: float
    rank: int | None
    contributions: dict[str, float]
    warnings: list[str]


class FeedbackRead(BaseModel):
    user_id: str
    feedback: str
    note: str | None = None
    created_date: date | None = None


class DesignRead(BaseModel):
    design_id: str
    project_id: str
    source: str
    smiles: str
    canonical_smiles: str
    series: str | None
    submitted_by: str | None
    status: str
    notes: str | None = None
    created_date: date | None = None
    predictions: list[PredictionRead] = Field(default_factory=list)
    rank: RankRead | None = None
    feedback: list[FeedbackRead] = Field(default_factory=list)


class DesignCreate(BaseModel):
    smiles: str
    series: str | None = None
    submitted_by: str = "chemist"
    notes: str | None = None
    source: str = "human"


class DesignUpdate(BaseModel):
    smiles: str | None = None
    series: str | None = None
    notes: str | None = None
    status: str | None = None


class FeedbackCreate(BaseModel):
    user_id: str
    feedback: str
    note: str | None = None


class SmilesPredictionRequest(BaseModel):
    smiles: str


class ScoreResponse(BaseModel):
    project_id: str
    model_runs: int
    predictions: int
    ranked_designs: int


class ModelReport(BaseModel):
    project_id: str
    project_name: str
    target: str
    primary_goal: str
    feedback_count: int
    models: list[dict[str, Any]]
