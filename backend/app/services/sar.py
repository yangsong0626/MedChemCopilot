from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AssayResult, Project
from app.services.chemistry import morgan_fingerprint


@dataclass(frozen=True)
class SARMolecule:
    compound_id: str
    smiles: str
    canonical_smiles: str
    series: str | None
    pIC50: float
    fingerprint: list[int]


@dataclass(frozen=True)
class SARPair:
    rank: int
    compound_a_id: str
    compound_b_id: str
    smiles_a: str
    smiles_b: str
    series_a: str | None
    series_b: str | None
    pIC50_a: float
    pIC50_b: float
    delta_potency: float
    similarity: float
    cliff_score: float


def tanimoto_similarity(fingerprint_a: list[int], fingerprint_b: list[int]) -> float:
    intersection = 0
    union = 0
    for bit_a, bit_b in zip(fingerprint_a, fingerprint_b):
        if bit_a or bit_b:
            union += 1
        if bit_a and bit_b:
            intersection += 1
    return intersection / union if union else 0.0


def _measured_potency_molecules(db: Session, project: Project) -> list[SARMolecule]:
    rows = db.scalars(
        select(AssayResult).where(
            AssayResult.project == project,
            AssayResult.property_name == "pIC50",
        )
    ).all()
    molecules: list[SARMolecule] = []
    seen: set[str] = set()
    for row in rows:
        canonical = row.compound.canonical_smiles
        if canonical in seen:
            continue
        seen.add(canonical)
        molecules.append(
            SARMolecule(
                compound_id=row.compound.compound_id,
                smiles=row.compound.smiles,
                canonical_smiles=canonical,
                series=row.compound.series,
                pIC50=float(row.value),
                fingerprint=morgan_fingerprint(canonical, n_bits=256),
            )
        )
    return molecules


def potency_cliff_pairs(
    db: Session,
    project: Project,
    limit: int = 100,
    min_similarity: float = 0.0,
) -> list[SARPair]:
    molecules = _measured_potency_molecules(db, project)
    pairs: list[SARPair] = []
    for index, molecule_a in enumerate(molecules):
        for molecule_b in molecules[index + 1 :]:
            similarity = tanimoto_similarity(molecule_a.fingerprint, molecule_b.fingerprint)
            if similarity < min_similarity or similarity >= 0.999:
                continue
            high, low = (
                (molecule_a, molecule_b)
                if molecule_a.pIC50 >= molecule_b.pIC50
                else (molecule_b, molecule_a)
            )
            delta = high.pIC50 - low.pIC50
            score = delta / (1.0 - similarity)
            pairs.append(
                SARPair(
                    rank=0,
                    compound_a_id=high.compound_id,
                    compound_b_id=low.compound_id,
                    smiles_a=high.canonical_smiles,
                    smiles_b=low.canonical_smiles,
                    series_a=high.series,
                    series_b=low.series,
                    pIC50_a=high.pIC50,
                    pIC50_b=low.pIC50,
                    delta_potency=delta,
                    similarity=similarity,
                    cliff_score=score,
                )
            )
    ranked = sorted(pairs, key=lambda pair: pair.cliff_score, reverse=True)[:limit]
    return [
        SARPair(
            rank=rank,
            compound_a_id=pair.compound_a_id,
            compound_b_id=pair.compound_b_id,
            smiles_a=pair.smiles_a,
            smiles_b=pair.smiles_b,
            series_a=pair.series_a,
            series_b=pair.series_b,
            pIC50_a=pair.pIC50_a,
            pIC50_b=pair.pIC50_b,
            delta_potency=pair.delta_potency,
            similarity=pair.similarity,
            cliff_score=pair.cliff_score,
        )
        for rank, pair in enumerate(ranked, start=1)
    ]
