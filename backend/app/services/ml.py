from __future__ import annotations

import json
import pickle
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import ADMETResult, AssayResult, ModelRun, Project
from app.services.chemistry import feature_vector
from app.services.ingestion import ADMET_PROPERTIES, POTENCY_PROPERTIES

try:
    import joblib
    import numpy as np
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
    from sklearn.model_selection import train_test_split
except ImportError:  # pragma: no cover
    joblib = None
    np = None
    RandomForestRegressor = None
    mean_absolute_error = None
    mean_squared_error = None
    r2_score = None
    train_test_split = None


PROPERTIES = tuple(sorted(POTENCY_PROPERTIES | ADMET_PROPERTIES))


@dataclass
class MeanRegressor:
    value: float

    def predict(self, rows):
        return [self.value for _ in rows]


def measured_rows(db: Session, project: Project, property_name: str) -> list[tuple[str, float]]:
    model = AssayResult if property_name in POTENCY_PROPERTIES else ADMETResult
    rows = db.scalars(
        select(model).where(model.project == project, model.property_name == property_name)
    ).all()
    return [(row.compound.smiles, float(row.value)) for row in rows]


def model_metrics(y_true: list[float], y_pred: list[float]) -> dict:
    if not y_true:
        return {}
    if np is None or len(y_true) < 2:
        errors = [abs(a - b) for a, b in zip(y_true, y_pred)]
        return {"mae": sum(errors) / len(errors), "rmse": (sum(error * error for error in errors) / len(errors)) ** 0.5}
    return {
        "r2": float(r2_score(y_true, y_pred)) if len(set(y_true)) > 1 else 0.0,
        "rmse": float(mean_squared_error(y_true, y_pred) ** 0.5),
        "mae": float(mean_absolute_error(y_true, y_pred)),
    }


def dump_model(model, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if joblib is not None:
        joblib.dump(model, path)
    else:
        with path.open("wb") as handle:
            pickle.dump(model, handle)


def load_model(path: str | Path):
    if joblib is not None:
        return joblib.load(path)
    with Path(path).open("rb") as handle:
        return pickle.load(handle)


def train_property_model(db: Session, project: Project, property_name: str) -> ModelRun | None:
    rows = measured_rows(db, project, property_name)
    if len(rows) < 3:
        return None

    x = [feature_vector(smiles) for smiles, _ in rows]
    y = [value for _, value in rows]

    if RandomForestRegressor is None or len(rows) < 5:
        model = MeanRegressor(sum(y) / len(y))
        predictions = model.predict(x)
        metrics = model_metrics(y, predictions)
        model_type = "MeanRegressor"
        split_details = "all data fallback"
    else:
        test_size = 0.25 if len(rows) >= 8 else 0.33
        x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=test_size, random_state=42)
        model = RandomForestRegressor(n_estimators=120, random_state=42)
        model.fit(x_train, y_train)
        predictions = model.predict(x_test).tolist()
        metrics = model_metrics(y_test, predictions)
        model_type = "RandomForestRegressor"
        split_details = f"train={len(y_train)}, test={len(y_test)}, random_state=42"

    version = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    settings = get_settings()
    artifact_path = settings.model_dir / project.project_id / f"{property_name}-{version}.pkl"
    report_path = settings.report_dir / project.project_id / f"{property_name}-{version}.json"
    dump_model(model, artifact_path)

    for previous in db.scalars(
        select(ModelRun).where(ModelRun.project == project, ModelRun.property_name == property_name)
    ):
        previous.is_active = False

    metrics = {
        **metrics,
        "n": len(rows),
        "split_details": split_details,
        "training_data_size": len(rows),
    }
    model_run = ModelRun(
        project=project,
        property_name=property_name,
        model_type=model_type,
        version=version,
        feature_type="RDKit descriptors + Morgan fingerprint",
        metrics=metrics,
        artifact_path=str(artifact_path),
        report_path=str(report_path),
        is_active=True,
    )
    db.add(model_run)
    db.commit()
    report = {
        "project_id": project.project_id,
        "property_name": property_name,
        "model_type": model_type,
        "version": version,
        "feature_type": model_run.feature_type,
        "metrics": metrics,
        "applicability_domain": "placeholder: descriptor range and fingerprint similarity checks planned",
        "caveats": ["Synthetic decoy data only", "Tiny training set", "Use for workflow testing, not decisions"],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2))
    return model_run


def train_project_models(db: Session, project_id: str) -> list[ModelRun]:
    project = db.scalar(select(Project).where(Project.project_id == project_id))
    if project is None:
        raise ValueError(f"Unknown project_id: {project_id}")
    runs = []
    for property_name in PROPERTIES:
        run = train_property_model(db, project, property_name)
        if run is not None:
            runs.append(run)
    return runs

