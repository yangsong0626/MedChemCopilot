from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.services.ingestion import load_seed_data
from app.services.ml import train_project_models
from app.services.prediction import score_project_designs
from app.services.ranking import rank_project_designs


def main() -> None:
    init_db()
    with SessionLocal() as db:
        imports = load_seed_data(db)
        print(f"Imported: {imports}")
        for project_id in ("KIN001", "GPCR002", "PROT003"):
            runs = train_project_models(db, project_id)
            predictions = score_project_designs(db, project_id)
            ranks = rank_project_designs(db, project_id)
            print(
                f"{project_id}: model_runs={len(runs)} "
                f"predictions={len(predictions)} ranked_designs={len(ranks)}"
            )


if __name__ == "__main__":
    main()

