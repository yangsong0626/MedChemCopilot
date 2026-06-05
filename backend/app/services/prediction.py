from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Design, ModelRun, Prediction, Project
from app.services.chemistry import feature_vector
from app.services.ml import PROPERTIES, load_model


def latest_active_model(db: Session, project: Project, property_name: str) -> ModelRun | None:
    return db.scalar(
        select(ModelRun)
        .where(
            ModelRun.project == project,
            ModelRun.property_name == property_name,
            ModelRun.is_active.is_(True),
        )
        .order_by(ModelRun.trained_at.desc())
    )


def predict_design(db: Session, design: Design) -> list[Prediction]:
    outputs = []
    features = [feature_vector(design.smiles)]
    for property_name in PROPERTIES:
        model_run = latest_active_model(db, design.project, property_name)
        if model_run is None or not model_run.artifact_path:
            continue
        model = load_model(model_run.artifact_path)
        value = float(model.predict(features)[0])
        prediction = db.scalar(
            select(Prediction).where(Prediction.design == design, Prediction.model_run == model_run)
        )
        if prediction is None:
            prediction = Prediction(
                design=design,
                model_run=model_run,
                property_name=property_name,
                predicted_value=value,
                confidence=0.65,
                applicability_domain="unknown",
            )
            db.add(prediction)
        else:
            prediction.predicted_value = value
            prediction.confidence = 0.65
            prediction.applicability_domain = "unknown"
        outputs.append(prediction)
    db.commit()
    return outputs


def predict_smiles(db: Session, project_id: str, smiles: str) -> list[dict]:
    project = db.scalar(select(Project).where(Project.project_id == project_id))
    if project is None:
        raise ValueError(f"Unknown project_id: {project_id}")
    features = [feature_vector(smiles)]
    outputs = []
    for property_name in PROPERTIES:
        model_run = latest_active_model(db, project, property_name)
        if model_run is None or not model_run.artifact_path:
            continue
        model = load_model(model_run.artifact_path)
        outputs.append(
            {
                "property_name": property_name,
                "predicted_value": float(model.predict(features)[0]),
                "confidence": 0.65,
                "applicability_domain": "unknown",
                "model_version": model_run.version,
            }
        )
    return sorted(outputs, key=lambda item: item["property_name"])


def score_project_designs(db: Session, project_id: str) -> list[Prediction]:
    project = db.scalar(select(Project).where(Project.project_id == project_id))
    if project is None:
        raise ValueError(f"Unknown project_id: {project_id}")
    outputs = []
    for design in db.scalars(select(Design).where(Design.project == project)).all():
        outputs.extend(predict_design(db, design))
    return outputs
