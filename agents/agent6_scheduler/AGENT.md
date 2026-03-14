# Agent6 — Payment Scheduler

## Responsabilità
- Generare F24 precompilati con codici tributo e importi validati da Agent3b
- Costruire scadenzario annuale completo
- Alimentare Agent9 con date e importi per notifiche

## Input
- Importi validati da Agent3b
- Codici tributo da Agent3
- Calendario fiscale da `shared/tax_calendar.json`

## Output
- F24 precompilati pronti per il pagamento
- Scadenzario annuale completo
- Feed scadenze verso Agent9

## Integrazioni
- `shared/tax_calendar.json` — Calendario scadenze fiscali
- `agents/agent9_notifier/` — Notifiche scadenze
