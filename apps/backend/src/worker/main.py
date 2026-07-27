from __future__ import annotations

# The worker is also supported as a direct script. The path bootstrap must
# happen before importing the backend package and the repository-level ML code.
# ruff: noqa: E402
import logging
import sys
from pathlib import Path

BACKEND_SRC = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[4]
for path in (BACKEND_SRC, PROJECT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from worker.pipeline_worker import PipelineWorker


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    PipelineWorker().run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
