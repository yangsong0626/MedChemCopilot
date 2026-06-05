from app.services.pregenerated import _candidate_smiles, diverse_pick


def test_project_generators_have_enough_valid_molecules():
    for project_id in ("KIN001", "GPCR002", "PROT003"):
        candidates = _candidate_smiles(project_id)
        assert len(candidates) >= 5000


def test_diverse_pick_returns_requested_unique_count():
    candidates = _candidate_smiles("KIN001")
    picked = diverse_pick(candidates, count=50)
    assert len(picked) == 50
    assert len(set(picked)) == 50
