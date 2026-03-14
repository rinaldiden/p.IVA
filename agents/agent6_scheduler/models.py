"""Data models for Agent6 Payment Scheduler."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass
class F24Entry:
    """Single line item in an F24."""
    sezione: str  # "erario", "inps", "regioni"
    codice_tributo: str = ""
    causale_contributo: str = ""
    anno_riferimento: int = 0
    periodo_da: str = ""
    periodo_a: str = ""
    importo_debito: Decimal = Decimal("0")
    importo_credito: Decimal = Decimal("0")
    descrizione: str = ""


@dataclass
class F24:
    """Complete F24 payment form."""
    contribuente_cf: str
    contribuente_nome: str
    contribuente_cognome: str
    data_versamento: date
    scadenza_id: str  # e.g. "saldo_imposta_2024"
    anno_fiscale: int
    righe: list[F24Entry] = field(default_factory=list)
    totale_debito: Decimal = Decimal("0")
    totale_credito: Decimal = Decimal("0")
    saldo: Decimal = Decimal("0")
    iban: str = ""
    descrizione: str = ""

    def calcola_totali(self) -> None:
        self.totale_debito = sum(r.importo_debito for r in self.righe)
        self.totale_credito = sum(r.importo_credito for r in self.righe)
        self.saldo = self.totale_debito - self.totale_credito


@dataclass
class ScadenzaFiscale:
    """A scheduled payment deadline."""
    id: str
    data: date
    descrizione: str
    importo: Decimal
    codice_tributo: str = ""
    causale: str = ""
    f24: F24 | None = None
    stato: str = "da_pagare"  # da_pagare, pagato, scaduto


@dataclass
class PianoAnnuale:
    """Complete annual payment plan."""
    contribuente_id: str
    anno_fiscale: int
    scadenze: list[ScadenzaFiscale] = field(default_factory=list)
    totale_annuo: Decimal = Decimal("0")
    marche_bollo_totale: Decimal = Decimal("0")
    crediti_compensati: Decimal = Decimal("0")
