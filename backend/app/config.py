from functools import lru_cache
from pathlib import Path
from pydantic import BaseModel


class Settings(BaseModel):
    database_url: str = "sqlite:///./medchem.db"
    seed_data_dir: Path = Path(__file__).resolve().parents[2] / "data" / "seed"
    project_data_dir: Path = Path(__file__).resolve().parents[2] / "data" / "projects"
    model_dir: Path = Path(__file__).resolve().parents[1] / "models"
    report_dir: Path = Path(__file__).resolve().parents[1] / "reports"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.project_data_dir.mkdir(parents=True, exist_ok=True)
    settings.model_dir.mkdir(parents=True, exist_ok=True)
    settings.report_dir.mkdir(parents=True, exist_ok=True)
    return settings
