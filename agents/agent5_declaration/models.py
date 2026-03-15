"""Data models for Agent5 Declaration Generator."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass
class AtecoLM:
    """Single ATECO entry for Quadro LM rows LM23-26."""

    codice_ateco: str
    ricavi: Decimal = Decimal("0")
    coefficiente_redditivita: Decimal = Decimal("0")
    reddito_lordo: Decimal = Decimal("0")


@dataclass
class QuadroLM:
    """Quadro LM — Regime forfettario section of Modello Redditi PF.

    Fields map to official Modello Redditi PF line numbers.
    """

    # LM21 — Totale ricavi/compensi
    lm21_ricavi_totali: Decimal = Decimal("0")

    # LM22 — Codice attivita ATECO principale
    lm22_codice_ateco_principale: str = ""

    # LM23-26 — Dettaglio per ATECO
    dettaglio_ateco: list[AtecoLM] = field(default_factory=list)

    # LM27 — Totale reddito lordo
    lm27_reddito_lordo: Decimal = Decimal("0")

    # LM28 — Contributi previdenziali versati (deduzione INPS)
    lm28_contributi_previdenziali: Decimal = Decimal("0")

    # LM29 — Reddito netto (LM27 - LM28, min 0)
    lm29_reddito_netto: Decimal = Decimal("0")

    # LM30 — Perdite pregresse utilizzate
    lm30_perdite_pregresse: Decimal = Decimal("0")

    # LM31 — Reddito al netto delle perdite
    lm31_reddito_al_netto_perdite: Decimal = Decimal("0")

    # LM32 — Reddito imponibile
    lm32_reddito_imponibile: Decimal = Decimal("0")

    # LM33 — Aliquota imposta sostitutiva (5% o 15%)
    lm33_aliquota: Decimal = Decimal("0")

    # LM34 — Imposta dovuta
    lm34_imposta_dovuta: Decimal = Decimal("0")

    # LM35 — Acconti versati
    lm35_acconti_versati: Decimal = Decimal("0")

    # LM36 — Ritenute d'acconto subite
    lm36_ritenute: Decimal = Decimal("0")

    # LM37 — Eccedenze da precedente dichiarazione
    lm37_eccedenze_precedenti: Decimal = Decimal("0")

    # LM38 — Imposta a debito (positivo) o credito (negativo)
    lm38_imposta_netta: Decimal = Decimal("0")


@dataclass
class SezioneINPS:
    """Single INPS section in Quadro RR."""

    tipo_gestione: str  # "gestione_separata", "artigiani", "commercianti"
    base_imponibile: Decimal = Decimal("0")
    aliquota: Decimal = Decimal("0")
    contributi_dovuti: Decimal = Decimal("0")
    contributi_fissi: Decimal = Decimal("0")
    contributi_eccedenza: Decimal = Decimal("0")
    acconti_versati: Decimal = Decimal("0")
    saldo: Decimal = Decimal("0")
    riduzione_35: bool = False


@dataclass
class QuadroRR:
    """Quadro RR — Contributi previdenziali INPS."""

    # Sezione I: Gestione artigiani/commercianti
    sezione_i: SezioneINPS | None = None

    # Sezione II: Gestione separata
    sezione_ii: SezioneINPS | None = None

    totale_contributi_dovuti: Decimal = Decimal("0")
    totale_acconti: Decimal = Decimal("0")
    totale_saldo: Decimal = Decimal("0")


@dataclass
class Declaration:
    """Complete Modello Redditi PF declaration for forfettario."""

    anno_fiscale: int
    contribuente_id: str
    quadro_lm: QuadroLM = field(default_factory=QuadroLM)
    quadro_rr: QuadroRR = field(default_factory=QuadroRR)
    riepilogo: dict = field(default_factory=dict)
    status: str = "bozza"  # bozza, compilata, validata, inviata, errore
    errors: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        now = datetime.utcnow().isoformat()
        if not self.created_at:
            self.created_at = now
        self.updated_at = now


@dataclass
class SubmitResult:
    """Result of declaration submission."""

    success: bool
    protocol_number: str = ""
    timestamp: str = ""
    dry_run: bool = True
    errors: list[str] = field(default_factory=list)
