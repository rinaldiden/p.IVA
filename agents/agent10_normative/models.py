"""Data models for Agent10 NormativeWatcher."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class ParameterChange:
    """A single parameter that changed due to a normative update."""

    nome_parametro: str         # e.g. "inps_rates.2025.gestione_separata.aliquota"
    file_destinazione: str      # e.g. "shared/inps_rates.json"
    valore_precedente: str
    valore_nuovo: str
    data_efficacia: date
    norma_riferimento: str      # e.g. "L. 197/2022 art. 1 c. 54"
    certezza: str               # "alta" | "media" | "bassa"
    url_fonte: str


@dataclass
class NormativeUpdate:
    """A normative document that triggers one or more parameter changes."""

    update_id: str
    timestamp_rilevazione: datetime
    fonte: str                  # "gazzetta_ufficiale" | "agenzia_entrate" | "inps" | "normattiva"
    documento_titolo: str
    documento_url: str
    hash_documento: str         # SHA-256 of the source text
    parametri_modificati: list[ParameterChange] = field(default_factory=list)
    stato: str = "pending"      # "pending" | "scheduled" | "applied" | "review_needed"
    data_applicazione: date | None = None


@dataclass
class SourceResult:
    """Result from fetching a normative source."""

    fonte: str
    titolo: str
    url: str
    testo: str
    data_pubblicazione: date
    hash_documento: str         # SHA-256 of testo
    gia_processato: bool = False


@dataclass
class RelevanceCheck:
    """LLM assessment of whether a document is relevant."""

    rilevante: bool
    parametri_coinvolti: list[str] = field(default_factory=list)
    motivazione: str = ""
