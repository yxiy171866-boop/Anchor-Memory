#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run Anchor Midnight Consolidation Pipeline.

Can be run via cron, scheduled tasks, or triggered manually.

Usage:
    python scripts/run_midnight.py [--date YYYY-MM-DD]
"""
import sys
import argparse
import logging
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from anchor.midnight.pipeline import MidnightPipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("run_midnight")


def main():
    parser = argparse.ArgumentParser(description="Run Anchor Midnight Consolidation Pipeline")
    parser.add_argument("--date", type=str, default=None, help="Target date in YYYY-MM-DD format (defaults to today)")
    args = parser.parse_args()

    pipeline = MidnightPipeline()
    logger.info(f"Triggering midnight consolidation for date: {args.date or 'today'}...")
    res = pipeline.run_midnight_consolidation(target_date=args.date)
    logger.info(f"Consolidation completed: {res}")


if __name__ == "__main__":
    main()
