"""FiscalSimulator — wraps Agent3 + Agent3b, adds regime comparison."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from agents.agent3_calculator.calculator import calcola
from agents.agent3_calculator.models import ContribuenteInput
from agents.agent3b_validator.models import InputFiscale
from agents.agent3b_validator.validator import validate

from .models import ProfiloContribuente, Scadenza, SimulationResult


class SimulationError(Exception):
    """Raised when Agent3b blocks the calculation."""


def _round(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _calcola_irpef_2024(reddito_imponibile: Decimal) -> Decimal:
    """Approximate IRPEF calculation with 2024 brackets."""
    r = reddito_imponibile
    if r <= Decimal("0"):
        return Decimal("0")

    imposta = Decimal("0")
    # 23% fino a 28.000
    scaglione_1 = min(r, Decimal("28000"))
    imposta += _round(scaglione_1 * Decimal("0.23"))

    # 35% da 28.001 a 50.000
    if r > Decimal("28000"):
        scaglione_2 = min(r - Decimal("28000"), Decimal("22000"))
        imposta += _round(scaglione_2 * Decimal("0.35"))

    # 43% oltre 50.000
    if r > Decimal("50000"):
        scaglione_3 = r - Decimal("50000")
        imposta += _round(scaglione_3 * Decimal("0.43"))

    return _round(imposta)


def _build_scadenze(
    sim: SimulationResult,
    anno: int,
) -> list[Scadenza]:
    """Build the payment schedule."""
    scadenze: list[Scadenza] = []

    if sim.profilo.primo_anno:
        # First year: only balance next June
        if sim.da_versare > Decimal("0"):
            scadenze.append(Scadenza(
                data=f"{anno + 1}-06-30",
                descrizione="Saldo imposta sostitutiva",
                importo=sim.da_versare,
                codice_tributo="1792",
            ))
        # INPS for artigiani/commercianti: quarterly payments
        if sim.profilo.gestione_inps in ("artigiani", "commercianti"):
            trimestrale = _round(sim.contributo_inps / Decimal("4"))
            for data, desc in [
                (f"{anno}-08-20", "INPS 2° trimestre"),
                (f"{anno}-11-16", "INPS 3° trimestre"),
                (f"{anno + 1}-02-16", "INPS 4° trimestre"),
            ]:
                scadenze.append(Scadenza(
                    data=data,
                    descrizione=desc,
                    importo=trimestrale,
                ))
    else:
        # Subsequent years
        if sim.acconto_prima_rata > Decimal("0"):
            scadenze.append(Scadenza(
                data=f"{anno}-06-30",
                descrizione="Acconto 1ª rata imposta sostitutiva (40%)",
                importo=sim.acconto_prima_rata,
                codice_tributo="1790",
            ))
        if sim.acconto_seconda_rata > Decimal("0"):
            scadenze.append(Scadenza(
                data=f"{anno}-11-30",
                descrizione="Acconto 2ª rata imposta sostitutiva (60%)",
                importo=sim.acconto_seconda_rata,
                codice_tributo="1791",
            ))
        if sim.da_versare > Decimal("0"):
            scadenze.append(Scadenza(
                data=f"{anno + 1}-06-30",
                descrizione="Saldo imposta sostitutiva",
                importo=sim.da_versare,
                codice_tributo="1792",
            ))

    return scadenze


def simulate(
    profilo: ProfiloContribuente,
    ricavi_per_ateco: dict[str, Decimal],
    imposta_anno_prec: Decimal = Decimal("0"),
    anno_fiscale: int | None = None,
) -> SimulationResult:
    """Run fiscal simulation via Agent3, validate via Agent3b, enrich."""
    from datetime import date as date_type

    anno = anno_fiscale or date_type.today().year

    # Build Agent3 input
    a3_input = ContribuenteInput(
        contribuente_id=profilo.contribuente_id,
        anno_fiscale=anno,
        primo_anno=profilo.primo_anno,
        ateco_ricavi=ricavi_per_ateco,
        rivalsa_inps_applicata=Decimal("0"),
        regime_agevolato=profilo.regime_agevolato,
        gestione_inps=profilo.gestione_inps,
        riduzione_inps_35=profilo.riduzione_inps_35,
        contributi_inps_versati=Decimal("0"),
        imposta_anno_precedente=imposta_anno_prec,
        acconti_versati=Decimal("0"),
        crediti_precedenti=Decimal("0"),
    )

    # Agent3: calculate
    a3_result = calcola(a3_input)

    # Agent3b: validate
    a3b_input = InputFiscale(
        id_contribuente=profilo.contribuente_id,
        anno=anno,
        is_primo_anno=profilo.primo_anno,
        ricavi_per_ateco=ricavi_per_ateco,
        rivalsa_4_percento=Decimal("0"),
        aliquota_agevolata=profilo.regime_agevolato,
        tipo_gestione_inps=profilo.gestione_inps,
        ha_riduzione_35=profilo.riduzione_inps_35,
        inps_gia_versati=Decimal("0"),
        imposta_anno_prima=imposta_anno_prec,
        acconti_gia_versati=Decimal("0"),
        crediti_da_prima=Decimal("0"),
    )

    a3_dict: dict[str, Any] = {
        "reddito_lordo": str(a3_result.reddito_lordo),
        "reddito_imponibile": str(a3_result.reddito_imponibile),
        "imposta_sostitutiva": str(a3_result.imposta_sostitutiva),
        "acconti_dovuti": str(a3_result.acconti_dovuti),
        "acconto_prima_rata": str(a3_result.acconto_prima_rata),
        "acconto_seconda_rata": str(a3_result.acconto_seconda_rata),
        "da_versare": str(a3_result.da_versare),
        "credito_anno_prossimo": str(a3_result.credito_anno_prossimo),
        "contributo_inps_calcolato": str(a3_result.contributo_inps_calcolato),
        "checksum": a3_result.checksum,
    }

    esito = validate(a3b_input, a3_dict)
    if esito.blocco:
        divergenze = "; ".join(
            f"{d.campo}: agent3={d.valore_agent3} vs agent3b={d.valore_agent3b}"
            for d in esito.divergenze
        )
        raise SimulationError(
            f"Agent3b ha bloccato il calcolo. Divergenze: {divergenze}"
        )

    # Build SimulationResult
    ricavi_totali = _round(sum(ricavi_per_ateco.values()))

    sim = SimulationResult(
        profilo=profilo,
        anno_fiscale=anno,
        ricavi_totali=ricavi_totali,
        reddito_lordo=a3_result.reddito_lordo,
        reddito_imponibile=a3_result.reddito_imponibile,
        aliquota=a3_result.aliquota,
        imposta_sostitutiva=a3_result.imposta_sostitutiva,
        contributo_inps=a3_result.contributo_inps_calcolato,
        acconti_dovuti=a3_result.acconti_dovuti,
        acconto_prima_rata=a3_result.acconto_prima_rata,
        acconto_seconda_rata=a3_result.acconto_seconda_rata,
        da_versare=a3_result.da_versare,
        credito_anno_prossimo=a3_result.credito_anno_prossimo,
        dettaglio_ateco=[
            {"codice": d.codice_ateco, "ricavi": str(d.ricavi),
             "coefficiente": str(d.coefficiente), "reddito": str(d.reddito)}
            for d in a3_result.dettaglio_ateco
        ],
        dettaglio_inps=a3_result.dettaglio_inps,
        checksum=a3_result.checksum,
    )

    # --- Regime comparison ---
    irpef_stimata = _calcola_irpef_2024(sim.reddito_imponibile)
    totale_forfettario = _round(sim.imposta_sostitutiva + sim.contributo_inps)
    totale_ordinario = _round(irpef_stimata + sim.contributo_inps)
    sim.risparmio_vs_ordinario = _round(totale_ordinario - totale_forfettario)
    sim.confronto_regimi = {
        "forfettario": {
            "imposta": str(sim.imposta_sostitutiva),
            "inps": str(sim.contributo_inps),
            "totale": str(totale_forfettario),
        },
        "ordinario_stimato": {
            "irpef": str(irpef_stimata),
            "inps": str(sim.contributo_inps),
            "totale": str(totale_ordinario),
        },
        "risparmio_forfettario": str(sim.risparmio_vs_ordinario),
    }

    # --- Monthly savings ---
    sim.rata_mensile_da_accantonare = _round(totale_forfettario / Decimal("12"))

    # --- Payment schedule ---
    sim.scadenze_anno_corrente = _build_scadenze(sim, anno)

    # --- Warnings ---
    if ricavi_totali >= Decimal("70000"):
        sim.warnings.append(
            f"Ricavi stimati {ricavi_totali}€ — vicino alla soglia 85.000€. "
            f"Agent4 monitorerà durante l'anno."
        )
    if ricavi_totali >= Decimal("85000"):
        sim.warnings.append(
            "Ricavi stimati superano 85.000€ — uscita dal forfettario "
            "dall'anno prossimo."
        )

    return sim
