"""Data models for Agent3 Calculator."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class ContribuenteInput:
    """Input data for fiscal calculation."""

    contribuente_id: str
    anno_fiscale: int
    primo_anno: bool
    ateco_ricavi: dict[str, Decimal]  # {"codice_ateco": importo_ricavi}
    rivalsa_inps_applicata: Decimal  # NOT included in taxable income
    regime_agevolato: bool  # True = 5%, False = 15%
    gestione_inps: str  # "separata" | "artigiani" | "commercianti"
    riduzione_inps_35: bool
    contributi_inps_versati: Decimal
    imposta_anno_precedente: Decimal  # 0 if primo_anno
    acconti_versati: Decimal
    crediti_precedenti: Decimal


@dataclass
class AtecoDetail:
    """Calculation breakdown for a single ATECO code."""

    codice_ateco: str
    ricavi: Decimal
    coefficiente: Decimal
    reddito: Decimal


@dataclass
class F24Entry:
    """Single F24 payment entry."""

    codice_tributo: str
    descrizione: str
    importo: Decimal
    scadenza: str  # "MM-DD"


@dataclass
class CalcoloResult:
    """Complete calculation output."""

    contribuente_id: str
    anno_fiscale: int
    primo_anno: bool

    # Per-ATECO breakdown
    dettaglio_ateco: list[AtecoDetail] = field(default_factory=list)

    # Aggregated
    reddito_lordo: Decimal = Decimal("0")
    contributi_inps_dedotti: Decimal = Decimal("0")
    reddito_imponibile: Decimal = Decimal("0")

    # Tax
    aliquota: Decimal = Decimal("0")
    imposta_sostitutiva: Decimal = Decimal("0")

    # Advances
    acconti_dovuti: Decimal = Decimal("0")
    acconto_prima_rata: Decimal = Decimal("0")
    acconto_seconda_rata: Decimal = Decimal("0")

    # Balance
    acconti_versati: Decimal = Decimal("0")
    crediti_precedenti: Decimal = Decimal("0")
    saldo: Decimal = Decimal("0")
    da_versare: Decimal = Decimal("0")
    credito_anno_prossimo: Decimal = Decimal("0")

    # INPS
    contributo_inps_calcolato: Decimal = Decimal("0")
    dettaglio_inps: dict = field(default_factory=dict)

    # Rivalsa (informational only — does NOT affect calculation)
    rivalsa_inps_applicata: Decimal = Decimal("0")

    # F24
    f24_entries: list[F24Entry] = field(default_factory=list)

    # Integrity
    checksum: str = ""
