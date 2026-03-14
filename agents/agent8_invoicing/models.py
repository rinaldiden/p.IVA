"""Data models for Agent8 Invoicing."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass
class DatiCliente:
    denominazione: str
    partita_iva: str = ""
    codice_fiscale: str = ""
    indirizzo: str = ""
    cap: str = ""
    comune: str = ""
    provincia: str = ""
    nazione: str = "IT"
    codice_sdi: str = "0000000"  # default: cassetto fiscale
    pec: str = ""
    # PA fields
    is_pa: bool = False
    codice_ufficio_pa: str = ""
    cig: str = ""
    cup: str = ""


@dataclass
class LineaFattura:
    numero_linea: int
    descrizione: str
    quantita: Decimal = Decimal("1")
    prezzo_unitario: Decimal = Decimal("0")
    aliquota_iva: Decimal = Decimal("0")
    natura: str = "N2.2"  # Non soggetto IVA - forfettario

    @property
    def prezzo_totale(self) -> Decimal:
        return (self.quantita * self.prezzo_unitario).quantize(Decimal("0.01"))


@dataclass
class Fattura:
    """Fattura elettronica forfettario."""
    numero: str  # e.g. "2024/001"
    data: date
    anno: int

    # Soggetti
    cedente_piva: str
    cedente_cf: str
    cedente_denominazione: str
    cedente_indirizzo: str = ""
    cedente_cap: str = ""
    cedente_comune: str = ""
    cedente_provincia: str = ""
    cliente: DatiCliente = field(default_factory=DatiCliente)

    # Linee
    linee: list[LineaFattura] = field(default_factory=list)

    # Rivalsa INPS 4%
    rivalsa_inps_4: bool = False
    importo_rivalsa: Decimal = Decimal("0")

    # Bollo
    bollo_applicato: bool = False
    importo_bollo: Decimal = Decimal("2.00")

    # Totali
    imponibile: Decimal = Decimal("0")
    totale_documento: Decimal = Decimal("0")

    # Dicitura obbligatoria
    dicitura_forfettario: str = (
        "Operazione effettuata ai sensi dell'art. 1, commi da 54 a 89, "
        "della Legge n. 190/2014 — Regime forfettario. "
        "Operazione senza applicazione dell'IVA ai sensi dell'art. 1, "
        "comma 58, Legge 190/2014. "
        "Si richiede la non applicazione della ritenuta alla fonte a titolo "
        "d'acconto ai sensi dell'art. 1, comma 67, Legge 190/2014."
    )

    # SDI
    regime_fiscale: str = "RF19"
    formato_trasmissione: str = "FPR12"  # FPA12 per PA
    stato_sdi: str = "da_inviare"  # da_inviare, inviata, consegnata, scartata, ...
    esito_sdi: str = ""

    # Pagamento
    modalita_pagamento: str = "MP05"  # bonifico
    iban: str = ""
    scadenza_pagamento: date | None = None

    @property
    def ricavo_netto(self) -> Decimal:
        """Ricavo ai fini forfettario (senza rivalsa e senza bollo)."""
        return self.imponibile


@dataclass
class NotaCredito:
    """Nota di credito (tipo documento TD04)."""
    numero: str
    data: date
    fattura_riferimento: str  # numero fattura originale
    data_fattura_riferimento: date
    importo: Decimal
    descrizione: str
    cliente: DatiCliente = field(default_factory=DatiCliente)


@dataclass
class EsitoSDI:
    """Esito ricevuto da SDI."""
    fattura_numero: str
    codice: str  # RC, MC, NS, EC, AT
    descrizione: str = ""
    codice_errore: str = ""
    data_ricezione: date = field(default_factory=date.today)
    azione_automatica: str = ""
    richiede_intervento: bool = False
