"""
Agent0 — Wizard & Bootstrap

Guida l'utente dall'inizio alla fine per aprire la P.IVA.
Gestisce tutto il pre-requisito (PEC, SPID) e genera il modello AA9/12.

Flusso:
1. Raccolta dati anagrafici (minimo indispensabile)
2. Scelta ATECO con simulazione fiscale
3. Verifica requisiti 5%
4. Checklist prerequisiti (PEC, SPID) con link diretti
5. Generazione modello AA9/12 precompilato
6. Guida passo-passo apertura sul sito AdE
7. Post-apertura: inizializzazione profilo nel Supervisor

Input:  interattivo (CLI) o dati da wizard HTML
Output: data/contribuente/profilo.json
        data/contribuente/aa9_12.json
        context/guida_apertura.md
"""

import json
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from config import settings
from agents.supervisor import profilo_vuoto, salva_profilo, carica_profilo
from agents.agent3_calculator import (
    calcola_imposta, calcola_inps_gestione_separata,
    calcola_inps_artigiani, calcola_inps_commercianti,
)

LOGS_DIR = settings.LOGS_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOGS_DIR / "agent0.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("agent0")


# ---------------------------------------------------------------------------
# ATECO consigliati
# ---------------------------------------------------------------------------
ATECO_SUGGERITI = [
    {"codice": "62.01.00", "descrizione": "Produzione di software", "coefficiente": 67, "inps": "separata",
     "per_chi": "Sviluppo SW, app, firmware, sistemi embedded, AI"},
    {"codice": "62.09.09", "descrizione": "Altri servizi IT", "coefficiente": 67, "inps": "separata",
     "per_chi": "Consulenza IT, integrazione sistemi, IoT, automazione"},
    {"codice": "72.19.09", "descrizione": "Ricerca e sviluppo", "coefficiente": 78, "inps": "separata",
     "per_chi": "R&D, prototipazione, robotica, guida autonoma"},
    {"codice": "43.21.02", "descrizione": "Installazione impianti elettronici", "coefficiente": 86, "inps": "artigiani",
     "per_chi": "Cablaggi, reti, installazione HW — richiede CCIAA"},
    {"codice": "33.12.10", "descrizione": "Riparazione macchine", "coefficiente": 86, "inps": "artigiani",
     "per_chi": "Manutenzione meccanica, motori — richiede CCIAA"},
]


