"""Data models for Agent3b Validator — completely independent from Agent3."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class InputFiscale:
    """Fiscal calculation input — mirrors Agent3's ContribuenteInput
    but is a completely separate class. Zero imports from agent3.
    """

    id_contribuente: str
    anno: int
    is_primo_anno: bool
    ricavi_per_ateco: dict[str, Decimal]  # {"codice": importo}
    rivalsa_4_percento: Decimal
    aliquota_agevolata: bool  # True = 5%, False = 15%
    tipo_gestione_inps: str  # "separata" | "artigiani" | "commercianti"
    ha_riduzione_35: bool
    inps_gia_versati: Decimal
    imposta_anno_prima: Decimal
    acconti_gia_versati: Decimal
    crediti_da_prima: Decimal


@dataclass
class Divergenza:
    """A single field-level divergence between Agent3 and Agent3b."""

    campo: str
    valore_agent3: str
    valore_agent3b: str
    delta: str


@dataclass
class EsitoValidazione:
    """Validation result."""

    valid: bool
    blocco: bool  # True = stop everything, notify Agent9
    contribuente_id: str = ""
    anno: int = 0
    checksum_ok: bool = True
    divergenze: list[Divergenza] = field(default_factory=list)
    dettaglio: dict = field(default_factory=dict)
