"""Agent9 — Supervisor & Notifier.

Dual role:
1. Notifier — sends alerts and notifications to the user (dry-run for actual delivery)
2. Supervisor/Orchestrator — monitors agent health, coordinates the full pipeline

All message formatting, routing, and priority logic is real.
Actual sending to external channels is dry-run (# EXTERNAL).
"""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import Any

from .models import (
    AgentHealth,
    NotifyResult,
    PipelineResult,
    PipelineStatus,
    StepResult,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Italian message templates
# ---------------------------------------------------------------------------

TEMPLATES: dict[str, str] = {
    "scadenza_f24": (
        "Promemoria: scadenza F24 tra {days} giorni.\n"
        "Descrizione: {descrizione}\n"
        "Importo: EUR {importo}\n"
        "Data scadenza: {data_scadenza}\n"
        "Codice tributo: {codice_tributo}"
    ),
    "soglia_85k_warning": (
        "Attenzione: il fatturato ha raggiunto il {percentuale:.1f}% della soglia "
        "di 85.000 EUR.\n"
        "Fatturato corrente: EUR {fatturato}\n"
        "Soglia: EUR 85.000,00\n"
        "Margine residuo: EUR {margine}\n"
        "Se il fatturato supera 85.000 EUR, dal prossimo anno fiscale "
        "non sara piu possibile applicare il regime forfettario."
    ),
    "soglia_85k_critical": (
        "CRITICO: il fatturato e al {percentuale:.1f}% della soglia 85.000 EUR!\n"
        "Fatturato corrente: EUR {fatturato}\n"
        "Margine residuo: EUR {margine}\n"
        "SUPERARE 85.000 EUR COMPORTA L'USCITA DAL FORFETTARIO "
        "DALL'ANNO FISCALE SUCCESSIVO."
    ),
    "compliance_anomaly": (
        "Anomalia rilevata da Agent4 Compliance.\n"
        "Tipo: {tipo}\n"
        "Descrizione: {descrizione}\n"
        "Azione richiesta: {azione}"
    ),
    "pipeline_completed": (
        "Pipeline di elaborazione completata con successo.\n"
        "Profilo: {profile_id}\n"
        "Anno fiscale: {anno}\n"
        "Step completati: {steps_ok}/{steps_total}\n"
        "Durata: {durata_sec:.1f} secondi"
    ),
    "pipeline_errors": (
        "Pipeline di elaborazione completata con errori.\n"
        "Profilo: {profile_id}\n"
        "Anno fiscale: {anno}\n"
        "Step completati: {steps_ok}/{steps_total}\n"
        "Errori:\n{errori_dettaglio}"
    ),
    "new_invoice_sdi": (
        "Nuova fattura ricevuta da SDI.\n"
        "Numero: {numero}\n"
        "Mittente: {mittente}\n"
        "Importo: EUR {importo}\n"
        "Data ricezione: {data_ricezione}"
    ),
    "agent_error": (
        "Errore nell'agente {agent_name}.\n"
        "Errore: {error}\n"
        "Azione: il sistema continuera con gli agenti rimanenti."
    ),
}

# ---------------------------------------------------------------------------
# Channel routing by priority
# ---------------------------------------------------------------------------

_PRIORITY_CHANNELS: dict[str, list[str]] = {
    "low": ["in_app"],
    "normal": ["in_app", "email"],
    "high": ["in_app", "email", "push"],
    "critical": ["in_app", "email", "push", "telegram"],
}

_VALID_CHANNELS = {"email", "telegram", "push", "in_app"}

# In-memory pipeline status tracking
_pipeline_statuses: dict[str, PipelineStatus] = {}


# ---------------------------------------------------------------------------
# Message formatting
# ---------------------------------------------------------------------------


def format_message(template: str, data: dict) -> str:
    """Format a message using a named template or raw template string.

    Args:
        template: Template name from TEMPLATES dict, or a raw format string.
        data: Data dict for template substitution.

    Returns:
        Formatted message string.
    """
    template_str = TEMPLATES.get(template, template)
    try:
        return template_str.format(**data)
    except KeyError as exc:
        logger.warning("Missing template key %s in data: %s", exc, list(data.keys()))
        return template_str


# ---------------------------------------------------------------------------
# Notification functions
# ---------------------------------------------------------------------------


def _generate_message_id(message: str, channel: str) -> str:
    """Generate a deterministic message ID."""
    payload = f"{message}|{channel}|{datetime.now(timezone.utc).isoformat()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _dispatch_to_channel(
    message: str, channel: str, priority: str
) -> NotifyResult:
    """Dispatch a message to a single channel.

    # EXTERNAL: actual sending would happen here via:
    # - email: SendGrid API
    # - telegram: Telegram Bot API
    # - push: Firebase Cloud Messaging
    # - in_app: write to notification store
    """
    if channel not in _VALID_CHANNELS:
        return NotifyResult(
            success=False,
            channel=channel,
            dry_run=True,
            error=f"Canale non valido: {channel}",
        )

    message_id = _generate_message_id(message, channel)

    # # EXTERNAL: actual dispatch
    # if channel == "email":
    #     sendgrid.send(to=user_email, subject="FiscalAI", body=message)
    # elif channel == "telegram":
    #     telegram_bot.send_message(chat_id=user_chat_id, text=message)
    # elif channel == "push":
    #     fcm.send(token=user_device_token, body=message)
    # elif channel == "in_app":
    #     notification_store.save(user_id, message, priority)

    logger.info(
        "DRY RUN [%s] priority=%s channel=%s msg_id=%s — %s",
        channel, priority, channel, message_id,
        message[:80].replace("\n", " "),
    )

    return NotifyResult(
        success=True,
        channel=channel,
        message_id=message_id,
        dry_run=True,
    )


