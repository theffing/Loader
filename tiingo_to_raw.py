#!/usr/bin/env python3
"""Collect Tiingo CSVs from per-ticker folders into a flat raw/ directory."""

import argparse
import os
import shutil
from pathlib import Path


def find_source_csv(ticker_dir: Path) -> Path | None:
    """Pick the most likely price CSV for a ticker directory."""
    preferred = ticker_dir / "prices_daily.csv"
    if preferred.is_file():
        return preferred

    csv_files = sorted(ticker_dir.glob("*.csv"))
    if len(csv_files) == 1:
        return csv_files[0]

    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Copy Tiingo CSVs from per-ticker folders into a flat raw/ directory."
    )
    parser.add_argument(
        "--source",
        default="tiingo_us_data",
        help="Source folder containing per-ticker subfolders (default: tiingo_us_data)",
    )
    parser.add_argument(
        "--dest",
        default="stock-api/raw",
        help="Destination folder for flattened CSVs (default: stock-api/raw)",
    )
    parser.add_argument(
        "--move",
        action="store_true",
        help="Move files instead of copying",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite destination files if they already exist",
    )

    args = parser.parse_args()
    source_dir = Path(args.source).resolve()
    dest_dir = Path(args.dest).resolve()

    if not source_dir.is_dir():
        print(f"Source folder not found: {source_dir}")
        return 1

    dest_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    skipped = 0
    missing = 0

    for entry in sorted(source_dir.iterdir()):
        if not entry.is_dir():
            continue

        ticker = entry.name
        src_csv = find_source_csv(entry)
        if src_csv is None:
            print(f"Skip {ticker}: no single CSV (or prices_daily.csv) found")
            missing += 1
            continue

        dest_csv = dest_dir / f"{ticker}.csv"
        if dest_csv.exists() and not args.overwrite:
            print(f"Skip {ticker}: {dest_csv.name} exists")
            skipped += 1
            continue

        if args.move:
            if dest_csv.exists():
                dest_csv.unlink()
            shutil.move(str(src_csv), str(dest_csv))
        else:
            shutil.copy2(src_csv, dest_csv)

        copied += 1

    print(
        "Done. "
        f"copied={copied}, skipped={skipped}, missing={missing}, "
        f"dest={dest_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
