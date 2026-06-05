from __future__ import annotations

from datetime import date

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.init_db import init_db
from app.db.session import get_db
from app.models import (
    ADMETResult,
    AssayResult,
    Compound,
    Design,
    DesignFeedback,
    DesignRank,
    ModelRun,
    Project,
)
from app.schemas import (
    CompoundMeasurement,
    DesignCreate,
    DesignRead,
    DesignUpdate,
    FeedbackCreate,
    FeedbackRead,
    ModelReport,
    PredictionRead,
    ProjectRead,
    ProjectSummary,
    RankRead,
    ScoreResponse,
    SmilesPredictionRequest,
)
from app.services.chemistry import canonicalize_smiles, mol_svg
from app.services.ingestion import load_seed_data
from app.services.ml import train_project_models
from app.services.prediction import predict_smiles, score_project_designs
from app.services.pregenerated import random_project_design
from app.services.ranking import rank_project_designs
from app.services.reports import model_performance_report

app = FastAPI(title="MedChemCopilot API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()


def project_or_404(db: Session, project_id: str) -> Project:
    project = db.scalar(select(Project).where(Project.project_id == project_id))
    if project is None:
        raise HTTPException(status_code=404, detail=f"Unknown project_id: {project_id}")
    return project


def design_or_404(db: Session, design_id: str) -> Design:
    design = db.scalar(select(Design).where(Design.design_id == design_id))
    if design is None:
        raise HTTPException(status_code=404, detail=f"Unknown design_id: {design_id}")
    return design


def serialize_design(design: Design) -> DesignRead:
    latest_rank = sorted(design.ranks, key=lambda rank: rank.created_at, reverse=True)[0] if design.ranks else None
    active_predictions = [
        prediction for prediction in design.predictions if prediction.model_run.is_active
    ]
    return DesignRead(
        design_id=design.design_id,
        project_id=design.project.project_id,
        source=design.source,
        smiles=design.smiles,
        canonical_smiles=design.canonical_smiles,
        series=design.series,
        submitted_by=design.submitted_by,
        status=design.status,
        notes=design.notes,
        created_date=design.created_date,
        predictions=[
            PredictionRead(
                property_name=prediction.property_name,
                predicted_value=prediction.predicted_value,
                confidence=prediction.confidence,
                applicability_domain=prediction.applicability_domain,
                model_version=prediction.model_run.version,
            )
            for prediction in sorted(active_predictions, key=lambda item: item.property_name)
        ],
        rank=RankRead(
            total_score=latest_rank.total_score,
            rank=latest_rank.rank,
            contributions=latest_rank.contributions,
            warnings=latest_rank.warnings,
        )
        if latest_rank
        else None,
        feedback=[
            FeedbackRead(
                user_id=item.user_id,
                feedback=item.feedback,
                note=item.note,
                created_date=item.created_date,
            )
            for item in design.feedback
        ],
    )


@app.post("/admin/load-seed")
def load_seed(db: Session = Depends(get_db)) -> dict[str, int]:
    return load_seed_data(db)


@app.get("/structures/svg")
def structure_svg(
    smiles: str = Query(..., min_length=1),
    width: int = Query(default=260, ge=80, le=700),
    height: int = Query(default=180, ge=60, le=500),
) -> Response:
    try:
        svg = mol_svg(smiles, width=width, height=height)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/projects", response_model=list[ProjectRead])
def list_projects(db: Session = Depends(get_db)) -> list[Project]:
    return db.scalars(select(Project).order_by(Project.project_id)).all()


@app.get("/projects/{project_id}", response_model=ProjectSummary)
def project_summary(project_id: str, db: Session = Depends(get_db)) -> ProjectSummary:
    project = project_or_404(db, project_id)
    measured_compounds = db.scalar(
        select(func.count(func.distinct(AssayResult.compound_id))).where(AssayResult.project == project)
    )
    design_count = db.scalar(select(func.count(Design.id)).where(Design.project == project))
    feedback_count = db.scalar(
        select(func.count(DesignFeedback.id)).join(Design).where(Design.project == project)
    )
    active_models = db.scalar(
        select(func.count(ModelRun.id)).where(ModelRun.project == project, ModelRun.is_active.is_(True))
    )
    return ProjectSummary(
        project_id=project.project_id,
        project_name=project.project_name,
        target=project.target,
        therapeutic_area=project.therapeutic_area,
        primary_goal=project.primary_goal,
        measured_compounds=measured_compounds or 0,
        design_count=design_count or 0,
        feedback_count=feedback_count or 0,
        active_models=active_models or 0,
    )


@app.get("/projects/{project_id}/measured-compounds", response_model=list[CompoundMeasurement])
def list_measured_compounds(project_id: str, db: Session = Depends(get_db)) -> list[CompoundMeasurement]:
    project = project_or_404(db, project_id)
    compounds = {}
    for result in db.scalars(select(AssayResult).where(AssayResult.project == project)).all():
        compounds.setdefault(result.compound_id, {"compound": result.compound, "properties": {}})
        compounds[result.compound_id]["properties"][result.property_name] = result.value
    for result in db.scalars(select(ADMETResult).where(ADMETResult.project == project)).all():
        compounds.setdefault(result.compound_id, {"compound": result.compound, "properties": {}})
        compounds[result.compound_id]["properties"][result.property_name] = result.value
    return [
        CompoundMeasurement(
            compound_id=item["compound"].compound_id,
            smiles=item["compound"].smiles,
            canonical_smiles=item["compound"].canonical_smiles,
            series=item["compound"].series,
            properties=item["properties"],
        )
        for item in compounds.values()
    ]


@app.get("/projects/{project_id}/designs", response_model=list[DesignRead])
def list_designs(
    project_id: str,
    source: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[DesignRead]:
    project = project_or_404(db, project_id)
    stmt = select(Design).where(Design.project == project)
    if source:
        stmt = stmt.where(Design.source == source)
    designs = db.scalars(stmt).all()
    return sorted(
        [serialize_design(design) for design in designs],
        key=lambda item: item.rank.rank if item.rank and item.rank.rank else 9999,
    )


def project_prediction_payload(db: Session, project_id: str, smiles: str) -> list[dict]:
    predictions = predict_smiles(db, project_id, smiles)
    if not predictions:
        train_project_models(db, project_id)
        predictions = predict_smiles(db, project_id, smiles)
    return predictions


@app.get("/projects/{project_id}/pregenerated/random")
def get_random_pregenerated_design(project_id: str, db: Session = Depends(get_db)) -> dict:
    project_or_404(db, project_id)
    try:
        design = random_project_design(project_id)
        predictions = project_prediction_payload(db, project_id, design["canonical_smiles"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {**design, "predictions": predictions}


@app.post("/projects/{project_id}/predict-smiles")
def predict_project_smiles(
    project_id: str,
    payload: SmilesPredictionRequest,
    db: Session = Depends(get_db),
) -> dict:
    project_or_404(db, project_id)
    try:
        canonical = canonicalize_smiles(payload.smiles)
        predictions = project_prediction_payload(db, project_id, canonical)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "project_id": project_id,
        "smiles": payload.smiles,
        "canonical_smiles": canonical,
        "predictions": predictions,
    }


@app.post("/projects/{project_id}/designs", response_model=DesignRead)
def submit_design(project_id: str, payload: DesignCreate, db: Session = Depends(get_db)) -> DesignRead:
    project = project_or_404(db, project_id)
    canonical = canonicalize_smiles(payload.smiles)
    count = db.scalar(select(func.count(Design.id)).where(Design.project == project)) or 0
    design = Design(
        design_id=f"{project.project_id}-H{count + 1:03d}",
        project=project,
        source=payload.source,
        smiles=payload.smiles,
        canonical_smiles=canonical,
        series=payload.series,
        submitted_by=payload.submitted_by,
        notes=payload.notes,
        status="pending",
        created_date=date.today(),
    )
    db.add(design)
    db.commit()
    db.refresh(design)
    return serialize_design(design)


@app.patch("/designs/{design_id}", response_model=DesignRead)
def update_design(design_id: str, payload: DesignUpdate, db: Session = Depends(get_db)) -> DesignRead:
    design = design_or_404(db, design_id)
    if payload.smiles is not None:
        design.smiles = payload.smiles
        design.canonical_smiles = canonicalize_smiles(payload.smiles)
    if payload.series is not None:
        design.series = payload.series
    if payload.notes is not None:
        design.notes = payload.notes
    if payload.status is not None:
        design.status = payload.status
    db.commit()
    db.refresh(design)
    return serialize_design(design)


@app.post("/designs/{design_id}/feedback", response_model=FeedbackRead)
def add_feedback(design_id: str, payload: FeedbackCreate, db: Session = Depends(get_db)) -> FeedbackRead:
    design = design_or_404(db, design_id)
    feedback = DesignFeedback(
        design=design,
        user_id=payload.user_id,
        feedback=payload.feedback,
        note=payload.note,
        created_date=date.today(),
    )
    db.add(feedback)
    if payload.feedback in {"like", "dislike", "shortlist"}:
        design.status = payload.feedback
    db.commit()
    return FeedbackRead(
        user_id=feedback.user_id,
        feedback=feedback.feedback,
        note=feedback.note,
        created_date=feedback.created_date,
    )


@app.post("/projects/{project_id}/score", response_model=ScoreResponse)
def score_project(project_id: str, db: Session = Depends(get_db)) -> ScoreResponse:
    project_or_404(db, project_id)
    model_runs = train_project_models(db, project_id)
    predictions = score_project_designs(db, project_id)
    ranks = rank_project_designs(db, project_id)
    return ScoreResponse(
        project_id=project_id,
        model_runs=len(model_runs),
        predictions=len(predictions),
        ranked_designs=len(ranks),
    )


@app.get("/projects/{project_id}/model-report", response_model=ModelReport)
def get_model_report(project_id: str, db: Session = Depends(get_db)) -> dict:
    project_or_404(db, project_id)
    return model_performance_report(db, project_id)