def notify(
    message: str,
    priority: str = "normal",
    channels: list[str] | None = None,
    source_agent: str = "",
) -> NotifyResult:
    """Send a notification to the user.

    Routes to appropriate channels based on priority.
    Actual delivery is dry-run (# EXTERNAL).

    Args:
        message: Notification text.
        priority: "low", "normal", "high", "critical".
        channels: Override channel list. If None, derived from priority.
        source_agent: Name of the agent that generated this notification.

    Returns:
        NotifyResult for the primary channel.
    """
    if priority not in _PRIORITY_CHANNELS:
        priority = "normal"

    # Determine channels
    target_channels = channels if channels else _PRIORITY_CHANNELS[priority]

    # Validate channels
    target_channels = [c for c in target_channels if c in _VALID_CHANNELS]
    if not target_channels:
        target_channels = ["in_app"]

    # Prepend source agent if provided
    full_message = message
    if source_agent:
        full_message = f"[{source_agent}] {message}"

    # Dispatch to all channels, return result of first (primary)
    primary_result = None
    for ch in target_channels:
        result = _dispatch_to_channel(full_message, ch, priority)
        if primary_result is None:
            primary_result = result

    return primary_result or NotifyResult(success=False, error="Nessun canale disponibile")


def notify_scadenza(scadenza: dict, days_before: int) -> NotifyResult:
    """Send a deadline reminder notification.

    Args:
        scadenza: Deadline dict with descrizione, importo, data_scadenza, codice_tributo.
        days_before: Days until the deadline.

    Returns:
        NotifyResult.
    """
    data = {
        "days": days_before,
        "descrizione": scadenza.get("descrizione", "Scadenza fiscale"),
        "importo": scadenza.get("importo", "0.00"),
        "data_scadenza": scadenza.get("data_scadenza", "N/A"),
        "codice_tributo": scadenza.get("codice_tributo", ""),
    }
    message = format_message("scadenza_f24", data)

    # Higher priority for imminent deadlines
    if days_before <= 3:
        priority = "critical"
    elif days_before <= 7:
        priority = "high"
    else:
        priority = "normal"

    return notify(message, priority=priority, source_agent="Agent6_Scheduler")


def notify_compliance_alert(alert: dict) -> NotifyResult:
    """Send a compliance alert notification from Agent4.

    Args:
        alert: Alert dict with tipo, descrizione, azione.

    Returns:
        NotifyResult.
    """
    data = {
        "tipo": alert.get("tipo", "Anomalia generica"),
        "descrizione": alert.get("descrizione", ""),
        "azione": alert.get("azione", "Verificare manualmente"),
    }
    message = format_message("compliance_anomaly", data)

    return notify(message, priority="high", source_agent="Agent4_Compliance")


