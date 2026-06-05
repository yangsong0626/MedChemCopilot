from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DesignFeedback, ModelRun, Project


def model_performance_report(db: Session, project_id: str) -> dict:
    project = db.scalar(select(Project).where(Project.project_id == project_id))
    if project is None:
        raise ValueError(f"Unknown project_id: {project_id}")
    runs = db.scalars(
        select(ModelRun).where(ModelRun.project == project).order_by(ModelRun.property_name, ModelRun.trained_at.desc())
    ).all()
    feedback_count = db.scalars(select(DesignFeedback).join(DesignFeedback.design).where(DesignFeedback.design.has(project=project))).all()
    return {
        "project_id": project.project_id,
        "project_name": project.project_name,
        "target": project.target,
        "primary_goal": project.primary_goal,
        "feedback_count": len(feedback_count),
        "models": [
            {
                "property_name": run.property_name,
                "model_type": run.model_type,
                "version": run.version,
                "feature_type": run.feature_type,
                "trained_at": run.trained_at.isoformat(),
                "is_active": run.is_active,
                "metrics": run.metrics,
                "artifact_path": run.artifact_path,
                "report_path": run.report_path,
                "applicability_domain": "placeholder: add descriptor and similarity coverage checks",
                "caveats": ["Synthetic decoy data", "Small N baseline model"],
            }
            for run in runs
        ],
    }

