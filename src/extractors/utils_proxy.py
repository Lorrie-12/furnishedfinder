import logging
from typing import Any, Dict

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger("furnished_finder.utils_proxy")

def _clean_proxy_config(proxy_config: Dict[str, Any]) -> Dict[str, str]:
    """
    Remove empty values and keep only http/https proxies.
    """
    if not isinstance(proxy_config, dict):
        return {}

    cleaned: Dict[str, str] = {}
    for key in ("http", "https"):
        val = proxy_config.get(key)
        if isinstance(val, str) and val.strip():
            cleaned[key] = val.strip()
    return cleaned

def create_session(
    headers: Dict[str, str],
    proxy_config: Dict[str, Any],
) -> requests.Session:
    """
    Initialize a configured requests.Session with optional proxies and retries.
    """
    session = requests.Session()

    cleaned_proxies = _clean_proxy_config(proxy_config)
    if cleaned_proxies:
        logger.info("Using proxies for HTTP requests.")
        session.proxies.update(cleaned_proxies)
    else:
        logger.debug("No proxies configured; using direct connection.")

    # Apply default headers
    if headers:
        session.headers.update(headers)

    # Attach retry strategy
    retry_strategy = Retry(
        total=3,
        backoff_factor=1.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    return session