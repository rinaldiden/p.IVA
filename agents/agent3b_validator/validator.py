"""Agent3b — Independent deterministic validator for fiscal calculations.

Completely independent from Agent3. Zero imports from agents/agent3_calculator/.
Same fiscal logic, different implementation, different variable names.
If Agent3 and Agent3b produce different results, something is wrong.
"""

from __future__ import annotations

import hashlib
import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from .models import Divergenza, EsitoValidazione, InputFiscale

# Paths to shared data (same source files, independent loading)
_DATA_ROOT = Path(__file__).resolve().parent.parent.parent / "shared"
_COEFFICIENTI_PATH = _DATA_ROOT / "ateco_coefficients.json"
_PARAMETRI_INPS_PATH = _DATA_ROOT / "inps_rates.json"


def _carica_json(percorso: Path) -> dict[str, Any]:
    with open(percorso, encoding="utf-8") as fh:
        return json.load(fh)


def _cerca_coefficiente(codice: str) -> Decimal:
    """Find coefficient for ATECO code. Independent implementation."""
    dati = _carica_json(_COEFFICIENTI_PATH)
    tabella = dati["coefficients"]

    # Ricerca esatta
    if codice in tabella:
        return Decimal(tabella[codice]["coefficient"])

    # Ricerca per prefisso
    for chiave, voce in tabella.items():
        if chiave.startswith(codice) or codice.startswith(chiave):
            return Decimal(voce["coefficient"])

    # Ricerca per divisione (range)
    divisione = int(codice.split(".")[0])
    tabella_range = dati.get("range_fallback", {})
    for intervallo, voce in tabella_range.items():
        if intervallo.startswith("_"):
            continue
        estremi = intervallo.split("-")
        if len(estremi) == 2:
            if int(estremi[0]) <= divisione <= int(estremi[1]):
                return Decimal(voce["coefficient"])
        elif int(estremi[0]) == divisione:
            return Decimal(voce["coefficient"])

    raise ValueError(f"Coefficiente ATECO non trovato: {codice}")


def _parametri_previdenziali(anno: int, tipo: str) -> dict[str, Any]:
    """Load INPS parameters. Independent implementation."""
    dati = _carica_json(_PARAMETRI_INPS_PATH)
    chiave_anno = str(anno)

    if chiave_anno not in dati:
        raise ValueError(f"Parametri INPS non disponibili per anno {anno}")

    sezione = dati[chiave_anno]
    # Map short name to JSON key (e.g. "separata" → "gestione_separata")
    tipo_chiave = f"gestione_{tipo}" if tipo == "separata" else tipo
    if tipo_chiave not in sezione:
        raise ValueError(f"Tipo gestione INPS sconosciuto: {tipo}")
    tipo = tipo_chiave

    parametri = sezione[tipo]
    for k, v in parametri.items():
        if not k.startswith("_") and v is None:
            raise ValueError(
                f"Parametro INPS '{k}' per {tipo}/{anno} è nullo. "
                f"Aggiornare shared/inps_rates.json."
            )

    return parametri


def _arrotonda(importo: Decimal) -> Decimal:
    return importo.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _calcola_hash(
    id_contrib: str,
    anno: int,
    reddito_imp: Decimal,
    imposta: Decimal,
    versare: Decimal,
    credito_futuro: Decimal,
) -> str:
    stringa = (
        f"{id_contrib}|{anno}|{reddito_imp}|"
        f"{imposta}|{versare}|{credito_futuro}"
    )
    return hashlib.sha256(stringa.encode("utf-8")).hexdigest()


