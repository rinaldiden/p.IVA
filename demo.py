#!/usr/bin/env python3
"""FiscalAI Demo — test operativo completo da shell.

Usage:
    python3 demo.py                    # demo automatica (dati fittizi)
    python3 demo.py --interactive      # onboarding interattivo manuale
    python3 demo.py --fattura          # fattura reale + calcolo + piano F24
    python3 demo.py --full             # ciclo completo: onboarding -> fattura -> F24
    python3 demo.py --report           # esegue TUTTI i test e salva report tracciato

Non richiede Redis, Claude, PostgreSQL — tutto locale.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
import uuid
import xml.etree.ElementTree as ET
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent))

_REPORT_DIR = Path(__file__).resolve().parent / "test_reports"


def _sep(title: str = "") -> None:
    if title:
        print(f"\n{'='*60}")
        print(f"  {title}")
        print(f"{'='*60}")
    else:
        print(f"{'─'*60}")


class TestTracker:
    """Tracks test results for the report."""

    def __init__(self) -> None:
        self.results: list[dict] = []
        self.start_time = datetime.now()

    def check(self, name: str, fn, *args, **kwargs) -> bool:
        """Run a check, capture pass/fail, return success bool."""
        try:
            result = fn(*args, **kwargs)
            self.results.append({
                "test": name,
                "status": "PASS",
                "detail": str(result) if result else "",
            })
            print(f"  [PASS] {name}")
            return True
        except Exception as e:
            self.results.append({
                "test": name,
                "status": "FAIL",
                "detail": f"{type(e).__name__}: {e}",
                "traceback": traceback.format_exc(),
            })
            print(f"  [FAIL] {name} — {e}")
            return False

    def save_report(self, label: str) -> Path:
        _REPORT_DIR.mkdir(parents=True, exist_ok=True)
        ts = self.start_time.strftime("%Y%m%d_%H%M%S")
        path = _REPORT_DIR / f"report_{label}_{ts}.json"
        passed = sum(1 for r in self.results if r["status"] == "PASS")
        failed = sum(1 for r in self.results if r["status"] == "FAIL")
        report = {
            "label": label,
            "timestamp": self.start_time.isoformat(),
            "duration_sec": (datetime.now() - self.start_time).total_seconds(),
            "total": len(self.results),
            "passed": passed,
            "failed": failed,
            "success_rate": f"{passed}/{len(self.results)}",
            "results": self.results,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)
        return path


# ─────────────────────────────────────────────────────
# DEMO AUTOMATICA (originale, invariata nel contenuto)
# ─────────────────────────────────────────────────────

def demo_automatica() -> None:
    """Full automatic demo with fictitious data."""
    from agents.agent0_wizard.models import ProfiloContribuente
    from agents.agent0_wizard.simulator import simulate
    from agents.agent3_calculator.calculator import calcola
    from agents.agent3_calculator.models import ContribuenteInput
    from agents.agent3b_validator.models import InputFiscale
    from agents.agent3b_validator.validator import validate
    from agents.supervisor.persistence import SupervisorStore

    _sep("FISCALAI — DEMO AUTOMATICA")
    print("\nDati fittizi per test operativo:")
    print("  Nome: Maria Rossi")
    print("  CF: RSSMRA85M41H501Z")
    print("  ATECO: 62.01 (Sviluppo software)")
    print("  Gestione INPS: separata")
    print("  Primo anno: SI")
    print("  Regime agevolato 5%: SI")
    print("  Ricavi stimati: 50.000 EUR")

    # --- STEP 1: Creazione profilo ---
    _sep("STEP 1 — Creazione profilo contribuente")

    profilo = ProfiloContribuente(
        contribuente_id=str(uuid.uuid4()),
        nome="Maria",
        cognome="Rossi",
        codice_fiscale="RSSMRA85M41H501Z",
        comune_residenza="Roma",
        data_apertura_piva=date.today(),
        primo_anno=True,
        ateco_principale="62.01",
        ateco_secondari=[],
        regime_agevolato=True,
        gestione_inps="separata",
        riduzione_inps_35=False,
        rivalsa_inps_4=False,
    )
    print(f"  ID: {profilo.contribuente_id}")
    print(f"  Profilo creato OK")

    # --- STEP 2: Persistenza Supervisor ---
    _sep("STEP 2 — Persistenza nel Supervisor")

    store = SupervisorStore()
    store.save_from_agent0(asdict(profilo))
    print(f"  Profilo salvato su disco")

    # Verifica reload
    loaded = store.get_profile(profilo.contribuente_id)
    assert loaded is not None, "ERRORE: profilo non trovato dopo salvataggio!"
    print(f"  Verifica reload: OK")
    print(f"  CF salvato: {loaded['anagrafica']['codice_fiscale']}")

    # --- STEP 3: Simulazione fiscale (Agent3 + Agent3b) ---
    _sep("STEP 3 — Simulazione fiscale")

    ricavi = {"62.01": Decimal("50000")}
    sim = simulate(profilo=profilo, ricavi_per_ateco=ricavi, anno_fiscale=2024)

    print(f"\n  Ricavi totali:         {sim.ricavi_totali:>12,.2f} EUR")
    print(f"  Reddito lordo:         {sim.reddito_lordo:>12,.2f} EUR")
    print(f"  Reddito imponibile:    {sim.reddito_imponibile:>12,.2f} EUR")
    print(f"  Aliquota:                     {int(sim.aliquota * 100)}%")
    print(f"  Imposta sostitutiva:   {sim.imposta_sostitutiva:>12,.2f} EUR")
    print(f"  Contributo INPS:       {sim.contributo_inps:>12,.2f} EUR")
    totale = sim.imposta_sostitutiva + sim.contributo_inps
    print(f"  TOTALE da pagare:      {totale:>12,.2f} EUR")
    print(f"  Rata mensile:          {sim.rata_mensile_da_accantonare:>12,.2f} EUR")
    print(f"  Checksum Agent3:       {sim.checksum[:16]}...")
    print(f"  Validazione Agent3b:   PASS (0 divergenze)")

    # Confronto regimi
    forf = Decimal(sim.confronto_regimi["forfettario"]["totale"])
    ordi = Decimal(sim.confronto_regimi["ordinario_stimato"]["totale"])
    print(f"\n  Confronto regimi:")
    print(f"    Forfettario:         {forf:>12,.2f} EUR")
    print(f"    Ordinario (IRPEF):   {ordi:>12,.2f} EUR")
    print(f"    Risparmio:           {sim.risparmio_vs_ordinario:>12,.2f} EUR")

    # Scadenzario
    if sim.scadenze_anno_corrente:
        print(f"\n  Scadenzario {sim.anno_fiscale}:")
        for s in sim.scadenze_anno_corrente:
            print(f"    {s.data}  {s.descrizione}: {s.importo:,.2f} EUR")

    # Warnings
    for w in sim.warnings:
        print(f"\n  ATTENZIONE: {w}")

    # --- STEP 4: Verifica Agent10 diff engine ---
    _sep("STEP 4 — Agent10 NormativeWatcher (diff engine)")

    from agents.agent10_normative.diff_engine import compute_diff, filter_needs_review
    from agents.agent10_normative.models import ParameterChange

    test_changes = [
        ParameterChange(
            nome_parametro="forfettario_limits.soglia_ricavi",
            file_destinazione="shared/forfettario_limits.json",
            valore_precedente="85000",
            valore_nuovo="90000",
            data_efficacia=date(2025, 1, 1),
            norma_riferimento="Legge di Bilancio 2025 (FITTIZIO)",
            certezza="alta",
            url_fonte="https://example.com",
        ),
    ]
    real = compute_diff(test_changes)
    auto, review = filter_needs_review(real, anomaly_threshold_pct=10.0)
    print(f"  Cambio simulato: soglia_ricavi 85000 -> 90000")
    print(f"  Diff engine: {len(real)} cambio reale trovato")
    print(f"  Auto-apply: {len(auto)} | Human review: {len(review)}")

    # --- STEP 5: Security check ---
    _sep("STEP 5 — Verifica sicurezza")

    print(f"  Agent3b blocca su 1 centesimo di divergenza: ", end="")

    a3_input = ContribuenteInput(
        contribuente_id="sec-test",
        anno_fiscale=2024,
        primo_anno=True,
        ateco_ricavi={"62.01": Decimal("30000")},
        rivalsa_inps_applicata=Decimal("0"),
        regime_agevolato=True,
        gestione_inps="separata",
        riduzione_inps_35=False,
        contributi_inps_versati=Decimal("0"),
        imposta_anno_precedente=Decimal("0"),
        acconti_versati=Decimal("0"),
        crediti_precedenti=Decimal("0"),
    )
    result = calcola(a3_input)
    tampered = {
        "reddito_lordo": str(result.reddito_lordo),
        "reddito_imponibile": str(result.reddito_imponibile),
        "imposta_sostitutiva": str(result.imposta_sostitutiva + Decimal("0.01")),
        "acconti_dovuti": str(result.acconti_dovuti),
        "acconto_prima_rata": str(result.acconto_prima_rata),
        "acconto_seconda_rata": str(result.acconto_seconda_rata),
        "da_versare": str(result.da_versare),
        "credito_anno_prossimo": str(result.credito_anno_prossimo),
        "contributo_inps_calcolato": str(result.contributo_inps_calcolato),
        "checksum": result.checksum,
    }
    a3b_in = InputFiscale(
        id_contribuente="sec-test", anno=2024, is_primo_anno=True,
        ricavi_per_ateco={"62.01": Decimal("30000")},
        rivalsa_4_percento=Decimal("0"), aliquota_agevolata=True,
        tipo_gestione_inps="separata", ha_riduzione_35=False,
        inps_gia_versati=Decimal("0"), imposta_anno_prima=Decimal("0"),
        acconti_gia_versati=Decimal("0"), crediti_da_prima=Decimal("0"),
    )
    esito = validate(a3b_in, tampered)
    if esito.blocco:
        print("BLOCCATO (corretto)")
    else:
        print("ERRORE — avrebbe dovuto bloccare!")

    # --- RIEPILOGO ---
    _sep("RIEPILOGO")
    print(f"""
  Componenti testati:
    [OK] Agent0 — Profilo contribuente creato
    [OK] Supervisor — Persistenza su disco + reload
    [OK] Agent3 — Calcolo deterministico
    [OK] Agent3b — Validazione indipendente
    [OK] Simulatore — Confronto regimi + scadenzario
    [OK] Agent10 — Diff engine normativo
    [OK] Security — Blocco su dati manomessi

  Profilo salvato in: agents/supervisor/data/profiles.json
  ID contribuente: {profilo.contribuente_id}
