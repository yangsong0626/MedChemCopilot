from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import ADMETResult, AssayResult, Compound, Design, DesignFeedback, Project
from app.services.chemistry import canonicalize_smiles

POTENCY_PROPERTIES = {"pIC50"}
ADMET_PROPERTIES = {"logD", "solubility_uM", "microsomal_CLint", "hERG_IC50_uM", "Caco2_Papp"}


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def read_csv(path: Path, required_columns: Iterable[str]) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        missing = set(required_columns) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path} is missing required columns: {sorted(missing)}")
        return list(reader)


def get_or_create_project(db: Session, row: dict[str, str]) -> Project:
    project = db.scalar(select(Project).where(Project.project_id == row["project_id"]))
    if project is None:
        project = Project(
            project_id=row["project_id"].strip(),
            project_name=row["project_name"].strip(),
            target=row["target"].strip(),
            therapeutic_area=row["therapeutic_area"].strip(),
            primary_goal=row["primary_goal"].strip(),
        )
        db.add(project)
    else:
        project.project_name = row["project_name"].strip()
        project.target = row["target"].strip()
        project.therapeutic_area = row["therapeutic_area"].strip()
        project.primary_goal = row["primary_goal"].strip()
    return project


def get_or_create_compound(db: Session, row: dict[str, str]) -> Compound:
    compound = db.scalar(select(Compound).where(Compound.compound_id == row["compound_id"]))
    canonical = canonicalize_smiles(row["smiles"])
    if compound is None:
        compound = Compound(
            compound_id=row["compound_id"].strip(),
            smiles=row["smiles"].strip(),
            canonical_smiles=canonical,
            series=row.get("series") or None,
        )
        db.add(compound)
    else:
        compound.smiles = row["smiles"].strip()
        compound.canonical_smiles = canonical
        compound.series = row.get("series") or compound.series
    return compound


def upsert_result(
    db: Session,
    model: type[AssayResult] | type[ADMETResult],
    project: Project,
    compound: Compound,
    property_name: str,
    value: str,
    unit: str | None,
    assay_date: date | None,
) -> None:
    result = db.scalar(
        select(model).where(
            model.project == project,
            model.compound == compound,
            model.property_name == property_name,
        )
    )
    if result is None:
        result = model(
            project=project,
            compound=compound,
            property_name=property_name,
            value=float(value),
            unit=unit,
            assay_date=assay_date,
        )
        db.add(result)
    else:
        result.value = float(value)
        result.unit = unit
        result.assay_date = assay_date


def load_projects(db: Session, seed_dir: Path) -> int:
    rows = read_csv(seed_dir / "projects.csv", ["project_id", "project_name", "target", "therapeutic_area", "primary_goal"])
    for row in rows:
        get_or_create_project(db, row)
    db.commit()
    return len(rows)


def load_measured_compounds(db: Session, seed_dir: Path) -> int:
    required = ["project_id", "compound_id", "smiles", "series", "pIC50", *ADMET_PROPERTIES, "assay_date"]
    rows = read_csv(seed_dir / "measured_compounds.csv", required)
    for row in rows:
        project = db.scalar(select(Project).where(Project.project_id == row["project_id"]))
        if project is None:
            raise ValueError(f"Unknown project_id: {row['project_id']}")
        compound = get_or_create_compound(db, row)
        db.flush()
        assay_date = parse_date(row.get("assay_date"))
        upsert_result(db, AssayResult, project, compound, "pIC50", row["pIC50"], "unitless", assay_date)
        for property_name in ADMET_PROPERTIES:
            upsert_result(db, ADMETResult, project, compound, property_name, row[property_name], property_name, assay_date)
    db.commit()
    return len(rows)


def load_design_candidates(db: Session, seed_dir: Path) -> int:
    rows = read_csv(seed_dir / "design_candidates.csv", ["project_id", "design_id", "source", "smiles", "series", "submitted_by", "status", "created_date"])
    for row in rows:
        project = db.scalar(select(Project).where(Project.project_id == row["project_id"]))
        if project is None:
            raise ValueError(f"Unknown project_id: {row['project_id']}")
        canonical = canonicalize_smiles(row["smiles"])
        design = db.scalar(select(Design).where(Design.design_id == row["design_id"]))
        if design is None:
            design = Design(
                design_id=row["design_id"].strip(),
                project=project,
                source=row["source"].strip(),
                smiles=row["smiles"].strip(),
                canonical_smiles=canonical,
                series=row.get("series") or None,
                submitted_by=row.get("submitted_by") or None,
                status=row.get("status") or "pending",
                created_date=parse_date(row.get("created_date")),
            )
            db.add(design)
        else:
            design.project = project
            design.source = row["source"].strip()
            design.smiles = row["smiles"].strip()
            design.canonical_smiles = canonical
            design.series = row.get("series") or design.series
            design.submitted_by = row.get("submitted_by") or design.submitted_by
            design.status = row.get("status") or design.status
            design.created_date = parse_date(row.get("created_date"))
    db.commit()
    return len(rows)


def load_chemist_feedback(db: Session, seed_dir: Path) -> int:
    rows = read_csv(seed_dir / "chemist_feedback.csv", ["project_id", "design_id", "user_id", "feedback", "note", "created_date"])
    existing = {
        (item.design_id, item.user_id, item.feedback, item.note)
        for item in db.scalars(select(DesignFeedback)).all()
    }
    for row in rows:
        design = db.scalar(select(Design).where(Design.design_id == row["design_id"]))
        if design is None:
            raise ValueError(f"Unknown design_id: {row['design_id']}")
        key = (design.id, row["user_id"], row["feedback"], row["note"])
        if key in existing:
            continue
        db.add(
            DesignFeedback(
                design=design,
                user_id=row["user_id"].strip(),
                feedback=row["feedback"].strip(),
                note=row.get("note") or None,
                created_date=parse_date(row.get("created_date")),
            )
        )
    db.commit()
    return len(rows)


def load_seed_data(db: Session, seed_dir: Path | None = None) -> dict[str, int]:
    seed_dir = seed_dir or get_settings().seed_data_dir
    return {
        "projects": load_projects(db, seed_dir),
        "measured_compounds": load_measured_compounds(db, seed_dir),
        "design_candidates": load_design_candidates(db, seed_dir),
        "chemist_feedback": load_chemist_feedback(db, seed_dir),
    }
