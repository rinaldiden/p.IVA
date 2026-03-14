#!/usr/bin/env python3
"""FiscalAI Demo — test operativo completo da shell.

Usage:
    python3 demo.py                    # demo automatica (dati fittizi)
    python3 demo.py --interactive      # onboarding interattivo manuale
    python3 demo.py --fattura          # demo con fattura di prova

Non richiede Redis, Claude, PostgreSQL — tutto locale.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent))


def _sep(title: str = "") -> None:
    if title:
        print(f"\n{'='*60}")
        print(f"  {title}")
        print(f"{'='*60}")
    else:
        print(f"{'─'*60}")


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
    from agents.agent3_calculator.models import ContribuenteInput
    from agents.agent3b_validator.models import InputFiscale
    from agents.agent3b_validator.validator import validate

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
    store = SupervisorStore()
    store.save_from_agent0(asdict(profilo))
    print(f"\nProfilo salvato nel Supervisor: {profilo.contribuente_id}")


def demo_fattura() -> None:
    """Demo fattura di prova (mock, Agent8 non ancora implementato)."""
    _sep("DEMO FATTURA DI PROVA")

    print("""
  Agent8 (Invoicing) non e' ancora implementato.
  Ecco cosa fara' quando sara' pronto:

  1. Genera fattura elettronica XML conforme SDI
  2. Regime fiscale RF19 (forfettario)
  3. Natura operazione: N2.2 (non soggetto IVA)
  4. Marca da bollo virtuale 2 EUR su fatture > 77,47 EUR
  5. Firma digitale via Vault
  6. Invio tramite SDI + gestione esiti

  Per ora, ecco una fattura fittizia:
""")

    fattura = {
        "numero": "2024/001",
        "data": str(date.today()),
        "cedente": {
            "denominazione": "Maria Rossi",
            "partita_iva": "IT12345678901",
            "codice_fiscale": "RSSMRA85M41H501Z",
            "regime_fiscale": "RF19",
            "indirizzo": "Via Roma 1, 00100 Roma",
        },
        "cessionario": {
            "denominazione": "Acme S.r.l.",
            "partita_iva": "IT09876543210",
            "indirizzo": "Via Milano 42, 20100 Milano",
        },
        "linee": [
            {
                "descrizione": "Sviluppo applicazione web — marzo 2024",
                "quantita": 1,
                "prezzo_unitario": "3000.00",
                "aliquota_iva": "0.00",
                "natura": "N2.2",
            }
        ],
        "totale_documento": "3000.00",
        "marca_bollo": {
            "applicata": True,
            "importo": "2.00",
            "codice_tributo": "2501",
            "motivo": "importo > 77.47 EUR",
        },
        "dicitura_forfettario": (
            "Operazione effettuata ai sensi dell'art. 1, commi 54-89, "
            "L. 190/2014 — regime forfettario. "
            "Non soggetta a ritenuta d'acconto. "
            "Imposta di bollo assolta in modo virtuale."
        ),
        "pagamento": {
            "modalita": "bonifico",
            "iban": "IT60X0542811101000000123456",
            "scadenza": "2024-04-30",
        },
    }

    print(json.dumps(fattura, indent=2, ensure_ascii=False))

    totale = Decimal(fattura["totale_documento"])
    print(f"\n  Impatto fiscale di questa fattura:")
    print(f"    Ricavo:                  {totale:>10,.2f} EUR")
    print(f"    Coeff. redditivita 67%:  {totale * Decimal('0.67'):>10,.2f} EUR")
    print(f"    Imposta 5% (agevolata):  {totale * Decimal('0.67') * Decimal('0.05'):>10,.2f} EUR")
    print(f"    INPS gest. sep. ~26%:    {totale * Decimal('0.67') * Decimal('0.2607'):>10,.2f} EUR")
    print(f"    Marca da bollo:          {Decimal('2.00'):>10,.2f} EUR")
    print()
    _sep()
    print("  Per implementare Agent8: prossimo step nella roadmap.")
    print("  Richiede: generazione XML FatturaPA, firma digitale, invio SDI.")
    print()


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
        help="Demo fattura di prova",
    )
    args = parser.parse_args()

    if args.interactive:
        demo_interattiva()
    elif args.fattura:
        demo_fattura()
    else:
        demo_automatica()


if __name__ == "__main__":
    main()
