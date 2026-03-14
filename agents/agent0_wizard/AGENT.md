# Agent0 — Wizard & Onboarding

## Responsabilità
- **Onboarding interattivo** in 6 step: dati base, attività ATECO, stima ricavi, INPS, simulazione fiscale, spiegazione personalizzata
- **Simulazione fiscale** via Agent3 + Agent3b (dual deterministic engine)
- **Confronto regimi** forfettario vs ordinario con risparmio stimato
- **Suggerimento ATECO** via Claude API (top 3 con coefficiente e motivazione)
- **Spiegazione personalizzata** in linguaggio naturale via Claude API
- **Scadenzario** con date e importi per primo anno e anni successivi
- **Calcolo rata mensile** da accantonare (imposta + INPS) / 12
- **Warning soglie** ricavi (70k alert precoce, 85k uscita forfettario)

## NON implementato (fase 2, post-Vault)
- Firma digitale
- Apertura P.IVA (modello AA9/12)
- SPID/CIE
- Iscrizione CCIAA / INPS
- Connessione reale PSD2

## Architettura

```
CLI → OnboardingWizard (6 step)
          │
          ├─ Explainer (Claude API) → suggerimenti ATECO, spiegazioni
          │
          └─ Simulator
               ├─ Agent3 (calcola)
               ├─ Agent3b (valida) — blocco se divergenza
               └─ Confronto regimi + scadenzario
```

## File
- `wizard.py` — orchestratore principale
- `simulator.py` — wrappa Agent3+3b, confronto regimi, scadenzario
- `explainer.py` — Claude API (suggest_ateco, explain_simulation, explain_inps, answer_question)
- `onboarding.py` — raccolta dati 6 step interattivi
- `models.py` — ProfiloContribuente, SimulationResult, Scadenza, ATECOSuggestion
- `redis_publisher.py` — pubblica su `fiscalai:agent0:onboarding_complete`
- `cli.py` — `python -m agents.agent0_wizard.cli [--no-claude] [--no-redis]`

## Evento Redis

Stream: `fiscalai:agent0:onboarding_complete`

Payload: profilo contribuente completo + risultato simulazione

## Integrazioni
- `agents/agent3_calculator/` — calcolo deterministico
- `agents/agent3b_validator/` — validazione indipendente
- `shared/ateco_coefficients.json` — catalogo ATECO con coefficienti
- `shared/inps_rates.json` — parametri INPS per anno
- Claude API — linguaggio naturale (model: claude-sonnet-4-20250514)