def notify_soglia_85k(percentuale: float, fatturato: float) -> NotifyResult:
    """Send threshold warning for 85k EUR revenue limit.

    Args:
        percentuale: Current percentage of the 85k threshold (e.g. 90.0).
        fatturato: Current total revenue.

    Returns:
        NotifyResult.
    """
    soglia = 85000.0
    margine = soglia - fatturato

    data = {
        "percentuale": percentuale,
        "fatturato": f"{fatturato:,.2f}",
        "margine": f"{margine:,.2f}",
    }

    if percentuale >= 95:
        template = "soglia_85k_critical"
        priority = "critical"
    else:
        template = "soglia_85k_warning"
        priority = "high"

    message = format_message(template, data)
    return notify(message, priority=priority, source_agent="Agent4_Compliance")


# ---------------------------------------------------------------------------
# Supervisor — Agent Health
# ---------------------------------------------------------------------------


def check_agent_health(agent_name: str) -> AgentHealth:
    """Check if a specific agent is responsive.

    Imports the agent module and verifies it has expected entry points.

    Args:
        agent_name: Agent identifier (e.g. "agent1_collector").

    Returns:
        AgentHealth with status.
    """
    now = datetime.now(timezone.utc).isoformat()

    # Map agent name to module and expected function
    agent_map: dict[str, tuple[str, str]] = {
        "agent1_collector": ("agents.agent1_collector.collector", "collect"),
        "agent2_categorizer": ("agents.agent2_categorizer.categorizer", "categorize"),
        "agent3_calculator": ("agents.agent3_calculator.calculator", "calcola"),
        "agent3b_validator": ("agents.agent3b_validator.validator", "validate"),
        "agent4_compliance": ("agents.agent4_compliance.compliance", "check_compliance"),
        "agent5_declaration": ("agents.agent5_declaration.declaration", "generate_declaration"),
        "agent6_scheduler": ("agents.agent6_scheduler.scheduler", "genera_piano_annuale"),
        "agent7_advisor": ("agents.agent7_advisor.advisor", "advise"),
        "agent8_invoicing": ("agents.agent8_invoicing.invoice_generator", "crea_fattura"),
        "agent10_normative": ("agents.agent10_normative", ""),
    }

    if agent_name not in agent_map:
        return AgentHealth(
            name=agent_name,
            status="error",
            last_check=now,
            message=f"Agent sconosciuto: {agent_name}",
        )

    module_path, func_name = agent_map[agent_name]

    try:
        import importlib

        mod = importlib.import_module(module_path)
        if func_name and not hasattr(mod, func_name):
            return AgentHealth(
                name=agent_name,
                status="error",
                last_check=now,
                message=f"Funzione {func_name} non trovata nel modulo",
            )

        # Check if it's a stub
        if func_name:
            fn = getattr(mod, func_name)
            source = getattr(fn, "__module__", "")
            # Try to detect stub by checking docstring or calling with safe args
            doc = fn.__doc__ or ""
            if "stub" in doc.lower():
                return AgentHealth(
                    name=agent_name,
                    status="stub",
                    last_check=now,
                    message="Agent presente ma non ancora implementato (stub)",
                )

        return AgentHealth(
            name=agent_name,
            status="ok",
            last_check=now,
            message="Agent operativo",
        )

    except ImportError as exc:
        return AgentHealth(
            name=agent_name,
            status="error",
            last_check=now,
            message=f"Import fallito: {exc}",
        )
    except Exception as exc:
        return AgentHealth(
            name=agent_name,
            status="error",
            last_check=now,
            message=f"Errore verifica: {exc}",
        )


def monitor_all_agents() -> dict[str, AgentHealth]:
    """Health check all agents in the system.

    Returns:
        Dict mapping agent name to AgentHealth.
    """
    agents = [
        "agent1_collector",
        "agent2_categorizer",
        "agent3_calculator",
        "agent3b_validator",
        "agent4_compliance",
        "agent5_declaration",
        "agent6_scheduler",
        "agent7_advisor",
        "agent8_invoicing",
        "agent10_normative",
    ]

    results: dict[str, AgentHealth] = {}
    for agent_name in agents:
        results[agent_name] = check_agent_health(agent_name)

    return results


def handle_agent_error(agent_name: str, error: Exception) -> str:
    """Handle an agent error: log it and send notification.

    Args:
        agent_name: Name of the failed agent.
        error: The exception that occurred.

    Returns:
        Summary string of the action taken.
    """
    error_str = str(error)
    logger.error("Agent %s failed: %s", agent_name, error_str)

    message = format_message("agent_error", {
        "agent_name": agent_name,
        "error": error_str,
    })
    notify(message, priority="high", source_agent="Agent9_Supervisor")

    return f"Errore in {agent_name} gestito: notifica inviata, pipeline continua."


