import csv
import json
import logging
import os
from typing import Any, Dict, Iterable, List

logger = logging.getLogger("furnished_finder.export_manager")

def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)

def export_to_json(data: Any, path: str) -> None:
    """
    Write Python data structures to a JSON file with UTF-8 encoding.
    """
    _ensure_parent_dir(path)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("Wrote JSON output to %s", path)
    except OSError as exc:
        logger.error("Failed to write JSON output to %s: %s", path, exc)
        raise

def _collect_fieldnames(rows: Iterable[Dict[str, Any]]) -> List[str]:
    """
    Collect a stable set of CSV columns from an iterable of dictionaries.
    """
    fieldnames: List[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)
    return fieldnames

def export_to_csv(rows: List[Dict[str, Any]], path: str) -> None:
    """
    Write a list of dictionaries to a CSV file. Nested dictionaries are flattened
    using a best-effort approach.
    """
    _ensure_parent_dir(path)

    if not rows:
        logger.warning("No rows provided to export_to_csv; creating empty file at %s.", path)
        # Still create an empty file so downstream steps don't fail.
        open(path, "w", encoding="utf-8").close()
        return

    # Flatten nested dictionaries for common fields like rentAmount, approxLocation, hostProfile.
    flattened_rows: List[Dict[str, Any]] = []
    for row in rows:
        flat: Dict[str, Any] = {}
        for key, value in row.items():
            if isinstance(value, dict):
                for sub_key, sub_val in value.items():
                    flat[f"{key}_{sub_key}"] = sub_val
            else:
                flat[key] = value
        flattened_rows.append(flat)

    fieldnames = _collect_fieldnames(flattened_rows)

    try:
        with open(path, "w", encoding="utf-8", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for flat in flattened_rows:
                writer.writerow(flat)
        logger.info("Wrote CSV output to %s", path)
    except OSError as exc:
        logger.error("Failed to write CSV output to %s: %s", path, exc)
        raise