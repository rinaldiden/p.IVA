"""Payment Scheduler — generates F24s and annual payment plan.

Takes Agent3/Agent3b validated results and produces:
- Complete F24 forms with correct tax codes
- Annual payment schedule with deadlines
- Credit compensation across F24s
- Marca da bollo annual payment
"""

from __future__ import annotations

import json
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from .models import F24, F24Entry, PianoAnnuale, ScadenzaFiscale

_SHARED_DIR = Path(__file__).resolve().parent.parent.parent / "shared"


def _round(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _load_json(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _make_f24(
    cf: str,
    nome: str,
    cognome: str,
    data: date,
    scadenza_id: str,
    anno: int,
    righe: list[F24Entry],
    iban: str = "",
    descrizione: str = "",
) -> F24:
    f24 = F24(
        contribuente_cf=cf,
        contribuente_nome=nome,
        contribuente_cognome=cognome,
        data_versamento=data,
        scadenza_id=scadenza_id,
        anno_fiscale=anno,
        righe=righe,
        iban=iban,
        descrizione=descrizione,
    )
    f24.calcola_totali()
    return f24


def genera_piano_annuale(
    contribuente_id: str,
    contribuente_cf: str,
    contribuente_nome: str,
    contribuente_cognome: str,
    anno_fiscale: int,
    gestione_inps: str,
    primo_anno: bool,
    imposta_sostitutiva: Decimal,
    contributo_inps: Decimal,
    acconti_dovuti: Decimal = Decimal("0"),
    acconto_prima_rata: Decimal = Decimal("0"),
    acconto_seconda_rata: Decimal = Decimal("0"),
    da_versare: Decimal = Decimal("0"),
    crediti_precedenti: Decimal = Decimal("0"),
    marche_bollo_totale: Decimal = Decimal("0"),
    iban: str = "",
    contributo_fisso_trimestrale: Decimal = Decimal("0"),
) -> PianoAnnuale:
    """Generate the complete annual payment plan with F24s."""

    piano = PianoAnnuale(
        contribuente_id=contribuente_id,
        anno_fiscale=anno_fiscale,
        marche_bollo_totale=marche_bollo_totale,
    )

    credito_residuo = crediti_precedenti

    # === IMPOSTA SOSTITUTIVA ===

    # Saldo (June 30 of next year for first year, or current year)
    anno_saldo = anno_fiscale + 1 if primo_anno else anno_fiscale
    if da_versare > Decimal("0"):
        saldo_importo = da_versare

        # Apply credit compensation
        if credito_residuo > Decimal("0"):
            compensazione = min(credito_residuo, saldo_importo)
            credito_residuo -= compensazione
            piano.crediti_compensati += compensazione
            saldo_netto = _round(saldo_importo - compensazione)
        else:
            saldo_netto = saldo_importo
            compensazione = Decimal("0")

        righe_saldo = [F24Entry(
            sezione="erario",
            codice_tributo="1792",
            anno_riferimento=anno_fiscale,
            importo_debito=saldo_importo,
            importo_credito=compensazione,
            descrizione="Imposta sostitutiva forfettario — SALDO",
        )]

        f24_saldo = _make_f24(
            cf=contribuente_cf, nome=contribuente_nome, cognome=contribuente_cognome,
            data=date(anno_saldo, 6, 30),
            scadenza_id=f"saldo_imposta_{anno_fiscale}",
            anno=anno_fiscale, righe=righe_saldo, iban=iban,
            descrizione=f"Saldo imposta sostitutiva {anno_fiscale}",
        )
        piano.scadenze.append(ScadenzaFiscale(
            id=f"saldo_imposta_{anno_fiscale}",
            data=date(anno_saldo, 6, 30),
            descrizione=f"Saldo imposta sostitutiva {anno_fiscale}",
            importo=saldo_netto,
            codice_tributo="1792",
            f24=f24_saldo,
        ))

    # Acconti (solo se non primo anno)
    if not primo_anno and acconto_prima_rata > Decimal("0"):
        righe_acc1 = [F24Entry(
            sezione="erario",
            codice_tributo="1790",
            anno_riferimento=anno_fiscale,
            importo_debito=acconto_prima_rata,
            descrizione="Imposta sostitutiva forfettario — ACCONTO 1ª RATA (40%)",
        )]
        f24_acc1 = _make_f24(
            cf=contribuente_cf, nome=contribuente_nome, cognome=contribuente_cognome,
            data=date(anno_fiscale, 6, 30),
            scadenza_id=f"acconto1_imposta_{anno_fiscale}",
            anno=anno_fiscale, righe=righe_acc1, iban=iban,
            descrizione=f"Acconto 1ª rata imposta sostitutiva {anno_fiscale}",
        )
        piano.scadenze.append(ScadenzaFiscale(
            id=f"acconto1_imposta_{anno_fiscale}",
            data=date(anno_fiscale, 6, 30),
            descrizione=f"Acconto 1ª rata imposta sostitutiva (40%)",
            importo=acconto_prima_rata,
            codice_tributo="1790",
            f24=f24_acc1,
        ))

    if not primo_anno and acconto_seconda_rata > Decimal("0"):
        righe_acc2 = [F24Entry(
            sezione="erario",
            codice_tributo="1791",
            anno_riferimento=anno_fiscale,
            importo_debito=acconto_seconda_rata,
            descrizione="Imposta sostitutiva forfettario — ACCONTO 2ª RATA (60%)",
        )]
        f24_acc2 = _make_f24(
            cf=contribuente_cf, nome=contribuente_nome, cognome=contribuente_cognome,
            data=date(anno_fiscale, 11, 30),
            scadenza_id=f"acconto2_imposta_{anno_fiscale}",
            anno=anno_fiscale, righe=righe_acc2, iban=iban,
            descrizione=f"Acconto 2ª rata imposta sostitutiva {anno_fiscale}",
        )
        piano.scadenze.append(ScadenzaFiscale(
            id=f"acconto2_imposta_{anno_fiscale}",
            data=date(anno_fiscale, 11, 30),
            descrizione=f"Acconto 2ª rata imposta sostitutiva (60%)",
            importo=acconto_seconda_rata,
            codice_tributo="1791",
            f24=f24_acc2,
        ))

    # === INPS ===
    if gestione_inps == "separata":
        _aggiungi_inps_separata(piano, contribuente_cf, contribuente_nome,
                                contribuente_cognome, anno_fiscale, contributo_inps,
                                primo_anno, iban)
    elif gestione_inps in ("artigiani", "commercianti"):
        _aggiungi_inps_artigiani(piano, contribuente_cf, contribuente_nome,
                                 contribuente_cognome, anno_fiscale, gestione_inps,
                                 contributo_fisso_trimestrale, contributo_inps,
                                 primo_anno, iban)

    # === MARCA DA BOLLO (versamento annuale) ===
    if marche_bollo_totale > Decimal("0"):
        righe_bollo = [F24Entry(
            sezione="erario",
            codice_tributo="2501",
            anno_riferimento=anno_fiscale,
            importo_debito=marche_bollo_totale,
            descrizione="Imposta di bollo fatture elettroniche — annuale",
        )]
        f24_bollo = _make_f24(
            cf=contribuente_cf, nome=contribuente_nome, cognome=contribuente_cognome,
            data=date(anno_fiscale + 1, 1, 30),
            scadenza_id=f"bollo_{anno_fiscale}",
            anno=anno_fiscale, righe=righe_bollo, iban=iban,
            descrizione=f"Marche da bollo virtuali {anno_fiscale}",
        )
        piano.scadenze.append(ScadenzaFiscale(
            id=f"bollo_{anno_fiscale}",
            data=date(anno_fiscale + 1, 1, 30),
            descrizione=f"Versamento marche da bollo virtuali {anno_fiscale}",
            importo=marche_bollo_totale,
            codice_tributo="2501",
            f24=f24_bollo,
        ))

    # Sort by date
    piano.scadenze.sort(key=lambda s: s.data)

    # Total
    piano.totale_annuo = _round(sum(s.importo for s in piano.scadenze))

    return piano


def _aggiungi_inps_separata(
    piano: PianoAnnuale,
    cf: str, nome: str, cognome: str,
    anno: int, contributo: Decimal,
    primo_anno: bool, iban: str,
) -> None:
    """Add gestione separata INPS payments to the plan."""
    anno_pag = anno + 1 if primo_anno else anno

    # Saldo INPS
    if contributo > Decimal("0"):
        righe = [F24Entry(
            sezione="inps",
            causale_contributo="PXX",
            periodo_da=f"01/{anno}",
            periodo_a=f"12/{anno}",
            importo_debito=contributo,
            descrizione=f"INPS gestione separata — saldo {anno}",
        )]
        f24 = _make_f24(
            cf=cf, nome=nome, cognome=cognome,
            data=date(anno_pag, 6, 30),
            scadenza_id=f"saldo_inps_gs_{anno}",
            anno=anno, righe=righe, iban=iban,
            descrizione=f"Saldo INPS gestione separata {anno}",
        )
        piano.scadenze.append(ScadenzaFiscale(
            id=f"saldo_inps_gs_{anno}",
            data=date(anno_pag, 6, 30),
            descrizione=f"Saldo INPS gestione separata {anno}",
            importo=contributo,
            causale="PXX",
            f24=f24,
        ))

    # Acconti (solo anno successivo, non primo anno)
    if not primo_anno:
        acc1 = _round(contributo * Decimal("0.40"))
        acc2 = _round(contributo * Decimal("0.60"))

        if acc1 > Decimal("0"):
            piano.scadenze.append(ScadenzaFiscale(
                id=f"acconto1_inps_gs_{anno}",
                data=date(anno, 6, 30),
                descrizione="Acconto 1ª rata INPS gest. separata (40%)",
                importo=acc1,
                causale="PXX",
            ))
        if acc2 > Decimal("0"):
            piano.scadenze.append(ScadenzaFiscale(
                id=f"acconto2_inps_gs_{anno}",
                data=date(anno, 11, 30),
                descrizione="Acconto 2ª rata INPS gest. separata (60%)",
                importo=acc2,
                causale="PXX",
            ))


def _aggiungi_inps_artigiani(
    piano: PianoAnnuale,
    cf: str, nome: str, cognome: str,
    anno: int, gestione: str,
    fisso_trim: Decimal, contributo_totale: Decimal,
    primo_anno: bool, iban: str,
) -> None:
    """Add artigiani/commercianti INPS payments (quarterly fixed + variable)."""
    causale_fisso = "AF" if gestione == "artigiani" else "CF"
    scadenze_trim = [
        (date(anno, 2, 16), "Q1"),
        (date(anno, 5, 16), "Q2"),
        (date(anno, 8, 20), "Q3"),
        (date(anno, 11, 16), "Q4"),
    ]

    for data_scad, trimestre in scadenze_trim:
        if fisso_trim > Decimal("0"):
            piano.scadenze.append(ScadenzaFiscale(
                id=f"inps_{gestione}_fisso_{trimestre}_{anno}",
                data=data_scad,
                descrizione=f"INPS {gestione} — rata fissa {trimestre}",
                importo=fisso_trim,
                causale=causale_fisso,
            ))

    # Eccedenza minimale (saldo)
    eccedenza = _round(contributo_totale - (fisso_trim * 4))
    if eccedenza > Decimal("0"):
        causale_ecc = "APR" if gestione == "artigiani" else "CPR"
        piano.scadenze.append(ScadenzaFiscale(
            id=f"inps_{gestione}_eccedenza_{anno}",
            data=date(anno + 1, 6, 30),
            descrizione=f"INPS {gestione} — eccedenza minimale {anno}",
            importo=eccedenza,
            causale=causale_ecc,
        ))
