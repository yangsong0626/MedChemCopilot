from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Design, DesignRank, Project

RANKING_VERSION = "default-v1"


def window_score(value: float, low: float, high: float, weight: float) -> tuple[float, str | None]:
    if low <= value <= high:
        return weight, None
    distance = min(abs(value - low), abs(value - high))
    penalty = max(0.0, weight - distance / max(high - low, 1e-6) * weight)
    warning = f"outside preferred range {low:g}-{high:g}"
    return penalty, warning


def threshold_score(value: float, threshold: float, weight: float, higher_is_better: bool) -> tuple[float, str | None]:
    passes = value >= threshold if higher_is_better else value <= threshold
    if passes:
        return weight, None
    ratio = value / threshold if higher_is_better else threshold / max(value, 1e-6)
    return max(0.0, weight * ratio), f"{'below' if higher_is_better else 'above'} preferred threshold {threshold:g}"


def rank_design_score(predictions: dict[str, float]) -> tuple[float, dict[str, float], list[str]]:
    contributions: dict[str, float] = {}
    warnings: list[str] = []

    if "pIC50" in predictions:
        contributions["pIC50"] = max(0.0, min(35.0, (predictions["pIC50"] - 5.0) / 3.0 * 35.0))

    if "logD" in predictions:
        score, warning = window_score(predictions["logD"], 1.5, 3.5, 15.0)
        contributions["logD"] = score
        if warning:
            warnings.append(f"logD {warning}")

    thresholds = {
        "solubility_uM": (30.0, 15.0, True),
        "microsomal_CLint": (30.0, 15.0, False),
        "hERG_IC50_uM": (10.0, 10.0, True),
        "Caco2_Papp": (10.0, 10.0, True),
    }
    for property_name, (threshold, weight, higher_is_better) in thresholds.items():
        if property_name not in predictions:
            continue
        score, warning = threshold_score(predictions[property_name], threshold, weight, higher_is_better)
        contributions[property_name] = score
        if warning:
            warnings.append(f"{property_name} {warning}")

    total = sum(contributions.values())
    return total, contributions, warnings


def rank_project_designs(db: Session, project_id: str) -> list[DesignRank]:
    project = db.scalar(select(Project).where(Project.project_id == project_id))
    if project is None:
        raise ValueError(f"Unknown project_id: {project_id}")

    ranks = []
    for design in db.scalars(select(Design).where(Design.project == project)).all():
        latest_by_property = {}
        for prediction in design.predictions:
            if not prediction.model_run.is_active:
                continue
            latest_by_property[prediction.property_name] = prediction.predicted_value
        total, contributions, warnings = rank_design_score(latest_by_property)
        rank = db.scalar(
            select(DesignRank).where(
                DesignRank.design == design,
                DesignRank.ranking_version == RANKING_VERSION,
            )
        )
        if rank is None:
            rank = DesignRank(
                design=design,
                ranking_version=RANKING_VERSION,
                total_score=total,
                contributions=contributions,
                warnings=warnings,
            )
            db.add(rank)
        else:
            rank.total_score = total
            rank.contributions = contributions
            rank.warnings = warnings
        ranks.append(rank)

    db.flush()
    ranks.sort(key=lambda item: item.total_score, reverse=True)
    for index, item in enumerate(ranks, start=1):
        item.rank = index
    db.commit()
    return ranks
