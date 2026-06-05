# Backend

FastAPI backend for MedChemCopilot.

## Main Modules

- `app.models` - SQLAlchemy domain models.
- `app.services.ingestion` - idempotent seed/import pipeline.
- `app.services.chemistry` - RDKit-backed SMILES validation and descriptors.
- `app.services.ml` - baseline model training and reporting.
- `app.services.prediction` - model inference for designs.
- `app.services.ranking` - project scoring and rank assignment.
- `app.services.iteration` - end-to-end project refresh loop.

## Run

```bash
pip install -e ".[dev]"
python -m app.db.init_db
uvicorn app.main:app --reload
```

