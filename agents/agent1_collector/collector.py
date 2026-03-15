"""Agent1 — Collector (Multi-channel data aggregator)

Collects financial data from three channels:
- SDI: Electronic invoices (FatturaPA XML) — sent and received
- PSD2: Bank transactions via Open Banking
- OCR: Receipts and documents (pre-processed)

All parsing, normalization, deduplication, and business logic is fully
implemented. External API call points are marked with EXTERNAL comments.
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from .models import (
    CollectionResult,
    ConsentStatus,
    FonteTransazione,
    StatoSDI,
    TipoOperazioneBancaria,
    TipoTransazione,
    Transazione,
    TransazioneBancaria,
    TransazioneOCR,
    TransazioneSDI,
)

logger = logging.getLogger(__name__)

# FatturaPA XML namespace
_NS_FATTURA = "http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2"
_NS = {"p": _NS_FATTURA}

# PSD2 consent validity: 90 days per regulation
_PSD2_CONSENT_DAYS = 90
_PSD2_RENEWAL_WARNING_DAYS = 10

# SDI notification type mapping
_SDI_NOTIFICATION_TAGS = {
    "RicevutaConsegna": StatoSDI.RC,
    "NotificaScarto": StatoSDI.NS,
    "NotificaMancataConsegna": StatoSDI.MC,
    "AttestazioneTrasmissione": StatoSDI.AT,
    "NotificaDecorrenzaTermini": StatoSDI.DT,
    "NotificaEsito": StatoSDI.NE,
}

# Keywords to classify bank transactions
_F24_KEYWORDS = ["f24", "modello f24", "tribut", "agenzia entrate", "inps versamento"]
_COMMISSIONE_KEYWORDS = ["commissione", "canone", "spese bancarie", "spese conto"]


# ---------------------------------------------------------------------------
# SDI Channel
# ---------------------------------------------------------------------------

def parse_fattura_xml(xml_str: str) -> dict:
    """Parse a FatturaPA XML string into a structured dict.

    Handles both namespaced (p:FatturaElettronica) and non-namespaced XML.
    Extracts all key invoice fields for forfettario regime.
    """
    # Strip BOM if present
    xml_str = xml_str.strip()
    if xml_str.startswith("\ufeff"):
        xml_str = xml_str[1:]

    root = ET.fromstring(xml_str)

    # Detect namespace usage
    ns = ""
    if root.tag.startswith("{"):
        ns_uri = root.tag.split("}")[0] + "}"
        ns = ns_uri
    elif root.tag.startswith("p:"):
        # Register namespace for xpath
        pass

    def _find(parent: ET.Element, path: str) -> ET.Element | None:
        """Find element trying multiple namespace strategies."""
        # Try direct
        el = parent.find(path)
        if el is not None:
            return el
        # Try with namespace prefix
        if ns:
            ns_path = "/".join(f"{ns}{p}" for p in path.split("/"))
            el = parent.find(ns_path)
            if el is not None:
                return el
        # Try without any namespace (strip p: prefix)
        stripped = re.sub(r"p:", "", path)
        el = parent.find(stripped)
        return el

    def _text(parent: ET.Element, path: str, default: str = "") -> str:
        el = _find(parent, path)
        return el.text.strip() if el is not None and el.text else default

    def _find_any(parent: ET.Element, tag: str) -> ET.Element | None:
        """Find element by local name, ignoring namespace."""
        for el in parent.iter():
            local = el.tag.split("}")[-1] if "}" in el.tag else el.tag
            if local == tag:
                return el
        return None

    def _text_any(parent: ET.Element, tag: str, default: str = "") -> str:
        el = _find_any(parent, tag)
        return el.text.strip() if el is not None and el.text else default

    result: dict[str, Any] = {}

    # Header
    header = _find_any(root, "FatturaElettronicaHeader")
    if header is None:
        header = root  # fallback: search from root

    # Formato trasmissione
    result["formato_trasmissione"] = _text_any(root, "FormatoTrasmissione", "FPR12")

    # Cedente/Prestatore
    cedente = _find_any(header, "CedentePrestatore")
    if cedente is not None:
        result["cedente"] = {
            "denominazione": _text_any(cedente, "Denominazione"),
            "partita_iva": _text_any(cedente, "IdCodice"),
            "codice_fiscale": _text_any(cedente, "CodiceFiscale"),
            "regime_fiscale": _text_any(cedente, "RegimeFiscale"),
        }
    else:
        result["cedente"] = {}

    # Cessionario/Committente
    cessionario = _find_any(header, "CessionarioCommittente")
    if cessionario is not None:
        result["cessionario"] = {
            "denominazione": _text_any(cessionario, "Denominazione"),
            "partita_iva": _text_any(cessionario, "IdCodice"),
            "codice_fiscale": _text_any(cessionario, "CodiceFiscale"),
        }
    else:
        result["cessionario"] = {}

    # Body
    body = _find_any(root, "FatturaElettronicaBody")
    if body is None:
        body = root

    # Dati generali
    result["tipo_documento"] = _text_any(body, "TipoDocumento", "TD01")
    result["divisa"] = _text_any(body, "Divisa", "EUR")
    result["data"] = _text_any(body, "Data")
    result["numero"] = _text_any(body, "Numero")
    result["causale"] = _text_any(body, "Causale")
    result["importo_totale"] = _text_any(body, "ImportoTotaleDocumento", "0")

    # Bollo
    bollo_el = _find_any(body, "DatiBollo")
    if bollo_el is not None:
        result["bollo_virtuale"] = _text_any(bollo_el, "BolloVirtuale") == "SI"
        result["importo_bollo"] = _text_any(bollo_el, "ImportoBollo", "0")
    else:
        result["bollo_virtuale"] = False
        result["importo_bollo"] = "0"

    # Line items
    linee = []
    for det in root.iter():
        local = det.tag.split("}")[-1] if "}" in det.tag else det.tag
        if local == "DettaglioLinee":
            linea = {
                "numero_linea": _text_any(det, "NumeroLinea"),
                "descrizione": _text_any(det, "Descrizione"),
                "quantita": _text_any(det, "Quantita", "1"),
                "prezzo_unitario": _text_any(det, "PrezzoUnitario", "0"),
                "prezzo_totale": _text_any(det, "PrezzoTotale", "0"),
                "aliquota_iva": _text_any(det, "AliquotaIVA", "0"),
                "natura": _text_any(det, "Natura"),
            }
            linee.append(linea)
    result["linee"] = linee

    # Riepilogo
    result["imponibile"] = _text_any(body, "ImponibileImporto", "0")
    result["imposta"] = _text_any(body, "Imposta", "0")

    # Payment
    result["modalita_pagamento"] = _text_any(body, "ModalitaPagamento")
    result["importo_pagamento"] = _text_any(body, "ImportoPagamento", "0")
    result["iban"] = _text_any(body, "IBAN")
    result["data_scadenza"] = _text_any(body, "DataScadenzaPagamento")

    return result


def collect_sdi(xml_content: str) -> TransazioneSDI:
    """Parse a FatturaPA XML and return a TransazioneSDI.

    Works for both sent (emesse) and received (ricevute) invoices.
    """
    # EXTERNAL: replace with real API call to fetch XML from SDI
    parsed = parse_fattura_xml(xml_content)

    # Determine importo
    importo_str = parsed.get("importo_totale", "0") or "0"
    try:
        importo = Decimal(importo_str)
    except (InvalidOperation, ValueError):
        importo = Decimal("0")

    # Parse date
    data_str = parsed.get("data", "")
    try:
        data_fattura = date.fromisoformat(data_str)
    except (ValueError, TypeError):
        data_fattura = date.today()

    cedente_info = parsed.get("cedente", {})
    cessionario_info = parsed.get("cessionario", {})
    regime = cedente_info.get("regime_fiscale", "")

    # Determine tipo: if cedente is us -> ricavo, if cessionario is us -> spesa
    # This is set later by the caller based on profile; default to ricavo
    tipo = TipoTransazione.RICAVO

    tx = TransazioneSDI(
        id=str(uuid.uuid4()),
        data=data_fattura,
        importo=importo,
        tipo=tipo,
        fonte=FonteTransazione.SDI,
        descrizione=parsed.get("causale", ""),
        raw_data=parsed,
        numero_fattura=parsed.get("numero", ""),
        cedente=cedente_info.get("denominazione", ""),
        cedente_piva=cedente_info.get("partita_iva", ""),
        cessionario=cessionario_info.get("denominazione", ""),
        cessionario_piva=cessionario_info.get("partita_iva", ""),
        stato_sdi="",
        regime_fiscale=regime,
        aliquota_iva=Decimal("0"),
        tipo_documento=parsed.get("tipo_documento", "TD01"),
        data_fattura=data_fattura,
    )

    # If cedente regime is RF19 (forfettario), IVA is 0
    if regime == "RF19":
        tx.aliquota_iva = Decimal("0")

    return tx


def track_sdi_status(fattura_id: str, notifica_xml: str) -> str:
    """Process an SDI notification XML and return the status code.

    Parses notification XML to extract the status type (RC, NS, MC, AT, DT, NE).
    """
    # EXTERNAL: replace with real API call to poll SDI notifications
    try:
        root = ET.fromstring(notifica_xml.strip())
    except ET.ParseError:
        logger.error("Invalid SDI notification XML for fattura %s", fattura_id)
        return ""

    # Check root tag against known notification types
    root_tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag

    for tag_name, status in _SDI_NOTIFICATION_TAGS.items():
        if tag_name in root_tag:
            logger.info("SDI status for %s: %s", fattura_id, status.value)
            return status.value

    # Also check child elements
    for child in root:
        child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        for tag_name, status in _SDI_NOTIFICATION_TAGS.items():
            if tag_name in child_tag:
                logger.info("SDI status for %s: %s", fattura_id, status.value)
                return status.value

    # Fallback: look for Esito element
    for el in root.iter():
        local = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        if local == "Esito" and el.text:
            return el.text.strip()

    logger.warning("Could not determine SDI status for fattura %s", fattura_id)
    return ""


# ---------------------------------------------------------------------------
# PSD2 Channel
# ---------------------------------------------------------------------------

def check_psd2_consent(consent_data: dict) -> ConsentStatus:
    """Check the PSD2 consent lifecycle status.

    Consent expires every 90 days per PSD2 regulation.
    Returns status with renewal action if needed.
    """
    # EXTERNAL: replace with real API call to check consent with ASPSP
    consent_id = consent_data.get("consent_id", "")
    valid_until_str = consent_data.get("valid_until", "")
    status_str = consent_data.get("status", "")

    if not consent_id or status_str == "expired":
        return ConsentStatus(
            valid=False,
            consent_id=consent_id,
            needs_renewal=True,
            action_required="new_consent",
            days_remaining=0,
        )

    # Parse expiry
    expires_at = None
    days_remaining = 0
    if valid_until_str:
        try:
            expires_at = datetime.fromisoformat(valid_until_str)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            delta = expires_at - now
            days_remaining = max(0, delta.days)
        except (ValueError, TypeError):
            return ConsentStatus(
                valid=False,
                consent_id=consent_id,
                needs_renewal=True,
                action_required="new_consent",
            )

    is_valid = days_remaining > 0 and status_str in ("valid", "active", "")
    needs_renewal = days_remaining <= _PSD2_RENEWAL_WARNING_DAYS

    if is_valid and not needs_renewal:
        action = "none"
    elif is_valid and needs_renewal:
        action = "renew"
    else:
        action = "new_consent"

    return ConsentStatus(
        valid=is_valid,
        consent_id=consent_id,
        expires_at=expires_at,
        needs_renewal=needs_renewal,
        action_required=action,
        days_remaining=days_remaining,
    )


def _classify_bank_operation(causale: str, importo: Decimal) -> tuple[TipoOperazioneBancaria, TipoTransazione]:
    """Classify a bank transaction by its causale and amount."""
    causale_lower = causale.lower()

    # F24 payments
    if any(kw in causale_lower for kw in _F24_KEYWORDS):
        return TipoOperazioneBancaria.F24, TipoTransazione.F24

    # Bank fees
    if any(kw in causale_lower for kw in _COMMISSIONE_KEYWORDS):
        return TipoOperazioneBancaria.COMMISSIONE, TipoTransazione.SPESA

    # Card payments are always expenses
    if "pagamento carta" in causale_lower or "pos" in causale_lower:
        return TipoOperazioneBancaria.PAGAMENTO_CARTA, TipoTransazione.SPESA

    # Bonifico classification by sign
    if "bonifico" in causale_lower or "sepa" in causale_lower:
        if importo >= 0:
            return TipoOperazioneBancaria.BONIFICO_IN, TipoTransazione.RICAVO
        else:
            return TipoOperazioneBancaria.BONIFICO_OUT, TipoTransazione.SPESA

    # Addebito / Accredito
    if "addebito" in causale_lower:
        return TipoOperazioneBancaria.ADDEBITO, TipoTransazione.SPESA
    if "accredito" in causale_lower:
        return TipoOperazioneBancaria.ACCREDITO, TipoTransazione.RICAVO

    # Default: use sign
    if importo >= 0:
        return TipoOperazioneBancaria.ACCREDITO, TipoTransazione.RICAVO
    return TipoOperazioneBancaria.ADDEBITO, TipoTransazione.SPESA


def normalize_transaction(raw: dict) -> TransazioneBancaria:
    """Normalize a single raw PSD2/OBP bank transaction into TransazioneBancaria.

    Expected raw fields (OBP-style):
    - transaction_id / id
    - booking_date / date
    - amount / value
    - currency
    - creditor_name / counterpart_name
    - creditor_iban / counterpart_iban
    - remittance_information / causale / description
    - value_date
    """
    tx_id = raw.get("transaction_id") or raw.get("id") or str(uuid.uuid4())

    # Parse amount
    amount_raw = raw.get("amount") or raw.get("value") or "0"
    try:
        importo = Decimal(str(amount_raw))
    except (InvalidOperation, ValueError):
        importo = Decimal("0")

    # Parse date
    date_str = raw.get("booking_date") or raw.get("date") or ""
    try:
        tx_date = date.fromisoformat(date_str)
    except (ValueError, TypeError):
        tx_date = date.today()

    # Value date
    vdate_str = raw.get("value_date") or ""
    try:
        value_date = date.fromisoformat(vdate_str)
    except (ValueError, TypeError):
        value_date = None

    causale = (
        raw.get("remittance_information")
        or raw.get("causale")
        or raw.get("description")
        or ""
    )

    controparte = (
        raw.get("creditor_name")
        or raw.get("counterpart_name")
        or raw.get("debtor_name")
        or ""
    )

    iban_controparte = (
        raw.get("creditor_iban")
        or raw.get("counterpart_iban")
        or raw.get("debtor_iban")
        or ""
    )

    iban_proprio = raw.get("account_iban") or raw.get("iban") or ""

    tipo_op, tipo_tx = _classify_bank_operation(causale, importo)

    return TransazioneBancaria(
        id=tx_id,
        data=tx_date,
        importo=abs(importo),  # store absolute, tipo indicates direction
        tipo=tipo_tx,
        fonte=FonteTransazione.PSD2,
        descrizione=causale,
        raw_data=raw,
        iban=iban_proprio,
        iban_controparte=iban_controparte,
        causale=causale,
        tipo_operazione=tipo_op,
        data_valuta=value_date,
        denominazione_controparte=controparte,
    )


def collect_psd2(transactions: list[dict]) -> list[TransazioneBancaria]:
    """Normalize a list of raw PSD2 bank transactions.

    Args:
        transactions: List of raw OBP-format transaction dicts.

    Returns:
        List of normalized TransazioneBancaria objects.
    """
    # EXTERNAL: replace with real API call to fetch transactions from ASPSP
    result = []
    for raw in transactions:
        try:
            tx = normalize_transaction(raw)
            result.append(tx)
        except Exception as e:
            logger.error("Failed to normalize PSD2 transaction: %s — %s", raw.get("id", "?"), e)
    return result


# ---------------------------------------------------------------------------
# OCR Channel
# ---------------------------------------------------------------------------

def collect_ocr(ocr_result: dict) -> TransazioneOCR:
    """Process a pre-OCR'd receipt/document into TransazioneOCR.

    Expected fields:
    - date / data
    - amount / importo / total
    - vendor / fornitore
    - vendor_vat / partita_iva
    - category / categoria
    - payment_method / metodo_pagamento
    - confidence
    - description / descrizione
    """
    # Parse date
    date_str = ocr_result.get("date") or ocr_result.get("data") or ""
    try:
        tx_date = date.fromisoformat(date_str)
    except (ValueError, TypeError):
        tx_date = date.today()

    # Parse amount
    amount_raw = ocr_result.get("amount") or ocr_result.get("importo") or ocr_result.get("total") or "0"
    # Handle comma as decimal separator (Italian format)
    amount_str = str(amount_raw).replace(",", ".")
    try:
        importo = Decimal(amount_str)
    except (InvalidOperation, ValueError):
        importo = Decimal("0")

    fornitore = ocr_result.get("vendor") or ocr_result.get("fornitore") or ""
    categoria = ocr_result.get("category") or ocr_result.get("categoria") or ""
    piva = ocr_result.get("vendor_vat") or ocr_result.get("partita_iva") or ""
    metodo = ocr_result.get("payment_method") or ocr_result.get("metodo_pagamento") or ""
    confidence = float(ocr_result.get("confidence", 0.0))
    descrizione = ocr_result.get("description") or ocr_result.get("descrizione") or ""

    return TransazioneOCR(
        id=str(uuid.uuid4()),
        data=tx_date,
        importo=importo,
        tipo=TipoTransazione.SPESA,  # OCR receipts are typically expenses
        fonte=FonteTransazione.OCR,
        descrizione=descrizione or f"Acquisto {fornitore}",
        raw_data=ocr_result,
        fornitore=fornitore,
        categoria_spesa=categoria,
        partita_iva_fornitore=piva,
        metodo_pagamento=metodo,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Merge & Deduplication
# ---------------------------------------------------------------------------

def _transaction_fingerprint(tx: Transazione) -> str:
    """Create a fingerprint for deduplication.

    Uses date + importo + description/causale similarity.
    """
    key_parts = [
        tx.data.isoformat(),
        str(tx.importo),
    ]

    # Add source-specific identifier
    if isinstance(tx, TransazioneSDI):
        key_parts.append(f"sdi:{tx.numero_fattura}")
    elif isinstance(tx, TransazioneBancaria):
        key_parts.append(f"psd2:{tx.causale[:30]}")
    elif isinstance(tx, TransazioneOCR):
        key_parts.append(f"ocr:{tx.fornitore}")

    raw = "|".join(key_parts).lower()
    return hashlib.md5(raw.encode()).hexdigest()


def merge_transactions(
    sdi: list[TransazioneSDI],
    psd2: list[TransazioneBancaria],
    ocr: list[TransazioneOCR],
) -> list[Transazione]:
    """Merge and deduplicate transactions from all channels.

    Priority: SDI > PSD2 > OCR (SDI is the authoritative source).
    Deduplication uses date + amount matching within a 3-day window.
    """
    seen_fingerprints: set[str] = set()
    merged: list[Transazione] = []

    # SDI first (highest priority)
    for tx in sdi:
        fp = _transaction_fingerprint(tx)
        seen_fingerprints.add(fp)
        merged.append(tx)

    # PSD2: check for duplicates against SDI by amount+date proximity
    sdi_lookup: list[tuple[date, Decimal]] = [(t.data, t.importo) for t in sdi]

    for tx in psd2:
        fp = _transaction_fingerprint(tx)
        if fp in seen_fingerprints:
            continue

        # Check if this PSD2 transaction matches an SDI invoice
        is_dup = False
        for sdi_date, sdi_amount in sdi_lookup:
            date_diff = abs((tx.data - sdi_date).days)
            if date_diff <= 3 and tx.importo == sdi_amount:
                is_dup = True
                break

        if not is_dup:
            seen_fingerprints.add(fp)
            merged.append(tx)

    # OCR: check for duplicates against all existing
    all_lookup: list[tuple[date, Decimal]] = [(t.data, t.importo) for t in merged]

    for tx in ocr:
        fp = _transaction_fingerprint(tx)
        if fp in seen_fingerprints:
            continue

        is_dup = False
        for existing_date, existing_amount in all_lookup:
            date_diff = abs((tx.data - existing_date).days)
            if date_diff <= 2 and tx.importo == existing_amount:
                is_dup = True
                break

        if not is_dup:
            seen_fingerprints.add(fp)
            merged.append(tx)

    # Sort by date
    merged.sort(key=lambda t: t.data)
    return merged


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def collect_all(profile: dict, sources: dict) -> CollectionResult:
    """Orchestrate collection from all channels.

    Args:
        profile: Contribuente profile dict (from persistence).
        sources: Dict with optional keys:
            - "sdi_xmls": list of XML strings (sent/received invoices)
            - "psd2_transactions": list of raw bank transaction dicts
            - "psd2_consent": consent status dict
            - "ocr_results": list of OCR result dicts

    Returns:
        CollectionResult with all transactions merged and deduplicated.
    """
    result = CollectionResult()
    piva = (
        profile.get("anagrafica", {}).get("partita_iva", "")
        or profile.get("partita_iva", "")
    )

    # --- SDI ---
    sdi_transactions: list[TransazioneSDI] = []
    sdi_xmls = sources.get("sdi_xmls", [])
    if sdi_xmls:
        result.sources_processed.append("sdi")
        for xml_str in sdi_xmls:
            try:
                tx = collect_sdi(xml_str)
                # Determine if this is a sent or received invoice
                if piva and tx.cedente_piva == piva:
                    tx.tipo = TipoTransazione.RICAVO
                elif piva and tx.cessionario_piva == piva:
                    tx.tipo = TipoTransazione.SPESA
                sdi_transactions.append(tx)
            except Exception as e:
                result.errors.append(f"SDI parse error: {e}")

    # --- PSD2 ---
    psd2_transactions: list[TransazioneBancaria] = []
    psd2_raw = sources.get("psd2_transactions", [])
    psd2_consent = sources.get("psd2_consent")

    if psd2_consent:
        consent_status = check_psd2_consent(psd2_consent)
        if not consent_status.valid:
            result.warnings.append(
                f"PSD2 consent invalid — action: {consent_status.action_required}"
            )
        elif consent_status.needs_renewal:
            result.warnings.append(
                f"PSD2 consent expires in {consent_status.days_remaining} days — renew soon"
            )

    if psd2_raw:
        result.sources_processed.append("psd2")
        psd2_transactions = collect_psd2(psd2_raw)

    # --- OCR ---
    ocr_transactions: list[TransazioneOCR] = []
    ocr_results = sources.get("ocr_results", [])
    if ocr_results:
        result.sources_processed.append("ocr")
        for ocr_data in ocr_results:
            try:
                tx = collect_ocr(ocr_data)
                ocr_transactions.append(tx)
            except Exception as e:
                result.errors.append(f"OCR parse error: {e}")

    # --- Merge ---
    merged = merge_transactions(sdi_transactions, psd2_transactions, ocr_transactions)
    result.transactions = merged

    # Compute totals
    for tx in merged:
        if tx.tipo == TipoTransazione.RICAVO:
            result.total_ricavi += tx.importo
        elif tx.tipo in (TipoTransazione.SPESA, TipoTransazione.F24):
            result.total_spese += tx.importo

    return result
