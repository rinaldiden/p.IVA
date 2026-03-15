"""Agent5 — Declaration Generator (Dichiarazione dei Redditi).

Compila Modello Redditi PF con Quadro LM (regime forfettario, multi-ATECO)
e Quadro RR (contributi INPS).

Pure Python, deterministic. Uses Agent3 calculator for tax computation.
Submission is dry-run only (# EXTERNAL: intermediario abilitato).
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from agents.agent3_calculator.calculator import calcola
from agents.agent3_calculator.models import ContribuenteInput

from .models import (
    AtecoLM,
    Declaration,
    QuadroLM,
    QuadroRR,
    SezioneINPS,
    SubmitResult,
)

logger = logging.getLogger(__name__)

_SHARED_DIR = Path(__file__).resolve().parent.parent.parent / "shared"
_INPS_FILE = _SHARED_DIR / "inps_rates.json"


def _load_json(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _round_euro(amount: Decimal) -> Decimal:
    """Round to 2 decimal places using standard rounding."""
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _extract_ateco_ricavi(profile: dict, anno: int) -> dict[str, Decimal]:
    """Extract per-ATECO revenue from profile fatture for the given year."""
    anagrafica = profile.get("anagrafica", {})
    fatture = profile.get("fatture", [])

    # Aggregate revenue by ATECO from invoices
    ricavi_per_ateco: dict[str, Decimal] = {}
    ateco_principale = anagrafica.get("ateco_principale", "")

    for fattura in fatture:
        anno_fattura = fattura.get("anno", 0)
        if anno_fattura != anno:
            continue

        importo = Decimal(str(fattura.get("imponibile", fattura.get("importo", "0"))))
        codice_ateco = fattura.get("codice_ateco", ateco_principale)

        if codice_ateco:
            ricavi_per_ateco[codice_ateco] = (
                ricavi_per_ateco.get(codice_ateco, Decimal("0")) + importo
            )

    # If no invoices found but profile has direct ricavi data, use that
    if not ricavi_per_ateco:
        ricavi_diretti = profile.get("ricavi_per_ateco", {})
        for ateco, importo in ricavi_diretti.items():
            ricavi_per_ateco[ateco] = Decimal(str(importo))

    return ricavi_per_ateco


def _extract_contributi_versati(profile: dict, anno: int) -> Decimal:
    """Extract total INPS contributions paid during the year."""
    spese = profile.get("spese", [])
    totale = Decimal("0")

    for spesa in spese:
        if spesa.get("anno", 0) != anno:
            continue
        if spesa.get("tipo", "").lower() in ("inps", "contributi_inps", "previdenza"):
            totale += Decimal(str(spesa.get("importo", "0")))

    # Fallback: direct field in profile
    if totale == Decimal("0"):
        totale = Decimal(str(profile.get("contributi_inps_versati", "0")))

    return totale


def _build_contribuente_input(
    profile: dict, anno: int
) -> ContribuenteInput:
    """Build Agent3 ContribuenteInput from a profile dict."""
    anagrafica = profile.get("anagrafica", {})
    ricavi = _extract_ateco_ricavi(profile, anno)

    if not ricavi:
        raise ValueError(
            f"Nessun ricavo trovato per l'anno {anno}. "
            "Verificare fatture o ricavi_per_ateco nel profilo."
        )

    contributi_versati = _extract_contributi_versati(profile, anno)

    return ContribuenteInput(
        contribuente_id=profile.get("contribuente_id", anagrafica.get("codice_fiscale", "")),
        anno_fiscale=anno,
        primo_anno=anagrafica.get("primo_anno", False),
        ateco_ricavi=ricavi,
        rivalsa_inps_applicata=Decimal(str(profile.get("rivalsa_inps_applicata", "0"))),
        regime_agevolato=anagrafica.get("regime_agevolato", True),
        gestione_inps=anagrafica.get("gestione_inps", "separata"),
        riduzione_inps_35=anagrafica.get("riduzione_inps_35", False),
        contributi_inps_versati=contributi_versati,
        imposta_anno_precedente=Decimal(str(profile.get("imposta_anno_precedente", "0"))),
        acconti_versati=Decimal(str(profile.get("acconti_versati", "0"))),
        crediti_precedenti=Decimal(str(profile.get("crediti_precedenti", "0"))),
    )


def compile_quadro_lm(profile: dict, anno: int) -> QuadroLM:
    """Compile Quadro LM (regime forfettario) using Agent3 calculator.

    This is the core section for forfettario contributors.
    """
    input_data = _build_contribuente_input(profile, anno)
    result = calcola(input_data)

    lm = QuadroLM()

    # LM21 — Totale ricavi
    lm.lm21_ricavi_totali = sum(
        d.ricavi for d in result.dettaglio_ateco
    )

    # LM22 — Codice ATECO principale
    anagrafica = profile.get("anagrafica", {})
    lm.lm22_codice_ateco_principale = anagrafica.get("ateco_principale", "")

    # LM23-26 — Dettaglio per ATECO
    for det in result.dettaglio_ateco:
        lm.dettaglio_ateco.append(
            AtecoLM(
                codice_ateco=det.codice_ateco,
                ricavi=det.ricavi,
                coefficiente_redditivita=det.coefficiente,
                reddito_lordo=det.reddito,
            )
        )

    # LM27 — Totale reddito lordo
    lm.lm27_reddito_lordo = result.reddito_lordo

    # LM28 — Contributi previdenziali dedotti
    lm.lm28_contributi_previdenziali = result.contributi_inps_dedotti

    # LM29 — Reddito netto
    lm.lm29_reddito_netto = result.reddito_imponibile

    # LM30 — Perdite pregresse
    perdite = Decimal(str(profile.get("perdite_pregresse", "0")))
    lm.lm30_perdite_pregresse = min(perdite, result.reddito_imponibile)

    # LM31 — Reddito al netto delle perdite
    lm.lm31_reddito_al_netto_perdite = _round_euro(
        max(Decimal("0"), result.reddito_imponibile - lm.lm30_perdite_pregresse)
    )

    # LM32 — Reddito imponibile (same as LM31 for forfettario)
    lm.lm32_reddito_imponibile = lm.lm31_reddito_al_netto_perdite

    # LM33 — Aliquota
    lm.lm33_aliquota = result.aliquota

    # LM34 — Imposta dovuta
    lm.lm34_imposta_dovuta = _round_euro(
        lm.lm32_reddito_imponibile * lm.lm33_aliquota
    )

    # LM35 — Acconti versati
    lm.lm35_acconti_versati = result.acconti_versati

    # LM36 — Ritenute d'acconto subite
    lm.lm36_ritenute = Decimal(str(profile.get("ritenute_subite", "0")))

    # LM37 — Eccedenze da precedente dichiarazione
    lm.lm37_eccedenze_precedenti = result.crediti_precedenti

    # LM38 — Imposta a debito/credito
    lm.lm38_imposta_netta = _round_euro(
        lm.lm34_imposta_dovuta
        - lm.lm35_acconti_versati
        - lm.lm36_ritenute
        - lm.lm37_eccedenze_precedenti
    )

    return lm


def compile_quadro_rr(profile: dict, anno: int) -> QuadroRR:
    """Compile Quadro RR (contributi INPS) loading rates from shared data."""
    anagrafica = profile.get("anagrafica", {})
    gestione = anagrafica.get("gestione_inps", "separata")

    input_data = _build_contribuente_input(profile, anno)
    result = calcola(input_data)

    rr = QuadroRR()

    # Load INPS rates
    inps_data = _load_json(_INPS_FILE)
    anno_str = str(anno)

    if anno_str not in inps_data:
        logger.warning("INPS rates not available for year %d, using calculator result", anno)
        # Fallback to calculator result
        sezione = SezioneINPS(
            tipo_gestione=gestione,
            base_imponibile=result.reddito_imponibile,
            contributi_dovuti=result.contributo_inps_calcolato,
            saldo=result.contributo_inps_calcolato,
        )
        if gestione == "separata":
            rr.sezione_ii = sezione
        else:
            rr.sezione_i = sezione

        rr.totale_contributi_dovuti = result.contributo_inps_calcolato
        rr.totale_saldo = result.contributo_inps_calcolato
        return rr

    # Map gestione key
    gestione_key = f"gestione_{gestione}" if gestione == "separata" else gestione
    rates = inps_data[anno_str].get(gestione_key, {})

    acconti_inps = Decimal(str(profile.get("acconti_inps_versati", "0")))

    if gestione == "separata":
        aliquota = Decimal(str(rates.get("aliquota", "0.2607")))
        contributi_dovuti = _round_euro(result.reddito_imponibile * aliquota)
        saldo_inps = _round_euro(contributi_dovuti - acconti_inps)

        rr.sezione_ii = SezioneINPS(
            tipo_gestione="gestione_separata",
            base_imponibile=result.reddito_imponibile,
            aliquota=aliquota,
            contributi_dovuti=contributi_dovuti,
            acconti_versati=acconti_inps,
            saldo=saldo_inps,
        )

    elif gestione in ("artigiani", "commercianti"):
        contributo_fisso = Decimal(str(rates.get("contributo_fisso_annuo", "0")))
        minimale = Decimal(str(rates.get("minimale_annuo", "0")))
        aliquota_ecc = Decimal(str(rates.get("aliquota_eccedenza", "0")))

        eccedenza = max(Decimal("0"), result.reddito_imponibile - minimale)
        contributo_variabile = _round_euro(eccedenza * aliquota_ecc)
        totale = _round_euro(contributo_fisso + contributo_variabile)

        riduzione = anagrafica.get("riduzione_inps_35", False)
        if riduzione:
            totale = _round_euro(totale * Decimal("0.65"))

        saldo_inps = _round_euro(totale - acconti_inps)

        rr.sezione_i = SezioneINPS(
            tipo_gestione=gestione,
            base_imponibile=result.reddito_imponibile,
            aliquota=aliquota_ecc,
            contributi_dovuti=totale,
            contributi_fissi=contributo_fisso,
            contributi_eccedenza=contributo_variabile,
            acconti_versati=acconti_inps,
            saldo=saldo_inps,
            riduzione_35=riduzione,
        )

    rr.totale_contributi_dovuti = (
        (rr.sezione_i.contributi_dovuti if rr.sezione_i else Decimal("0"))
        + (rr.sezione_ii.contributi_dovuti if rr.sezione_ii else Decimal("0"))
    )
    rr.totale_acconti = acconti_inps
    rr.totale_saldo = _round_euro(rr.totale_contributi_dovuti - acconti_inps)

    return rr


def generate_declaration(profile: dict, anno_fiscale: int) -> Declaration:
    """Generate complete Modello Redditi PF declaration for forfettario.

    This is the main entry point for Agent5.
    Calls Agent3 calculator internally for tax computation.

    Args:
        profile: Contribuente profile with anagrafica, fatture, spese.
        anno_fiscale: Fiscal year to declare.

    Returns:
        Complete Declaration with Quadro LM and Quadro RR.
    """
    anagrafica = profile.get("anagrafica", {})
    contribuente_id = profile.get(
        "contribuente_id",
        anagrafica.get("codice_fiscale", "UNKNOWN"),
    )

    declaration = Declaration(
        anno_fiscale=anno_fiscale,
        contribuente_id=contribuente_id,
    )

    try:
        # Compile Quadro LM
        declaration.quadro_lm = compile_quadro_lm(profile, anno_fiscale)

        # Compile Quadro RR
        declaration.quadro_rr = compile_quadro_rr(profile, anno_fiscale)

        # Generate summary
        declaration.riepilogo = genera_riepilogo(declaration)

        # Validate
        validation_errors = validate_declaration(declaration)
        if validation_errors:
            declaration.errors = validation_errors
            declaration.status = "errore"
        else:
            declaration.status = "compilata"

    except Exception as exc:
        logger.error("Error generating declaration: %s", exc)
        declaration.errors.append(str(exc))
        declaration.status = "errore"

    declaration.updated_at = datetime.now(timezone.utc).isoformat()
    return declaration


def genera_riepilogo(declaration: Declaration) -> dict:
    """Generate a human-readable summary of the declaration.

    Returns a flat dict suitable for display to the user.
    """
    lm = declaration.quadro_lm
    rr = declaration.quadro_rr

    riepilogo = {
        "anno_fiscale": declaration.anno_fiscale,
        "contribuente_id": declaration.contribuente_id,
        "status": declaration.status,
        # Quadro LM summary
        "ricavi_totali": str(lm.lm21_ricavi_totali),
        "numero_ateco": len(lm.dettaglio_ateco),
        "ateco_principale": lm.lm22_codice_ateco_principale,
        "reddito_lordo": str(lm.lm27_reddito_lordo),
        "contributi_inps_dedotti": str(lm.lm28_contributi_previdenziali),
        "reddito_netto": str(lm.lm29_reddito_netto),
        "perdite_pregresse_usate": str(lm.lm30_perdite_pregresse),
        "reddito_imponibile": str(lm.lm32_reddito_imponibile),
        "aliquota_imposta": str(lm.lm33_aliquota),
        "imposta_dovuta": str(lm.lm34_imposta_dovuta),
        "acconti_versati": str(lm.lm35_acconti_versati),
        "ritenute": str(lm.lm36_ritenute),
        "eccedenze_precedenti": str(lm.lm37_eccedenze_precedenti),
        "imposta_netta": str(lm.lm38_imposta_netta),
        # Quadro RR summary
        "inps_contributi_dovuti": str(rr.totale_contributi_dovuti),
        "inps_acconti_versati": str(rr.totale_acconti),
        "inps_saldo": str(rr.totale_saldo),
        # Totale da versare / a credito
        "totale_imposte_e_contributi": str(
            _round_euro(lm.lm38_imposta_netta + rr.totale_saldo)
        ),
    }

    # Dettaglio ATECO
    for i, ateco in enumerate(lm.dettaglio_ateco):
        prefix = f"ateco_{i + 1}"
        riepilogo[f"{prefix}_codice"] = ateco.codice_ateco
        riepilogo[f"{prefix}_ricavi"] = str(ateco.ricavi)
        riepilogo[f"{prefix}_coefficiente"] = str(ateco.coefficiente_redditivita)
        riepilogo[f"{prefix}_reddito_lordo"] = str(ateco.reddito_lordo)

    if declaration.errors:
        riepilogo["errori"] = declaration.errors

    return riepilogo


def validate_declaration(declaration: Declaration) -> list[str]:
    """Pre-submit validation checks on the declaration.

    Returns a list of error strings. Empty list = valid.
    """
    errors: list[str] = []
    lm = declaration.quadro_lm
    rr = declaration.quadro_rr

    # Basic completeness
    if not declaration.contribuente_id or declaration.contribuente_id == "UNKNOWN":
        errors.append("Contribuente ID mancante")

    if declaration.anno_fiscale < 2015:
        errors.append(
            f"Anno fiscale {declaration.anno_fiscale} non valido "
            "(regime forfettario dal 2015)"
        )

    # Quadro LM checks
    if lm.lm21_ricavi_totali <= Decimal("0"):
        errors.append("LM21: ricavi totali devono essere > 0")

    if lm.lm21_ricavi_totali > Decimal("85000"):
        errors.append(
            f"LM21: ricavi totali {lm.lm21_ricavi_totali} superano soglia 85.000 EUR. "
            "Verificare permanenza nel regime forfettario."
        )

    if not lm.lm22_codice_ateco_principale:
        errors.append("LM22: codice ATECO principale mancante")

    if not lm.dettaglio_ateco:
        errors.append("LM23-26: nessun dettaglio ATECO presente")

    # Verify LM27 = sum of ATECO redditi
    somma_redditi = sum(a.reddito_lordo for a in lm.dettaglio_ateco)
    if lm.lm27_reddito_lordo != somma_redditi:
        errors.append(
            f"LM27: reddito lordo {lm.lm27_reddito_lordo} != "
            f"somma ATECO {somma_redditi}"
        )

    # Verify LM29 = LM27 - LM28 (min 0)
    expected_lm29 = _round_euro(max(Decimal("0"), lm.lm27_reddito_lordo - lm.lm28_contributi_previdenziali))
    if lm.lm29_reddito_netto != expected_lm29:
        errors.append(
            f"LM29: reddito netto {lm.lm29_reddito_netto} != "
            f"atteso {expected_lm29} (LM27 - LM28)"
        )

    # Verify aliquota is valid
    if lm.lm33_aliquota not in (Decimal("0.05"), Decimal("0.15")):
        errors.append(
            f"LM33: aliquota {lm.lm33_aliquota} non valida "
            "(deve essere 0.05 o 0.15)"
        )

    # LM34 check
    expected_lm34 = _round_euro(lm.lm32_reddito_imponibile * lm.lm33_aliquota)
    if lm.lm34_imposta_dovuta != expected_lm34:
        errors.append(
            f"LM34: imposta dovuta {lm.lm34_imposta_dovuta} != "
            f"attesa {expected_lm34}"
        )

    # Quadro RR checks
    if rr.sezione_i is None and rr.sezione_ii is None:
        errors.append("Quadro RR: nessuna sezione INPS compilata")

    if rr.totale_contributi_dovuti < Decimal("0"):
        errors.append("Quadro RR: contributi dovuti negativi")

    return errors


def submit_declaration(declaration: Declaration) -> SubmitResult:
    """Submit the declaration via intermediario abilitato.

    # EXTERNAL: This would connect to the intermediario's platform
    # for telematic submission to Agenzia delle Entrate.
    # Currently operates in dry-run mode.

    Args:
        declaration: Compiled and validated declaration.

    Returns:
        SubmitResult with protocol number (dry-run).
    """
    # Pre-flight validation
    validation_errors = validate_declaration(declaration)
    if validation_errors:
        return SubmitResult(
            success=False,
            errors=validation_errors,
            dry_run=True,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    if declaration.status == "errore":
        return SubmitResult(
            success=False,
            errors=declaration.errors or ["Dichiarazione in stato di errore"],
            dry_run=True,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    # Generate a deterministic protocol number for dry-run
    payload = (
        f"{declaration.contribuente_id}|{declaration.anno_fiscale}|"
        f"{declaration.quadro_lm.lm34_imposta_dovuta}"
    )
    proto_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16].upper()
    protocol_number = f"DRY-{declaration.anno_fiscale}-{proto_hash}"

    now = datetime.now(timezone.utc).isoformat()

    # # EXTERNAL: here we would call the intermediario API
    # response = intermediario.submit(declaration_xml, firma_digitale)
    logger.info(
        "DRY RUN: Declaration %s/%d submitted with protocol %s",
        declaration.contribuente_id,
        declaration.anno_fiscale,
        protocol_number,
    )

    declaration.status = "inviata"
    declaration.updated_at = now

    return SubmitResult(
        success=True,
        protocol_number=protocol_number,
        timestamp=now,
        dry_run=True,
    )
