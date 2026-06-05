from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.services.ingestion import load_seed_data
from app.services.ml import train_project_models
from app.services.prediction import score_project_designs
from app.services.ranking import rank_project_designs


def run_project_iteration(db: Session, project_id: str, seed_dir: Path | None = None) -> dict:
    imports = load_seed_data(db, seed_dir)
    model_runs = train_project_models(db, project_id)
    predictions = score_project_designs(db, project_id)
    ranks = rank_project_designs(db, project_id)
    return {
        "imports": imports,
        "model_runs": len(model_runs),
        "predictions": len(predictions),
        "ranked_designs": len(ranks),
    }