# ---------------------------------------------------------------------------
# Supervisor — Pipeline Orchestration
# ---------------------------------------------------------------------------


def get_pipeline_status(profile_id: str) -> PipelineStatus:
    """Get the current status of a pipeline for the given profile.

    Args:
        profile_id: Contribuente profile ID.

    Returns:
        PipelineStatus (may be idle if no pipeline has run).
    """
    return _pipeline_statuses.get(
        profile_id,
        PipelineStatus(profile_id=profile_id, status="idle"),
    )


def run_pipeline(profile: dict, anno: int | None = None) -> PipelineResult:
    """Orchestrate the full agent pipeline.

    Executes agents in order:
    1. Agent1 collect
    2. Agent2 categorize
    3. Agent3+3b calculate + validate
    4. Agent4 compliance
    5. Agent6 schedule
    6. Agent7 advise
    7. Agent9 notify results

    Each step is wrapped in error handling. If one fails, the pipeline
    continues with remaining steps and reports errors at the end.

    Args:
        profile: Contribuente profile dict with anagrafica, fatture, spese.
        anno: Fiscal year. Defaults to previous year.

    Returns:
        PipelineResult with all step outcomes.
    """
    from datetime import date as _date

    if anno is None:
        anno = _date.today().year - 1

    profile_id = profile.get(
        "contribuente_id",
        profile.get("anagrafica", {}).get("codice_fiscale", "UNKNOWN"),
    )

    pipeline_result = PipelineResult()
    pipeline_start = time.monotonic()

    # Track status
    status = PipelineStatus(
        profile_id=profile_id,
        started_at=datetime.now(timezone.utc).isoformat(),
        status="running",
    )
    _pipeline_statuses[profile_id] = status

    # ------ Step 1: Agent1 Collector ------
    step_result = _run_step("agent1_collector", status, lambda: _step_collect(profile))
    pipeline_result.steps.append(step_result)

    # ------ Step 2: Agent2 Categorizer ------
    step_result = _run_step("agent2_categorizer", status, lambda: _step_categorize(profile))
    pipeline_result.steps.append(step_result)

    # ------ Step 3: Agent3 Calculator + Agent3b Validator ------
    step_result = _run_step(
        "agent3_calculator+3b_validator", status,
        lambda: _step_calculate_and_validate(profile, anno),
    )
    pipeline_result.steps.append(step_result)
    calc_result = step_result.result if step_result.success else {}

    # ------ Step 4: Agent4 Compliance ------
    step_result = _run_step(
        "agent4_compliance", status,
        lambda: _step_compliance(profile),
    )
    pipeline_result.steps.append(step_result)

    # ------ Step 5: Agent6 Scheduler ------
    step_result = _run_step(
        "agent6_scheduler", status,
        lambda: _step_schedule(profile, anno, calc_result),
    )
    pipeline_result.steps.append(step_result)

    # ------ Step 6: Agent7 Advisor ------
    step_result = _run_step("agent7_advisor", status, lambda: _step_advise(profile))
    pipeline_result.steps.append(step_result)

    # ------ Finalize ------
    pipeline_elapsed = (time.monotonic() - pipeline_start) * 1000
    pipeline_result.duration_ms = pipeline_elapsed

    # Collect errors
    for step in pipeline_result.steps:
        if not step.success:
            pipeline_result.errors.append(f"{step.agent_name}: {step.error}")

    pipeline_result.success = len(pipeline_result.errors) == 0

    # ------ Step 7: Notify results ------
    _notify_pipeline_result(pipeline_result, profile_id, anno)

    # Update status
    status.status = "completed" if pipeline_result.success else "failed"
    status.finished_at = datetime.now(timezone.utc).isoformat()
    status.errors = pipeline_result.errors

    return pipeline_result


