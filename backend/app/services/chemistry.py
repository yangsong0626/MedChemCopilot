from __future__ import annotations

import hashlib
from dataclasses import dataclass

try:
    from rdkit import Chem
    from rdkit.Chem import (
        Crippen,
        Descriptors,
        Lipinski,
        rdDepictor,
        rdFingerprintGenerator,
        rdMolDescriptors,
    )
    from rdkit.Chem.Draw import rdMolDraw2D
except ImportError:  # pragma: no cover - fallback keeps non-RDKit dev environments usable.
    Chem = None
    Crippen = None
    Descriptors = None
    Lipinski = None
    rdDepictor = None
    rdFingerprintGenerator = None
    rdMolDescriptors = None
    rdMolDraw2D = None


@dataclass(frozen=True)
class DescriptorSet:
    canonical_smiles: str
    molecular_weight: float
    logp: float
    tpsa: float
    hbd: int
    hba: int
    rotatable_bonds: int


def mol_from_smiles(smiles: str):
    if not smiles or not smiles.strip():
        return None
    if Chem is None:
        return smiles.strip()
    return Chem.MolFromSmiles(smiles)


def is_valid_smiles(smiles: str) -> bool:
    return mol_from_smiles(smiles) is not None


def canonicalize_smiles(smiles: str) -> str:
    mol = mol_from_smiles(smiles)
    if mol is None:
        raise ValueError(f"Invalid SMILES: {smiles}")
    if Chem is None:
        return smiles.strip()
    return Chem.MolToSmiles(mol, canonical=True)


def descriptors(smiles: str) -> DescriptorSet:
    mol = mol_from_smiles(smiles)
    if mol is None:
        raise ValueError(f"Invalid SMILES: {smiles}")
    canonical = canonicalize_smiles(smiles)
    if Chem is None:
        heavy_chars = sum(1 for char in canonical if char.isalpha() and char.isupper())
        hetero = sum(canonical.count(atom) for atom in ("N", "O", "S", "F", "Cl"))
        return DescriptorSet(
            canonical_smiles=canonical,
            molecular_weight=float(max(heavy_chars, 1) * 13.5),
            logp=float(max(0.0, len(canonical) / 18 - hetero * 0.2)),
            tpsa=float(hetero * 18),
            hbd=canonical.count("N") + canonical.count("O"),
            hba=hetero,
            rotatable_bonds=max(0, canonical.count("C") // 4),
        )
    return DescriptorSet(
        canonical_smiles=canonical,
        molecular_weight=float(Descriptors.MolWt(mol)),
        logp=float(Crippen.MolLogP(mol)),
        tpsa=float(rdMolDescriptors.CalcTPSA(mol)),
        hbd=int(Lipinski.NumHDonors(mol)),
        hba=int(Lipinski.NumHAcceptors(mol)),
        rotatable_bonds=int(Lipinski.NumRotatableBonds(mol)),
    )


def morgan_fingerprint(smiles: str, radius: int = 2, n_bits: int = 1024) -> list[int]:
    mol = mol_from_smiles(smiles)
    if mol is None:
        raise ValueError(f"Invalid SMILES: {smiles}")
    if Chem is None:
        digest = hashlib.sha256(canonicalize_smiles(smiles).encode()).digest()
        bits = [0] * n_bits
        for byte in digest:
            bits[byte % n_bits] = 1
        return bits
    generator = rdFingerprintGenerator.GetMorganGenerator(radius=radius, fpSize=n_bits)
    bitvect = generator.GetFingerprint(mol)
    return [int(bit) for bit in bitvect.ToBitString()]


def feature_vector(smiles: str) -> list[float]:
    desc = descriptors(smiles)
    return [
        desc.molecular_weight,
        desc.logp,
        desc.tpsa,
        float(desc.hbd),
        float(desc.hba),
        float(desc.rotatable_bonds),
        *[float(bit) for bit in morgan_fingerprint(smiles, n_bits=128)],
    ]


def mol_svg(smiles: str, width: int = 260, height: int = 180) -> str:
    mol = mol_from_smiles(smiles)
    if mol is None:
        raise ValueError(f"Invalid SMILES: {smiles}")
    if Chem is None or rdMolDraw2D is None or rdDepictor is None:
        canonical = canonicalize_smiles(smiles)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}">'
            '<rect width="100%" height="100%" fill="white"/>'
            f'<text x="12" y="{height // 2}" font-family="monospace" '
            f'font-size="13" fill="#223036">{canonical}</text></svg>'
        )
    rdDepictor.Compute2DCoords(mol)
    drawer = rdMolDraw2D.MolDraw2DSVG(width, height)
    options = drawer.drawOptions()
    options.clearBackground = False
    options.bondLineWidth = 1.8
    options.minFontSize = 11
    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()
    svg = drawer.GetDrawingText()
    return svg.replace("svg:", "")
