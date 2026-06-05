from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    project_name: Mapped[str] = mapped_column(String(255))
    target: Mapped[str] = mapped_column(String(255))
    therapeutic_area: Mapped[str] = mapped_column(String(255))
    primary_goal: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    assay_results: Mapped[list[AssayResult]] = relationship(back_populates="project")
    admet_results: Mapped[list[ADMETResult]] = relationship(back_populates="project")
    designs: Mapped[list[Design]] = relationship(back_populates="project")
    model_runs: Mapped[list[ModelRun]] = relationship(back_populates="project")


class Compound(Base):
    __tablename__ = "compounds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    compound_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    smiles: Mapped[str] = mapped_column(Text)
    canonical_smiles: Mapped[str] = mapped_column(Text, index=True)
    series: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    assay_results: Mapped[list[AssayResult]] = relationship(back_populates="compound")
    admet_results: Mapped[list[ADMETResult]] = relationship(back_populates="compound")


class AssayResult(Base):
    __tablename__ = "assay_results"
    __table_args__ = (UniqueConstraint("project_id", "compound_id", "property_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    compound_id: Mapped[int] = mapped_column(ForeignKey("compounds.id"))
    property_name: Mapped[str] = mapped_column(String(64))
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    assay_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    project: Mapped[Project] = relationship(back_populates="assay_results")
    compound: Mapped[Compound] = relationship(back_populates="assay_results")


class ADMETResult(Base):
    __tablename__ = "admet_results"
    __table_args__ = (UniqueConstraint("project_id", "compound_id", "property_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    compound_id: Mapped[int] = mapped_column(ForeignKey("compounds.id"))
    property_name: Mapped[str] = mapped_column(String(64))
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    assay_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    project: Mapped[Project] = relationship(back_populates="admet_results")
    compound: Mapped[Compound] = relationship(back_populates="admet_results")


class DesignBatch(Base):
    __tablename__ = "design_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(64), default="mixed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Design(Base):
    __tablename__ = "designs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    design_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("design_batches.id"), nullable=True)
    source: Mapped[str] = mapped_column(String(64))
    smiles: Mapped[str] = mapped_column(Text)
    canonical_smiles: Mapped[str] = mapped_column(Text, index=True)
    series: Mapped[str | None] = mapped_column(String(64), nullable=True)
    submitted_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(64), default="pending")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    project: Mapped[Project] = relationship(back_populates="designs")
    predictions: Mapped[list[Prediction]] = relationship(back_populates="design")
    feedback: Mapped[list[DesignFeedback]] = relationship(back_populates="design")
    ranks: Mapped[list[DesignRank]] = relationship(back_populates="design")


class ModelRun(Base):
    __tablename__ = "model_runs"
    __table_args__ = (UniqueConstraint("project_id", "property_name", "version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    property_name: Mapped[str] = mapped_column(String(64))
    model_type: Mapped[str] = mapped_column(String(128))
    version: Mapped[str] = mapped_column(String(64))
    feature_type: Mapped[str] = mapped_column(String(128))
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    artifact_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    project: Mapped[Project] = relationship(back_populates="model_runs")
    predictions: Mapped[list[Prediction]] = relationship(back_populates="model_run")


class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (UniqueConstraint("design_id", "model_run_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    design_id: Mapped[int] = mapped_column(ForeignKey("designs.id"))
    model_run_id: Mapped[int] = mapped_column(ForeignKey("model_runs.id"))
    property_name: Mapped[str] = mapped_column(String(64))
    predicted_value: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    applicability_domain: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    design: Mapped[Design] = relationship(back_populates="predictions")
    model_run: Mapped[ModelRun] = relationship(back_populates="predictions")


class DesignRank(Base):
    __tablename__ = "design_ranks"
    __table_args__ = (UniqueConstraint("design_id", "ranking_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    design_id: Mapped[int] = mapped_column(ForeignKey("designs.id"))
    ranking_version: Mapped[str] = mapped_column(String(64))
    total_score: Mapped[float] = mapped_column(Float)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    contributions: Mapped[dict] = mapped_column(JSON, default=dict)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    design: Mapped[Design] = relationship(back_populates="ranks")


class DesignFeedback(Base):
    __tablename__ = "design_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    design_id: Mapped[int] = mapped_column(ForeignKey("designs.id"))
    user_id: Mapped[str] = mapped_column(String(128))
    feedback: Mapped[str] = mapped_column(String(64))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    design: Mapped[Design] = relationship(back_populates="feedback")