# ---------------------------------------------------------------------------
# Generazione AA9/12
# ---------------------------------------------------------------------------
def genera_aa9_12(dati: dict) -> dict:
    """
    Genera il modello AA9/12 precompilato per apertura P.IVA.
    Restituisce un dict con tutti i campi del modello.
    """
    oggi = date.today().isoformat()

    aa9 = {
        "_modello": "AA9/12",
        "_tipo": "Dichiarazione di inizio attivita",
        "_generato_da": "FiscalAI Agent0",
        "_generato_il": oggi,

        # Quadro A — Tipo di dichiarazione
        "quadro_a": {
            "tipo_dichiarazione": "inizio_attivita",
            "data_inizio": dati.get("data_inizio", oggi),
        },

        # Quadro B — Soggetto d'imposta
        "quadro_b": {
            "codice_fiscale": dati["codice_fiscale"],
            "cognome": dati["cognome"],
            "nome": dati["nome"],
            "sesso": dati.get("sesso", "M"),
            "data_nascita": dati["data_nascita"],
            "comune_nascita": dati["comune_nascita"],
            "provincia_nascita": dati["provincia_nascita"],
            "residenza": {
                "comune": dati["comune_residenza"],
                "provincia": dati["provincia_residenza"],
                "cap": dati["cap_residenza"],
                "indirizzo": dati["indirizzo_residenza"],
            },
        },

        # Quadro B — Attivita esercitata e luogo di esercizio
        "quadro_b_attivita": {
            "codice_ateco": dati.get("ateco", "62.01.00"),
            "descrizione_attivita": dati.get("descrizione_attivita",
                "Sviluppo software, progettazione sistemi di controllo, prototipazione"),
            "luogo_esercizio": {
                "tipo": "residenza",
                "indirizzo": dati["indirizzo_residenza"],
                "comune": dati["comune_residenza"],
                "provincia": dati["provincia_residenza"],
                "cap": dati["cap_residenza"],
            },
            # NOTA: i forfettari NON indicano il volume d'affari presunto
            # (istruzioni pag.4: "non deve essere compilato dai soggetti che
            # intendono avvalersi del regime previsto dall'art. 1, comma 54, L. 190/2014")
            "volume_affari_presunto": None,
            "regime_fiscale_agevolato": "2",
            # Casella 2 = REGIME FORFETARIO (art. 1, comma 54, L. 23/12/2014, n. 190)
            "_nota_regime": "Barrare casella 2 nel riquadro 'Regimi fiscali agevolati'",
            "scritture_contabili": False,
            # Forfettari esonerati da scritture contabili
        },

        # Quadro C — Titolare
        "quadro_c": {
            "codice_fiscale_titolare": dati["codice_fiscale"],
            "residenza_anagrafica": {
                "comune": dati["comune_residenza"],
                "provincia": dati["provincia_residenza"],
                "cap": dati["cap_residenza"],
                "indirizzo": dati["indirizzo_residenza"],
            },
            "scritture_contabili": False,
        },

        # Quadro D — Rappresentante (NON compilare per persona fisica autonoma)
        "quadro_d": {
            "_nota": "Non compilare — il titolare agisce in proprio",
        },

        # Quadro E — Operazioni straordinarie (NON compilare per inizio attivita)
        "quadro_e": {
            "_nota": "Non compilare — dichiarazione di inizio attivita semplice",
        },

        # Quadro G — Altre attivita (compilare solo se ATECO secondario)
        "quadro_g": {
            "ateco_secondario": dati.get("ateco_secondario"),
            "descrizione_secondaria": dati.get("descrizione_secondaria"),
            "_nota": "Compilare solo se si esercitano altre attivita oltre a quella prevalente",
        },

        # Quadro I — Altre informazioni in sede di inizio attivita
        "quadro_i": {
            "email": dati.get("email", ""),
            "telefono": dati.get("telefono", ""),
            "pec": dati.get("pec", ""),
            "dati_immobile_sede": {
                "titolarita": dati.get("titolarita_immobile", "P"),
                # P = possesso, D = detenzione (affitto/comodato)
                "tipo_catasto": "F",  # F = fabbricato, T = terreno
            },
            "operazioni_intracomunitarie": dati.get("operazioni_intracomunitarie", False),
            # Se True, viene richiesta inclusione archivio VIES
            "tipologia_clientela": dati.get("tipologia_clientela", "1"),
            # 1 = imprese, 2 = enti pubblici, 3 = consumatori finali, 4 = altro
            "luogo_aperto_al_pubblico": dati.get("luogo_aperto_pubblico", False),
        },

        # Modalita di presentazione
        "presentazione": {
            "modalita": "telematica_diretta",
            # Opzioni: telematica_diretta (Fisconline con SPID),
            #          ufficio (duplice copia + documento),
            #          raccomandata (+ fotocopia documento),
            #          intermediario (commercialista/CAF)
            "url_fisconline": "https://www.agenziaentrate.gov.it/portale/invio-diretto-aa9-piva-pf-cittadini",
            "url_modello_pdf": "https://www.agenziaentrate.gov.it/portale/documents/20143/6020466/Modello+aa9_AA9_12+modello.pdf",
            "url_istruzioni_pdf": "https://www.agenziaentrate.gov.it/portale/documents/20143/6020466/AA9_12+istruzioni_2024.pdf",
            "url_software_compilazione": "https://www.agenziaentrate.gov.it/portale/schede/istanze/aa9_11-apertura-variazione-chiusura-pf/sw-compilazione-pi-pf",
            "_nota": "Presentazione entro 30 giorni dalla data di inizio attivita. "
                     "La data di inizio non puo essere successiva alla data di presentazione.",
        },
    }

    # Salva
    output = settings.DATA_CONTRIBUENTE / "aa9_12.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(aa9, f, indent=2, ensure_ascii=False)

    logger.info("Modello AA9/12 generato: %s", output)
    return aa9