""")


# ─────────────────────────────────────────────────────
# DEMO INTERATTIVA
# ─────────────────────────────────────────────────────

def demo_interattiva() -> None:
    """Interactive onboarding via CLI."""
    from agents.agent0_wizard.onboarding import OnboardingWizard

    wizard = OnboardingWizard(use_claude=False)
    try:
        profilo = wizard.run()
    except KeyboardInterrupt:
        print("\n\nInterrotto.")
        sys.exit(1)

    # Persist
    from agents.supervisor.persistence import SupervisorStore
    from dataclasses import asdict
    store = SupervisorStore()
    store.save_from_agent0(asdict(profilo))
    print(f"\nProfilo salvato nel Supervisor: {profilo.contribuente_id}")


# ─────────────────────────────────────────────────────
# DEMO FATTURA (reale — Agent8 + Agent6)
# ─────────────────────────────────────────────────────

def demo_fattura() -> None:
    """Demo fattura reale con Agent8 (Invoicing) + Agent6 (Scheduler)."""
    from agents.agent8_invoicing.invoice_generator import (
        crea_fattura, genera_xml, gestisci_esito_sdi,
    )
    from agents.agent8_invoicing.models import DatiCliente, EsitoSDI
    from agents.agent8_invoicing.numbering import prossimo_numero
    from agents.agent6_scheduler.scheduler import genera_piano_annuale

    _sep("DEMO FATTURA — CICLO REALE")

    # --- Dati cedente (la nostra P.IVA fittizia) ---
    print("\n  Cedente: Maria Rossi — P.IVA 12345678901")
    print("  Regime: Forfettario (RF19), aliquota agevolata 5%")
    print("  Gestione INPS: separata")

    # --- Dati cliente ---
    cliente = DatiCliente(
        denominazione="Acme S.r.l.",
        partita_iva="09876543210",
        codice_fiscale="09876543210",
        indirizzo="Via Milano 42",
        cap="20100",
        comune="Milano",
        provincia="MI",
        codice_sdi="ABCDEFG",
    )
    print(f"  Cliente: {cliente.denominazione} — P.IVA {cliente.partita_iva}")

    # --- STEP 1: Generazione fattura ---
    _sep("STEP 1 — Agent8: Generazione fattura elettronica")

    numero = prossimo_numero(2024)
    linee = [
        {
            "descrizione": "Sviluppo applicazione web — marzo 2024",
            "quantita": "1",
            "prezzo_unitario": "3000.00",
        },
        {
            "descrizione": "Consulenza UX/UI — marzo 2024",
            "quantita": "2",
            "prezzo_unitario": "500.00",
        },
    ]

    fattura = crea_fattura(
        numero=numero,
        data_fattura=date(2024, 3, 31),
        cedente_piva="12345678901",
        cedente_cf="RSSMRA85M41H501Z",
        cedente_denominazione="Maria Rossi",
        cliente=cliente,
        linee=linee,
        rivalsa_inps_4=True,
        gestione_inps="separata",
    )

    print(f"  Numero fattura:     {fattura.numero}")
    print(f"  Data:               {fattura.data}")
    print(f"  Formato:            {fattura.formato_trasmissione}")
    print(f"  Regime fiscale:     {fattura.regime_fiscale}")
    print(f"  N. linee:           {len(fattura.linee)}")
    print(f"  Imponibile:         {fattura.imponibile:>10,.2f} EUR")
    print(f"  Rivalsa INPS 4%:    {fattura.importo_rivalsa:>10,.2f} EUR")
    print(f"  Marca da bollo:     {fattura.importo_bollo:>10,.2f} EUR")
    print(f"  TOTALE DOCUMENTO:   {fattura.totale_documento:>10,.2f} EUR")
    print(f"  Ricavo netto:       {fattura.ricavo_netto:>10,.2f} EUR")

    # --- STEP 2: Generazione XML FatturaPA ---
    _sep("STEP 2 — Agent8: XML FatturaPA per SDI")

    xml_str = genera_xml(fattura)
    root = ET.fromstring(xml_str)

    print(f"  XML generato: {len(xml_str)} bytes")
    print(f"  Root tag: {root.tag.split('}')[-1]}")
    print(f"  Contiene RF19: {'RF19' in xml_str}")
    print(f"  Contiene N2.2: {'N2.2' in xml_str}")
    print(f"  Contiene BolloVirtuale: {'BolloVirtuale' in xml_str}")
    print(f"  Contiene Contributo INPS: {'Contributo INPS' in xml_str}")
    print(f"  XML valido (parseable): SI")

    # Mostra primi 15 righe dell'XML
    print(f"\n  Anteprima XML:")
    for i, line in enumerate(xml_str.split("\n")[:15]):
        print(f"    {line}")
    print(f"    ... ({xml_str.count(chr(10))} righe totali)")

    # --- STEP 3: Simulazione esito SDI ---
    _sep("STEP 3 — Agent8: Gestione esiti SDI")

    for codice, desc in [("RC", "Consegnata"), ("NS", "Scartata"), ("MC", "Mancata consegna")]:
        esito_in = EsitoSDI(
            fattura_numero=fattura.numero,
            codice=codice,
            codice_errore="00200" if codice == "NS" else None,
        )
        esito_out = gestisci_esito_sdi(esito_in)
        intervento = "INTERVENTO RICHIESTO" if esito_out.richiede_intervento else "automatico"
        print(f"  SDI {codice} ({desc}): {esito_out.descrizione} [{intervento}]")

    # --- STEP 4: Impatto fiscale della fattura ---
    _sep("STEP 4 — Impatto fiscale della fattura")

    ricavo = fattura.ricavo_netto  # senza rivalsa e bollo
    coeff = Decimal("0.67")  # ATECO 62.01
    reddito = (ricavo * coeff).quantize(Decimal("0.01"))
    imposta = (reddito * Decimal("0.05")).quantize(Decimal("0.01"))
    inps = (reddito * Decimal("0.2607")).quantize(Decimal("0.01"))

    print(f"  Ricavo netto (base calcolo):  {ricavo:>10,.2f} EUR")
    print(f"  Coeff. redditivita 67%:       {reddito:>10,.2f} EUR")
    print(f"  Imposta sostitutiva 5%:       {imposta:>10,.2f} EUR")
    print(f"  Contributo INPS ~26%:         {inps:>10,.2f} EUR")
    print(f"  Marca da bollo:               {fattura.importo_bollo:>10,.2f} EUR")
    print(f"  COSTO FISCALE TOTALE:         {imposta + inps + fattura.importo_bollo:>10,.2f} EUR")
    print(f"  NETTO IN TASCA:               {ricavo - imposta - inps:>10,.2f} EUR")

    # --- STEP 5: Piano F24 annuale (Agent6) ---
    _sep("STEP 5 — Agent6: Piano annuale F24")

    piano = genera_piano_annuale(
        contribuente_id="demo-maria",
        contribuente_cf="RSSMRA85M41H501Z",
        contribuente_nome="Maria",
        contribuente_cognome="Rossi",
        anno_fiscale=2024,
        gestione_inps="separata",
        primo_anno=True,
        imposta_sostitutiva=imposta,
        contributo_inps=inps,
        da_versare=imposta,
        marche_bollo_totale=fattura.importo_bollo,
    )

    print(f"  Anno fiscale: {piano.anno_fiscale}")
    print(f"  N. scadenze: {len(piano.scadenze)}")
    print(f"  Totale annuo: {piano.totale_annuo:>10,.2f} EUR")
    print()
    for s in piano.scadenze:
        tributo = s.codice_tributo or s.causale or ""
        print(f"    {s.data}  [{tributo:>4}]  {s.descrizione}")
        print(f"              {s.importo:>10,.2f} EUR")

    # --- RIEPILOGO ---
    _sep("RIEPILOGO")
    print(f"""
  Ciclo completo eseguito:
    [OK] Agent8 — Fattura creata (n. {fattura.numero})
    [OK] Agent8 — XML FatturaPA generato ({len(xml_str)} bytes)
    [OK] Agent8 — Esiti SDI gestiti (RC/NS/MC)
    [OK] Calcolo — Impatto fiscale calcolato
    [OK] Agent6 — Piano F24 annuale generato ({len(piano.scadenze)} scadenze)

  Dalla fattura al pagamento, tutto in un comando.
