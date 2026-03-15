# FiscalAI — P.IVA Autonoma

**Sistema multi-agente completamente autonomo per gestire il ciclo fiscale completo di un contribuente forfettario italiano.**

Dalla apertura della P.IVA fino all'invio telematico della dichiarazione dei redditi.
Obiettivo: zero commercialista, zero intervento umano. Tutti gli 11 agenti implementati con logica completa e 204 test. Mancano solo i canali esterni (SDI, PSD2, Entratel) per la produzione.

---

## Missione

Liberare i forfettari italiani dalla dipendenza dal commercialista.

Il regime forfettario è il più semplice che esista: aliquota fissa, niente IVA, niente registri contabili obbligatori. Eppure milioni di persone pagano centinaia di euro l'anno per farsi dire quanto devono al fisco. FiscalAI automatizza tutto il ciclo — dall'apertura della partita IVA alla dichiarazione dei redditi — con un sistema di agenti che lavorano in autonomia, si controllano a vicenda e non sbagliano i calcoli.

---

## Architettura

```
┌───────────────────────────────────────────────────────────────────────┐
│                            FiscalAI                                   │
│                                                                       │
│                     ┌────────────────────┐                            │
│                     │    SUPERVISOR      │                            │
│                     │ Profilo & Storico  │                            │
│                     │   Contribuente     │                            │
│                     └────────┬───────────┘                            │
│                              │ coordina tutto                         │
│                              │                                        │
│  ┌──────────┐    ┌───────────┤    ┌──────────┐    ┌──────────┐       │
│  │ Agent0   │    │ Agent1    │    │ Agent8   │    │ Agent2   │       │
│  │ Wizard & │───▶│ Collector │───▶│Invoicing │───▶│Categori- │       │
│  │Bootstrap │    │           │    │(fatture) │    │zer       │       │
│  └──────────┘    └─────┬─────┘    └──────────┘    └────┬─────┘       │
│       │                │               │               │             │
│       │          ┌───────────┐          │          ┌──────────┐       │
│       │          │    OCR    │          │          │ Agent3   │       │
│       │          │ Subagent  │          │          │Calcula-  │       │
│       │          └───────────┘          │          │tor (det.)│       │
│       │                                 │          └────┬─────┘       │
│       │                                 │               │            │
│       │                                 │          ┌──────────┐       │
│       │                                 │          │ Agent3b  │       │
│       │                                 │          │Validator │       │
│       │                                 │          │  (det.)  │       │
│       │                                 │          └────┬─────┘       │
│       │  ┌──────────┐    ┌──────────┐   │  ┌──────────┐ │            │
│       │  │ Agent4   │    │ Agent5   │   │  │ Agent6   │ │            │
│       │  │Compliance│◀──▶│Declara-  │◀──┘  │Scheduler │◀┘            │
│       │  │ Checker  │    │tion Gen  │◀─────│  + F24   │              │
│       │  └──────────┘    └──────────┘      └──────────┘              │
│       │       │                                 │                    │
│       │  ┌──────────┐                    ┌──────────┐                │
│       └─▶│ Agent7   │                    │ Agent9   │◀───────────    │
│          │ Advisor  │                    │ Notifier │                │
│          └──────────┘                    └──────────┘                │
│                                                                       │
│  ┌──────────┐                                                       │
│  │ Agent10  │  Monitora GU, AdE, INPS, Normattiva                   │
│  │Normative │  Aggiorna parametri shared/ dalla data di efficacia   │
│  │ Watcher  │  Certezza bassa → human review                        │
│  └──────────┘                                                       │
│                                                                       │
│  ┌────────────────────────────────────────────────────────────────┐   │
│  │                    Vault — Auth Agent                          │   │
│  │   Firma Digitale · SPID · PSD2 · SDI · HSM-backed            │   │
│  └────────────────────────────────────────────────────────────────┘   │
│  ┌────────────────────────────────────────────────────────────────┐   │
│  │                   Integrations Layer                           │   │
│  │  SDI · Open Banking · Agenzia Entrate · INPS · CCIAA         │   │
│  │  Conservazione Sostitutiva · Intermediario Abilitato          │   │
│  └────────────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────────┘
```

---

## Agenti

### Supervisor — Profilo Contribuente, Storico & Coordinamento
Fonte di verità unica. Mantiene profilo completo (supporto multi-ATECO), storico pluriennale, crediti d'imposta anno su anno, audit trail. Ogni gennaio verifica nuove circolari INPS e aggiornamenti normativi, aggiorna i parametri di sistema.

