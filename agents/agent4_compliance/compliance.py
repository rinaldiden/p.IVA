"""Agent4 — Compliance Monitor for Italian forfettario regime.

Monitors revenue thresholds, verifies deadline compliance, checks INPS payments,
flags missing marca da bollo, and detects anomalies in invoicing patterns.

Pure Python, zero LLM, zero external API calls.
All arithmetic uses Decimal for exact fiscal calculations.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SHARED_DIR = Path(__file__).resolve().parent.parent.parent / "shared"
_ATECO_FILE = _SHARED_DIR / "ateco_coefficients.json"
_INPS_FILE = _SHARED_DIR / "inps_rates.json"
_LIMITS_FILE = _SHARED_DIR / "forfettario_limits.json"
_CALENDAR_FILE = _SHARED_DIR / "tax_calendar.json"

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class SogliaCheck:
    """Result of revenue threshold monitoring against the 85k limit."""

    anno: int
    fatturato_corrente: Decimal
    soglia: Decimal = Decimal("85000")
    percentuale_raggiunta: Decimal = Decimal("0")
    superata: bool = False
    livello_alert: str = "ok"  # ok, warning_70, warning_80, warning_90, critical
    proiezione_annua: Decimal = Decimal("0")
    mese_proiezione: int = 0
    messaggio: str = ""


@dataclass
class ScadenzaCheck:
    """Result of a single deadline compliance check."""

    scadenza_id: str
    descrizione: str
    data_scadenza: date
    importo_dovuto: Decimal = Decimal("0")
    pagato: bool = False
    scaduto: bool = False
    giorni_rimasti: int = 0
    messaggio: str = ""


@dataclass
class BolloCheck:
    """Result of marca da bollo compliance for a single invoice."""

    numero_fattura: str
    importo_fattura: Decimal
    bollo_richiesto: bool = False
    bollo_presente: bool = False
    conforme: bool = True
    messaggio: str = ""


@dataclass
class Anomalia:
    """A detected anomaly in invoicing patterns."""

    tipo: str  # concentrazione_cliente, gap_numerazione, importo_anomalo, frequenza
    severita: str  # info, warning, critical
    descrizione: str
    dettaglio: dict = field(default_factory=dict)


@dataclass
class InpsCheck:
    """INPS contribution compliance check."""

    gestione: str
    contributo_dovuto_annuo: Decimal = Decimal("0")
    contributo_versato: Decimal = Decimal("0")
    conforme: bool = True
    rate_mancanti: list[str] = field(default_factory=list)
    messaggio: str = ""


@dataclass
class ComplianceReport:
    """Full compliance report for a contribuente."""

    contribuente_id: str
    anno: int
    data_report: date = field(default_factory=date.today)
    soglia: SogliaCheck | None = None
    scadenze: list[ScadenzaCheck] = field(default_factory=list)
    bolli: list[BolloCheck] = field(default_factory=list)
    inps: InpsCheck | None = None
    anomalie: list[Anomalia] = field(default_factory=list)
    overall_status: str = "ok"  # ok, warning, critical
    alert_count: int = 0
    messaggi: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _round(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _load_json(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _get_limits() -> dict[str, Any]:
    return _load_json(_LIMITS_FILE)


def _get_calendar() -> dict[str, Any]:
    return _load_json(_CALENDAR_FILE)


def _get_inps_rates(anno: int, gestione: str) -> dict[str, Any]:
    data = _load_json(_INPS_FILE)
    anno_str = str(anno)
    if anno_str not in data:
        # Fallback to previous year
        anno_str = str(anno - 1)
        if anno_str not in data:
            raise ValueError(f"INPS rates not available for year {anno}")

    year_data = data[anno_str]
    gestione_key = f"gestione_{gestione}" if gestione == "separata" else gestione
    if gestione_key not in year_data:
        raise ValueError(f"Unknown gestione INPS: {gestione}")
    return year_data[gestione_key]


def _get_ateco_info(codice_ateco: str) -> dict[str, Any]:
    data = _load_json(_ATECO_FILE)
    coefficients = data["coefficients"]
    if codice_ateco in coefficients:
        return coefficients[codice_ateco]
    for code, info in coefficients.items():
        if code.startswith(codice_ateco) or codice_ateco.startswith(code):
            return info
    return {}


def _parse_date(d: str | date) -> date:
    """Parse a date string (YYYY-MM-DD) or return as-is if already a date."""
    if isinstance(d, date):
        return d
    return datetime.strptime(d, "%Y-%m-%d").date()


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def check_soglia_85k(fatture: list[dict], anno: int) -> SogliaCheck:
    """Monitor revenue against the 85k forfettario threshold.

    Calculates current total, projects annual revenue based on invoicing pace,
    and triggers warnings at 70%, 80%, 90%, 100%.

    Args:
        fatture: List of invoice dicts, each with at least 'importo' (Decimal or str)
                 and optionally 'data' (YYYY-MM-DD) for projection.
        anno: Fiscal year to check.

    Returns:
        SogliaCheck with threshold analysis.
    """
    limits = _get_limits()
    soglia = Decimal(limits["soglia_ricavi"])

    # Sum invoices for the target year
    fatturato = Decimal("0")
    mese_max = 0
    for f in fatture:
        data_fattura = f.get("data")
        importo = Decimal(str(f.get("importo", "0")))

        if data_fattura:
            d = _parse_date(data_fattura)
            if d.year != anno:
                continue
            if d.month > mese_max:
                mese_max = d.month
        fatturato += importo

    fatturato = _round(fatturato)
    percentuale = _round((fatturato / soglia) * Decimal("100")) if soglia > 0 else Decimal("0")

    # Project annual revenue based on current pace
    if mese_max > 0:
        proiezione = _round(fatturato / Decimal(str(mese_max)) * Decimal("12"))
    else:
        proiezione = fatturato

    # Determine alert level
    if percentuale >= Decimal("100"):
        livello = "critical"
        msg = (f"ATTENZIONE: soglia 85.000 EUR superata! Fatturato {fatturato} EUR. "
               f"Uscita dal forfettario dall'anno fiscale {anno + 1}.")
    elif percentuale >= Decimal("90"):
        livello = "warning_90"
        msg = (f"Fatturato {fatturato} EUR = {percentuale}% della soglia. "
               f"Proiezione annua: {proiezione} EUR. Attenzione massima.")
    elif percentuale >= Decimal("80"):
        livello = "warning_80"
        msg = (f"Fatturato {fatturato} EUR = {percentuale}% della soglia. "
               f"Proiezione annua: {proiezione} EUR. Monitorare attentamente.")
    elif percentuale >= Decimal("70"):
        livello = "warning_70"
        msg = (f"Fatturato {fatturato} EUR = {percentuale}% della soglia. "
               f"Proiezione annua: {proiezione} EUR. In avvicinamento alla soglia.")
    else:
        livello = "ok"
        msg = f"Fatturato {fatturato} EUR = {percentuale}% della soglia. Nessun rischio."

    return SogliaCheck(
        anno=anno,
        fatturato_corrente=fatturato,
        soglia=soglia,
        percentuale_raggiunta=percentuale,
        superata=fatturato >= soglia,
        livello_alert=livello,
        proiezione_annua=proiezione,
        mese_proiezione=mese_max,
        messaggio=msg,
    )


def check_scadenze(profile: dict, anno: int) -> list[ScadenzaCheck]:
    """Verify upcoming F24 deadlines and flag missed/upcoming ones.

    Cross-references with the tax calendar and profile payment history.

    Args:
        profile: Contribuente profile dict (from persistence).
        anno: Fiscal year.

    Returns:
        List of ScadenzaCheck for each relevant deadline.
    """
    calendar = _get_calendar()
    today = date.today()

    anagrafica = profile.get("anagrafica", profile)
    gestione = anagrafica.get("gestione_inps", "separata")
    primo_anno = anagrafica.get("primo_anno", True)

    pagamenti_effettuati = {
        p.get("scadenza_id", ""): Decimal(str(p.get("importo", "0")))
        for p in profile.get("pagamenti", [])
        if p.get("anno") == anno
    }

    checks: list[ScadenzaCheck] = []

    # Imposta sostitutiva deadlines
    for scad in calendar.get("imposta_sostitutiva", []):
        scad_id = scad["id"]

        # Skip acconti for primo anno
        if primo_anno and "acconto" in scad_id:
            continue

        month, day = map(int, scad["date"].split("-"))
        data_scadenza = date(anno, month, day)

        pagato = scad_id in pagamenti_effettuati
        scaduto = not pagato and today > data_scadenza
        giorni = (data_scadenza - today).days

        if scaduto:
            msg = f"SCADUTO: {scad['description']} era il {data_scadenza.isoformat()}"
        elif giorni <= 30 and not pagato:
            msg = f"IN SCADENZA: {scad['description']} tra {giorni} giorni"
        elif pagato:
            msg = f"Pagato: {scad['description']}"
        else:
            msg = f"{scad['description']} — scadenza {data_scadenza.isoformat()}"

        checks.append(ScadenzaCheck(
            scadenza_id=scad_id,
            descrizione=scad["description"],
            data_scadenza=data_scadenza,
            importo_dovuto=pagamenti_effettuati.get(scad_id, Decimal("0")),
            pagato=pagato,
            scaduto=scaduto,
            giorni_rimasti=max(0, giorni),
            messaggio=msg,
        ))

    # INPS deadlines based on gestione
    if gestione == "separata":
        for scad in calendar.get("inps_gestione_separata", []):
            if primo_anno and "acconto" in scad["id"]:
                continue
            month, day = map(int, scad["date"].split("-"))
            data_scadenza = date(anno, month, day)
            pagato = scad["id"] in pagamenti_effettuati
            scaduto = not pagato and today > data_scadenza
            giorni = (data_scadenza - today).days

            checks.append(ScadenzaCheck(
                scadenza_id=scad["id"],
                descrizione=scad["description"],
                data_scadenza=data_scadenza,
                pagato=pagato,
                scaduto=scaduto,
                giorni_rimasti=max(0, giorni),
                messaggio=f"{'SCADUTO' if scaduto else 'OK'}: {scad['description']}",
            ))
    elif gestione in ("artigiani", "commercianti"):
        inps_ac = calendar.get("inps_artigiani_commercianti", {})
        for scad in inps_ac.get("fissi_trimestrali", []):
            month, day = map(int, scad["date"].split("-"))
            data_scadenza = date(anno, month, day)
            pagato = scad["id"] in pagamenti_effettuati
            scaduto = not pagato and today > data_scadenza
            giorni = (data_scadenza - today).days

            checks.append(ScadenzaCheck(
                scadenza_id=scad["id"],
                descrizione=scad["description"],
                data_scadenza=data_scadenza,
                pagato=pagato,
                scaduto=scaduto,
                giorni_rimasti=max(0, giorni),
                messaggio=f"{'SCADUTO' if scaduto else 'OK'}: {scad['description']}",
            ))

    # Dichiarazione deadline
    for scad in calendar.get("dichiarazione", []):
        month, day = map(int, scad["date"].split("-"))
        data_scadenza = date(anno, month, day)
        pagato = scad["id"] in pagamenti_effettuati
        scaduto = not pagato and today > data_scadenza
        giorni = (data_scadenza - today).days
        checks.append(ScadenzaCheck(
            scadenza_id=scad["id"],
            descrizione=scad["description"],
            data_scadenza=data_scadenza,
            pagato=pagato,
            scaduto=scaduto,
            giorni_rimasti=max(0, giorni),
            messaggio=f"{'SCADUTO' if scaduto else 'OK'}: {scad['description']}",
        ))

    return checks


def _check_bolli(fatture: list[dict]) -> list[BolloCheck]:
    """Check marca da bollo compliance for invoices over 77.47 EUR.

    Forfettario invoices over 77.47 EUR require a 2 EUR marca da bollo.

    Args:
        fatture: List of invoice dicts with 'importo', 'numero', and optionally 'bollo'.

    Returns:
        List of BolloCheck for each non-compliant invoice (and compliant ones >77.47).
    """
    limits = _get_limits()
    soglia_bollo = Decimal(limits["soglia_marca_bollo"])

    checks: list[BolloCheck] = []
    for f in fatture:
        importo = Decimal(str(f.get("importo", "0")))
        numero = str(f.get("numero", f.get("numero_fattura", "N/A")))

        if importo > soglia_bollo:
            bollo_presente = f.get("bollo", False)
            conforme = bool(bollo_presente)
            if not conforme:
                msg = (f"Fattura {numero}: importo {importo} EUR > {soglia_bollo} EUR, "
                       f"marca da bollo 2 EUR potenzialmente mancante.")
            else:
                msg = f"Fattura {numero}: marca da bollo correttamente applicata."

            checks.append(BolloCheck(
                numero_fattura=numero,
                importo_fattura=importo,
                bollo_richiesto=True,
                bollo_presente=conforme,
                conforme=conforme,
                messaggio=msg,
            ))

    return checks


def _check_inps(profile: dict, anno: int) -> InpsCheck:
    """Check INPS contribution compliance.

    For artigiani/commercianti: verify quarterly fixed payments are on track.
    For gestione separata: verify percentage-based calculation.

    Args:
        profile: Contribuente profile dict.
        anno: Fiscal year.

    Returns:
        InpsCheck with contribution compliance status.
    """
    anagrafica = profile.get("anagrafica", profile)
    gestione = anagrafica.get("gestione_inps", "separata")
    riduzione_35 = anagrafica.get("riduzione_inps_35", False)

    try:
        rates = _get_inps_rates(anno, gestione)
    except ValueError as e:
        return InpsCheck(
            gestione=gestione,
            conforme=False,
            messaggio=str(e),
        )

    pagamenti = profile.get("pagamenti", [])
    inps_versato = sum(
        Decimal(str(p.get("importo", "0")))
        for p in pagamenti
        if p.get("anno") == anno and "inps" in p.get("tipo", "").lower()
    )

    today = date.today()

    if gestione in ("artigiani", "commercianti"):
        fisso_annuo = Decimal(rates["contributo_fisso_annuo"])
        fisso_trim = Decimal(rates["contributo_fisso_trimestrale"])

        if riduzione_35:
            fisso_annuo = _round(fisso_annuo * Decimal("0.65"))
            fisso_trim = _round(fisso_trim * Decimal("0.65"))

        # Check which quarterly payments should have been made
        scadenze_trim = [
            (date(anno, 2, 16), "Q1"),
            (date(anno, 5, 16), "Q2"),
            (date(anno, 8, 20), "Q3"),
            (date(anno, 11, 16), "Q4"),
        ]

        rate_scadute = 0
        rate_mancanti: list[str] = []
        for data_scad, trimestre in scadenze_trim:
            if today > data_scad:
                rate_scadute += 1
                # Check if payment for this quarter exists
                q_pagato = any(
                    p.get("scadenza_id", "") == f"fisso_{trimestre.lower()}"
                    and p.get("anno") == anno
                    for p in pagamenti
                )
                if not q_pagato:
                    rate_mancanti.append(trimestre)

        importo_dovuto_finora = _round(fisso_trim * Decimal(str(rate_scadute)))
        conforme = inps_versato >= importo_dovuto_finora or len(rate_mancanti) == 0

        return InpsCheck(
            gestione=gestione,
            contributo_dovuto_annuo=fisso_annuo,
            contributo_versato=inps_versato,
            conforme=conforme,
            rate_mancanti=rate_mancanti,
            messaggio=(
                f"INPS {gestione}: contributo fisso annuo {fisso_annuo} EUR "
                f"({'ridotto 35%' if riduzione_35 else 'intero'}). "
                f"Versato finora: {inps_versato} EUR. "
                f"Rate mancanti: {', '.join(rate_mancanti) if rate_mancanti else 'nessuna'}."
            ),
        )

    else:  # gestione separata
        aliquota = Decimal(rates["aliquota"])
        # We cannot know the exact contribution due without reddito imponibile,
        # so we report the rate and what has been paid.
        return InpsCheck(
            gestione=gestione,
            contributo_dovuto_annuo=Decimal("0"),  # depends on reddito
            contributo_versato=inps_versato,
            conforme=True,  # will be verified at year-end
            messaggio=(
                f"INPS gestione separata: aliquota {aliquota}. "
                f"Versato finora: {inps_versato} EUR. "
                f"Il contributo effettivo dipende dal reddito imponibile."
            ),
        )


def check_anomalie(fatture: list[dict]) -> list[Anomalia]:
    """Detect anomalies in invoicing patterns.

    Checks for:
    - Client concentration (>50% of revenue from a single client)
    - Gaps in invoice numbering
    - Unusually large or small invoices compared to the average
    - Suspicious patterns (e.g., many invoices just below bollo threshold)

    Args:
        fatture: List of invoice dicts with 'numero', 'importo', 'cliente', 'data'.

    Returns:
        List of detected anomalies.
    """
    if not fatture:
        return []

    anomalie: list[Anomalia] = []
    totale = Decimal("0")
    per_cliente: dict[str, Decimal] = {}
    numeri: list[int] = []
    importi: list[Decimal] = []

    for f in fatture:
        importo = Decimal(str(f.get("importo", "0")))
        cliente = f.get("cliente", f.get("cliente_nome", "sconosciuto"))
        numero_raw = f.get("numero", f.get("numero_fattura", ""))

        totale += importo
        importi.append(importo)
        per_cliente[cliente] = per_cliente.get(cliente, Decimal("0")) + importo

        # Try to extract numeric part for gap detection
        try:
            num = int(str(numero_raw).split("/")[-1].split("-")[-1])
            numeri.append(num)
        except (ValueError, IndexError):
            pass

    # --- Client concentration ---
    if totale > Decimal("0"):
        for cliente, importo_cliente in per_cliente.items():
            percentuale = _round((importo_cliente / totale) * Decimal("100"))
            if percentuale > Decimal("50"):
                anomalie.append(Anomalia(
                    tipo="concentrazione_cliente",
                    severita="warning",
                    descrizione=(
                        f"Il cliente '{cliente}' rappresenta il {percentuale}% "
                        f"del fatturato totale ({importo_cliente} EUR su {totale} EUR). "
                        f"Potrebbe configurare un rapporto di lavoro subordinato mascherato."
                    ),
                    dettaglio={
                        "cliente": cliente,
                        "importo": str(importo_cliente),
                        "percentuale": str(percentuale),
                        "totale": str(totale),
                    },
                ))

    # --- Invoice numbering gaps ---
    if numeri:
        numeri_sorted = sorted(set(numeri))
        if len(numeri_sorted) > 1:
            for i in range(1, len(numeri_sorted)):
                gap = numeri_sorted[i] - numeri_sorted[i - 1]
                if gap > 1:
                    anomalie.append(Anomalia(
                        tipo="gap_numerazione",
                        severita="warning",
                        descrizione=(
                            f"Gap nella numerazione fatture: da {numeri_sorted[i - 1]} "
                            f"a {numeri_sorted[i]} (mancano {gap - 1} numeri). "
                            f"Verificare se sono state emesse note di credito o fatture annullate."
                        ),
                        dettaglio={
                            "da": numeri_sorted[i - 1],
                            "a": numeri_sorted[i],
                            "numeri_mancanti": gap - 1,
                        },
                    ))

    # --- Unusual invoice amounts ---
    if len(importi) >= 3:
        media = _round(sum(importi) / Decimal(str(len(importi))))
        for f in fatture:
            importo = Decimal(str(f.get("importo", "0")))
            numero = str(f.get("numero", f.get("numero_fattura", "N/A")))
            if media > Decimal("0"):
                rapporto = importo / media
                if rapporto > Decimal("3"):
                    anomalie.append(Anomalia(
                        tipo="importo_anomalo",
                        severita="info",
                        descrizione=(
                            f"Fattura {numero}: importo {importo} EUR significativamente "
                            f"superiore alla media ({media} EUR). Verificare correttezza."
                        ),
                        dettaglio={
                            "numero": numero,
                            "importo": str(importo),
                            "media": str(media),
                            "rapporto": str(_round(rapporto)),
                        },
                    ))

    # --- Suspicious bollo avoidance ---
    soglia_bollo = Decimal("77.47")
    fatture_sotto_soglia = [
        f for f in fatture
        if Decimal("70") <= Decimal(str(f.get("importo", "0"))) <= soglia_bollo
    ]
    if len(fatture_sotto_soglia) >= 3 and len(fatture) >= 5:
        pct = _round(Decimal(str(len(fatture_sotto_soglia))) / Decimal(str(len(fatture))) * Decimal("100"))
        if pct > Decimal("30"):
            anomalie.append(Anomalia(
                tipo="sospetto_evasione_bollo",
                severita="info",
                descrizione=(
                    f"{len(fatture_sotto_soglia)} fatture ({pct}%) con importo tra 70 e 77.47 EUR. "
                    f"Pattern potenzialmente sospetto di evasione marca da bollo."
                ),
                dettaglio={
                    "conteggio": len(fatture_sotto_soglia),
                    "percentuale": str(pct),
                },
            ))

    return anomalie


def check_compliance(profile: dict, anno: int | None = None) -> ComplianceReport:
    """Run a full compliance check for a contribuente.

    Aggregates results from all sub-checks: threshold monitoring, deadline
    compliance, INPS contributions, marca da bollo, and anomaly detection.

    Args:
        profile: Contribuente profile dict (from SupervisorStore).
        anno: Fiscal year (defaults to current year).

    Returns:
        ComplianceReport with all findings.
    """
    if anno is None:
        anno = date.today().year

    contribuente_id = profile.get("contribuente_id", profile.get("anagrafica", {}).get("codice_fiscale", "unknown"))

    fatture = profile.get("fatture", [])

    report = ComplianceReport(
        contribuente_id=contribuente_id,
        anno=anno,
    )

    # 1. Revenue threshold check
    report.soglia = check_soglia_85k(fatture, anno)
    if report.soglia.livello_alert != "ok":
        report.messaggi.append(report.soglia.messaggio)

    # 2. Deadline compliance
    report.scadenze = check_scadenze(profile, anno)
    for scad in report.scadenze:
        if scad.scaduto:
            report.messaggi.append(scad.messaggio)

    # 3. INPS compliance
    report.inps = _check_inps(profile, anno)
    if not report.inps.conforme:
        report.messaggi.append(report.inps.messaggio)

    # 4. Marca da bollo
    report.bolli = _check_bolli(fatture)
    for bollo in report.bolli:
        if not bollo.conforme:
            report.messaggi.append(bollo.messaggio)

    # 5. Anomaly detection
    report.anomalie = check_anomalie(fatture)
    for anomalia in report.anomalie:
        report.messaggi.append(f"[{anomalia.severita.upper()}] {anomalia.descrizione}")

    # Overall status
    report.alert_count = (
        (1 if report.soglia.livello_alert != "ok" else 0)
        + sum(1 for s in report.scadenze if s.scaduto)
        + (0 if report.inps.conforme else 1)
        + sum(1 for b in report.bolli if not b.conforme)
        + sum(1 for a in report.anomalie if a.severita in ("warning", "critical"))
    )

    if report.soglia.livello_alert == "critical" or any(s.scaduto for s in report.scadenze):
        report.overall_status = "critical"
    elif report.alert_count > 0:
        report.overall_status = "warning"
    else:
        report.overall_status = "ok"

    return report


def genera_alert(report: ComplianceReport) -> list[dict]:
    """Generate structured alerts from a ComplianceReport for Agent9.

    Args:
        report: Completed ComplianceReport.

    Returns:
        List of alert dicts ready for Agent9 notification system.
    """
    alerts: list[dict] = []

    # Soglia alert
    if report.soglia and report.soglia.livello_alert != "ok":
        priority = "high" if report.soglia.livello_alert == "critical" else "medium"
        alerts.append({
            "type": "soglia_85k",
            "priority": priority,
            "contribuente_id": report.contribuente_id,
            "anno": report.anno,
            "title": f"Soglia 85k: {report.soglia.livello_alert}",
            "message": report.soglia.messaggio,
            "data": {
                "fatturato": str(report.soglia.fatturato_corrente),
                "percentuale": str(report.soglia.percentuale_raggiunta),
                "proiezione": str(report.soglia.proiezione_annua),
                "superata": report.soglia.superata,
            },
        })

    # Scadenze scadute
    for scad in report.scadenze:
        if scad.scaduto:
            alerts.append({
                "type": "scadenza_mancata",
                "priority": "high",
                "contribuente_id": report.contribuente_id,
                "anno": report.anno,
                "title": f"Scadenza mancata: {scad.descrizione}",
                "message": scad.messaggio,
                "data": {
                    "scadenza_id": scad.scadenza_id,
                    "data_scadenza": scad.data_scadenza.isoformat(),
                },
            })
        elif scad.giorni_rimasti <= 7 and not scad.pagato:
            alerts.append({
                "type": "scadenza_imminente",
                "priority": "medium",
                "contribuente_id": report.contribuente_id,
                "anno": report.anno,
                "title": f"Scadenza imminente: {scad.descrizione}",
                "message": scad.messaggio,
                "data": {
                    "scadenza_id": scad.scadenza_id,
                    "data_scadenza": scad.data_scadenza.isoformat(),
                    "giorni_rimasti": scad.giorni_rimasti,
                },
            })

    # INPS non conforme
    if report.inps and not report.inps.conforme:
        alerts.append({
            "type": "inps_non_conforme",
            "priority": "medium",
            "contribuente_id": report.contribuente_id,
            "anno": report.anno,
            "title": f"INPS {report.inps.gestione}: contributi non in regola",
            "message": report.inps.messaggio,
            "data": {
                "gestione": report.inps.gestione,
                "dovuto": str(report.inps.contributo_dovuto_annuo),
                "versato": str(report.inps.contributo_versato),
                "rate_mancanti": report.inps.rate_mancanti,
            },
        })

    # Bolli mancanti
    bolli_mancanti = [b for b in report.bolli if not b.conforme]
    if bolli_mancanti:
        alerts.append({
            "type": "bollo_mancante",
            "priority": "low",
            "contribuente_id": report.contribuente_id,
            "anno": report.anno,
            "title": f"{len(bolli_mancanti)} fatture senza marca da bollo",
            "message": "; ".join(b.messaggio for b in bolli_mancanti),
            "data": {
                "fatture": [b.numero_fattura for b in bolli_mancanti],
            },
        })

    # Anomalie
    for anomalia in report.anomalie:
        if anomalia.severita in ("warning", "critical"):
            alerts.append({
                "type": f"anomalia_{anomalia.tipo}",
                "priority": "medium" if anomalia.severita == "warning" else "high",
                "contribuente_id": report.contribuente_id,
                "anno": report.anno,
                "title": f"Anomalia: {anomalia.tipo}",
                "message": anomalia.descrizione,
                "data": anomalia.dettaglio,
            })

    return alerts