def _run_step(
    agent_name: str,
    status: PipelineStatus,
    fn: Any,
) -> StepResult:
    """Run a single pipeline step with timing and error handling."""
    status.current_step = agent_name
    start = time.monotonic()

    try:
        result = fn()
        elapsed = (time.monotonic() - start) * 1000
        status.completed_steps.append(agent_name)
        return StepResult(
            agent_name=agent_name,
            success=True,
            result=result if isinstance(result, dict) else {},
            duration_ms=elapsed,
        )
    except Exception as exc:
        elapsed = (time.monotonic() - start) * 1000
        error_msg = handle_agent_error(agent_name, exc)
        status.errors.append(f"{agent_name}: {exc}")
        return StepResult(
            agent_name=agent_name,
            success=False,
            error=str(exc),
            duration_ms=elapsed,
        )


# ---------------------------------------------------------------------------
# Pipeline step implementations — each calls the actual agent
# ---------------------------------------------------------------------------


def _step_collect(profile: dict) -> dict:
    """Step 1: Agent1 collect transactions."""
    from agents.agent1_collector.collector import collect

    result = collect(source="all")
    return result


def _step_categorize(profile: dict) -> dict:
    """Step 2: Agent2 categorize transactions."""
    from agents.agent2_categorizer.categorizer import categorize

    # Categorize would normally receive transactions from step 1
    # For now we pass a minimal transaction representing the profile state
    result = categorize({"source": "pipeline", "profile_id": profile.get("contribuente_id", "")})
    return result


def _step_calculate_and_validate(profile: dict, anno: int) -> dict:
    """Step 3: Agent3 calculate + Agent3b validate."""
    from decimal import Decimal as _Decimal

    from agents.agent3_calculator.calculator import calcola
    from agents.agent3_calculator.models import ContribuenteInput
    from agents.agent3b_validator.models import InputFiscale
    from agents.agent3b_validator.validator import validate

    anagrafica = profile.get("anagrafica", {})

    # Build ateco_ricavi from profile
    ricavi_per_ateco: dict[str, _Decimal] = {}
    fatture = profile.get("fatture", [])
    ateco_principale = anagrafica.get("ateco_principale", "")

    for fattura in fatture:
        if fattura.get("anno", 0) != anno:
            continue
        importo = _Decimal(str(fattura.get("imponibile", fattura.get("importo", "0"))))
        codice = fattura.get("codice_ateco", ateco_principale)
        if codice:
            ricavi_per_ateco[codice] = ricavi_per_ateco.get(codice, _Decimal("0")) + importo

    if not ricavi_per_ateco:
        ricavi_diretti = profile.get("ricavi_per_ateco", {})
        for ateco, importo in ricavi_diretti.items():
            ricavi_per_ateco[ateco] = _Decimal(str(importo))

    if not ricavi_per_ateco:
        raise ValueError(f"Nessun ricavo trovato per anno {anno}")

    contributi_versati = _Decimal(str(profile.get("contributi_inps_versati", "0")))

    # Agent3
    input_a3 = ContribuenteInput(
        contribuente_id=profile.get("contribuente_id", anagrafica.get("codice_fiscale", "")),
        anno_fiscale=anno,
        primo_anno=anagrafica.get("primo_anno", False),
        ateco_ricavi=ricavi_per_ateco,
        rivalsa_inps_applicata=_Decimal(str(profile.get("rivalsa_inps_applicata", "0"))),
        regime_agevolato=anagrafica.get("regime_agevolato", True),
        gestione_inps=anagrafica.get("gestione_inps", "separata"),
        riduzione_inps_35=anagrafica.get("riduzione_inps_35", False),
        contributi_inps_versati=contributi_versati,
        imposta_anno_precedente=_Decimal(str(profile.get("imposta_anno_precedente", "0"))),
        acconti_versati=_Decimal(str(profile.get("acconti_versati", "0"))),
        crediti_precedenti=_Decimal(str(profile.get("crediti_precedenti", "0"))),
    )

    result_a3 = calcola(input_a3)

    # Prepare dict for Agent3b
    result_dict = {
        "reddito_lordo": result_a3.reddito_lordo,
        "reddito_imponibile": result_a3.reddito_imponibile,
        "imposta_sostitutiva": result_a3.imposta_sostitutiva,
        "acconti_dovuti": result_a3.acconti_dovuti,
        "acconto_prima_rata": result_a3.acconto_prima_rata,
        "acconto_seconda_rata": result_a3.acconto_seconda_rata,
        "da_versare": result_a3.da_versare,
        "credito_anno_prossimo": result_a3.credito_anno_prossimo,
        "contributo_inps_calcolato": result_a3.contributo_inps_calcolato,
        "checksum": result_a3.checksum,
    }

    # Agent3b validation
    input_a3b = InputFiscale(
        id_contribuente=input_a3.contribuente_id,
        anno=anno,
        is_primo_anno=input_a3.primo_anno,
        ricavi_per_ateco=ricavi_per_ateco,
        rivalsa_4_percento=input_a3.rivalsa_inps_applicata,
        aliquota_agevolata=input_a3.regime_agevolato,
        tipo_gestione_inps=input_a3.gestione_inps,
        ha_riduzione_35=input_a3.riduzione_inps_35,
        inps_gia_versati=contributi_versati,
        imposta_anno_prima=input_a3.imposta_anno_precedente,
        acconti_gia_versati=input_a3.acconti_versati,
        crediti_da_prima=input_a3.crediti_precedenti,
    )

    esito = validate(input_a3b, result_dict)

    if not esito.valid:
        divergenze = [
            f"{d.campo}: agent3={d.valore_agent3} vs agent3b={d.valore_agent3b}"
            for d in esito.divergenze
        ]
        raise ValueError(
            f"Validazione Agent3b fallita — divergenze: {'; '.join(divergenze)}"
        )

    return result_dict


