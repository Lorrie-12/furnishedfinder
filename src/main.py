import argparse
import json
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

# Make sure the src directory is on the Python path when running from repo root
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from extractors.listings_parser import ListingsScraper  # type: ignore
from extractors.hosts_extractor import extract_host_profiles  # type: ignore
from outputs.export_manager import export_to_json, export_to_csv  # type: ignore

logger = logging.getLogger("furnished_finder.main")

def load_config(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config file not found at '{path}'")

    with open(path, "r", encoding="utf-8") as f:
        config = json.load(f)

    return config

def load_input(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        logger.warning("Input file not found at '%s', using empty search payload.", path)
        return {}

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data

def build_default_paths() -> Dict[str, str]:
    data_dir = os.path.join(REPO_ROOT, "data")
    os.makedirs(data_dir, exist_ok=True)

    return {
        "config": os.path.join(CURRENT_DIR, "config", "settings.json"),
        "input": os.path.join(data_dir, "sample_input.json"),
        "output_json": os.path.join(
            data_dir,
            f"furnishedfinder_listings_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json",
        ),
        "output_csv": os.path.join(
            data_dir,
            f"furnishedfinder_listings_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv",
        ),
    }

def parse_args(defaults: Dict[str, str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape rental listings from Furnished Finder."
    )
    parser.add_argument(
        "--config",
        type=str,
        default=defaults["config"],
        help="Path to settings JSON file.",
    )
    parser.add_argument(
        "--input",
        type=str,
        default=defaults["input"],
        help="Path to JSON file with search parameters.",
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default=defaults["output_json"],
        help="Path to JSON file where listings will be saved.",
    )
    parser.add_argument(
        "--output-csv",
        type=str,
        default=defaults["output_csv"],
        help="Path to CSV file where a flattened copy of listings will be saved.",
    )
    parser.add_argument(
        "--max-listings",
        type=int,
        default=None,
        help="Maximum number of listings to retrieve.",
    )
    parser.add_argument(
        "--include-hosts",
        action="store_true",
        help="Extract host profile information into a separate CSV file.",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        help="Logging level (DEBUG, INFO, WARNING, ERROR).",
    )
    return parser.parse_args()

def setup_logging(level: str) -> None:
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

def main() -> None:
    default_paths = build_default_paths()
    args = parse_args(default_paths)
    setup_logging(args.log_level)

    logger.info("Using config file: %s", args.config)
    config = load_config(args.config)

    logger.info("Loading input from: %s", args.input)
    input_data = load_input(args.input)

    search_payload: Dict[str, Any] = input_data.get("search", {})
    max_listings: int = (
        args.max_listings
        if args.max_listings is not None
        else int(input_data.get("maxListings", 100))
    )
    include_hosts: bool = bool(
        args.include_hosts or input_data.get("includeHostProfile", False)
    )

    scraper = ListingsScraper.from_config(config)

    logger.info(
        "Starting scrape with max_listings=%d, include_hosts=%s",
        max_listings,
        include_hosts,
    )

    listings: List[Dict[str, Any]] = scraper.fetch_listings(
        search_params=search_payload,
        max_listings=max_listings,
    )

    if not listings:
        logger.warning("No listings were returned from scraper.")
    else:
        logger.info("Scraped %d listing(s).", len(listings))

    logger.info("Exporting listings to JSON: %s", args.output_json)
    export_to_json(listings, args.output_json)

    # Always save a CSV copy of the listings
    logger.info("Exporting listings to CSV: %s", args.output_csv)
    export_to_csv(listings, args.output_csv)

    # Optionally extract hosts into a separate CSV file
    if include_hosts and listings:
        hosts = extract_host_profiles(listings)
        if hosts:
            host_csv_path = args.output_csv.replace(".csv", "_hosts.csv")
            logger.info(
                "Extracting %d host profile(s) to CSV: %s", len(hosts), host_csv_path
            )
            export_to_csv(hosts, host_csv_path)
        else:
            logger.info(
                "include-hosts was set, but no hostProfile data found in listings."
            )

    logger.info("Done.")

if __name__ == "__main__":
    main()