"""Connectors to normative data sources."""

from __future__ import annotations

import hashlib
import json
import logging
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .models import SourceResult

logger = logging.getLogger(__name__)

# Keywords for filtering relevant documents
KEYWORDS = [
    "forfettario", "regime forfetario", "partita IVA",
    "gestione separata", "contributi INPS", "imposta sostitutiva",
    "coefficienti di redditività", "soglia ricavi",
    "partite IVA minori", "artigiani", "commercianti",
    "aliquote contributive", "minimale", "massimale",
]

_AUDIT_DIR = Path(__file__).resolve().parent / "audit"
_CHANGES_FILE = _AUDIT_DIR / "changes.jsonl"


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _already_processed(doc_hash: str) -> bool:
    """Check if document hash is already in the audit trail."""
    if not _CHANGES_FILE.exists():
        return False
    with open(_CHANGES_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if entry.get("hash_documento") == doc_hash:
                    return True
            except json.JSONDecodeError:
                continue
    return False


def _matches_keywords(text: str) -> bool:
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in KEYWORDS)


def fetch_gazzetta_ufficiale(http_client: Any = None) -> list[SourceResult]:
    """Fetch from Gazzetta Ufficiale RSS feed.

    Args:
        http_client: Callable that takes a URL and returns response text.
                     If None, uses requests.
    """
    url = "https://www.gazzettaufficiale.it/rss/esatto.xml"

    if http_client is None:
        try:
            import requests
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            content = resp.text
        except Exception as e:
            logger.error("Failed to fetch GU RSS: %s", e)
            return []
    else:
        content = http_client(url)

    return _parse_rss(content, fonte="gazzetta_ufficiale")


def fetch_agenzia_entrate(http_client: Any = None) -> list[SourceResult]:
    """Fetch from Agenzia delle Entrate normativa e prassi."""
    url = "https://www.agenziaentrate.gov.it/portale/normativa-e-prassi"

    if http_client is None:
        try:
            import requests
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            content = resp.text
        except Exception as e:
            logger.error("Failed to fetch AdE: %s", e)
            return []
    else:
        content = http_client(url)

    # For now, treat as potential RSS or HTML — extract items
    return _parse_rss(content, fonte="agenzia_entrate")


def fetch_inps_circolari(http_client: Any = None) -> list[SourceResult]:
    """Fetch INPS circulars."""
    url = "https://www.inps.it/circolari"

    if http_client is None:
        try:
            import requests
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            content = resp.text
        except Exception as e:
            logger.error("Failed to fetch INPS: %s", e)
            return []
    else:
        content = http_client(url)

    return _parse_rss(content, fonte="inps")


def fetch_normattiva(http_client: Any = None) -> list[SourceResult]:
    """Fetch from Normattiva (consolidated law texts)."""
    url = "https://www.normattiva.it"

    if http_client is None:
        try:
            import requests
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            content = resp.text
        except Exception as e:
            logger.error("Failed to fetch Normattiva: %s", e)
            return []
    else:
        content = http_client(url)

    return _parse_rss(content, fonte="normattiva")


def _parse_rss(content: str, fonte: str) -> list[SourceResult]:
    """Parse RSS/XML content into SourceResult list, filtering by keywords."""
    results: list[SourceResult] = []

    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        logger.warning("Could not parse XML from %s", fonte)
        return results

    # Handle RSS 2.0 format
    for item in root.iter("item"):
        title_el = item.find("title")
        link_el = item.find("link")
        desc_el = item.find("description")
        pubdate_el = item.find("pubDate")

        title = title_el.text if title_el is not None and title_el.text else ""
        link = link_el.text if link_el is not None and link_el.text else ""
        desc = desc_el.text if desc_el is not None and desc_el.text else ""
        combined_text = f"{title} {desc}"

        if not _matches_keywords(combined_text):
            continue

        doc_hash = _hash_text(combined_text)
        if _already_processed(doc_hash):
            continue

        pub_date = date.today()
        if pubdate_el is not None and pubdate_el.text:
            try:
                pub_date = datetime.strptime(
                    pubdate_el.text[:10], "%Y-%m-%d"
                ).date()
            except ValueError:
                pass

        results.append(SourceResult(
            fonte=fonte,
            titolo=title,
            url=link,
            testo=combined_text,
            data_pubblicazione=pub_date,
            hash_documento=doc_hash,
        ))

    return results


ALL_FETCHERS = {
    "gazzetta_ufficiale": fetch_gazzetta_ufficiale,
    "agenzia_entrate": fetch_agenzia_entrate,
    "inps": fetch_inps_circolari,
    "normattiva": fetch_normattiva,
}
