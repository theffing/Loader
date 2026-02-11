"""RQ worker to process queued CSV ingest jobs."""

import logging
import os

from redis import Redis
from rq import Connection, Queue, Worker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def build_redis_client() -> Redis:
    return Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        password=os.getenv("REDIS_PASSWORD") or None,
        decode_responses=True,
    )


def main() -> int:
    queue_name = os.getenv("PIPELINE_QUEUE_NAME", "ingest")
    redis_client = build_redis_client()
    queue = Queue(queue_name)

    logger.info("Starting worker for queue '%s'", queue_name)
    with Connection(redis_client):
        worker = Worker([queue])
        worker.work(with_scheduler=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
