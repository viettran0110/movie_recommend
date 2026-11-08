from pathlib import Path

from alembic.config import Config

API_ROOT = Path(__file__).resolve().parents[2]
PG_IMAGE = "pgvector/pgvector:0.8.7-pg17"  # keep in sync with infra/docker-compose.yml


def alembic_config(url: str) -> Config:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url)
    config.attributes["configure_logger"] = False
    return config
