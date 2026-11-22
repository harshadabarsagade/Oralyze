"""IBM Cloud IAM Token Management.

Thread-safe cached IAM access token provider for IBM Cloud services.
Refreshes tokens 120 seconds before expiration.
"""
import threading
import time
import requests
from config import Config

IAM_TOKEN_URL = "https://iam.cloud.ibm.com/identity/token"

_lock = threading.Lock()
_cached_token: str | None = None
_token_expiry: float = 0.0


class IAMAuthError(Exception):
    """Raised when IAM token acquisition fails."""
    pass


def get_token(force_refresh: bool = False) -> str:
    """Retrieve a valid IBM IAM Bearer token.
    
    Refreshes automatically if within 120 seconds of expiration.
    Thread-safe across multiple concurrent requests.
    """
    global _cached_token, _token_expiry

    if not Config.IBM_API_KEY:
        raise IAMAuthError(
            "IBM_API_KEY is missing. Please set IBM_API_KEY in your environment or .env file, "
            "or run with MOCK_MODE=1."
        )

    now = time.time()
    with _lock:
        if (
            not force_refresh
            and _cached_token is not None
            and now < (_token_expiry - 120)
        ):
            return _cached_token

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json"
        }
        data = {
            "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
            "apikey": Config.IBM_API_KEY
        }

        try:
            resp = requests.post(IAM_TOKEN_URL, headers=headers, data=data, timeout=30)
        except requests.RequestException as e:
            raise IAMAuthError(f"Network error requesting IBM IAM token: {e}") from e

        if resp.status_code != 200:
            raise IAMAuthError(
                f"Failed to acquire IAM token (HTTP {resp.status_code}): {resp.text}"
            )

        payload = resp.json()
        token = payload.get("access_token")
        expires_in = payload.get("expires_in", 3600)

        if not token:
            raise IAMAuthError("IAM response did not contain access_token")

        _cached_token = token
        _token_expiry = now + float(expires_in)
        return _cached_token


def reset_token_cache() -> None:
    """Reset cached token state (useful for tests or re-authenticating)."""
    global _cached_token, _token_expiry
    with _lock:
        _cached_token = None
        _token_expiry = 0.0
