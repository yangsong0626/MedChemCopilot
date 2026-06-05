# MedChemCopilot

MedChemCopilot is a full-stack medicinal chemistry design-ranking prototype.
It separates measured project data, candidate designs, model predictions,
ranking outputs, and chemist feedback so CADD/IT workflows and chemistry review
workflows can evolve independently.

## Structure

- `backend/` - FastAPI API, database models, chemistry utilities, ML services.
- `frontend/` - React + TypeScript app for project/design review.
- `data/seed/` - Synthetic decoy project, compound, design, and feedback data.
- `docs/` - Architecture notes and development prompts.
- `scripts/` - Local helper scripts.
- `tests/` - Integration-oriented tests that exercise the backend services.

## Local Development

Backend:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m app.db.init_db
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

The backend defaults to SQLite at `backend/medchem.db`. Seed data lives in
`data/seed`.

