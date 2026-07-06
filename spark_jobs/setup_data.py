#!/usr/bin/env python3
"""
NYC Mobility Analytics — Data Setup Script
===========================================
Copies uploaded raw data files into the project's data/raw/ directory
and validates all required files are present.

Usage:
    python spark_jobs/setup_data.py \
        --source /path/to/uploads \
        --dest   data/raw
"""

import argparse
import logging
import shutil
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("setup_data")

REQUIRED_FILES = [
    "yellow_tripdata_2025-01.parquet",
    "green_tripdata_2025-01.parquet",
    "fhv_tripdata_2025-01.parquet",
    "202501-citibike-tripdata_1.csv",
    "202501-citibike-tripdata_2.csv",
    "202501-citibike-tripdata_3.csv",
]


def setup_data(source_dir: str, dest_dir: str):
    src  = Path(source_dir)
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    log.info(f"Source: {src}")
    log.info(f"Destination: {dest}")

    missing = []
    for fname in REQUIRED_FILES:
        src_path  = src / fname
        dest_path = dest / fname

        if not src_path.exists():
            log.warning(f"  NOT FOUND: {fname}")
            missing.append(fname)
            continue

        if dest_path.exists():
            log.info(f"  Already exists: {fname}")
        else:
            shutil.copy2(src_path, dest_path)
            size_mb = dest_path.stat().st_size / 1_048_576
            log.info(f"  Copied: {fname} ({size_mb:.1f} MB)")

    if missing:
        log.error(f"\n{len(missing)} file(s) missing from source:")
        for f in missing:
            log.error(f"  - {f}")
        sys.exit(1)
    else:
        log.info(f"\nAll {len(REQUIRED_FILES)} files ready in {dest} ✓")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Setup raw data files")
    parser.add_argument("--source", default="/mnt/user-data/uploads",
                        help="Directory containing uploaded files")
    parser.add_argument("--dest",   default="data/raw",
                        help="Project data/raw directory")
    args = parser.parse_args()
    setup_data(args.source, args.dest)
