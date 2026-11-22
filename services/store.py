"""IBM Cloudant Persistence Service with Local JSON Fallback.

Capabilities:
- REST API implementation for IBM Cloudant (PUT db, PUT doc, GET _all_docs)
- Local fallback to data/scorecards.json when Cloudant is not configured or offline
- One document per completed viva session
"""
import datetime
import json
import logging
import os
import requests
from config import Config
from services.ibm_auth import get_token

logger = logging.getLogger("store")

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
LOCAL_STORE_PATH = os.path.join(DATA_DIR, "scorecards.json")

_db_initialized = False


def _ensure_data_dir() -> None:
    """Ensure data/ directory exists."""
    os.makedirs(DATA_DIR, exist_ok=True)


def _load_local_docs() -> list[dict]:
    """Load scorecards from local JSON file."""
    _ensure_data_dir()
    if not os.path.exists(LOCAL_STORE_PATH):
        return []
    try:
        with open(LOCAL_STORE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("[store] Failed to read %s: %s", LOCAL_STORE_PATH, e)
        return []


def _save_local_doc(doc: dict) -> bool:
    """Save scorecard to local JSON file."""
    _ensure_data_dir()
    docs = _load_local_docs()
    # Replace existing or append
    doc_id = doc.get("_id") or doc.get("session_id")
    replaced = False
    for i, d in enumerate(docs):
        if (d.get("_id") or d.get("session_id")) == doc_id:
            docs[i] = doc
            replaced = True
            break
    if not replaced:
        docs.insert(0, doc)

    try:
        with open(LOCAL_STORE_PATH, "w", encoding="utf-8") as f:
            json.dump(docs, f, indent=2)
        return True
    except Exception as e:
        logger.error("[store] Failed to write %s: %s", LOCAL_STORE_PATH, e)
        return False


def cloudant_enabled() -> bool:
    """Check if IBM Cloudant credentials are configured."""
    return bool(Config.CLOUDANT_URL and Config.IBM_API_KEY and not Config.MOCK_MODE)


def _init_cloudant_db() -> bool:
    """Create Cloudant database if it does not already exist."""
    global _db_initialized
    if _db_initialized:
        return True

    if not cloudant_enabled():
        return False

    url = f"{Config.CLOUDANT_URL}/{Config.CLOUDANT_DB}"
    try:
        token = get_token()
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.put(url, headers=headers, timeout=15)
        # 201 Created or 412 Precondition Failed (already exists)
        if resp.status_code in (201, 202, 412):
            _db_initialized = True
            return True
        logger.warning("[store] Cloudant DB init status %s: %s", resp.status_code, resp.text)
    except Exception as e:
        logger.warning("[store] Cloudant DB init error: %s", e)

    return False


def save(doc: dict) -> bool:
    """Save completed viva session document to Cloudant or local fallback."""
    doc_id = doc.get("_id") or doc.get("session_id")
    if not doc_id:
        logger.error("[store] Cannot save doc without _id or session_id")
        return False

    doc["_id"] = doc_id
    if "created_at" not in doc:
        doc["created_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Always ensure local copy exists as safe backup
    _save_local_doc(doc)

    if not cloudant_enabled():
        return True

    try:
        _init_cloudant_db()
        token = get_token()
        url = f"{Config.CLOUDANT_URL}/{Config.CLOUDANT_DB}/{doc_id}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        resp = requests.put(url, headers=headers, json=doc, timeout=20)
        if resp.status_code in (200, 201):
            return True
        logger.warning("[store] Cloudant save returned HTTP %s: %s", resp.status_code, resp.text)
    except Exception as e:
        logger.warning("[store] Cloudant save exception: %s", e)

    return False


def get(doc_id: str) -> dict | None:
    """Retrieve document by ID from Cloudant or local store."""
    if cloudant_enabled():
        try:
            token = get_token()
            url = f"{Config.CLOUDANT_URL}/{Config.CLOUDANT_DB}/{doc_id}"
            headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.warning("[store] Cloudant get error: %s", e)

    # Local store fallback
    for d in _load_local_docs():
        if (d.get("_id") or d.get("session_id")) == doc_id:
            return d
    return None


def recent(limit: int = 25) -> list[dict]:
    """Retrieve recent scorecard documents from Cloudant or local store."""
    if cloudant_enabled():
        try:
            token = get_token()
            url = f"{Config.CLOUDANT_URL}/{Config.CLOUDANT_DB}/_all_docs?include_docs=true&limit={limit}"
            headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
            resp = requests.get(url, headers=headers, timeout=20)
            if resp.status_code == 200:
                rows = resp.json().get("rows", [])
                docs = [r["doc"] for r in rows if "doc" in r and not r["id"].startswith("_design")]
                docs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
                return docs[:limit]
        except Exception as e:
            logger.warning("[store] Cloudant recent error: %s", e)

    local_docs = _load_local_docs()
    local_docs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return local_docs[:limit]