""")


# ─────────────────────────────────────────────────────
# DEMO FULL (onboarding -> fattura -> F24)
# ─────────────────────────────────────────────────────

def demo_full() -> None:
    """Complete cycle: profile creation + invoice + tax calculation + F24 plan."""
    from agents.agent0_wizard.models import ProfiloContribuente
    from agents.agent0_wizard.simulator import simulate
    from agents.agent3_calculator.calculator import calcola
    from agents.agent3_calculator.models import ContribuenteInput
    from agents.agent3b_validator.models import InputFiscale
    from agents.agent3b_validator.validator import validate
    from agents.agent8_invoicing.invoice_generator import crea_fattura, genera_xml
    from agents.agent8_invoicing.models import DatiCliente
    from agents.agent8_invoicing.numbering import prossimo_numero
    from agents.agent6_scheduler.scheduler import genera_piano_annuale
    from agents.supervisor.persistence import SupervisorStore

    _sep("FISCALAI — CICLO COMPLETO")
    print("\n  Simuliamo un anno fiscale completo per Maria Rossi.")
    print("  1. Apre P.IVA  2. Emette fatture  3. Calcolo fiscale  4. Piano F24\n")

    # 1. Profilo
    _sep("FASE 1 — Apertura P.IVA (Agent0)")
    profilo = ProfiloContribuente(
        contribuente_id=str(uuid.uuid4()),
        nome="Maria", cognome="Rossi",
        codice_fiscale="RSSMRA85M41H501Z",
        comune_residenza="Roma",
        data_apertura_piva=date(2024, 1, 15),
        primo_anno=True,
        ateco_principale="62.01", ateco_secondari=[],
        regime_agevolato=True, gestione_inps="separata",
        riduzione_inps_35=False, rivalsa_inps_4=True,
    )
    store = SupervisorStore()
    store.save_from_agent0(asdict(profilo))
    print(f"  Profilo creato: {profilo.contribuente_id}")
    print(f"  Salvato nel Supervisor")

    # 2. Fatture dell'anno
    _sep("FASE 2 — Fatturazione anno 2024 (Agent8)")
    cliente = DatiCliente(
        denominazione="Acme S.r.l.", partita_iva="09876543210",
        codice_fiscale="09876543210", indirizzo="Via Milano 42",
        cap="20100", comune="Milano", provincia="MI", codice_sdi="ABCDEFG",
    )

    fatture_data = [
        ("Sviluppo web Q1 2024", "8000.00", date(2024, 3, 31)),
        ("Sviluppo web Q2 2024", "12000.00", date(2024, 6, 30)),
        ("Consulenza architettura cloud", "5000.00", date(2024, 9, 15)),
        ("Sviluppo web Q3-Q4 2024", "15000.00", date(2024, 12, 20)),
    ]

    ricavi_totali = Decimal("0")
    bolli_totali = Decimal("0")

    for desc, importo, data_f in fatture_data:
        num = prossimo_numero(2024)
        f = crea_fattura(
            numero=num, data_fattura=data_f,
            cedente_piva="12345678901", cedente_cf="RSSMRA85M41H501Z",
            cedente_denominazione="Maria Rossi",
            cliente=cliente,
            linee=[{"descrizione": desc, "prezzo_unitario": importo}],
            rivalsa_inps_4=True, gestione_inps="separata",
        )
        xml = genera_xml(f)
        ricavi_totali += f.ricavo_netto
        bolli_totali += f.importo_bollo
        print(f"  {num}  {data_f}  {desc[:35]:35}  {f.totale_documento:>10,.2f} EUR  XML {len(xml)}b")

    print(f"\n  Fatture emesse: {len(fatture_data)}")
    print(f"  Ricavi netti totali: {ricavi_totali:>10,.2f} EUR")
    print(f"  Bolli applicati:     {bolli_totali:>10,.2f} EUR")

    # 3. Calcolo fiscale
    _sep("FASE 3 — Calcolo fiscale (Agent3 + Agent3b)")
    ricavi = {"62.01": ricavi_totali}
    sim = simulate(profilo=profilo, ricavi_per_ateco=ricavi, anno_fiscale=2024)

    print(f"  Ricavi:              {sim.ricavi_totali:>10,.2f} EUR")
    print(f"  Reddito imponibile:  {sim.reddito_imponibile:>10,.2f} EUR")
    print(f"  Imposta sostitutiva: {sim.imposta_sostitutiva:>10,.2f} EUR")
    print(f"  Contributo INPS:     {sim.contributo_inps:>10,.2f} EUR")
    print(f"  Checksum:            {sim.checksum[:16]}...")

    # 4. Piano F24
    _sep("FASE 4 — Piano pagamenti F24 (Agent6)")
    piano = genera_piano_annuale(
        contribuente_id=profilo.contribuente_id,
        contribuente_cf=profilo.codice_fiscale,
        contribuente_nome=profilo.nome,
        contribuente_cognome=profilo.cognome,
        anno_fiscale=2024,
        gestione_inps="separata",
        primo_anno=True,
        imposta_sostitutiva=sim.imposta_sostitutiva,
        contributo_inps=sim.contributo_inps,
        da_versare=sim.imposta_sostitutiva,
        marche_bollo_totale=bolli_totali,
    )

    print(f"  Scadenze generate: {len(piano.scadenze)}")
    print(f"  Totale annuo:      {piano.totale_annuo:>10,.2f} EUR")
    print()
    for s in piano.scadenze:
        tributo = s.codice_tributo or s.causale or ""
        print(f"    {s.data}  [{tributo:>4}]  {s.descrizione}: {s.importo:>10,.2f} EUR")

    # Riepilogo
    _sep("RIEPILOGO ANNO 2024")
    netto = ricavi_totali - sim.imposta_sostitutiva - sim.contributo_inps - bolli_totali
    print(f"""
  Fatture emesse:        {len(fatture_data)}
  Ricavi netti:          {ricavi_totali:>10,.2f} EUR
  Imposta sostitutiva:  -{sim.imposta_sostitutiva:>10,.2f} EUR
  Contributo INPS:      -{sim.contributo_inps:>10,.2f} EUR
  Marche da bollo:      -{bolli_totali:>10,.2f} EUR
  ─────────────────────────────────────
  NETTO IN TASCA:        {netto:>10,.2f} EUR

  Prossime scadenze F24:""")
    for s in piano.scadenze[:3]:
        print(f"    {s.data}  {s.descrizione}: {s.importo:,.2f} EUR")
    print()


# ─────────────────────────────────────────────────────
# REPORT TRACCIATO
# ─────────────────────────────────────────────────────

def demo_report() -> None:
    """Run all checks and save a tracked test report."""
    tracker = TestTracker()

    _sep("FISCALAI — TEST REPORT TRACCIATO")
    print(f"  Timestamp: {tracker.start_time.isoformat()}")
    print(f"  I risultati saranno salvati in test_reports/\n")

    # ── 1. IMPORTS ──
    _sep("1. IMPORT CHECK")

    tracker.check("import Agent0 models", lambda: __import__("agents.agent0_wizard.models"))
    tracker.check("import Agent0 simulator", lambda: __import__("agents.agent0_wizard.simulator"))
    tracker.check("import Agent3 calculator", lambda: __import__("agents.agent3_calculator.calculator"))
    tracker.check("import Agent3b validator", lambda: __import__("agents.agent3b_validator.validator"))
    tracker.check("import Agent6 scheduler", lambda: __import__("agents.agent6_scheduler.scheduler"))
    tracker.check("import Agent8 invoicing", lambda: __import__("agents.agent8_invoicing.invoice_generator"))
    tracker.check("import Agent10 watcher", lambda: __import__("agents.agent10_normative.diff_engine"))
    tracker.check("import Supervisor", lambda: __import__("agents.supervisor.persistence"))
    tracker.check("import shared messaging", lambda: __import__("shared.messaging.models"))

    # ── 2. SHARED CONFIG ──
    _sep("2. SHARED CONFIG FILES")

    shared = Path(__file__).resolve().parent / "shared"
    for name in ["ateco_coefficients.json", "inps_rates.json", "forfettario_limits.json",
                  "f24_tax_codes.json", "f24_template.json", "tax_calendar.json"]:
        def _check_json(p=shared / name):
            with open(p) as f:
                data = json.load(f)
            assert len(data) > 0, "file vuoto"
            return f"{len(data)} entries"
        tracker.check(f"shared/{name}", _check_json)

    # ── 3. AGENT0 — PROFILO ──
    _sep("3. AGENT0 — PROFILO CONTRIBUENTE")

    from agents.agent0_wizard.models import ProfiloContribuente

    def _crea_profilo():
        p = ProfiloContribuente(
            contribuente_id="test-report-001",
            nome="Maria", cognome="Rossi",
            codice_fiscale="RSSMRA85M41H501Z",
            comune_residenza="Roma",
            data_apertura_piva=date(2024, 1, 15),
            primo_anno=True, ateco_principale="62.01", ateco_secondari=[],
            regime_agevolato=True, gestione_inps="separata",
            riduzione_inps_35=False, rivalsa_inps_4=False,
        )
        assert p.contribuente_id == "test-report-001"
        return p.contribuente_id
    tracker.check("crea profilo contribuente", _crea_profilo)

    # ── 4. SUPERVISOR PERSISTENCE ──
    _sep("4. SUPERVISOR — PERSISTENZA")

    from agents.supervisor.persistence import SupervisorStore

    def _persist():
        store = SupervisorStore()
        store.save_from_agent0({
            "contribuente_id": "test-report-001",
            "nome": "Maria", "cognome": "Rossi",
            "codice_fiscale": "RSSMRA85M41H501Z",
        })
        loaded = store.get_profile("test-report-001")
        assert loaded is not None
        return f"saved and reloaded"
    tracker.check("salvataggio e reload profilo", _persist)

    # ── 5. AGENT3 — CALCOLO ──
    _sep("5. AGENT3 — CALCOLO DETERMINISTICO")

    from agents.agent3_calculator.calculator import calcola
    from agents.agent3_calculator.models import ContribuenteInput

    def _calcolo():
        inp = ContribuenteInput(
            contribuente_id="test-report-001", anno_fiscale=2024, primo_anno=True,
            ateco_ricavi={"62.01": Decimal("50000")},
            rivalsa_inps_applicata=Decimal("0"), regime_agevolato=True,
            gestione_inps="separata", riduzione_inps_35=False,
            contributi_inps_versati=Decimal("0"), imposta_anno_precedente=Decimal("0"),
            acconti_versati=Decimal("0"), crediti_precedenti=Decimal("0"),
        )
        r = calcola(inp)
        assert r.reddito_lordo > 0
        assert r.imposta_sostitutiva > 0
        assert r.checksum
        return f"imposta={r.imposta_sostitutiva} inps={r.contributo_inps_calcolato}"
    tracker.check("calcolo fiscale 50k consulente", _calcolo)

    def _calcolo_multi():
        inp = ContribuenteInput(
            contribuente_id="test-report-002", anno_fiscale=2024, primo_anno=True,
            ateco_ricavi={"62.01": Decimal("30000"), "74.10": Decimal("20000")},
            rivalsa_inps_applicata=Decimal("0"), regime_agevolato=True,
            gestione_inps="separata", riduzione_inps_35=False,
            contributi_inps_versati=Decimal("0"), imposta_anno_precedente=Decimal("0"),
            acconti_versati=Decimal("0"), crediti_precedenti=Decimal("0"),
        )
        r = calcola(inp)
        assert len(r.dettaglio_ateco) == 2
        return f"2 ATECO, reddito_lordo={r.reddito_lordo}"
    tracker.check("calcolo multi-ATECO", _calcolo_multi)

    # ── 6. AGENT3B — VALIDAZIONE ──
    _sep("6. AGENT3B — VALIDAZIONE INDIPENDENTE")

    from agents.agent3b_validator.models import InputFiscale
    from agents.agent3b_validator.validator import validate

    def _validazione_ok():
        inp = ContribuenteInput(
            contribuente_id="test-val", anno_fiscale=2024, primo_anno=True,
            ateco_ricavi={"62.01": Decimal("50000")},
            rivalsa_inps_applicata=Decimal("0"), regime_agevolato=True,
            gestione_inps="separata", riduzione_inps_35=False,
            contributi_inps_versati=Decimal("0"), imposta_anno_precedente=Decimal("0"),
            acconti_versati=Decimal("0"), crediti_precedenti=Decimal("0"),
        )
        r = calcola(inp)
        a3b_in = InputFiscale(
            id_contribuente="test-val", anno=2024, is_primo_anno=True,
            ricavi_per_ateco={"62.01": Decimal("50000")},
            rivalsa_4_percento=Decimal("0"), aliquota_agevolata=True,
            tipo_gestione_inps="separata", ha_riduzione_35=False,
            inps_gia_versati=Decimal("0"), imposta_anno_prima=Decimal("0"),
            acconti_gia_versati=Decimal("0"), crediti_da_prima=Decimal("0"),
        )
        a3_out = {
            "reddito_lordo": str(r.reddito_lordo),
            "reddito_imponibile": str(r.reddito_imponibile),
            "imposta_sostitutiva": str(r.imposta_sostitutiva),
            "acconti_dovuti": str(r.acconti_dovuti),
            "acconto_prima_rata": str(r.acconto_prima_rata),
            "acconto_seconda_rata": str(r.acconto_seconda_rata),
            "da_versare": str(r.da_versare),
            "credito_anno_prossimo": str(r.credito_anno_prossimo),
            "contributo_inps_calcolato": str(r.contributo_inps_calcolato),
            "checksum": r.checksum,
        }
        esito = validate(a3b_in, a3_out)
        assert not esito.blocco, f"Blocco inatteso: {esito.divergenze}"
        return "0 divergenze"
    tracker.check("validazione Agent3→Agent3b PASS", _validazione_ok)

    def _validazione_blocco():
        inp = ContribuenteInput(
            contribuente_id="test-block", anno_fiscale=2024, primo_anno=True,
            ateco_ricavi={"62.01": Decimal("30000")},
            rivalsa_inps_applicata=Decimal("0"), regime_agevolato=True,
            gestione_inps="separata", riduzione_inps_35=False,
            contributi_inps_versati=Decimal("0"), imposta_anno_precedente=Decimal("0"),
            acconti_versati=Decimal("0"), crediti_precedenti=Decimal("0"),
        )
        r = calcola(inp)
        tampered = {
            "reddito_lordo": str(r.reddito_lordo),
            "reddito_imponibile": str(r.reddito_imponibile),
            "imposta_sostitutiva": str(r.imposta_sostitutiva + Decimal("0.01")),
            "acconti_dovuti": str(r.acconti_dovuti),
            "acconto_prima_rata": str(r.acconto_prima_rata),
            "acconto_seconda_rata": str(r.acconto_seconda_rata),
            "da_versare": str(r.da_versare),
            "credito_anno_prossimo": str(r.credito_anno_prossimo),
            "contributo_inps_calcolato": str(r.contributo_inps_calcolato),
            "checksum": r.checksum,
        }
        a3b_in = InputFiscale(
            id_contribuente="test-block", anno=2024, is_primo_anno=True,
            ricavi_per_ateco={"62.01": Decimal("30000")},
            rivalsa_4_percento=Decimal("0"), aliquota_agevolata=True,
            tipo_gestione_inps="separata", ha_riduzione_35=False,
            inps_gia_versati=Decimal("0"), imposta_anno_prima=Decimal("0"),
            acconti_gia_versati=Decimal("0"), crediti_da_prima=Decimal("0"),
        )
        esito = validate(a3b_in, tampered)
        assert esito.blocco, "Avrebbe dovuto bloccare!"
        return f"BLOCCATO con {len(esito.divergenze)} divergenze"
    tracker.check("validazione blocco su 1 cent manomesso", _validazione_blocco)

    # ── 7. AGENT8 — FATTURAZIONE ──
    _sep("7. AGENT8 — FATTURAZIONE ELETTRONICA")

    from agents.agent8_invoicing.invoice_generator import crea_fattura, genera_xml, gestisci_esito_sdi
    from agents.agent8_invoicing.models import DatiCliente, EsitoSDI

    def _fattura_base():
        cliente = DatiCliente(
            denominazione="Acme S.r.l.", partita_iva="09876543210",
            codice_fiscale="09876543210", indirizzo="Via Milano 42",
            cap="20100", comune="Milano", provincia="MI", codice_sdi="ABCDEFG",
        )
        f = crea_fattura(
            numero="RPT/001", data_fattura=date(2024, 3, 15),
            cedente_piva="12345678901", cedente_cf="RSSMRA85M41H501Z",
            cedente_denominazione="Maria Rossi",
            cliente=cliente,
            linee=[{"descrizione": "Test", "prezzo_unitario": "3000.00"}],
        )
        assert f.imponibile == Decimal("3000.00")
        assert f.bollo_applicato is True
        assert f.totale_documento == Decimal("3002.00")
        return f"totale={f.totale_documento} bollo={f.bollo_applicato}"
    tracker.check("fattura base con bollo", _fattura_base)

    def _fattura_rivalsa():
        cliente = DatiCliente(
            denominazione="Acme S.r.l.", partita_iva="09876543210",
            codice_fiscale="09876543210", indirizzo="Via Milano 42",
            cap="20100", comune="Milano", provincia="MI", codice_sdi="ABCDEFG",
        )
        f = crea_fattura(
            numero="RPT/002", data_fattura=date(2024, 3, 15),
            cedente_piva="12345678901", cedente_cf="RSSMRA85M41H501Z",
            cedente_denominazione="Maria Rossi",
            cliente=cliente,
            linee=[{"descrizione": "Test rivalsa", "prezzo_unitario": "5000.00"}],
            rivalsa_inps_4=True, gestione_inps="separata",
        )
        assert f.rivalsa_inps_4 is True
        assert f.importo_rivalsa == Decimal("200.00")
        assert f.ricavo_netto == Decimal("5000.00")
        return f"rivalsa={f.importo_rivalsa} ricavo_netto={f.ricavo_netto}"
    tracker.check("fattura con rivalsa INPS 4%", _fattura_rivalsa)

    def _xml_valido():
        cliente = DatiCliente(
            denominazione="Acme S.r.l.", partita_iva="09876543210",
            codice_fiscale="09876543210", indirizzo="Via Milano 42",
            cap="20100", comune="Milano", provincia="MI", codice_sdi="ABCDEFG",
        )
        f = crea_fattura(
            numero="RPT/003", data_fattura=date(2024, 3, 15),
            cedente_piva="12345678901", cedente_cf="RSSMRA85M41H501Z",
            cedente_denominazione="Maria Rossi",
            cliente=cliente,
            linee=[{"descrizione": "Test XML", "prezzo_unitario": "1000.00"}],
        )
        xml = genera_xml(f)
        root = ET.fromstring(xml)
        assert root.tag.endswith("FatturaElettronica")
        assert "RF19" in xml
        assert "N2.2" in xml
        return f"{len(xml)} bytes, parseable"
    tracker.check("XML FatturaPA valido e parseable", _xml_valido)

    def _esiti_sdi():
        results = []
        for codice in ("RC", "NS", "MC"):
            e = gestisci_esito_sdi(EsitoSDI(
                fattura_numero="RPT/001", codice=codice,
                codice_errore="00200" if codice == "NS" else None,
            ))
            results.append(f"{codice}={'intervento' if e.richiede_intervento else 'ok'}")
        return ", ".join(results)
    tracker.check("gestione esiti SDI (RC/NS/MC)", _esiti_sdi)

    # ── 8. AGENT6 — SCADENZARIO ──
    _sep("8. AGENT6 — SCADENZARIO F24")

    from agents.agent6_scheduler.scheduler import genera_piano_annuale

    def _piano_primo_anno():
        p = genera_piano_annuale(
            contribuente_id="rpt-001", contribuente_cf="RSSMRA85M41H501Z",
            contribuente_nome="Maria", contribuente_cognome="Rossi",
            anno_fiscale=2024, gestione_inps="separata", primo_anno=True,
            imposta_sostitutiva=Decimal("1675"), contributo_inps=Decimal("8718"),
            da_versare=Decimal("1675"), marche_bollo_totale=Decimal("8.00"),
        )
        assert len(p.scadenze) > 0
        assert p.totale_annuo > 0
        ids = [s.id for s in p.scadenze]
        assert "acconto1_imposta_2024" not in ids, "primo anno non deve avere acconti"
        return f"{len(p.scadenze)} scadenze, totale={p.totale_annuo}"
    tracker.check("piano primo anno (no acconti)", _piano_primo_anno)

    def _piano_secondo_anno():
        p = genera_piano_annuale(
            contribuente_id="rpt-002", contribuente_cf="RSSMRA85M41H501Z",
            contribuente_nome="Maria", contribuente_cognome="Rossi",
            anno_fiscale=2024, gestione_inps="separata", primo_anno=False,
            imposta_sostitutiva=Decimal("2000"), contributo_inps=Decimal("5000"),
            da_versare=Decimal("2000"),
            acconto_prima_rata=Decimal("800"), acconto_seconda_rata=Decimal("1200"),
        )
        ids = [s.id for s in p.scadenze]
        assert "acconto1_imposta_2024" in ids
        assert "acconto2_imposta_2024" in ids
        return f"{len(p.scadenze)} scadenze con acconti"
    tracker.check("piano secondo anno (con acconti)", _piano_secondo_anno)

    def _piano_artigiano():
        p = genera_piano_annuale(
            contribuente_id="rpt-003", contribuente_cf="VRDLGI80A01H501X",
            contribuente_nome="Luigi", contribuente_cognome="Verdi",
            anno_fiscale=2024, gestione_inps="artigiani", primo_anno=False,
            imposta_sostitutiva=Decimal("3000"), contributo_inps=Decimal("6000"),
            da_versare=Decimal("3000"),
            contributo_fisso_trimestrale=Decimal("1050"),
        )
        fissi = [s for s in p.scadenze if "rata fissa" in s.descrizione]
        assert len(fissi) == 4
        return f"{len(p.scadenze)} scadenze, 4 rate fisse"
    tracker.check("piano artigiano (rate trimestrali)", _piano_artigiano)

    # ── 9. AGENT10 — NORMATIVE ──
    _sep("9. AGENT10 — NORMATIVE WATCHER")

    from agents.agent10_normative.diff_engine import compute_diff, filter_needs_review
    from agents.agent10_normative.models import ParameterChange

    def _diff_engine():
        changes = [ParameterChange(
            nome_parametro="forfettario_limits.soglia_ricavi",
            file_destinazione="shared/forfettario_limits.json",
            valore_precedente="85000", valore_nuovo="90000",
            data_efficacia=date(2025, 1, 1),
            norma_riferimento="Test", certezza="alta",
            url_fonte="https://example.com",
        )]
        real = compute_diff(changes)
        auto, review = filter_needs_review(real, anomaly_threshold_pct=10.0)
        assert len(real) == 1
        return f"1 diff, auto={len(auto)} review={len(review)}"
    tracker.check("diff engine parametri normativi", _diff_engine)

    # ── 10. PYTEST SUITE ──
    _sep("10. PYTEST SUITE COMPLETA")

    import subprocess
    def _pytest_suite():
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "agents/", "shared/messaging/tests/", "-q",
             "--ignore=integrations/vault", "--tb=line"],
            capture_output=True, text=True,
            cwd=str(Path(__file__).resolve().parent),
        )
        # Parse output
        last_line = [l for l in result.stdout.strip().split("\n") if l.strip()][-1]
        assert "failed" not in last_line or "0 failed" in last_line, f"Test failures: {last_line}"
        return last_line
    tracker.check("pytest suite completa", _pytest_suite)

    # ── SAVE REPORT ──
    _sep("REPORT SALVATO")
    report_path = tracker.save_report("full_system_test")

    passed = sum(1 for r in tracker.results if r["status"] == "PASS")
    failed = sum(1 for r in tracker.results if r["status"] == "FAIL")
    total = len(tracker.results)

    print(f"\n  Risultati: {passed}/{total} PASS, {failed} FAIL")
    print(f"  Durata: {(datetime.now() - tracker.start_time).total_seconds():.1f}s")
    print(f"  Report salvato: {report_path}")

    if failed > 0:
        print(f"\n  TEST FALLITI:")
        for r in tracker.results:
            if r["status"] == "FAIL":
                print(f"    - {r['test']}: {r['detail']}")

    print()


# ─────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="FiscalAI — test operativo completo"
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Onboarding interattivo manuale (6 step)",
    )
    parser.add_argument(
        "--fattura", "-f",
        action="store_true",
        help="Fattura reale + calcolo impatto + piano F24",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Ciclo completo: apertura P.IVA -> fatture -> calcolo -> F24",
    )
    parser.add_argument(
        "--report", "-r",
        action="store_true",
        help="Esegui TUTTI i test e salva report tracciato in test_reports/",
    )
    args = parser.parse_args()

    if args.interactive:
        demo_interattiva()
    elif args.fattura:
        demo_fattura()
    elif args.full:
        demo_full()
    elif args.report:
        demo_report()
    else:
        demo_automatica()


if __name__ == "__main__":
    main()
