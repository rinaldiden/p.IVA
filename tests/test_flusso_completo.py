"""
Test flusso completo FiscalAI — end-to-end

Scenario A: Gestione Separata (ATECO 62.01.00, coeff 67%, aliquota 5%)
Scenario B: Artigiano (ATECO 43.21.02, coeff 86%, aliquota 5%, riduzione INPS 35%)

Simula: apertura → fatturazione → calcolo → compliance → F24 → bilancio
"""

import json
import shutil
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))


def pulisci():
    """Pulisce dati di test."""
    for d in ["data", "context", "logs"]:
        p = BASE_DIR / d
        if p.exists():
            shutil.rmtree(p)


def stampa_sezione(titolo: str):
    print(f"\n{'='*60}")
    print(f"  {titolo}")
    print(f"{'='*60}")


def stampa_scadenzario(scadenzario: dict):
    print(f"\n  Scadenzario {scadenzario['anno']} — {scadenzario['gestione_inps']}")
    print(f"  Primo anno: {'SI' if scadenzario['primo_anno'] else 'NO'}")
    print(f"  {'─'*50}")
    for s in scadenzario["scadenze"]:
        if "importo" in s:
            print(f"  {s['data']}  €{s['importo']:>10,.2f}  {s['tipo']}")
        elif "nota" in s:
            print(f"  {s['data']}  {'':>10}  {s.get('tipo', '')} — {s['nota']}")
    print(f"  {'─'*50}")
    print(f"  TOTALE F24: €{scadenzario['totale_f24']:,.2f} ({scadenzario['num_f24']} modelli)")