# ---------------------------------------------------------------------------
# Checklist prerequisiti
# ---------------------------------------------------------------------------
def genera_checklist(dati: dict) -> dict:
    """Genera checklist con stato e link per ogni prerequisito."""
    checklist = {
        "pec": {
            "nome": "PEC — Posta Elettronica Certificata",
            "obbligatorio": True,
            "stato": "da_fare" if not dati.get("pec") else "fatto",
            "come_fare": "Apri una PEC su uno di questi provider (2 minuti, €5-10/anno)",
            "link": [
                {"provider": "Aruba PEC", "url": "https://www.pec.it/acquista-posta-elettronica-certificata.aspx", "prezzo": "€5/anno"},
                {"provider": "Register.it", "url": "https://www.register.it/pec/", "prezzo": "€5/anno"},
                {"provider": "Legalmail (InfoCert)", "url": "https://www.legalmail.it/", "prezzo": "€6/anno"},
            ],
            "nota": "Scegli quella che costa meno. Serve solo per ricevere comunicazioni ufficiali.",
        },
        "spid": {
            "nome": "SPID — Identita Digitale",
            "obbligatorio": True,
            "stato": "da_fare",
            "come_fare": "Riconoscimento video online (10 minuti). Gratis o €10 una tantum.",
            "link": [
                {"provider": "Poste Italiane", "url": "https://posteid.poste.it/", "prezzo": "Gratis (con CIE/SMS)"},
                {"provider": "Aruba", "url": "https://www.pec.it/richiedi-spid-aruba-id.aspx", "prezzo": "Gratis"},
                {"provider": "Namirial", "url": "https://www.namirial.it/spid/", "prezzo": "€15 una tantum"},
                {"provider": "InfoCert", "url": "https://identitadigitale.infocert.it/", "prezzo": "Gratis (con CIE)"},
            ],
            "nota": "Se hai la CIE (carta d'identita nuova con chip), puoi fare SPID gratis con Poste o InfoCert. Se no, Namirial con riconoscimento video a €15.",
        },
        "conto_corrente": {
            "nome": "Conto corrente",
            "obbligatorio": False,
            "stato": "opzionale",
            "come_fare": "Puoi usare il tuo conto personale. Un conto business dedicato e' consigliato ma non obbligatorio per i forfettari.",
            "link": [],
            "nota": "Per i forfettari non c'e' obbligo di conto dedicato.",
        },
    }

    return checklist


