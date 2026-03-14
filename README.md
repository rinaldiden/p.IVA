# FiscalAI — P.IVA Autonoma

**Sistema multi-agente completamente autonomo per gestire il ciclo fiscale completo di un contribuente forfettario italiano.**

Dalla apertura della P.IVA fino all'invio telematico della dichiarazione dei redditi.
Zero commercialista. Zero intervento umano.

---

## Missione

Liberare i forfettari italiani dalla dipendenza dal commercialista.

Il regime forfettario è il più semplice che esista: aliquota fissa, niente IVA, niente registri contabili obbligatori. Eppure milioni di persone pagano centinaia di euro l'anno per farsi dire quanto devono al fisco. FiscalAI automatizza tutto il ciclo — dall'apertura della partita IVA alla dichiarazione dei redditi — con un sistema di agenti che lavorano in autonomia, si controllano a vicenda e non sbagliano i calcoli.

---

## Architettura

```
┌──────────────────────────────────────────────────────────────────────┐
│                           FiscalAI                                   │
│                                                                      │
│                    ┌────────────────────┐                            │
│                    │    SUPERVISOR      │                            │
│                    │ Profilo & Storico  │                            │
│                    │   Contribuente     │                            │
│                    └────────┬───────────┘                            │
│                             │ coordina tutto                        │
│  ┌──────────┐    ┌──────────┴┐    ┌──────────┐    ┌──────────┐     │
│  │ Agent0   │    │ Agent1    │    │ Agent2   │    │ Agent3   │     │
│  │ Wizard & │───▶│ Collector │───▶│Categori- │───▶│Calcula-  │     │
│  │Bootstrap │    │           │    │zer       │    │tor (LLM) │     │
│  └──────────┘    └───────────┘    └──────────┘    └────┬─────┘     │
│       │               │                               │           │
│       │          ┌───────────┐                   ┌──────────┐      │
│       │          │    OCR    │                   │ Agent3b  │      │
│       │          │ Subagent  │                   │Validator │      │
│       │          └───────────┘                   │(determ.) │      │
│       │                                          └────┬─────┘      │
│       │  ┌──────────┐    ┌──────────┐    ┌──────────┐ │            │
│       │  │ Agent4   │    │ Agent5   │    │ Agent6   │ │            │
│       │  │Compliance│◀──▶│Declara-  │◀───│Scheduler │◀┘            │
│       │  │ Checker  │    │tion Gen  │    │          │              │
│       │  └──────────┘    └──────────┘    └──────────┘              │
│       │       │                               │                    │
│       │  ┌──────────┐              ┌──────────┐                    │
│       └─▶│ Agent7   │              │ Agent9   │◀───────────────    │
│          │ Advisor  │              │ Notifier │                    │
│          └──────────┘              └──────────┘                    │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                  Integrations Layer                           │   │
│  │  SDI · Open Banking · Agenzia Entrate · INPS · CCIAA        │   │
│  │  Firma Digitale · Intermediario Abilitato                    │   │
│  └──────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Agenti

### Supervisor — Profilo Contribuente & Coordinamento
Fonte di verità unica per tutti i dati del contribuente. Mantiene profilo completo, storico pluriennale (ricavi, imposte, dichiarazioni, F24 anno per anno), coordina il flusso tra agenti e archivia ogni documento generato.

### Agent0 — Wizard & Bootstrap
Guida l'utente nell'ottenimento della firma digitale (Camera di Commercio, SPID, provider certificato) e poi incamera le credenziali per uso automatico. Apre la P.IVA tramite intermediario abilitato, iscrive alla CCIAA/INPS, configura banca PSD2 e canali documenti. Gestisce la richiesta annuale di riduzione contributiva 35%.

### Agent1 — Collector
Aggrega flussi da tre canali: SDI (fattura elettronica XML), banca PSD2 (polling movimenti), OCR Subagent (foto scontrini via app/email/Google Drive/Google Foto). Input continuo, non solo a fine anno.

### Agent2 — Categorizer
Classifica ricavi per tipo, archivia spese per documentazione gestionale, flagga anomalie, tiene il contatore ricavi aggiornato e monitora il trend di fatturazione con proiezione annuale.

### Agent3 — Calculator
Calcola imposta sostitutiva (coefficiente redditività ATECO × ricavi × aliquota), contributi INPS (gestione separata o artigiani/commercianti con riduzione 35%), acconti e saldo. Genera importi F24 con codici tributo corretti.

### Agent3b — Validator (deterministico)
Ricalcola tutto indipendentemente da Agent3 usando **puro codice Python, zero LLM**. Aritmetica, tabelle e regole fiscali codificate. Se i risultati di Agent3 e Agent3b coincidono il flusso prosegue, se divergono si blocca tutto e parte l'alert. Nessun F24 esce senza doppia validazione.

### Agent4 — Compliance Checker
Monitora andamento fatturazione con proiezione annuale. Alert proattivi multi-soglia:
- **70k**: "stai andando bene, tieni d'occhio"
- **80k**: "ti avvicini alla soglia"
- **84k**: "valuta se rinviare fatture"
- **85k**: "superata — dal prossimo anno sei in regime ordinario"
- **95k**: "pericolo — se arrivi a 100k esci subito"
- **100k**: "CRITICO — uscita immediata con IVA retroattiva"

Verifica cause ostative e esclusioni (partecipazioni, redditi dipendente > 30k, fatturato verso ex datore).

### Agent5 — Declaration Generator
Compila Modello Redditi PF (Quadro LM + Quadro RS), firma digitalmente con credenziali di Agent0, trasmette via intermediario abilitato.

### Agent6 — Payment Scheduler
Genera F24 precompilati da template con codici tributo e importi validati. Costruisce scadenzario personalizzato (diverso per gestione separata vs artigiani/commercianti). Gestisce rateizzazione con interessi.

### Agent7 — Advisor
Analisi proattiva, simulazione comparativa forfettario vs ordinario vs SRL con numeri concreti, pianificazione fiscale anno successivo, suggerimenti timing fatturazione.

### Agent9 — Notifier
SMS + email + push notification 7 giorni prima di ogni scadenza fiscale, con importo esatto.

---

## Invio Telematico

L'invio avviene SEMPRE tramite **intermediario abilitato** ex art. 3 DPR 322/98. La firma digitale viene apposta con le credenziali archiviate da Agent0, la trasmissione viene instradata tramite l'intermediario scelto.

> L'intermediario specifico è ancora da definire. Candidati in valutazione: Abletech API, TeamSystem API, altri.

---

## Stack Tecnologico (previsto)

- **Runtime**: Python 3.12+
- **Orchestrazione agenti**: Claude Agent SDK / LangGraph
- **LLM**: Claude (Anthropic API)
- **Validatore deterministico**: Python puro (Agent3b — zero LLM)
- **OCR**: Claude Vision / Tesseract come fallback
- **Database**: PostgreSQL + pgvector per classificazione semantica
- **Message queue**: Redis Streams / NATS per comunicazione inter-agente
- **API Layer**: FastAPI
- **Open Banking**: Tink / Yapily (PSD2)
- **Fatturazione elettronica**: SDK SDI Agenzia Entrate
- **Firma digitale**: Aruba Sign API / Namirial / InfoCert (credenziali utente)
- **Invio telematico**: Intermediario abilitato (da definire)
- **Documenti**: Google Drive API / Google Photos API
- **Notifiche**: Twilio (SMS) + SendGrid (email) + push notification app
- **Infra**: Docker + Railway / Fly.io
- **CI/CD**: GitHub Actions

---

## Struttura Repository

```
p.IVA/
├── README.md
├── agents/
│   ├── supervisor/           # Profilo contribuente & coordinamento
│   ├── agent0_wizard/        # Onboarding & bootstrap
│   ├── agent1_collector/     # Raccolta dati
│   │   └── ocr_subagent/     # OCR scontrini
│   ├── agent2_categorizer/   # Classificazione
│   ├── agent3_calculator/    # Calcolo imposte (LLM-assisted)
│   ├── agent3b_validator/    # Doppio controllo (deterministico)
│   ├── agent4_compliance/    # Verifica compliance e soglie
│   ├── agent5_declaration/   # Generazione dichiarazione
│   ├── agent6_scheduler/     # Scadenzario e F24
│   ├── agent7_advisor/       # Advisory proattivo
│   └── agent9_notifier/      # Notifiche
├── integrations/
│   ├── agenzia_entrate/      # API Agenzia delle Entrate
│   ├── open_banking/         # PSD2
│   ├── sdi/                  # Sistema di Interscambio
│   ├── firma_digitale/       # Provider firma digitale
│   ├── inps/                 # Gestione contributiva
│   ├── cciaa_comunica/       # Camera di Commercio
│   └── invio_telematico/     # Intermediario abilitato
├── shared/
│   ├── ateco_coefficients.json  # Coefficienti redditività per ATECO
│   ├── tax_calendar.json        # Scadenze fiscali complete
│   ├── f24_tax_codes.json       # Codici tributo F24
│   ├── f24_template.json        # Template struttura F24
│   └── models/
├── tests/
└── docs/
```

Ogni cartella agente contiene un file `AGENT.md` con responsabilità, input, output e integrazioni.

---

## Roadmap

1. **Agent0 MVP** — Wizard che guida l'apertura P.IVA, stima imposte, spiega il regime
2. **Supervisor** — Profilo contribuente e storico pluriennale
3. **Agent1 + Agent2** — Collector e categorizzazione automatica
4. **Agent3 + Agent3b** — Calcolo LLM-assisted + validazione deterministica
5. **Agent6 + Agent9** — Scadenziario F24 e notifiche
6. **Agent5** — Generazione e invio dichiarazione via intermediario
7. **Agent4 + Agent7** — Compliance multi-soglia e advisory
8. **App mobile** — Interfaccia utente per scontrini e dashboard

---

## Note Legali

FiscalAI è un sistema di supporto automatizzato per la gestione fiscale. **Non sostituisce la consulenza professionale certificata** di un commercialista o consulente fiscale abilitato. L'utente è responsabile della verifica finale dei dati e degli adempimenti fiscali. Il sistema è progettato per il regime forfettario italiano e non copre altri regimi fiscali.

L'invio telematico delle dichiarazioni avviene esclusivamente tramite intermediario abilitato ai sensi dell'art. 3 del DPR 322/98.

---

*Costruito per un mondo dove la burocrazia fiscale non ruba più tempo alla vita.*
