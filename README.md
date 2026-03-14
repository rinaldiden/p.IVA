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
┌─────────────────────────────────────────────────────────────────┐
│                        FiscalAI                                 │
│                                                                 │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │ Agent0   │    │ Agent1   │    │ Agent2   │    │ Agent3   │  │
│  │ Wizard & │───▶│Collector │───▶│Categori- │───▶│Calcula-  │  │
│  │Bootstrap │    │          │    │zer       │    │tor       │  │
│  └──────────┘    └──────────┘    └──────────┘    └────┬─────┘  │
│       │               │                              │         │
│       │          ┌──────────┐                   ┌──────────┐   │
│       │          │  OCR     │                   │ Agent3b  │   │
│       │          │Subagent  │                   │Validator │   │
│       │          └──────────┘                   └────┬─────┘   │
│       │                                              │         │
│       │  ┌──────────┐    ┌──────────┐    ┌──────────┐│         │
│       │  │ Agent4   │    │ Agent5   │    │ Agent6   ││         │
│       │  │Compliance│◀──▶│Declara-  │◀───│Scheduler │◀┘        │
│       │  │ Checker  │    │tion Gen  │    │          │          │
│       │  └──────────┘    └──────────┘    └──────────┘          │
│       │                                       │                │
│       │  ┌──────────┐              ┌──────────┐                │
│       └─▶│ Agent7   │              │ Agent9   │◀───────────────│
│          │ Advisor  │              │ Notifier │                │
│          └──────────┘              └──────────┘                │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Integrations Layer                          │   │
│  │  SDI · Open Banking · Agenzia Entrate · INPS · CCIAA   │   │
│  │  Firma Digitale · Invio Telematico                       │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Agenti

### Agent0 — Wizard & Bootstrap
Onboarding completo: ottiene firma digitale via API, apre la P.IVA compilando il modello AA9/12, iscrive alla CCIAA via ComUnica se necessario, iscrive all'INPS, gestisce il SUAP telematico. Configura banca (Open Banking PSD2) e canali di ricezione documenti. La firma digitale ottenuta qui viene riutilizzata da tutti gli agenti successivi.

### Agent1 — Collector
Aggrega flussi da tre canali: SDI (fattura elettronica XML), banca PSD2 (polling movimenti), OCR Subagent (foto scontrini via app/WhatsApp/email/web). Input continuo, non solo a fine anno.

### Agent2 — Categorizer
Classifica ricavi per tipo, archivia spese per documentazione gestionale, flagga anomalie, tiene il contatore ricavi aggiornato in tempo reale verso soglia 85k.

### Agent3 — Calculator
Calcola imposta sostitutiva (coefficiente redditività ATECO × ricavi × aliquota), contributi INPS, acconti e saldo. Genera importi F24 con codici tributo corretti.

### Agent3b — Validator
Ricalcola tutto indipendentemente da Agent3 con logica separata. Se i risultati coincidono passa avanti, se divergono blocca il flusso e invia alert. Nessun F24 viene generato senza validazione superata.

### Agent4 — Compliance Checker
Verifica soglia ricavi 85.000€ (alert proattivi a 70k, 80k, 84k), controlla cause ostative, verifica esclusioni dal regime forfettario.

### Agent5 — Declaration Generator
Compila Modello Redditi PF (Quadro LM + Quadro RS), firma digitalmente con credenziali di Agent0.

### Agent6 — Payment Scheduler
Genera F24 precompilati con importi validati, costruisce scadenzario annuale, alimenta Agent9.

### Agent7 — Advisor
Analisi proattiva: avvisi soglia, suggerimenti ottimizzazione, valutazione passaggio a ordinario/SRL, pianificazione fiscale anno successivo.

### Agent9 — Notifier
SMS + email 7 giorni prima di ogni scadenza fiscale, con importo esatto da pagare.

### Invio Telematico
Firma digitale + trasmissione via intermediario abilitato (Abletech API / TeamSystem API / canale Entratel). Completamente automatico.

---

## Stack Tecnologico (previsto)

- **Runtime**: Python 3.12+
- **Orchestrazione agenti**: Claude Agent SDK / LangGraph
- **LLM**: Claude (Anthropic API)
- **OCR**: Claude Vision / Tesseract come fallback
- **Database**: PostgreSQL + pgvector per classificazione semantica
- **Message queue**: Redis Streams / NATS per comunicazione inter-agente
- **API Layer**: FastAPI
- **Open Banking**: Tink / Yapily (PSD2)
- **Fatturazione elettronica**: SDK SDI Agenzia Entrate
- **Firma digitale**: Aruba Sign API / Namirial / InfoCert
- **Invio telematico**: Abletech API / TeamSystem
- **Notifiche**: Twilio (SMS) + SendGrid (email) + WhatsApp Business API
- **Infra**: Docker + Railway / Fly.io
- **CI/CD**: GitHub Actions

---

## Roadmap

1. **Agent0 MVP** — Wizard che guida l'apertura P.IVA, stima imposte, spiega il regime
2. **Agent1 + Agent2** — Collector e categorizzazione automatica
3. **Agent3 + Agent3b** — Calcolo e doppia validazione
4. **Agent6 + Agent9** — Scadenziario e notifiche
5. **Agent5** — Generazione dichiarazione
6. **Agent4 + Agent7** — Compliance e advisory
7. **Invio telematico end-to-end** — Firma + trasmissione automatica
8. **App mobile** — Interfaccia utente per scontrini e dashboard

---

## Note Legali

FiscalAI è un sistema di supporto automatizzato per la gestione fiscale. **Non sostituisce la consulenza professionale certificata** di un commercialista o consulente fiscale abilitato. L'utente è responsabile della verifica finale dei dati e degli adempimenti fiscali. Il sistema è progettato per il regime forfettario italiano e non copre altri regimi fiscali.

---

---

*Costruito per un mondo dove la burocrazia fiscale non ruba più tempo alla vita.*