def run_scenario(nome: str, profilo_update: dict, fatture: list):
    pulisci()

    from config import settings
    # Forza ricreazione directory
    for d in [settings.DATA_CONTRIBUENTE, settings.DATA_FATTURE, settings.DATA_F24,
              settings.DATA_DICHIARAZIONI, settings.DATA_TRANSAZIONI, settings.DATA_NOTIFICHE,
              settings.LOGS_DIR, settings.CONTEXT_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    # Reimporta dopo pulizia
    import importlib
    import agents.supervisor as supervisor
    importlib.reload(supervisor)

    stampa_sezione(f"SCENARIO: {nome}")

    # 1. APERTURA — Init profilo
    stampa_sezione("1. APERTURA P.IVA")
    profilo = supervisor.profilo_vuoto()
    for key, value in profilo_update.items():
        if isinstance(value, dict) and key in profilo:
            profilo[key].update(value)
        else:
            profilo[key] = value
    supervisor.salva_profilo(profilo)
    p = supervisor.carica_profilo()
    print(f"  Nome: {p['anagrafica']['nome']} {p['anagrafica']['cognome']}")
    print(f"  ATECO: {p['piva']['ateco_primario']} (coeff {p['piva']['coefficiente_redditivita']}%)")
    print(f"  Regime: {p['regime']['tipo']} al {int(p['regime']['aliquota']*100)}%")
    print(f"  INPS: {p['inps']['gestione']}")
    print(f"  Riduzione 35%: {p['regime'].get('riduzione_contributiva_35', False)}")

    # 2. FATTURAZIONE
    stampa_sezione("2. EMISSIONE FATTURE")
    from agents.agent8_invoicer import genera_xml_fattura
    importlib.reload(sys.modules["agents.agent8_invoicer"])
    from agents.agent8_invoicer import genera_xml_fattura

    for fatt in fatture:
        result = genera_xml_fattura(fatt["cliente"], fatt["prestazioni"])
        bollo = "SI €2" if result["bollo_virtuale"] else "NO"
        print(f"  Fattura n.{result['numero']} → {result['cliente']} → €{result['importo']:,.2f} (bollo: {bollo})")

    # 3. CALCOLO FISCALE
    stampa_sezione("3. CALCOLO FISCALE")
    from agents.agent3_calculator import calcola_tutto
    importlib.reload(sys.modules["agents.agent3_calculator"])
    from agents.agent3_calculator import calcola_tutto

    calc = calcola_tutto(2026)
    print(f"  Ricavi totali:        €{calc['ricavi']:>10,.2f}")
    print(f"  Reddito (×{int(calc['imposta']['coefficiente']*100)}%):      €{calc['imposta']['reddito_lordo']:>10,.2f}")
    print(f"  INPS dedotti:         €{calc['imposta']['inps_dedotti']:>10,.2f}")
    print(f"  Reddito imponibile:   €{calc['imposta']['reddito_imponibile']:>10,.2f}")
    print(f"  INPS contributi:      €{calc['inps']['contributi_totali']:>10,.2f}")
    if calc['inps'].get('fissi', 0) > 0:
        print(f"    di cui fissi:       €{calc['inps']['fissi']:>10,.2f}")
        print(f"    di cui variabili:   €{calc['inps']['variabili']:>10,.2f}")
    print(f"  Imposta {int(calc['imposta']['aliquota']*100)}%:           €{calc['imposta']['imposta']:>10,.2f}")
    print(f"  Bollo virtuale:       €{calc['bollo_virtuale']['totale']:>10,.2f}")
    print(f"  ─────────────────────────────────")
    print(f"  TOTALE TASSE:         €{calc['totale_tasse']:>10,.2f}")
    print(f"  NETTO IN TASCA:       €{calc['netto']:>10,.2f}")
    print(f"  Aliquota effettiva:   {calc['aliquota_effettiva']}%")
    print(f"  Accantona/mese:       €{calc['accantonamento_mensile']:>10,.2f}")

    # 4. COMPLIANCE
    stampa_sezione("4. COMPLIANCE CHECK")
    from agents.agent4_compliance import controlla_compliance
    importlib.reload(sys.modules["agents.agent4_compliance"])
    from agents.agent4_compliance import controlla_compliance

    comp = controlla_compliance(2026)
    print(f"  Ricavi: €{comp['ricavi_totali']:,.2f}")
    print(f"  Proiezione annuale: €{comp['proiezione'].get('proiezione_annuale', 0):,.2f}")
    print(f"  Supera 85k: {'SI' if comp['proiezione'].get('supera_85k') else 'NO'}")
    print(f"  Alert: {comp['totale_alert']}")
    for a in comp.get("alert_soglie", []):
        print(f"    [{a['livello']}] {a['messaggio']}")
    for a in comp.get("alert_bollo", []):
        print(f"    [{a['livello']}] {a['messaggio']}")

    # 5. SCADENZARIO & F24
    stampa_sezione("5. SCADENZARIO & F24")
    from agents.agent6_scheduler import genera_scadenzario
    importlib.reload(sys.modules["agents.agent6_scheduler"])
    from agents.agent6_scheduler import genera_scadenzario

    sched = genera_scadenzario(2026)
    stampa_scadenzario(sched)

    # 6. RIEPILOGO FINALE
    stampa_sezione("6. RIEPILOGO FINALE")
    storico = supervisor.carica_storico(2026)
    print(f"  Fatture emesse: {len(storico['fatture_emesse'])}")
    print(f"  F24 generati:   {len(storico['f24_generati'])}")
    print(f"  Ricavi totali:  €{storico['ricavi_totali']:,.2f}")
    print(f"  Eventi log:     {len(storico['eventi'])}")

    # Conta file generati
    xml_count = len(list((BASE_DIR / "data" / "fatture").rglob("*.xml")))
    f24_count = len(list((BASE_DIR / "data" / "f24").rglob("*.json")))
    print(f"  File XML fatture: {xml_count}")
    print(f"  File JSON F24:    {f24_count}")

    return calc


# ============================================================
# FATTURE DI TEST (stesso set per entrambi gli scenari)
# ============================================================
FATTURE_TEST = [
    {
        "cliente": {
            "denominazione": "Costruzioni Alpine S.r.l.",
            "piva": "09876543210", "codice_sdi": "ABCDEFG",
            "indirizzo": "Via dei Monti 15", "cap": "28845",
            "comune": "Domodossola", "provincia": "VB",
        },
        "prestazioni": [
            {"descrizione": "Sviluppo firmware controllo motori stampa 3D", "importo": 3500.00},
            {"descrizione": "Progettazione guida autonoma bicicletta — fase 1", "importo": 5000.00},
        ]
    },
    {
        "cliente": {
            "denominazione": "BikeMotion Tech GmbH",
            "piva": "DE123456789", "codice_sdi": "XXXXXXX",
            "indirizzo": "Hauptstrasse 42", "cap": "80331",
            "comune": "Munchen", "provincia": "DE",
        },
        "prestazioni": [
            {"descrizione": "Consulenza tecnica sistema guida autonoma — Q1 2026", "importo": 12000.00},
        ]
    },
    {
        "cliente": {
            "denominazione": "Marco Bianchi",
            "cf": "BNCMRC85B01H501X", "codice_sdi": "0000000",
            "indirizzo": "Via Garibaldi 7", "cap": "10100",
            "comune": "Torino", "provincia": "TO",
        },
        "prestazioni": [
            {"descrizione": "Stampa 3D componenti custom — lotto 12 pezzi", "importo": 60.00, "quantita": 12},
        ]
    },
    {
        "cliente": {
            "denominazione": "Elettronica Moderna S.p.A.",
            "piva": "11223344556", "codice_sdi": "M5UXCR1",
            "indirizzo": "Viale dell'Industria 100", "cap": "20090",
            "comune": "Assago", "provincia": "MI",
        },
        "prestazioni": [
            {"descrizione": "Sviluppo software IoT per linea produttiva", "importo": 15000.00},
            {"descrizione": "Integrazione sensori e attuatori — 40 ore", "importo": 80.00, "quantita": 40},
        ]
    },
    {
        "cliente": {
            "denominazione": "Comune di Verbania",
            "cf": "00182910034", "codice_sdi": "UFABC1",
            "indirizzo": "Piazza Garibaldi 1", "cap": "28922",
            "comune": "Verbania", "provincia": "VB",
        },
        "prestazioni": [
            {"descrizione": "Fornitura e installazione sistema bike sharing autonomo — progetto pilota", "importo": 25000.00},
        ]
    },
]

# ============================================================
# SCENARIO A: GESTIONE SEPARATA
# ============================================================
print("\n" + "█" * 60)
print("█  TEST FLUSSO COMPLETO — GESTIONE SEPARATA")
print("█" * 60)

calc_gs = run_scenario(
    "GESTIONE SEPARATA — ATECO 62.01.00, coeff 67%, aliquota 5%",
    {
        "anagrafica": {
            "nome": "Daniele", "cognome": "Rinaldi",
            "codice_fiscale": "RNLDNL90A01H501Z",
            "residenza": "Via Roma 1, 28845 Domodossola (VB)",
            "email": "daniele@example.com",
        },
        "piva": {
            "numero": "12345678901", "data_apertura": "2026-01-15",
            "stato": "attiva", "ateco_primario": "62.01.00",
            "coefficiente_redditivita": 67,
        },
        "regime": {"tipo": "forfettario", "aliquota": 0.05, "anno_inizio": 2026},
        "inps": {"gestione": "separata"},
    },
    FATTURE_TEST,
)

# ============================================================
# SCENARIO B: ARTIGIANO
# ============================================================
print("\n\n" + "█" * 60)
print("█  TEST FLUSSO COMPLETO — ARTIGIANO")
print("█" * 60)

calc_art = run_scenario(
    "ARTIGIANO — ATECO 43.21.02, coeff 86%, aliquota 5%, riduzione INPS 35%",
    {
        "anagrafica": {
            "nome": "Daniele", "cognome": "Rinaldi",
            "codice_fiscale": "RNLDNL90A01H501Z",
            "residenza": "Via Roma 1, 28845 Domodossola (VB)",
            "email": "daniele@example.com",
        },
        "piva": {
            "numero": "12345678901", "data_apertura": "2026-01-15",
            "stato": "attiva", "ateco_primario": "43.21.02",
            "coefficiente_redditivita": 86,
        },
        "regime": {
            "tipo": "forfettario", "aliquota": 0.05,
            "anno_inizio": 2026, "riduzione_contributiva_35": True,
        },
        "inps": {"gestione": "artigiani"},
    },
    FATTURE_TEST,
)

# ============================================================
# CONFRONTO FINALE
# ============================================================
stampa_sezione("CONFRONTO FINALE")
print(f"  {'':30} {'Gest.Sep.':>12} {'Artigiano':>12}")
print(f"  {'─'*56}")
print(f"  {'Ricavi':30} €{calc_gs['ricavi']:>10,.2f}  €{calc_art['ricavi']:>10,.2f}")
print(f"  {'Reddito imponibile':30} €{calc_gs['imposta']['reddito_lordo']:>10,.2f}  €{calc_art['imposta']['reddito_lordo']:>10,.2f}")
print(f"  {'INPS totali':30} €{calc_gs['inps']['contributi_totali']:>10,.2f}  €{calc_art['inps']['contributi_totali']:>10,.2f}")
print(f"  {'Imposta sostitutiva':30} €{calc_gs['imposta']['imposta']:>10,.2f}  €{calc_art['imposta']['imposta']:>10,.2f}")
print(f"  {'Totale tasse':30} €{calc_gs['totale_tasse']:>10,.2f}  €{calc_art['totale_tasse']:>10,.2f}")
print(f"  {'NETTO IN TASCA':30} €{calc_gs['netto']:>10,.2f}  €{calc_art['netto']:>10,.2f}")
print(f"  {'Aliquota effettiva':30} {calc_gs['aliquota_effettiva']:>10}%  {calc_art['aliquota_effettiva']:>10}%")
print(f"  {'Accantona/mese':30} €{calc_gs['accantonamento_mensile']:>10,.2f}  €{calc_art['accantonamento_mensile']:>10,.2f}")

winner = "GESTIONE SEPARATA" if calc_gs['netto'] > calc_art['netto'] else "ARTIGIANO"
diff = abs(calc_gs['netto'] - calc_art['netto'])
print(f"\n  >>> VINCE: {winner} (+€{diff:,.2f} netti)")
print(f"\n{'='*60}")
print("  ✅ TEST COMPLETO — TUTTI GLI AGENTI FUNZIONANO")
print(f"{'='*60}")
