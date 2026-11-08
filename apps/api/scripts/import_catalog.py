"""Import the CSV catalog from CATALOG_DATA_DIR into Postgres (ADR-023).

    cd apps/api && uv run python -m scripts.import_catalog [--data-dir ../../data]
    docker compose -f infra/docker-compose.yml run --rm worker python -m scripts.import_catalog

Same code path as the `catalog.import` worker task. Idempotent; safe to re-run.
"""

import argparse
import asyncio
import json
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.modules.catalog.service import run_import


def main() -> None:
    parser = argparse.ArgumentParser(description="Import the CSV catalog into Postgres.")
    parser.add_argument("--data-dir", type=Path, help="overrides CATALOG_DATA_DIR")
    args = parser.parse_args()

    settings = get_settings()
    if args.data_dir is not None:
        settings = settings.model_copy(update={"catalog_data_dir": args.data_dir})
    configure_logging(settings.log_level)

    report = asyncio.run(run_import(settings))
    summary = report.model_dump(exclude={"changed_title_ids"})
    summary["changed_titles"] = len(report.changed_title_ids)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
