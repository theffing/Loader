"""Background jobs for the data pipeline."""

import logging
import os
import shutil
from pathlib import Path

from loader import CSVLoader
from sources import get_tables, DATA_TABLE, METADATA_TABLE

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

RAW_DIR = Path(os.getenv("PIPELINE_RAW_DIR", "stock-api/raw")).resolve()
PROCESSED_DIR = Path(os.getenv("PIPELINE_PROCESSED_DIR", "stock-api/processed")).resolve()
FAILED_DIR = Path(os.getenv("PIPELINE_FAILED_DIR", "stock-api/failed")).resolve()


def process_csv_job(file_path: str) -> bool:
    path = Path(file_path)
    if not path.exists():
        logger.error("File not found: %s", file_path)
        return False

    processed_dir = PROCESSED_DIR
    failed_dir = FAILED_DIR

    loader = CSVLoader(
        csv_dir=str(path.parent),
        processed_dir=str(processed_dir),
        failed_dir=str(failed_dir),
    )

    if not loader.validate_csv(str(path)):
        logger.error("Validation failed for %s", path.name)
        _move_to_failed(path, failed_dir)
        return False

    return loader.process_csv_file(str(path))


def _move_to_failed(file_path: Path, failed_dir: Path) -> None:
    failed_dir.mkdir(parents=True, exist_ok=True)
    dest = failed_dir / file_path.name
    if dest.exists():
        dest.unlink()
    shutil.move(str(file_path), str(dest))
