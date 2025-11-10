import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

from extractors.utils_proxy import create_session

logger = logging.getLogger("furnished_finder.listings_parser")

@dataclass
class ScraperConfig:
    base_url: str
    timeout: int = 20
    max_retries: int = 3
    retry_backoff_seconds: int = 2
    headers: Optional[Dict[str, str]] = None
    proxy: Optional[Dict[str, Any]] = None

class ListingsScraper:
    """
    Handles HTTP communication with Furnished Finder and normalizes listing data.
    """

    def __init__(self, config: ScraperConfig) -> None:
        self.config = config
        self.session = create_session(
            headers=config.headers or {},
            proxy_config=config.proxy or {},
        )

    @classmethod
    def from_config(cls, config_dict: Dict[str, Any]) -> "ListingsScraper":
        cfg = ScraperConfig(
            base_url=config_dict.get(
                "base_url", "https://www.furnishedfinder.com/graphql"
            ),
            timeout=int(config_dict.get("request_timeout", 20)),
            max_retries=int(config_dict.get("max_retries", 3)),
            retry_backoff_seconds=int(config_dict.get("retry_backoff_seconds", 2)),
            headers=config_dict.get("default_headers", {}),
            proxy=config_dict.get("proxy") or {},
        )
        return cls(cfg)

    def _post_with_retry(self, json_payload: Dict[str, Any]) -> Optional[requests.Response]:
        last_error: Optional[Exception] = None

        for attempt in range(1, self.config.max_retries + 1):
            try:
                logger.debug(
                    "POST attempt %d to %s with payload keys=%s",
                    attempt,
                    self.config.base_url,
                    list(json_payload.keys()),
                )
                response = self.session.post(
                    self.config.base_url,
                    json=json_payload,
                    timeout=self.config.timeout,
                )
                response.raise_for_status()
                return response
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
                logger.warning(
                    "Request attempt %d/%d failed: %s",
                    attempt,
                    self.config.max_retries,
                    exc,
                )
                if attempt < self.config.max_retries:
                    sleep_seconds = self.config.retry_backoff_seconds * attempt
                    logger.debug("Sleeping for %d second(s) before retry.", sleep_seconds)
                    time.sleep(sleep_seconds)

        logger.error("All retries failed. Last error: %s", last_error)
        return None

    def fetch_listings(
        self,
        search_params: Dict[str, Any],
        max_listings: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Submit a search request and parse the listings into normalized dictionaries.
        The exact API payload/shape may differ in practice, but this provides a robust
        and configurable implementation.
        """
        payload = {
            "operationName": "SearchListings",
            "variables": {
                "filters": search_params,
                "pagination": {"first": max_listings},
            },
            "query": """
                query SearchListings($filters: ListingFiltersInput!, $pagination: PaginationInput!) {
                  listings(filters: $filters, pagination: $pagination) {
                    edges {
                      node {
                        id
                        title
                        propertyType
                        propertyTypeClass
                        rentAmount {
                          amount
                          currency
                        }
                        bedroomCount
                        bathroomCount
                        availableOnDate
                        amenities
                        photos
                        approxLocation {
                          latitude
                          longitude
                        }
                        hostProfile {
                          name
                          email
                          phone
                        }
                      }
                    }
                  }
                }
            """,
        }

        response = self._post_with_retry(json_payload=payload)
        if response is None:
            return []

        try:
            raw = response.json()
        except json.JSONDecodeError as exc:
            logger.error("Failed to decode JSON response: %s", exc)
            return []

        listings = self._normalize_listings(raw, max_listings=max_listings)
        return listings

    def _normalize_listings(
        self, raw: Any, max_listings: int
    ) -> List[Dict[str, Any]]:
        """
        Normalize API/HTML response into a standardized list of listing dictionaries.
        Attempts to handle multiple shapes gracefully.
        """
        items: List[Dict[str, Any]] = []

        # GraphQL-style shape
        try:
            edges = (
                raw.get("data", {})
                .get("listings", {})
                .get("edges", [])
            )
            if edges:
                for edge in edges:
                    node = edge.get("node") or {}
                    items.append(self._normalize_single(node))
        except AttributeError:
            # raw may not be dict-like; ignore and try other patterns
            logger.debug("Response not in expected GraphQL shape.")

        # Fallback: direct list of listings
        if not items and isinstance(raw, list):
            for entry in raw:
                if isinstance(entry, dict):
                    items.append(self._normalize_single(entry))

        # Fallback: direct "listings" key
        if not items and isinstance(raw, dict) and "listings" in raw:
            for entry in raw.get("listings", []):
                if isinstance(entry, dict):
                    items.append(self._normalize_single(entry))

        if not items:
            logger.warning("No listings found in response payload.")
            return []

        if max_listings and len(items) > max_listings:
            items = items[:max_listings]

        logger.info("Normalized %d listing(s) from response.", len(items))
        return items

    def _normalize_single(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map arbitrary response keys into the normalized schema used by this project.
        """
        # Some backends might use different keys; we try common aliases.
        listing_id = (
            raw.get("listingId")
            or raw.get("id")
            or raw.get("listing_id")
        )
        title = (
            raw.get("name")
            or raw.get("title")
            or raw.get("headline")
        )

        rent = raw.get("rentAmount") or raw.get("pricing") or {}
        if isinstance(rent, (int, float, str)):
            rent = {"amount": str(rent), "currency": "USD"}

        approx_location = raw.get("approxLocation") or raw.get("location") or {}
        if isinstance(approx_location, dict):
            lat = approx_location.get("latitude") or approx_location.get("lat")
            lng = approx_location.get("longitude") or approx_location.get("lng")
            approx_location = {
                "latitude": lat,
                "longitude": lng,
            }
        else:
            approx_location = {"latitude": None, "longitude": None}

        normalized = {
            "propertyType": raw.get("propertyType"),
            "propertyTypeClass": raw.get("propertyTypeClass"),
            "name": title,
            "listingId": listing_id,
            "rentAmount": {
                "amount": rent.get("amount"),
                "currency": rent.get("currency", "USD"),
            }
            if isinstance(rent, dict)
            else {"amount": None, "currency": None},
            "bedroomCount": raw.get("bedroomCount") or raw.get("bedrooms"),
            "bathroomCount": raw.get("bathroomCount") or raw.get("bathrooms"),
            "availableOnDate": raw.get("availableOnDate") or raw.get("available_on"),
            "amenities": raw.get("amenities") or [],
            "photos": raw.get("photos") or raw.get("images") or [],
            "approxLocation": approx_location,
        }

        # Optional host profile
        host_profile = raw.get("hostProfile") or raw.get("host") or {}
        if isinstance(host_profile, dict) and host_profile:
            normalized["hostProfile"] = {
                "name": host_profile.get("name"),
                "email": host_profile.get("email"),
                "phone": host_profile.get("phone"),
            }

        return normalized