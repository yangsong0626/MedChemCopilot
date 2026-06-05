import pytest

from app.services.chemistry import (
    canonicalize_smiles,
    descriptors,
    is_valid_smiles,
    mol_svg,
    morgan_fingerprint,
)


def test_smiles_validation_and_descriptors():
    assert is_valid_smiles("CCO")
    assert not is_valid_smiles("")
    desc = descriptors("CCO")
    assert desc.molecular_weight > 0
    assert canonicalize_smiles("CCO")


def test_invalid_smiles_raises():
    with pytest.raises(ValueError):
        canonicalize_smiles("")


def test_fingerprint_shape():
    fp = morgan_fingerprint("CCO", n_bits=32)
    assert len(fp) == 32
    assert set(fp) <= {0, 1}


def test_molecule_svg_renders():
    svg = mol_svg("CCO", width=120, height=80)
    assert "<svg" in svg
    assert "</svg>" in svg
