"""Agent7 — Fiscal Advisor for Italian forfettario regime.

Provides proactive fiscal analysis and advisory:
- Regime comparison (forfettario vs ordinario vs SRL)
- Break-even point calculation
- Invoice timing optimization
- Multi-ATECO revenue split optimization
- What-if scenario simulation

Pure Python, zero LLM, zero external API calls.
All arithmetic uses Decimal for exact fiscal calculations.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SHARED_DIR = Path(__file__).resolve().parent.parent.parent / "shared"
_ATECO_FILE = _SHARED_DIR / "ateco_coefficients.json"
_INPS_FILE = _SHARED_DIR / "inps_rates.json"
_LIMITS_FILE = _SHARED_DIR / "forfettario_limits.json"

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class RegimeDetail:
    """Tax breakdown for a single regime."""

    nome: str
    imposta_principale: Decimal = Decimal("0")
    inps: Decimal = Decimal("0")
    irap: Decimal = Decimal("0")
    iva_netta: Decimal = Decimal("0")  # IVA incassata - IVA detratta (ordinario only)
    dividendi_tassazione: Decimal = Decimal("0")  # SRL only
    totale_carico_fiscale: Decimal = Decimal("0")
    aliquota_effettiva: Decimal = Decimal("0")  # % on fatturato
    netto_disponibile: Decimal = Decimal("0")
    dettaglio: dict = field(default_factory=dict)


@dataclass
class ConfrontoRegimi:
    """Comparison between forfettario, ordinario, and SRL."""

    fatturato: Decimal
    ateco: str
    gestione_inps: str
    forfettario: RegimeDetail = field(default_factory=lambda: RegimeDetail(nome="forfettario"))
    ordinario: RegimeDetail = field(default_factory=lambda: RegimeDetail(nome="ordinario"))
    srl: RegimeDetail = field(default_factory=lambda: RegimeDetail(nome="srl"))
    regime_consigliato: str = ""
    risparmio_forfettario_vs_ordinario: Decimal = Decimal("0")
    risparmio_forfettario_vs_srl: Decimal = Decimal("0")
    note: list[str] = field(default_factory=list)


@dataclass
class WhatIfResult:
    """Result of a what-if scenario simulation."""

    scenario_descrizione: str = ""
    fatturato_base: Decimal = Decimal("0")
    fatturato_scenario: Decimal = Decimal("0")
    delta_fatturato: Decimal = Decimal("0")
    imposta_base: Decimal = Decimal("0")
    imposta_scenario: Decimal = Decimal("0")
    delta_imposta: Decimal = Decimal("0")
    inps_base: Decimal = Decimal("0")
    inps_scenario: Decimal = Decimal("0")
    delta_inps: Decimal = Decimal("0")
    netto_base: Decimal = Decimal("0")
    netto_scenario: Decimal = Decimal("0")
    delta_netto: Decimal = Decimal("0")
    supera_soglia: bool = False
    note: list[str] = field(default_factory=list)


@dataclass
class TimingAdvice:
    """Advice on invoice timing for fiscal optimization."""

    consiglio: str
    fatturato_corrente: Decimal = Decimal("0")
    soglia: Decimal = Decimal("85000")
    margine_rimasto: Decimal = Decimal("0")
    mesi_rimasti: int = 0
    budget_mensile: Decimal = Decimal("0")
    note: list[str] = field(default_factory=list)


@dataclass
class MultiAtecoAdvice:
    """Optimization advice for multi-ATECO revenue split."""

    ricavi_originali: dict = field(default_factory=dict)
    ricavi_ottimizzati: dict = field(default_factory=dict)
    reddito_originale: Decimal = Decimal("0")
    reddito_ottimizzato: Decimal = Decimal("0")
    risparmio_imposta: Decimal = Decimal("0")
    note: list[str] = field(default_factory=list)


@dataclass
class AdvisoryReport:
    """Full advisory report for a contribuente."""

    contribuente_id: str
    anno: int
    data_report: date = field(default_factory=date.today)
    confronto: ConfrontoRegimi | None = None
    soglia_convenienza: Decimal = Decimal("0")
    timing: TimingAdvice | None = None
    what_if: list[WhatIfResult] = field(default_factory=list)
    multi_ateco: MultiAtecoAdvice | None = None
    raccomandazioni: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _round(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _load_json(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _get_ateco_coefficient(codice_ateco: str) -> Decimal:
    """Look up the redditivity coefficient for an ATECO code."""
    data = _load_json(_ATECO_FILE)
    coefficients = data["coefficients"]
    if codice_ateco in coefficients:
        return Decimal(coefficients[codice_ateco]["coefficient"])
    for code, info in coefficients.items():
        if code.startswith(codice_ateco) or codice_ateco.startswith(code):
            return Decimal(info["coefficient"])
    # Range fallback
    division = codice_ateco.split(".")[0]
    div_num = int(division)
    for range_key, info in data.get("range_fallback", {}).items():
        if range_key.startswith("_"):
            continue
        parts = range_key.split("-")
        if len(parts) == 2:
            low, high = int(parts[0]), int(parts[1])
            if low <= div_num <= high:
                return Decimal(info["coefficient"])
        elif int(parts[0]) == div_num:
            return Decimal(info["coefficient"])
    raise ValueError(f"No coefficient found for ATECO code: {codice_ateco}")


def _get_ateco_gestione(codice_ateco: str) -> str:
    """Look up the gestione INPS for an ATECO code."""
    data = _load_json(_ATECO_FILE)
    coefficients = data["coefficients"]
    if codice_ateco in coefficients:
        return coefficients[codice_ateco].get("gestione_inps", "separata")
    for code, info in coefficients.items():
        if code.startswith(codice_ateco) or codice_ateco.startswith(code):
            return info.get("gestione_inps", "separata")
    return "separata"


def _get_inps_rates(anno: int, gestione: str) -> dict[str, Any]:
    data = _load_json(_INPS_FILE)
    anno_str = str(anno)
    if anno_str not in data:
        anno_str = str(anno - 1)
        if anno_str not in data:
            raise ValueError(f"INPS rates not available for year {anno}")
    year_data = data[anno_str]
    gestione_key = f"gestione_{gestione}" if gestione == "separata" else gestione
    if gestione_key not in year_data:
        raise ValueError(f"Unknown gestione INPS: {gestione}")
    return year_data[gestione_key]


# ---------------------------------------------------------------------------
# IRPEF scaglioni 2024+
# ---------------------------------------------------------------------------

def _calcola_irpef(reddito_imponibile: Decimal) -> Decimal:
    """IRPEF with 2024 brackets: 23% up to 28k, 25% 28-50k, 35% 50-55k, 43% over 55k."""
    r = reddito_imponibile
    if r <= Decimal("0"):
        return Decimal("0")

    imposta = Decimal("0")

    # 23% fino a 28.000
    scaglione = min(r, Decimal("28000"))
    imposta += _round(scaglione * Decimal("0.23"))

    # 25% da 28.001 a 50.000
    if r > Decimal("28000"):
        scaglione = min(r - Decimal("28000"), Decimal("22000"))
        imposta += _round(scaglione * Decimal("0.25"))

    # 35% da 50.001 a 55.000
    if r > Decimal("50000"):
        scaglione = min(r - Decimal("50000"), Decimal("5000"))
        imposta += _round(scaglione * Decimal("0.35"))

    # 43% oltre 55.000
    if r > Decimal("55000"):
        scaglione = r - Decimal("55000")
        imposta += _round(scaglione * Decimal("0.43"))

    return _round(imposta)


# ---------------------------------------------------------------------------
# INPS calculation helpers
# ---------------------------------------------------------------------------

def _calcola_inps_forfettario(
    reddito_imponibile: Decimal,
    anno: int,
    gestione: str,
    riduzione_35: bool = False,
) -> Decimal:
    """Calculate INPS contributions for forfettario regime."""
    rates = _get_inps_rates(anno, gestione)

    if gestione == "separata":
        aliquota = Decimal(rates["aliquota"])
        return _round(reddito_imponibile * aliquota)

    elif gestione in ("artigiani", "commercianti"):
        fisso = Decimal(rates["contributo_fisso_annuo"])
        minimale = Decimal(rates["minimale_annuo"])
        aliquota_ecc = Decimal(rates["aliquota_eccedenza"])

        eccedenza = max(Decimal("0"), reddito_imponibile - minimale)
        variabile = _round(eccedenza * aliquota_ecc)
        totale = _round(fisso + variabile)

        if riduzione_35:
            totale = _round(totale * Decimal("0.65"))

        return totale

    return Decimal("0")


def _calcola_inps_ordinario(
    reddito_imponibile: Decimal,
    anno: int,
    gestione: str,
) -> Decimal:
    """Calculate INPS for ordinario regime (same rates, different base)."""
    # In ordinario, INPS is calculated on the same base for professionisti
    return _calcola_inps_forfettario(reddito_imponibile, anno, gestione, riduzione_35=False)


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def confronto_regimi(
    fatturato: Decimal,
    ateco: str,
    gestione: str,
    anno: int | None = None,
    regime_agevolato: bool = False,
    riduzione_35: bool = False,
    costi_deducibili_pct: Decimal = Decimal("0.20"),
) -> ConfrontoRegimi:
    """Compare forfettario vs ordinario vs SRL at the same revenue level.

    Args:
        fatturato: Gross revenue (ricavi lordi).
        ateco: Primary ATECO code.
        gestione: INPS management type ("separata", "artigiani", "commercianti").
        anno: Fiscal year (defaults to current year).
        regime_agevolato: True = 5% tax rate (first 5 years), False = 15%.
        riduzione_35: INPS 35% reduction for forfettari.
        costi_deducibili_pct: Estimated deductible costs as % of revenue (for ordinario).

    Returns:
        ConfrontoRegimi with full breakdown for each regime.
    """
    if anno is None:
        anno = date.today().year

    coeff = _get_ateco_coefficient(ateco)
    confronto = ConfrontoRegimi(fatturato=fatturato, ateco=ateco, gestione_inps=gestione)

    # === FORFETTARIO ===
    reddito_forf = _round(fatturato * coeff)
    aliquota_forf = Decimal("0.05") if regime_agevolato else Decimal("0.15")
    inps_forf = _calcola_inps_forfettario(reddito_forf, anno, gestione, riduzione_35)
    # INPS is deductible in forfettario
    reddito_forf_netto_inps = max(Decimal("0"), reddito_forf - inps_forf)
    imposta_forf = _round(reddito_forf_netto_inps * aliquota_forf)
    totale_forf = _round(imposta_forf + inps_forf)

    confronto.forfettario = RegimeDetail(
        nome="forfettario",
        imposta_principale=imposta_forf,
        inps=inps_forf,
        totale_carico_fiscale=totale_forf,
        aliquota_effettiva=_round((totale_forf / fatturato) * Decimal("100")) if fatturato > 0 else Decimal("0"),
        netto_disponibile=_round(fatturato - totale_forf),
        dettaglio={
            "coefficiente_redditivita": str(coeff),
            "reddito_lordo": str(reddito_forf),
            "inps_dedotto": str(inps_forf),
            "reddito_imponibile": str(reddito_forf_netto_inps),
            "aliquota": str(aliquota_forf),
            "riduzione_35": riduzione_35,
        },
    )

    # === ORDINARIO ===
    # In ordinario, actual costs are deducted (estimated via costi_deducibili_pct)
    costi_deducibili = _round(fatturato * costi_deducibili_pct)
    reddito_ord = _round(fatturato - costi_deducibili)
    inps_ord = _calcola_inps_ordinario(reddito_ord, anno, gestione)
    # INPS is deductible also in ordinario
    reddito_ord_netto = max(Decimal("0"), reddito_ord - inps_ord)
    irpef = _calcola_irpef(reddito_ord_netto)

    # IRAP 3.9% (applicable to attivita organizzate — simplified here)
    irap = _round(reddito_ord * Decimal("0.039"))

    # IVA: in ordinario IVA is charged but also deducted on purchases
    # Net IVA effect depends on cost structure; estimate as IVA on margin
    iva_aliquota = Decimal("0.22")
    iva_incassata = _round(fatturato * iva_aliquota)
    iva_su_costi = _round(costi_deducibili * iva_aliquota)
    iva_netta = _round(iva_incassata - iva_su_costi)

    totale_ord = _round(irpef + inps_ord + irap)
    # IVA is not a cost per se (pass-through), but affects cash flow.
    # We include it separately for awareness.

    confronto.ordinario = RegimeDetail(
        nome="ordinario",
        imposta_principale=irpef,
        inps=inps_ord,
        irap=irap,
        iva_netta=iva_netta,
        totale_carico_fiscale=totale_ord,
        aliquota_effettiva=_round((totale_ord / fatturato) * Decimal("100")) if fatturato > 0 else Decimal("0"),
        netto_disponibile=_round(fatturato - totale_ord),
        dettaglio={
            "costi_deducibili": str(costi_deducibili),
            "reddito_lordo": str(reddito_ord),
            "inps_dedotto": str(inps_ord),
            "reddito_imponibile": str(reddito_ord_netto),
            "irpef": str(irpef),
            "irap": str(irap),
            "iva_netta_stima": str(iva_netta),
            "nota_iva": "IVA e' un pass-through; impatto solo su cash flow",
        },
    )

    # === SRL ===
    # SRL: IRES 24% + IRAP 3.9% on utile; dividendi 26% on distributed profit
    costi_srl = _round(fatturato * costi_deducibili_pct)
    # Add estimated SRL running costs (commercialista, contributi INPS amministratore, etc.)
    costi_gestione_srl = Decimal("5000")  # stima conservativa
    utile_lordo = max(Decimal("0"), _round(fatturato - costi_srl - costi_gestione_srl))
    ires = _round(utile_lordo * Decimal("0.24"))
    irap_srl = _round(utile_lordo * Decimal("0.039"))
    utile_netto = _round(utile_lordo - ires - irap_srl)

    # Dividendi: tassazione 26% su distribuzione
    dividendi_tassa = _round(utile_netto * Decimal("0.26"))
    netto_srl = _round(utile_netto - dividendi_tassa)
    totale_srl = _round(ires + irap_srl + dividendi_tassa + costi_gestione_srl)

    confronto.srl = RegimeDetail(
        nome="srl",
        imposta_principale=ires,
        irap=irap_srl,
        dividendi_tassazione=dividendi_tassa,
        totale_carico_fiscale=totale_srl,
        aliquota_effettiva=_round((totale_srl / fatturato) * Decimal("100")) if fatturato > 0 else Decimal("0"),
        netto_disponibile=netto_srl,
        dettaglio={
            "utile_lordo": str(utile_lordo),
            "ires": str(ires),
            "irap": str(irap_srl),
            "utile_netto": str(utile_netto),
            "dividendi_tassazione": str(dividendi_tassa),
            "costi_gestione_srl": str(costi_gestione_srl),
        },
    )

    # === Recommendation ===
    confronto.risparmio_forfettario_vs_ordinario = _round(totale_ord - totale_forf)
    confronto.risparmio_forfettario_vs_srl = _round(totale_srl - totale_forf)

    regimi = [
        ("forfettario", totale_forf),
        ("ordinario", totale_ord),
        ("srl", totale_srl),
    ]
    regimi.sort(key=lambda x: x[1])
    confronto.regime_consigliato = regimi[0][0]

    if fatturato > Decimal("85000"):
        confronto.note.append(
            "Il fatturato supera la soglia di 85.000 EUR: il regime forfettario "
            "non e' accessibile. Confronto puramente indicativo."
        )
    if regime_agevolato:
        confronto.note.append(
            "Aliquota agevolata 5% applicata (primi 5 anni). "
            "Dopo i 5 anni l'aliquota sara' 15%."
        )

    return confronto


def soglia_convenienza(
    ateco: str,
    gestione: str,
    anno: int | None = None,
    regime_agevolato: bool = False,
    riduzione_35: bool = False,
    costi_deducibili_pct: Decimal = Decimal("0.20"),
    step: Decimal = Decimal("1000"),
) -> Decimal:
    """Calculate the revenue break-even point where forfettario stops being convenient.

    Uses binary search to find the crossing point where ordinario becomes cheaper.

    Args:
        ateco: ATECO code.
        gestione: INPS management type.
        anno: Fiscal year.
        regime_agevolato: Whether 5% rate applies.
        riduzione_35: INPS 35% reduction.
        costi_deducibili_pct: Estimated deductible costs for ordinario.
        step: Precision of the result.

    Returns:
        Revenue amount where forfettario becomes more expensive than ordinario,
        or Decimal("85000") if forfettario is always convenient up to the limit.
    """
    if anno is None:
        anno = date.today().year

    soglia_max = Decimal("85000")
    low = Decimal("10000")
    high = soglia_max

    # Check if forfettario is always convenient up to 85k
    confronto_85k = confronto_regimi(
        soglia_max, ateco, gestione, anno, regime_agevolato, riduzione_35,
        costi_deducibili_pct,
    )
    if confronto_85k.forfettario.totale_carico_fiscale <= confronto_85k.ordinario.totale_carico_fiscale:
        return soglia_max  # forfettario always convenient up to the limit

    # Binary search for crossing point
    while (high - low) > step:
        mid = _round((low + high) / Decimal("2"))
        c = confronto_regimi(
            mid, ateco, gestione, anno, regime_agevolato, riduzione_35,
            costi_deducibili_pct,
        )
        if c.forfettario.totale_carico_fiscale <= c.ordinario.totale_carico_fiscale:
            low = mid
        else:
            high = mid

    return _round(high)


def simulate_what_if(
    profile: dict,
    scenario: dict,
    anno: int | None = None,
) -> WhatIfResult:
    """Simulate a what-if scenario on top of the current profile.

    Args:
        profile: Contribuente profile dict.
        scenario: Dict with scenario parameters:
            - fatturato_aggiuntivo: Decimal, additional revenue to simulate
            - ateco: optional ATECO code for the additional revenue
            - descrizione: optional description of the scenario
        anno: Fiscal year.

    Returns:
        WhatIfResult comparing base vs scenario.
    """
    if anno is None:
        anno = date.today().year

    anagrafica = profile.get("anagrafica", profile)
    ateco = anagrafica.get("ateco_principale", "74.90.99")
    gestione = anagrafica.get("gestione_inps", "separata")
    regime_agevolato = anagrafica.get("regime_agevolato", True)
    riduzione_35 = anagrafica.get("riduzione_inps_35", False)

    coeff = _get_ateco_coefficient(ateco)
    aliquota = Decimal("0.05") if regime_agevolato else Decimal("0.15")

    # Base: current invoices
    fatture = profile.get("fatture", [])
    fatturato_base = sum(
        Decimal(str(f.get("importo", "0")))
        for f in fatture
        if not f.get("data") or str(anno) in str(f.get("data", ""))
    )
    fatturato_base = _round(fatturato_base)

    # Scenario: base + additional
    fatturato_agg = Decimal(str(scenario.get("fatturato_aggiuntivo", "0")))
    ateco_agg = scenario.get("ateco", ateco)
    coeff_agg = _get_ateco_coefficient(ateco_agg)

    fatturato_scenario = _round(fatturato_base + fatturato_agg)

    # Base calculation
    reddito_base = _round(fatturato_base * coeff)
    inps_base = _calcola_inps_forfettario(reddito_base, anno, gestione, riduzione_35)
    reddito_base_netto = max(Decimal("0"), reddito_base - inps_base)
    imposta_base = _round(reddito_base_netto * aliquota)

    # Scenario calculation
    reddito_scenario = _round(fatturato_base * coeff + fatturato_agg * coeff_agg)
    inps_scenario = _calcola_inps_forfettario(reddito_scenario, anno, gestione, riduzione_35)
    reddito_scenario_netto = max(Decimal("0"), reddito_scenario - inps_scenario)
    imposta_scenario = _round(reddito_scenario_netto * aliquota)

    netto_base = _round(fatturato_base - imposta_base - inps_base)
    netto_scenario = _round(fatturato_scenario - imposta_scenario - inps_scenario)

    supera = fatturato_scenario > Decimal("85000")

    result = WhatIfResult(
        scenario_descrizione=scenario.get("descrizione", f"Fatturato aggiuntivo di {fatturato_agg} EUR"),
        fatturato_base=fatturato_base,
        fatturato_scenario=fatturato_scenario,
        delta_fatturato=_round(fatturato_agg),
        imposta_base=imposta_base,
        imposta_scenario=imposta_scenario,
        delta_imposta=_round(imposta_scenario - imposta_base),
        inps_base=inps_base,
        inps_scenario=inps_scenario,
        delta_inps=_round(inps_scenario - inps_base),
        netto_base=netto_base,
        netto_scenario=netto_scenario,
        delta_netto=_round(netto_scenario - netto_base),
        supera_soglia=supera,
    )

    if supera:
        result.note.append(
            f"ATTENZIONE: con {fatturato_scenario} EUR si supera la soglia 85.000 EUR. "
            f"Uscita dal regime forfettario dall'anno {anno + 1}."
        )

    # Calculate marginal tax rate
    if fatturato_agg > Decimal("0"):
        marginal_tax = _round(
            ((imposta_scenario - imposta_base) + (inps_scenario - inps_base))
            / fatturato_agg * Decimal("100")
        )
        result.note.append(
            f"Aliquota marginale effettiva sui {fatturato_agg} EUR aggiuntivi: {marginal_tax}%"
        )

    return result


def ottimizza_multi_ateco(
    ricavi_per_ateco: dict[str, Decimal],
    coefficienti: dict[str, Decimal] | None = None,
) -> MultiAtecoAdvice:
    """Optimize revenue allocation across multiple ATECO codes.

    If a contribuente has multiple ATECO codes, different allocations of
    the same total revenue will produce different taxable income due to
    different redditivity coefficients.

    IMPORTANT: This is advisory only. Revenue must be genuinely earned
    under each ATECO code. Artificial shifting is tax evasion.

    Args:
        ricavi_per_ateco: Dict of {ateco_code: revenue_amount}.
        coefficienti: Optional pre-loaded coefficients dict. If None, loaded from file.

    Returns:
        MultiAtecoAdvice with original vs optimized breakdown.
    """
    if not ricavi_per_ateco:
        return MultiAtecoAdvice(note=["Nessun ricavo fornito."])

    # Load coefficients if not provided
    if coefficienti is None:
        coefficienti = {}
        for ateco in ricavi_per_ateco:
            try:
                coefficienti[ateco] = _get_ateco_coefficient(ateco)
            except ValueError:
                coefficienti[ateco] = Decimal("0.78")  # default

    totale_ricavi = sum(ricavi_per_ateco.values())

    # Original reddito
    reddito_originale = Decimal("0")
    for ateco, ricavi in ricavi_per_ateco.items():
        coeff = coefficienti.get(ateco, Decimal("0.78"))
        reddito_originale += _round(ricavi * coeff)
    reddito_originale = _round(reddito_originale)

    # Find optimal split: maximize allocation to lowest-coefficient ATECO
    # Sort ATECOs by coefficient (ascending — lower = less taxable income)
    ateco_sorted = sorted(coefficienti.items(), key=lambda x: x[1])

    # The "optimal" is to shift as much as legally possible to the lowest coefficient
    # In practice, this means awareness of which ATECO codes have lower coefficients
    ricavi_ottimizzati = dict(ricavi_per_ateco)  # start with original

    # Calculate reddito with current allocation
    reddito_ottimizzato = reddito_originale

    # Show which ATECO has the lowest coefficient
    if len(ateco_sorted) >= 2:
        lowest_ateco, lowest_coeff = ateco_sorted[0]
        highest_ateco, highest_coeff = ateco_sorted[-1]

        # Calculate how much reddito would change per 1000 EUR shifted
        delta_per_1000 = _round((highest_coeff - lowest_coeff) * Decimal("1000"))

        note = [
            f"ATECO con coefficiente piu' basso: {lowest_ateco} ({lowest_coeff})",
            f"ATECO con coefficiente piu' alto: {highest_ateco} ({highest_coeff})",
            f"Ogni 1.000 EUR spostati da {highest_ateco} a {lowest_ateco} "
            f"riducono il reddito di {delta_per_1000} EUR.",
            "ATTENZIONE: i ricavi devono essere genuinamente imputabili "
            "al codice ATECO corrispondente. Spostamenti artificiosi "
            "configurano evasione fiscale.",
        ]
    else:
        note = ["Un solo codice ATECO: nessuna ottimizzazione possibile."]

    return MultiAtecoAdvice(
        ricavi_originali={k: str(v) for k, v in ricavi_per_ateco.items()},
        ricavi_ottimizzati={k: str(v) for k, v in ricavi_ottimizzati.items()},
        reddito_originale=reddito_originale,
        reddito_ottimizzato=reddito_ottimizzato,
        risparmio_imposta=Decimal("0"),  # no artificial shift
        note=note,
    )


def _calcola_timing(profile: dict, anno: int) -> TimingAdvice:
    """Calculate invoice timing advice based on current revenue pace.

    Args:
        profile: Contribuente profile dict.
        anno: Fiscal year.

    Returns:
        TimingAdvice with monthly budget and pacing guidance.
    """
    fatture = profile.get("fatture", [])
    today = date.today()
    mesi_rimasti = max(1, 12 - today.month + 1) if today.year == anno else 12

    fatturato_corrente = Decimal("0")
    for f in fatture:
        importo = Decimal(str(f.get("importo", "0")))
        data_f = f.get("data")
        if data_f:
            try:
                d = date.fromisoformat(str(data_f)) if isinstance(data_f, str) else data_f
                if d.year != anno:
                    continue
            except (ValueError, TypeError):
                pass
        fatturato_corrente += importo

    fatturato_corrente = _round(fatturato_corrente)
    soglia = Decimal("85000")
    margine = _round(soglia - fatturato_corrente)
    budget_mensile = _round(margine / Decimal(str(mesi_rimasti))) if mesi_rimasti > 0 else Decimal("0")

    if margine <= Decimal("0"):
        consiglio = (
            "Soglia 85.000 EUR gia' raggiunta o superata. "
            "Valutare di posticipare la fatturazione al prossimo anno "
            "o prepararsi al passaggio al regime ordinario."
        )
    elif margine < Decimal("10000"):
        consiglio = (
            f"Margine ridotto: {margine} EUR rimasti. "
            f"Budget mensile massimo: {budget_mensile} EUR. "
            f"Considerare di posticipare fatture non urgenti a gennaio {anno + 1}."
        )
    else:
        consiglio = (
            f"Margine confortevole: {margine} EUR rimasti su {mesi_rimasti} mesi. "
            f"Budget mensile indicativo: {budget_mensile} EUR."
        )

    notes: list[str] = []
    if fatturato_corrente > Decimal("0") and today.month >= 6 and today.year == anno:
        proiezione = _round(fatturato_corrente / Decimal(str(today.month)) * Decimal("12"))
        if proiezione > Decimal("80000"):
            notes.append(
                f"Proiezione annua: {proiezione} EUR. "
                f"Rischio avvicinamento soglia. Monitorare mensilmente."
            )

    return TimingAdvice(
        consiglio=consiglio,
        fatturato_corrente=fatturato_corrente,
        soglia=soglia,
        margine_rimasto=margine,
        mesi_rimasti=mesi_rimasti,
        budget_mensile=budget_mensile,
        note=notes,
    )


def advise(profile: dict, anno: int | None = None) -> AdvisoryReport:
    """Run full advisory analysis for a contribuente.

    Aggregates regime comparison, break-even analysis, timing advice,
    and multi-ATECO optimization.

    Args:
        profile: Contribuente profile dict (from SupervisorStore).
        anno: Fiscal year (defaults to current year).

    Returns:
        AdvisoryReport with all advisory findings.
    """
    if anno is None:
        anno = date.today().year

    anagrafica = profile.get("anagrafica", profile)
    contribuente_id = profile.get("contribuente_id", anagrafica.get("codice_fiscale", "unknown"))
    ateco = anagrafica.get("ateco_principale", "74.90.99")
    gestione = anagrafica.get("gestione_inps", "separata")
    regime_agevolato = anagrafica.get("regime_agevolato", True)
    riduzione_35 = anagrafica.get("riduzione_inps_35", False)

    # Calculate current revenue
    fatture = profile.get("fatture", [])
    fatturato = _round(sum(
        Decimal(str(f.get("importo", "0")))
        for f in fatture
        if not f.get("data") or str(anno) in str(f.get("data", ""))
    ))

    # Use at least a minimum for meaningful comparison
    fatturato_confronto = max(fatturato, Decimal("30000"))

    report = AdvisoryReport(
        contribuente_id=contribuente_id,
        anno=anno,
    )

    # 1. Regime comparison
    report.confronto = confronto_regimi(
        fatturato_confronto, ateco, gestione, anno,
        regime_agevolato, riduzione_35,
    )

    # 2. Break-even point
    report.soglia_convenienza = soglia_convenienza(
        ateco, gestione, anno, regime_agevolato, riduzione_35,
    )

    # 3. Timing advice
    report.timing = _calcola_timing(profile, anno)

    # 4. Multi-ATECO optimization
    ateco_secondari = anagrafica.get("ateco_secondari", [])
    if ateco_secondari:
        # Build ricavi_per_ateco from invoices if possible, else split evenly
        ricavi_per_ateco: dict[str, Decimal] = {}
        for f in fatture:
            f_ateco = f.get("ateco", ateco)
            importo = Decimal(str(f.get("importo", "0")))
            ricavi_per_ateco[f_ateco] = ricavi_per_ateco.get(f_ateco, Decimal("0")) + importo

        # Ensure all ATECOs are represented
        all_ateco = [ateco] + ateco_secondari
        for a in all_ateco:
            if a not in ricavi_per_ateco:
                ricavi_per_ateco[a] = Decimal("0")

        report.multi_ateco = ottimizza_multi_ateco(ricavi_per_ateco)

    # 5. Generate recommendations
    if report.confronto:
        c = report.confronto
        if c.regime_consigliato == "forfettario":
            report.raccomandazioni.append(
                f"Il regime forfettario rimane il piu' conveniente con un risparmio "
                f"di {c.risparmio_forfettario_vs_ordinario} EUR rispetto all'ordinario."
            )
        else:
            report.raccomandazioni.append(
                f"Al livello di fatturato corrente ({fatturato_confronto} EUR), "
                f"il regime {c.regime_consigliato} risulta piu' conveniente. "
                f"Valutare la transizione."
            )

    if report.soglia_convenienza < Decimal("85000"):
        report.raccomandazioni.append(
            f"Soglia di convenienza forfettario: {report.soglia_convenienza} EUR. "
            f"Oltre questo fatturato, l'ordinario diventa piu' vantaggioso."
        )
    else:
        report.raccomandazioni.append(
            "Il forfettario resta conveniente fino alla soglia massima di 85.000 EUR."
        )

    if report.timing and report.timing.margine_rimasto < Decimal("15000"):
        report.raccomandazioni.append(report.timing.consiglio)

    return report
