from __future__ import annotations

import logging
import time

from infrastructure.storage.minio_storage import MinioStorage
from settings.factory import get_settings


logger = logging.getLogger("storage-init")


def ensure_storage_ready(
    *,
    attempts: int = 120,
    delay_seconds: float = 1.0,
) -> None:
    storage = MinioStorage(get_settings().object_storage)
    for attempt in range(1, attempts + 1):
        try:
            storage.ensure_bucket()
        except Exception:
            if attempt == attempts:
                raise
            logger.info(
                "MinIO is not ready, retrying (%s/%s)",
                attempt,
                attempts,
            )
            time.sleep(delay_seconds)
        else:
            logger.info("MinIO bucket is ready: %s", storage.bucket)
            return


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    ensure_storage_ready()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
