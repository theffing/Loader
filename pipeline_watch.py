"""Watch raw folders and enqueue CSV processing jobs."""

import argparse
import logging
import os
import time
from pathlib import Path

from redis import Redis
from rq import Queue
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from pipeline_jobs import process_csv_job
from sources import list_sources

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def build_redis_client() -> Redis:
    return Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        password=os.getenv("REDIS_PASSWORD") or None,
        decode_responses=True,
    )


def enqueue_file(queue: Queue, file_path: Path, source: str | None) -> None:
    if file_path.suffix.lower() != ".csv":
        return
    if not file_path.exists():
        return

    queue.enqueue(
        process_csv_job,
        str(file_path),
        source,
        job_timeout=1800,
    )
    logger.info("Enqueued %s", file_path)


class CSVEventHandler(FileSystemEventHandler):
    def __init__(self, queue: Queue, source: str | None):
        self.queue = queue
        self.source = source

    def on_created(self, event):
        if event.is_directory:
            return
        enqueue_file(self.queue, Path(event.src_path), self.source)

    def on_moved(self, event):
        if event.is_directory:
            return
        enqueue_file(self.queue, Path(event.dest_path), self.source)


def main() -> int:
    parser = argparse.ArgumentParser(description="Watch raw directories and enqueue CSV jobs")
    parser.add_argument(
        "--raw-dir",
        default=os.getenv("PIPELINE_RAW_DIR", "stock-api/raw"),
        help="Raw directory to watch",
    )
    parser.add_argument(
        "--source",
        default=None,
        help="Force a source name for all files",
    )
    parser.add_argument(
        "--scan-existing",
        action="store_true",
        help="Enqueue existing CSV files on startup",
    )
    args = parser.parse_args()

    raw_dir = Path(args.raw_dir).resolve()
    raw_dir.mkdir(parents=True, exist_ok=True)

    redis_client = build_redis_client()
    queue_name = os.getenv("PIPELINE_QUEUE_NAME", "ingest")
    queue = Queue(queue_name, connection=redis_client)

    if args.scan_existing:
        for csv_path in raw_dir.rglob("*.csv"):
            enqueue_file(queue, csv_path, args.source)

    event_handler = CSVEventHandler(queue, args.source)
    observer = Observer()

    if args.source:
        observer.schedule(event_handler, str(raw_dir), recursive=True)
    else:
        observer.schedule(event_handler, str(raw_dir), recursive=True)

    logger.info("Watching %s for CSV files", raw_dir)
    if not args.source:
        logger.info("Sources: %s", ", ".join(list_sources()))

    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()

    observer.join()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
