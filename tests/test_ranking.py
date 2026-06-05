from app.services.ranking import rank_design_score


def test_ranking_prefers_balanced_design():
    strong, _, strong_warnings = rank_design_score(
        {
            "pIC50": 7.6,
            "logD": 2.6,
            "solubility_uM": 65,
            "microsomal_CLint": 18,
            "hERG_IC50_uM": 22,
            "Caco2_Papp": 18,
        }
    )
    weak, _, weak_warnings = rank_design_score(
        {
            "pIC50": 6.2,
            "logD": 4.8,
            "solubility_uM": 8,
            "microsomal_CLint": 75,
            "hERG_IC50_uM": 3,
            "Caco2_Papp": 4,
        }
    )
    assert strong > weak
    assert not strong_warnings
    assert weak_warnings

