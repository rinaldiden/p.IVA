"""Data models for Agent0 Wizard."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass
class ProfiloContribuente:
    contribuente_id: str
    nome: str
    cognome: str
    codice_fiscale: str
    comune_residenza: str
    data_apertura_piva: date
    primo_anno: bool
    ateco_principale: str
    ateco_secondari: list[str] = field(default_factory=list)
    regime_agevolato: bool = True
    gestione_inps: str = "separata"
    riduzione_inps_35: bool = False
    rivalsa_inps_4: bool = False
    canale_scontrini: str = "app"
    banca_collegata: str = ""
    stato: str = "onboarding"


@dataclass
class Scadenza:
    data: str  # "YYYY-MM-DD"
    descrizione: str
    importo: Decimal
    codice_tributo: str = ""


@dataclass
class ATECOSuggestion:
    codice: str
    descrizione: str
    coefficiente: Decimal
    motivazione: str


@dataclass
class SimulationResult:
    profilo: ProfiloContribuente
    anno_fiscale: int

    # Core from Agent3
    ricavi_totali: Decimal = Decimal("0")
    reddito_lordo: Decimal = Decimal("0")
    reddito_imponibile: Decimal = Decimal("0")
    aliquota: Decimal = Decimal("0")
    imposta_sostitutiva: Decimal = Decimal("0")
    contributo_inps: Decimal = Decimal("0")
    acconti_dovuti: Decimal = Decimal("0")
    acconto_prima_rata: Decimal = Decimal("0")
    acconto_seconda_rata: Decimal = Decimal("0")
    da_versare: Decimal = Decimal("0")
    credito_anno_prossimo: Decimal = Decimal("0")

    # Added by simulator
    risparmio_vs_ordinario: Decimal = Decimal("0")
    rata_mensile_da_accantonare: Decimal = Decimal("0")
    scadenze_anno_corrente: list[Scadenza] = field(default_factory=list)
    confronto_regimi: dict = field(default_factory=dict)

    # Warnings
    warnings: list[str] = field(default_factory=list)

    # Agent3 raw
    dettaglio_ateco: list = field(default_factory=list)
    dettaglio_inps: dict = field(default_factory=dict)
    checksum: str = ""