# ---------------------------------------------------------------------------
# Guida apertura
# ---------------------------------------------------------------------------
def genera_guida_apertura(dati: dict) -> str:
    """Genera la guida step-by-step per aprire la P.IVA."""
    ateco = dati.get("ateco", "62.01.00")
    coeff = next((a["coefficiente"] for a in ATECO_SUGGERITI if a["codice"] == ateco), 67)
    fatturato = dati.get("fatturato_stimato", 40000)

    # Simulazione
    reddito = fatturato * (coeff / 100)
    inps = calcola_inps_gestione_separata(reddito)
    imposta = calcola_imposta(fatturato, coeff / 100, 0.05)

    guida = f"""# Guida Apertura P.IVA — FiscalAI

## I tuoi dati

- **Nome**: {dati.get('nome', '')} {dati.get('cognome', '')}
- **ATECO**: {ateco} (coefficiente {coeff}%)
- **Regime**: Forfettario al 5% (primi 5 anni)
- **INPS**: Gestione Separata (26,07% — zero contributi fissi)

## Simulazione su €{fatturato:,.0f} di fatturato

| Voce | Importo |
|------|---------|
| Ricavi | €{fatturato:,.2f} |
| Reddito imponibile ({coeff}%) | €{reddito:,.2f} |
| INPS gestione separata | €{inps['contributi_totali']:,.2f} |
| Imposta sostitutiva 5% | €{imposta['imposta']:,.2f} |
| **Totale tasse** | **€{inps['contributi_totali'] + imposta['imposta']:,.2f}** |
| **Netto in tasca** | **€{fatturato - inps['contributi_totali'] - imposta['imposta']:,.2f}** |
| Accantona al mese | €{(inps['contributi_totali'] + imposta['imposta']) / 12:,.2f} |

## Prerequisiti

### 1. PEC (2 minuti)
Vai su [pec.it](https://www.pec.it/acquista-posta-elettronica-certificata.aspx) e apri una PEC Aruba a €5/anno.
Appuntati l'indirizzo (es. tuonome@pec.it).

### 2. SPID (10 minuti)
Vai su [posteid.poste.it](https://posteid.poste.it/) e fai SPID con Poste (gratis).
Se non hai CIE, usa [Namirial](https://www.namirial.it/spid/) con video-riconoscimento (€15).

## Apertura P.IVA — 4 modi per presentare il modello

### Opzione 1: TELEMATICA DIRETTA (consigliata — con SPID)
1. Vai su [Invio diretto AA9/12](https://www.agenziaentrate.gov.it/portale/invio-diretto-aa9-piva-pf-cittadini)
2. Accedi con SPID
3. Compila il modello online con i dati qui sotto
4. Invia — ricevi il numero P.IVA lo stesso giorno o il giorno dopo

### Opzione 2: SOFTWARE AdE (alternativa — con SPID)
1. Scarica il [software di compilazione](https://www.agenziaentrate.gov.it/portale/schede/istanze/aa9_11-apertura-variazione-chiusura-pf/sw-compilazione-pi-pf)
2. Compila offline, genera il file
3. Caricalo nell'area riservata Fisconline

### Opzione 3: DI PERSONA (senza SPID)
1. Stampa il [modello AA9/12 PDF](https://www.agenziaentrate.gov.it/portale/documents/20143/6020466/Modello+aa9_AA9_12+modello.pdf)
2. Compilalo a mano con i dati qui sotto
3. Portalo in **duplice copia** a qualsiasi ufficio dell'Agenzia delle Entrate
4. Porta un documento d'identita valido
5. Ricevi il numero P.IVA in giornata

### Opzione 4: RACCOMANDATA (senza SPID, senza ufficio)
1. Stampa e compila il modello AA9/12
2. Allega fotocopia documento d'identita
3. Spedisci via raccomandata A/R a qualsiasi ufficio AdE
4. La dichiarazione si considera presentata il giorno della spedizione

---

## Dati da inserire nel modello AA9/12

**QUADRO A — Tipo dichiarazione**
- Barrare casella **1** (Inizio attivita)
- Data inizio attivita: **{date.today().strftime('%d/%m/%Y')}**

**QUADRO B — Soggetto d'imposta**
- Cognome: **{dati.get('cognome', '_______________')}**
- Nome: **{dati.get('nome', '_______________')}**
- Codice Fiscale: **{dati.get('codice_fiscale', '_______________')}**
- Codice ATECO: **{ateco}**
- Descrizione attivita: {dati.get('descrizione_attivita', 'Sviluppo software, progettazione sistemi di controllo, prototipazione')}
- Indirizzo sede: {dati.get('indirizzo_residenza', '_______________')}
  {dati.get('cap_residenza', '_____')} {dati.get('comune_residenza', '_______________')} ({dati.get('provincia_residenza', '__')})
- Volume d'affari presunto: **NON COMPILARE** (i forfettari non lo indicano!)
- Regimi fiscali agevolati: barrare casella **2** (Forfettario L. 190/2014)
- Scritture contabili: **NON barrare** (forfettari esonerati)

**QUADRO C — Titolare**
- Codice fiscale: {dati.get('codice_fiscale', '_______________')}
- Residenza: uguale al Quadro B

**QUADRO D — Rappresentante**: NON compilare
**QUADRO E — Operazioni straordinarie**: NON compilare
**QUADRO F, G, H**: NON compilare (salvo attivita secondarie)

**QUADRO I — Altre informazioni**
- PEC: **{dati.get('pec', '_______________')}**
- Email: {dati.get('email', '')}
- Telefono: {dati.get('telefono', '')}
- Titolarita immobile sede: P (possesso) o D (detenzione/affitto)
- Tipo catasto: F (fabbricato)
- Tipologia clientela prevalente: 1 (imprese) o 4 (misto)
- Operazioni intracomunitarie: {'SI (richiesta iscrizione VIES)' if dati.get('operazioni_intracomunitarie') else 'NO'}

## Dopo l'apertura

Torna qui con il numero di P.IVA. FiscalAI:
1. Inizializza il tuo profilo
2. Configura il canale SDI per le fatture elettroniche
3. Emette la prima fattura
4. Calcola lo scadenzario con tutte le date e gli importi
5. Ti notifica 7 giorni prima di ogni scadenza

**Non devi piu preoccuparti di nulla.**

---
*Generato da FiscalAI Agent0 il {date.today().strftime('%d/%m/%Y')}*
"""

    # Salva
    output = settings.CONTEXT_DIR / "guida_apertura.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        f.write(guida)

    logger.info("Guida apertura generata: %s", output)
    return guida


