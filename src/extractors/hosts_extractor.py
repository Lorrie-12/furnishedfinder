import logging
from typing import Any, Dict, List

logger = logging.getLogger("furnished_finder.hosts_extractor")

def extract_host_profiles(listings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Extract host contact information from normalized listing dictionaries.
    Returns a flat list of dictionaries suitable for CSV export.
    """
    hosts: List[Dict[str, Any]] = []

    for listing in listings:
        host = listing.get("hostProfile") or {}
        if not isinstance(host, dict) or not host:
            continue

        row = {
            "listingId": listing.get("listingId"),
            "listingName": listing.get("name"),
            "propertyType": listing.get("propertyType"),
            "hostName": host.get("name"),
            "hostEmail": host.get("email"),
            "hostPhone": host.get("phone"),
        }

        # Only keep rows that have at least one non-empty host field
        if any(row.get(k) for k in ("hostName", "hostEmail", "hostPhone")):
            hosts.append(row)

    logger.info("Extracted %d host profile(s) from %d listing(s).", len(hosts), len(listings))
    return hosts