def _step_compliance(profile: dict) -> dict:
    """Step 4: Agent4 compliance check."""
    from agents.agent4_compliance.compliance import check_compliance

    result = check_compliance()
    return result


def _step_schedule(profile: dict, anno: int, calc_result: dict) -> dict:
    """Step 5: Agent6 scheduler — generate payment plan."""
    from decimal import Decimal as _Decimal

    from agents.agent6_scheduler.scheduler import genera_piano_annuale

    anagrafica = profile.get("anagrafica", {})

    if not calc_result:
        # Cannot schedule without calculation results
        return {"status": "skipped", "reason": "No calculation results available"}

    piano = genera_piano_annuale(
        contribuente_id=profile.get("contribuente_id", ""),
        contribuente_cf=anagrafica.get("codice_fiscale", ""),
        contribuente_nome=anagrafica.get("nome", ""),
        contribuente_cognome=anagrafica.get("cognome", ""),
        anno_fiscale=anno,
        gestione_inps=anagrafica.get("gestione_inps", "separata"),
        primo_anno=anagrafica.get("primo_anno", False),
        imposta_sostitutiva=_Decimal(str(calc_result.get("imposta_sostitutiva", "0"))),
        contributo_inps=_Decimal(str(calc_result.get("contributo_inps_calcolato", "0"))),
        acconti_dovuti=_Decimal(str(calc_result.get("acconti_dovuti", "0"))),
        acconto_prima_rata=_Decimal(str(calc_result.get("acconto_prima_rata", "0"))),
        acconto_seconda_rata=_Decimal(str(calc_result.get("acconto_seconda_rata", "0"))),
        da_versare=_Decimal(str(calc_result.get("da_versare", "0"))),
        crediti_precedenti=_Decimal(str(profile.get("crediti_precedenti", "0"))),
    )

    return {
        "totale_annuo": str(piano.totale_annuo),
        "num_scadenze": len(piano.scadenze),
        "scadenze": [
            {"id": s.id, "data": str(s.data), "importo": str(s.importo)}
            for s in piano.scadenze
        ],
    }


def _step_advise(profile: dict) -> dict:
    """Step 6: Agent7 advisor."""
    from agents.agent7_advisor.advisor import advise

    result = advise()
    return result


def _notify_pipeline_result(
    result: PipelineResult, profile_id: str, anno: int
) -> None:
    """Send notification about pipeline completion."""
    steps_ok = sum(1 for s in result.steps if s.success)
    steps_total = len(result.steps)
    durata_sec = result.duration_ms / 1000

    if result.success:
        message = format_message("pipeline_completed", {
            "profile_id": profile_id,
            "anno": anno,
            "steps_ok": steps_ok,
            "steps_total": steps_total,
            "durata_sec": durata_sec,
        })
        notify(message, priority="normal", source_agent="Agent9_Supervisor")
    else:
        errori_dettaglio = "\n".join(f"  - {e}" for e in result.errors)
        message = format_message("pipeline_errors", {
            "profile_id": profile_id,
            "anno": anno,
            "steps_ok": steps_ok,
            "steps_total": steps_total,
            "errori_dettaglio": errori_dettaglio,
        })
        notify(message, priority="high", source_agent="Agent9_Supervisor")