### Agent0 — Wizard & Bootstrap
Guida l'utente nell'ottenimento della firma digitale e archivia le credenziali nel Vault. Acquisisce credenziali SPID per accesso ai servizi AdE/INPS. Apre la P.IVA (multi-ATECO) tramite intermediario, iscrive alla CCIAA/INPS, configura banca PSD2 e canali documenti, attiva la conservazione sostitutiva gratuita AdE.

### Agent1 — Collector
Aggrega flussi da: SDI (fatture XML emesse e ricevute), banca PSD2 (polling movimenti), OCR Subagent (scontrini via app/email/Google Drive/Google Foto). Gestisce il ciclo completo consent PSD2: alert a T-7 e T-3 con link re-consent, sospensione polling a T-0, backfill automatico al rinnovo. Verifica autenticità fatture ricevute da SDI e flagga anomalie. Archivia automaticamente le fatture nella conservazione sostitutiva AdE.

### Agent2 — Categorizer
Classifica ricavi **per codice ATECO**, archivia spese, flagga anomalie. Tiene contatori ricavi separati per ATECO e aggregati, con proiezione annuale per Agent4.

### Agent3 — Calculator (deterministico)
**Python puro, zero LLM.** Calcola per ciascun ATECO: `ricavi × coefficiente`. Poi: `reddito_imponibile = Σ(ricavi_ATECO × coeff) − contributi_INPS_versati`. Imposta sostitutiva, contributi INPS (con riduzione 35%), acconti, saldo, compensazione crediti. Supporta multi-ATECO.

### Agent3b — Validator (deterministico)
**Seconda implementazione indipendente**, stesso calcolo, codice diverso. Confronto campo per campo: se diverge anche di 1 centesimo, blocco totale + alert. Nessun F24 esce senza doppia validazione.

