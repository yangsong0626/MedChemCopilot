from __future__ import annotations

import csv
import random
from pathlib import Path

from app.config import get_settings
from app.services.chemistry import canonicalize_smiles, descriptors, is_valid_smiles

try:
    from rdkit import RDLogger
except ImportError:  # pragma: no cover
    RDLogger = None

SUBS_AROMATIC = [
    "F",
    "Cl",
    "Br",
    "C",
    "CC",
    "CO",
    "CCO",
    "CN",
    "N",
    "O",
    "S",
    "C(F)(F)F",
    "C#N",
    "C(=O)N",
    "C(=O)O",
]
SUBS_SMALL = ["C", "CC", "F", "Cl", "OC", "N", "CN", "C(F)(F)F", "CO", "CCO", "C#N", "O"]
AMINES = ["N1CCOCC1", "N1CCNCC1", "N1CCN(C)CC1", "N1CCCC1", "N1CCCCC1", "N(C)C", "NC"]
LINKERS = ["C(=O)N", "NC(=O)", "CH2_PLACEHOLDER", "SO2N"]


PROJECT_TEMPLATES = {
    "KIN001": [
        "{a}c1cc({b})ccc1Nc1ncc({c})cn1",
        "{a}c1ccc(Nc2ncc({b})cn2)c({c})c1",
        "{a}c1ccc(C(=O)Nc2ccc({b})cc2{c})cc1",
        "{a}c1cc({b})ccc1C(=O)Nc1cccc({c})n1",
        "{a}c1ccc(CCN2CCN({b})CC2)cc1",
    ],
    "GPCR002": [
        "{a}c1ccc(CCN2CCN({b})CC2)c({c})c1",
        "{a}c1cc({b})ccc1CCN1CCCCC1",
        "{a}c1ccc(CCN(C)C)c({b})c1{c}",
        "{a}c1ccc(OCCN2CCOCC2)c({b})c1",
        "{a}c1cc({b})ccc1CNC(=O)c1ccc({c})cc1",
    ],
    "PROT003": [
        "{a}c1ccc(C(=O)Nc2ccc(N3CCOCC3)c({b})c2)cc1{c}",
        "{a}c1cc({b})ccc1CNC(=O)c1cccc({c})n1",
        "{a}c1ccc(NC(=O)c2ccc({b})cc2)c(N2CCOCC2)c1",
        "{a}c1ccc(C(=O)Nc2ccc(N3CCN(C)CC3)cc2{b})cc1",
        "{a}c1cc({b})ccc1NC(=O)c1ccc(OCCN2CCOCC2)c({c})c1",
    ],
}


def project_library_path(project_id: str) -> Path:
    return get_settings().project_data_dir / project_id / "pregenerated_designs.csv"


def _candidate_smiles(project_id: str) -> list[str]:
    if RDLogger is not None:
        RDLogger.DisableLog("rdApp.*")
    templates = PROJECT_TEMPLATES[project_id]
    candidates: set[str] = set()
    for template in templates:
        for a in SUBS_AROMATIC:
            for b in SUBS_SMALL:
                for c in SUBS_SMALL:
                    smiles = template.format(a=a, b=b, c=c)
                    if "CH2_PLACEHOLDER" in smiles or "SO2N" in smiles:
                        continue
                    if not is_valid_smiles(smiles):
                        continue
                    candidates.add(canonicalize_smiles(smiles))
    return sorted(candidates)


def diverse_pick(smiles: list[str], count: int, seed: int = 17) -> list[str]:
    rng = random.Random(seed)
    bins: dict[tuple[int, int, int, int], list[str]] = {}
    for item in smiles:
        desc = descriptors(item)
        key = (
            int(desc.molecular_weight // 75),
            int((desc.logp + 2) // 1.25),
            int(desc.tpsa // 35),
            int(desc.rotatable_bonds // 2),
        )
        bins.setdefault(key, []).append(item)
    for group in bins.values():
        rng.shuffle(group)
    keys = list(bins)
    rng.shuffle(keys)
    selected: list[str] = []
    while len(selected) < count and keys:
        next_keys = []
        for key in keys:
            group = bins[key]
            if group:
                selected.append(group.pop())
                if len(selected) == count:
                    break
            if group:
                next_keys.append(key)
        keys = next_keys
    return selected


def generate_project_library(project_id: str, count: int = 5000, force: bool = False) -> Path:
    if project_id not in PROJECT_TEMPLATES:
        raise ValueError(f"Unknown pregeneration template project_id: {project_id}")
    path = project_library_path(project_id)
    if path.exists() and not force:
        return path
    candidates = _candidate_smiles(project_id)
    if len(candidates) < count:
        raise ValueError(f"Only generated {len(candidates)} molecules for {project_id}; need {count}")
    picked = diverse_pick(candidates, count=count)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "project_id",
                "library_id",
                "source",
                "smiles",
                "canonical_smiles",
                "series",
                "molecular_weight",
                "logp",
                "tpsa",
                "hbd",
                "hba",
                "rotatable_bonds",
            ],
        )
        writer.writeheader()
        for index, smiles in enumerate(picked, start=1):
            desc = descriptors(smiles)
            writer.writerow(
                {
                    "project_id": project_id,
                    "library_id": f"{project_id}-PG{index:05d}",
                    "source": "pregenerated",
                    "smiles": smiles,
                    "canonical_smiles": desc.canonical_smiles,
                    "series": "virtual",
                    "molecular_weight": f"{desc.molecular_weight:.2f}",
                    "logp": f"{desc.logp:.2f}",
                    "tpsa": f"{desc.tpsa:.2f}",
                    "hbd": desc.hbd,
                    "hba": desc.hba,
                    "rotatable_bonds": desc.rotatable_bonds,
                }
            )
    return path


def ensure_project_library(project_id: str, count: int = 5000) -> Path:
    return generate_project_library(project_id, count=count, force=False)


def read_project_library(project_id: str) -> list[dict[str, str]]:
    path = ensure_project_library(project_id)
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def random_project_design(project_id: str) -> dict[str, str]:
    rows = read_project_library(project_id)
    if not rows:
        raise ValueError(f"No pregenerated designs for {project_id}")
    return random.choice(rows)


def generate_all_project_libraries(count: int = 5000, force: bool = False) -> dict[str, str]:
    return {
        project_id: str(generate_project_library(project_id, count=count, force=force))
        for project_id in PROJECT_TEMPLATES
    }
