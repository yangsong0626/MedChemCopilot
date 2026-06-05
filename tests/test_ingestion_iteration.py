from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models import Base, Design, Project
from app.services.ingestion import load_seed_data
from app.services.iteration import run_project_iteration


def make_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_seed_data_loads_idempotently():
    db = make_db()
    first = load_seed_data(db)
    second = load_seed_data(db)
    assert first["projects"] == 3
    assert second["design_candidates"] == 12
    assert len(db.scalars(select(Project)).all()) == 3
    assert len(db.scalars(select(Design)).all()) == 12


def test_project_iteration_scores_and_ranks():
    db = make_db()
    output = run_project_iteration(db, "KIN001")
    assert output["model_runs"] >= 1
    assert output["ranked_designs"] == 4

