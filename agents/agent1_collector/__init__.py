"""Agent1 — Collector: Multi-channel data aggregator."""

from .collector import (
    collect_all,
    collect_ocr,
    collect_psd2,
    collect_sdi,
    check_psd2_consent,
    merge_transactions,
    normalize_transaction,
    parse_fattura_xml,
    track_sdi_status,
)
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

__all__ = [
    "collect_all",
    "collect_ocr",
    "collect_psd2",
    "collect_sdi",
    "check_psd2_consent",
    "merge_transactions",
    "normalize_transaction",
    "parse_fattura_xml",
    "track_sdi_status",
    "CollectionResult",
    "ConsentStatus",
    "FonteTransazione",
    "StatoSDI",
    "TipoOperazioneBancaria",
    "TipoTransazione",
    "Transazione",
    "TransazioneBancaria",
    "TransazioneOCR",
    "TransazioneSDI",
]