# ---------------------------------------------------------------------------
# Inizializzazione post-apertura
# ---------------------------------------------------------------------------
def inizializza_post_apertura(dati: dict, numero_piva: str) -> dict:
    """Chiamata dopo che l'utente ha ricevuto il numero P.IVA."""
    profilo = profilo_vuoto()

    profilo["anagrafica"].update({
        "nome": dati["nome"],
        "cognome": dati["cognome"],
        "codice_fiscale": dati.get("codice_fiscale", ""),
        "data_nascita": dati.get("data_nascita", ""),
        "comune_nascita": dati.get("comune_nascita", ""),
        "provincia_nascita": dati.get("provincia_nascita", ""),
        "residenza": f"{dati.get('indirizzo_residenza', '')}, {dati.get('cap_residenza', '')} {dati.get('comune_residenza', '')} ({dati.get('provincia_residenza', '')})",
        "email": dati.get("email", ""),
        "telefono": dati.get("telefono", ""),
    })

    ateco = dati.get("ateco", "62.01.00")
    coeff = next((a["coefficiente"] for a in ATECO_SUGGERITI if a["codice"] == ateco), 67)
    inps_tipo = next((a["inps"] for a in ATECO_SUGGERITI if a["codice"] == ateco), "separata")

    profilo["piva"].update({
        "numero": numero_piva,
        "data_apertura": date.today().isoformat(),
        "stato": "attiva",
        "ateco_primario": ateco,
        "coefficiente_redditivita": coeff,
    })

    profilo["regime"].update({
        "tipo": "forfettario",
        "aliquota": 0.05,
        "anno_inizio": date.today().year,
    })

    profilo["inps"]["gestione"] = inps_tipo

    profilo["canali_notifica"].update({
        "email": dati.get("email", ""),
        "telefono": dati.get("telefono", ""),
        "telegram_chat_id": dati.get("telegram_chat_id", ""),
    })

    salva_profilo(profilo)
    logger.info("Profilo inizializzato per P.IVA %s", numero_piva)
    return profilo


# ---------------------------------------------------------------------------
# Flusso completo
# ---------------------------------------------------------------------------
def esegui_wizard(dati: dict) -> dict:
    """
    Esegue il wizard completo.
    dati = dict con tutti i campi dell'utente.
    """
    risultato = {}

    # 1. Checklist
    risultato["checklist"] = genera_checklist(dati)

    # 2. AA9/12
    risultato["aa9_12"] = genera_aa9_12(dati)

    # 3. Guida
    risultato["guida"] = genera_guida_apertura(dati)

    # 4. Salva tutto
    output = settings.CONTEXT_DIR / "wizard_completo.json"
    # Non salviamo la guida (e' markdown), solo il resto
    save_data = {k: v for k, v in risultato.items() if k != "guida"}
    with open(output, "w", encoding="utf-8") as f:
        json.dump(save_data, f, indent=2, ensure_ascii=False)

    logger.info("Wizard completo eseguito")
    return risultato


if __name__ == "__main__":
    # Demo con dati di esempio
    dati_demo = {
        "nome": "Daniele",
        "cognome": "Rinaldi",
        "codice_fiscale": "",
        "data_nascita": "",
        "comune_nascita": "",
        "provincia_nascita": "",
        "sesso": "M",
        "indirizzo_residenza": "",
        "cap_residenza": "",
        "comune_residenza": "",
        "provincia_residenza": "",
        "email": "",
        "telefono": "",
        "pec": "",
        "ateco": "62.01.00",
        "descrizione_attivita": "Sviluppo software per controllo motori, stampa 3D, sistemi di guida autonoma per biciclette",
        "fatturato_stimato": 50000,
    }

    risultato = esegui_wizard(dati_demo)

    print("=== CHECKLIST ===")
    for k, v in risultato["checklist"].items():
        stato = "✅" if v["stato"] == "fatto" else "❌" if v["obbligatorio"] else "⚪"
        print(f"  {stato} {v['nome']}")
        if v["link"]:
            for link in v["link"]:
                print(f"     → {link['provider']}: {link['url']} ({link['prezzo']})")

    print("\n=== AA9/12 GENERATO ===")
    print(f"  File: data/contribuente/aa9_12.json")

    print("\n=== GUIDA APERTURA ===")
    print(f"  File: context/guida_apertura.md")
    print(f"  (apri il file per la guida passo-passo)")
