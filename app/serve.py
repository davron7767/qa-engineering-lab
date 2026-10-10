"""Container/host entrypoint: apply migrations, optionally seed, then start uvicorn.

Usage: python -m app.serve [--host 0.0.0.0] [--port 8000] [--reload]
"""

import argparse
import logging

import uvicorn

from app.config import get_settings
from app.db.migrate import upgrade_to_head

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("qa_commerce.serve")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run QA Commerce")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="auto-reload (development only)")
    args = parser.parse_args()

    settings = get_settings()
    logger.info("Starting QA Commerce env=%s", settings.app_env)
    if settings.defect_mode:
        logger.warning(
            "DEFECT LAB ACTIVE: defect_mode=%s - do not trust results", settings.defect_mode
        )

    upgrade_to_head()
    if settings.seed_on_startup:
        from app.db.seed import seed

        seed()

    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
