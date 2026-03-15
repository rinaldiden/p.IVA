"""Data models for Agent1 Collector."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any


class FonteTransazione(str, Enum):
    SDI = "sdi"
    PSD2 = "psd2"
    OCR = "ocr"


class TipoTransazione(str, Enum):
    RICAVO = "ricavo"
    SPESA = "spesa"
    F24 = "f24"
    ALTRO = "altro"


class TipoOperazioneBancaria(str, Enum):
    BONIFICO_IN = "bonifico_in"
    BONIFICO_OUT = "bonifico_out"
    ADDEBITO = "addebito"
    ACCREDITO = "accredito"
    F24 = "f24"
    PAGAMENTO_CARTA = "pagamento_carta"
    COMMISSIONE = "commissione"
    ALTRO = "altro"


class StatoSDI(str, Enum):
    """SDI notification status codes."""
    RC = "RC"   # Ricevuta di consegna
    NS = "NS"   # Notifica di scarto
    MC = "MC"   # Mancata consegna
    AT = "AT"   # Attestazione di trasmissione (PA)
    DT = "DT"   # Decorrenza termini (PA)
    NE = "NE"   # Notifica esito (PA)


@dataclass
class Transazione:
    """Base transaction model."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    data: date = field(default_factory=date.today)
    importo: Decimal = Decimal("0")
    tipo: TipoTransazione = TipoTransazione.ALTRO
    fonte: FonteTransazione = FonteTransazione.SDI
    categoria: str = ""
    descrizione: str = ""
    raw_data: dict = field(default_factory=dict)


@dataclass
class TransazioneSDI(Transazione):
    """Transaction from SDI (electronic invoice)."""
    numero_fattura: str = ""
    cedente: str = ""
    cedente_piva: str = ""
    cessionario: str = ""
    cessionario_piva: str = ""
    stato_sdi: StatoSDI | str = ""
    regime_fiscale: str = ""
    aliquota_iva: Decimal = Decimal("0")
    tipo_documento: str = ""  # TD01, TD04, etc.
    data_fattura: date | None = None
    conservazione_id: str = ""

    def __post_init__(self):
        self.fonte = FonteTransazione.SDI


@dataclass
class TransazioneBancaria(Transazione):
    """Transaction from PSD2 bank data."""
    iban: str = ""
    iban_controparte: str = ""
    causale: str = ""
    tipo_operazione: TipoOperazioneBancaria = TipoOperazioneBancaria.ALTRO
    data_valuta: date | None = None
    denominazione_controparte: str = ""

    def __post_init__(self):
        self.fonte = FonteTransazione.PSD2


@dataclass
class TransazioneOCR(Transazione):
    """Transaction from OCR receipt/document."""
    fornitore: str = ""
    categoria_spesa: str = ""
    partita_iva_fornitore: str = ""
    metodo_pagamento: str = ""
    confidence: float = 0.0

    def __post_init__(self):
        self.fonte = FonteTransazione.OCR


@dataclass
class ConsentStatus:
    """PSD2 consent status."""
    valid: bool = False
    consent_id: str = ""
    expires_at: datetime | None = None
    needs_renewal: bool = False
    action_required: str = ""  # "none", "renew", "new_consent"
    days_remaining: int = 0


@dataclass
class CollectionResult:
    """Result of a collection run across all channels."""
    transactions: list[Transazione] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sources_processed: list[str] = field(default_factory=list)
    total_ricavi: Decimal = Decimal("0")
    total_spese: Decimal = Decimal("0")

    @property
    def success(self) -> bool:
        return len(self.errors) == 0

    @property
    def count(self) -> int:
        return len(self.transactions)
