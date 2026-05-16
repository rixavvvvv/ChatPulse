#!/usr/bin/env python
"""Bootstrap script to seed the database with demo data.

Usage:
    python -m app.bootstrap.bootstrap          # Run bootstrap
    python -m app.bootstrap.bootstrap --reset # Reset and re-bootstrap
"""

import asyncio
import argparse
import logging
import sys

from app.db import AsyncSessionLocal, init_db
from app.bootstrap.service import run_bootstrap


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(description="Bootstrap ChatPulse database")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset all demo data before bootstrapping",
    )
    parser.add_argument(
        "--skip-init",
        action="store_true",
        help="Skip database initialization",
    )
    args = parser.parse_args()

    logger.info("Starting database bootstrap...")

    try:
        # Initialize database (create tables)
        if not args.skip_init:
            logger.info("Initializing database...")
            await init_db()
            logger.info("Database initialized")

        # Run bootstrap
        async with AsyncSessionLocal() as session:
            stats = await run_bootstrap(session, reset=args.reset)

        logger.info("=" * 50)
        logger.info("Bootstrap completed successfully!")
        logger.info("=" * 50)
        logger.info("Stats:")
        for key, value in stats.items():
            logger.info(f"  {key}: {value}")
        logger.info("=" * 50)
        logger.info("Demo credentials:")
        logger.info("  Email: admin@chatpulse.local")
        logger.info("  Password: demo123")
        logger.info("=" * 50)

    except Exception as e:
        logger.error(f"Bootstrap failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())