def _ricalcola(dati_in: InputFiscale) -> dict[str, Decimal]:
    """Independent recalculation of all fiscal figures."""
    risultato: dict[str, Decimal] = {}

    # --- Reddito per ATECO ---
    somma_reddito = Decimal("0")
    for cod_ateco, importo_ricavi in dati_in.ricavi_per_ateco.items():
        coeff = _cerca_coefficiente(cod_ateco)
        reddito_singolo = _arrotonda(importo_ricavi * coeff)
        somma_reddito += reddito_singolo

    risultato["reddito_lordo"] = _arrotonda(somma_reddito)

    # --- Deduzione INPS ---
    risultato["reddito_imponibile"] = _arrotonda(
        max(Decimal("0"), risultato["reddito_lordo"] - dati_in.inps_gia_versati)
    )

    # --- Imposta sostitutiva ---
    tasso = Decimal("0.05") if dati_in.aliquota_agevolata else Decimal("0.15")
    risultato["aliquota"] = tasso
    risultato["imposta_sostitutiva"] = _arrotonda(
        risultato["reddito_imponibile"] * tasso
    )

    # --- Acconti ---
    if dati_in.is_primo_anno:
        risultato["acconti_dovuti"] = Decimal("0")
        risultato["acconto_prima_rata"] = Decimal("0")
        risultato["acconto_seconda_rata"] = Decimal("0")
    else:
        risultato["acconti_dovuti"] = _arrotonda(
            dati_in.imposta_anno_prima * Decimal("1.00")
        )
        risultato["acconto_prima_rata"] = _arrotonda(
            dati_in.imposta_anno_prima * Decimal("0.40")
        )
        risultato["acconto_seconda_rata"] = _arrotonda(
            dati_in.imposta_anno_prima * Decimal("0.60")
        )

    # --- Saldo ---
    saldo_netto = (
        risultato["imposta_sostitutiva"]
        - dati_in.acconti_gia_versati
        - dati_in.crediti_da_prima
    )
    risultato["saldo"] = _arrotonda(saldo_netto)

    if risultato["saldo"] < Decimal("0"):
        risultato["credito_anno_prossimo"] = _arrotonda(abs(risultato["saldo"]))
        risultato["da_versare"] = Decimal("0")
    else:
        risultato["credito_anno_prossimo"] = Decimal("0")
        risultato["da_versare"] = risultato["saldo"]

    # --- INPS ---
    par = _parametri_previdenziali(dati_in.anno, dati_in.tipo_gestione_inps)

    if dati_in.tipo_gestione_inps == "separata":
        aliq_inps = Decimal(par["aliquota"])
        risultato["contributo_inps"] = _arrotonda(
            risultato["reddito_imponibile"] * aliq_inps
        )
    elif dati_in.tipo_gestione_inps in ("artigiani", "commercianti"):
        fisso = Decimal(par["contributo_fisso_annuo"])
        soglia_min = Decimal(par["minimale_annuo"])
        aliq_ecc = Decimal(par["aliquota_eccedenza"])

        parte_variabile = _arrotonda(
            max(Decimal("0"), risultato["reddito_imponibile"] - soglia_min) * aliq_ecc
        )
        totale_inps = _arrotonda(fisso + parte_variabile)

        if dati_in.ha_riduzione_35:
            totale_inps = _arrotonda(totale_inps * Decimal("0.65"))

        risultato["contributo_inps"] = totale_inps

    # --- Checksum ---
    risultato["checksum"] = _calcola_hash(
        dati_in.id_contribuente,
        dati_in.anno,
        risultato["reddito_imponibile"],
        risultato["imposta_sostitutiva"],
        risultato["da_versare"],
        risultato["credito_anno_prossimo"],
    )

    return risultato


def validate(
    input_fiscale: InputFiscale,
    result_agent3: dict[str, Any],
) -> EsitoValidazione:
    """Validate Agent3's results by independent recalculation.

    Compares field by field with ZERO tolerance.
    Even 0.01€ difference → full block.
    """
    esito = EsitoValidazione(
        valid=True,
        blocco=False,
        contribuente_id=input_fiscale.id_contribuente,
        anno=input_fiscale.anno,
    )

    # Recalculate independently
    ricalcolo = _ricalcola(input_fiscale)

    # Field mapping: agent3_key → agent3b_key
    confronti = {
        "reddito_lordo": "reddito_lordo",
        "reddito_imponibile": "reddito_imponibile",
        "imposta_sostitutiva": "imposta_sostitutiva",
        "acconti_dovuti": "acconti_dovuti",
        "acconto_prima_rata": "acconto_prima_rata",
        "acconto_seconda_rata": "acconto_seconda_rata",
        "da_versare": "da_versare",
        "credito_anno_prossimo": "credito_anno_prossimo",
        "contributo_inps_calcolato": "contributo_inps",
    }

    for chiave_a3, chiave_a3b in confronti.items():
        val_a3 = Decimal(str(result_agent3.get(chiave_a3, "0")))
        val_a3b = ricalcolo.get(chiave_a3b, Decimal("0"))

        if isinstance(val_a3b, str):
            val_a3b = Decimal(val_a3b)

        if val_a3 != val_a3b:
            delta = val_a3 - val_a3b
            esito.divergenze.append(
                Divergenza(
                    campo=chiave_a3,
                    valore_agent3=str(val_a3),
                    valore_agent3b=str(val_a3b),
                    delta=str(delta),
                )
            )

    # Verify checksum
    checksum_a3 = result_agent3.get("checksum", "")
    checksum_a3b = ricalcolo.get("checksum", "")
    if isinstance(checksum_a3b, Decimal):
        checksum_a3b = str(checksum_a3b)

    if checksum_a3 != checksum_a3b:
        esito.checksum_ok = False

    # Any divergence = block
    if esito.divergenze or not esito.checksum_ok:
        esito.valid = False
        esito.blocco = True

    esito.dettaglio = {
        "ricalcolo_agent3b": {k: str(v) for k, v in ricalcolo.items()},
        "checksum_agent3": checksum_a3,
        "checksum_agent3b": checksum_a3b,
    }

    return esito