### Agent4 — Compliance Checker
Monitora fatturazione aggregata multi-ATECO con proiezione annuale. Alert multi-soglia: **70k** (attenzione) → **80k** (avvicinamento) → **84k** (valuta rinvio) → **85k** (uscita dall'anno successivo). Il superamento della soglia comporta sempre l'uscita dal regime dall'anno fiscale successivo, mai in corso d'anno (normativa aggiornata al 2024, L. 197/2022). Verifica cause ostative, esclusioni, necessità visto di conformità per crediti > 5.000€.

### Agent5 — Declaration Generator
Compila Modello Redditi PF con Quadro LM multi-ATECO + Quadro RS. Firma tramite Vault, trasmette via intermediario abilitato.

### Agent6 — Payment Scheduler
Genera F24 da template con codici tributo, importi validati e **compensazione crediti d'imposta**. Scadenzario personalizzato per tipo gestione INPS. Include versamento marche da bollo virtuali (codice 2501). Gestisce rateizzazione.

### Agent7 — Advisor
Analisi proattiva, simulazione forfettario vs ordinario vs SRL, pianificazione fiscale, ottimizzazione mix ATECO.

### Agent8 — Invoicing (Fatturazione Attiva)
Nel flusso principale dopo Agent1. Emette fatture elettroniche XML conformi SDI. Regime fiscale RF19, natura N2.2, dicitura obbligatoria forfettari. Marca da bollo virtuale 2€ su fatture > 77,47€. Numerazione progressiva, note di credito, fatture PA. Gestione completa esiti SDI: RC (consegnata), MC (mancata consegna → alert), NS (scartata → correzione e ri-emissione automatica entro 5 giorni), EC (esito PA), AT (attestazione).

### Agent9 — Notifier
Hub notifiche centralizzato con sistema di priorità (informativa/normale/alta/critica). Trigger: scadenze fiscali (Agent6), scarti SDI (Agent8), consent PSD2 (Agent1), divergenza calcoli (Agent3b), soglie ricavi (Agent4), errori trasmissione (Agent5), raccomandazioni (Agent7), scadenza credenziali (Vault). Le notifiche critiche hanno retry ogni 4h fino a conferma lettura.

### Agent10 — NormativeWatcher
Monitora automaticamente Gazzetta Ufficiale, Agenzia delle Entrate, INPS e Normattiva. Aggiorna i parametri fiscali del sistema (coefficienti ATECO, aliquote INPS, soglie, scadenze) dalla data di efficacia della norma, non dalla data di pubblicazione. Certezza bassa → human review. Audit trail immutabile di ogni modifica normativa applicata.

### Vault — Auth Agent
Custodisce tutte le credenziali in vault dedicato HSM-backed. Gestisce sessioni SPID con 2FA, effettua login come client per gli agenti, policy di accesso per agente, audit trail di ogni accesso.

---

## Invio Telematico

L'invio avviene SEMPRE tramite **intermediario abilitato** ex art. 3 DPR 322/98. La firma digitale viene apposta tramite il Vault, la trasmissione viene instradata tramite l'intermediario.

> L'intermediario specifico è ancora da definire. Candidati in valutazione: Abletech API, TeamSystem API, altri.

---

## Calcolo Imposta — Formula

```
Per ciascun ATECO_i:
  reddito_ATECO_i = ricavi_ATECO_i × coefficiente_ATECO_i

Reddito lordo = Σ reddito_ATECO_i
Reddito imponibile = Reddito lordo − contributi_INPS_versati_anno

Imposta sostitutiva = Reddito imponibile × aliquota (5% o 15%)

Acconti = 100% imposta anno precedente (40% giugno + 60% novembre)
Saldo = Imposta anno corrente − acconti versati
  Se negativo → credito compensabile in F24 anno successivo
```

---

## Stack Tecnologico (previsto)

- **Runtime**: Python 3.12+
- **Orchestrazione agenti**: Claude Agent SDK / LangGraph
- **LLM**: Claude (Anthropic API) — solo per comunicazione naturale, NON per calcoli
- **Calcoli fiscali**: Python puro deterministico (Agent3 + Agent3b)
- **OCR**: Claude Vision / Tesseract come fallback
- **Database**: PostgreSQL + pgvector per classificazione semantica
- **Message queue**: Redis Streams / NATS per comunicazione inter-agente
- **API Layer**: FastAPI
- **Vault**: HashiCorp Vault / AWS KMS + HSM
- **Open Banking**: Tink / Yapily (PSD2)
- **Fatturazione elettronica**: SDK SDI Agenzia Entrate
- **Firma digitale**: Aruba Sign API / Namirial / InfoCert (credenziali in Vault)
- **Invio telematico**: Intermediario abilitato (da definire)
- **Conservazione sostitutiva**: Servizio gratuito AdE (Fatture e Corrispettivi)
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
│   ├── supervisor/              # Profilo contribuente & coordinamento
│   ├── agent0_wizard/           # Onboarding & bootstrap
│   ├── agent1_collector/        # Raccolta dati
│   │   └── ocr_subagent/        # OCR scontrini
│   ├── agent2_categorizer/      # Classificazione (multi-ATECO)
│   ├── agent3_calculator/       # Calcolo imposte (deterministico)
│   ├── agent3b_validator/       # Doppio controllo (deterministico)
│   ├── agent4_compliance/       # Compliance e soglie multi-livello
│   ├── agent5_declaration/      # Generazione dichiarazione
│   ├── agent6_scheduler/        # Scadenzario e F24 + compensazioni
│   ├── agent7_advisor/          # Advisory proattivo
│   ├── agent8_invoicing/        # Fatturazione attiva elettronica
│   ├── agent9_notifier/         # Notifiche
│   └── agent10_normative/      # Monitoraggio normativo autonomo
├── integrations/
│   ├── agenzia_entrate/         # API AdE + conservazione sostitutiva
│   ├── open_banking/            # PSD2 + gestione consent 90gg
│   ├── sdi/                     # Sistema di Interscambio
│   ├── firma_digitale/          # Provider firma digitale
│   ├── inps/                    # Gestione contributiva
│   ├── cciaa_comunica/          # Camera di Commercio
│   ├── invio_telematico/        # Intermediario abilitato
│   └── vault/                   # Auth Agent + Credential Manager
├── shared/
│   ├── ateco_coefficients.json  # Coefficienti redditività per ATECO
│   ├── tax_calendar.json        # Scadenze fiscali complete
│   ├── f24_tax_codes.json       # Codici tributo + causali INPS (separati)
│   ├── f24_template.json        # Template struttura F24
│   ├── inps_rates.json          # Aliquote INPS per anno (aggiornamento annuale)
│   ├── forfettario_limits.json  # Soglie, aliquote, limiti regime forfettario
│   ├── messaging/              # Inter-agent Redis Streams bus
│   └── models/
├── tests/
└── docs/
```

Ogni cartella agente contiene un file `AGENT.md` con responsabilità, input, output e integrazioni.

---

## Roadmap

1. **Vault** — Infrastruttura sicurezza credenziali (prerequisito bloccante per Agent0)
2. **Agent0 MVP** — Wizard onboarding, stima imposte, spiega il regime
3. **Supervisor** — Profilo contribuente, storico pluriennale, aggiornamenti normativi
4. **Agent8** — Fatturazione attiva elettronica (genera ricavi da subito)
5. **Agent1 + OCR Subagent** — Collector multi-canale + re-consent PSD2
6. **Agent2** — Categorizzazione multi-ATECO
7. **Agent3 + Agent3b** — Doppio calcolo deterministico + validazione
8. **Agent6 + Agent9** — Scadenzario F24 con compensazioni e notifiche
9. **Agent5** — Generazione e invio dichiarazione via intermediario
10. **Agent4 + Agent7** — Compliance multi-soglia e advisory
11. **App mobile** — Scontrini e dashboard
12. **Agent10** — NormativeWatcher: autonomia normativa completa

> Il Vault è prerequisito bloccante per Agent0: firma digitale e SPID non possono essere gestiti senza un sistema sicuro di credential management.

---

## Stato Implementazione

> Ultimo aggiornamento: 2026-03-15 — branch `v2-fiscal-fixes`

| Componente | Stato | Note |
|---|---|---|
| Vault | MVP ✅ | AES-256-GCM, policy per agente, audit trail, test integration |
| Agent0 — Wizard | MVP ✅ | Onboarding 6 step, simulatore, explainer Claude, ATECO→gestione auto, spese toggle |
| Agent3 — Calculator | MVP ✅ | Calcolo deterministico, multi-ATECO, F24, checksum |
| Agent3b — Validator | MVP ✅ | Validazione indipendente, blocco su 1 cent divergenza |
| Agent6 — Scheduler | MVP ✅ | Piano annuale F24, imposta sostitutiva saldo/acconti, INPS separata/artigiani/commercianti, compensazione crediti, 14 test |
| Agent8 — Invoicing | MVP ✅ | FatturaPA XML, marca da bollo, rivalsa INPS 4%, numerazione progressiva, esiti SDI, 12 test |
| Agent10 — NormativeWatcher | MVP ✅ | RSS GU, diff engine, scheduler, audit trail |
| Shared Messaging | MVP ✅ | Redis Streams, publisher/consumer, supervisor listener |
| Supervisor | Scheletro 🟡 | Persistenza profili flat, save_from_agent0, orchestrazione via Agent9 |
| Web App | MVP ✅ | Dashboard con sim live, gestione spese, fattura azienda/privato, lookup P.IVA VIES, storico fatture, stati SDI, download XML |
| Shared Config | MVP ✅ | ATECO catalog con gestione_inps (74 codici), INPS rates 2024-2025 completi |
| Agent1 — Collector | MVP ✅ | 3 canali (SDI XML parser, PSD2 normalizer, OCR), merge/dedup, consent lifecycle, 25 test |
| Agent2 — Categorizer | MVP ✅ | Categorizzazione ATECO per keyword, expense classifier, revenue counter, riconciliazione fattura↔pagamento, 19 test |
| Agent4 — Compliance | MVP ✅ | Soglia 85k (alert 70/80/90/100%), check scadenze F24, anomalie (concentrazione clienti, gap numerazione), bollo, INPS, 18 test |
| Agent5 — Declaration | MVP ✅ | Quadro LM completo (LM21-LM38), Quadro RR (INPS), validazione pre-invio, riepilogo, dry-run submit, 15 test |
| Agent7 — Advisor | MVP ✅ | Confronto forfettario/ordinario/SRL, soglia convenienza, what-if, ottimizzazione multi-ATECO, timing fatturazione, 17 test |
| Agent9 — Supervisor | MVP ✅ | Pipeline orchestrator (chiama tutti gli agent in sequenza), health check, error handling, notifiche multicanale (email/Telegram/push), template italiani, 25 test |

### Cosa manca per andare in produzione

- **Autenticazione utente** — login/registrazione con session Flask (secret_key impostata, mancano route login/logout e protezione endpoint)
- **Canali esterni reali** — SDI (serve intermediario API, consigliato Aruba 25€/anno o A-Cube free tier), PSD2 Open Banking (serve AISP license o aggregatore), OCR (serve servizio cloud)
- **Database** — persistenza su file JSON, da migrare a PostgreSQL per multi-utente
- **Test coverage** — 204 test passano; mancano test per route web e integration test end-to-end
- **Invio telematico dichiarazione** — Agent5 genera il modello completo ma l'invio richiede intermediario Entratel

---

## Note Legali

FiscalAI è un sistema di supporto automatizzato per la gestione fiscale. **Non sostituisce la consulenza professionale certificata** di un commercialista o consulente fiscale abilitato. L'utente è responsabile della verifica finale dei dati e degli adempimenti fiscali. Il sistema è progettato per il regime forfettario italiano e non copre altri regimi fiscali.

L'invio telematico delle dichiarazioni avviene esclusivamente tramite intermediario abilitato ai sensi dell'art. 3 del DPR 322/98. Per la fatturazione elettronica è sufficiente un canale accreditato SDI o un intermediario tecnologico (non serve abilitazione Entratel).

---

*Costruito per un mondo dove la burocrazia fiscale non ruba più tempo alla vita.*
