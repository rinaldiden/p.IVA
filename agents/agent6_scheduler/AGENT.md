# Agent6 — Payment Scheduler

## Responsabilità
- Generare F24 precompilati usando template da `shared/f24_template.json`
- Popolare con codici tributo da `shared/f24_tax_codes.json` e importi validati da Agent3b
- Costruire scadenzario annuale completo (imposta sostitutiva + contributi INPS)
- Gestire scadenze diverse per gestione separata vs artigiani/commercianti
- Calcolare rate se l'utente sceglie il pagamento rateizzato (con interessi)
- Alimentare Agent9 con date e importi per notifiche

## Input
- Importi validati da Agent3b
- Codici tributo da `shared/f24_tax_codes.json`
- Template F24 da `shared/f24_template.json`
- Calendario fiscale da `shared/tax_calendar.json`
- Tipo iscrizione INPS dal Supervisor

## Output
- F24 precompilati pronti per il pagamento
- Scadenzario annuale completo personalizzato
- Piano rateizzazione se richiesto
- Feed scadenze verso Agent9

## Integrazioni
- `shared/tax_calendar.json` — Calendario scadenze fiscali
- `shared/f24_tax_codes.json` — Codici tributo
- `shared/f24_template.json` — Template modello F24
- `agents/agent9_notifier/` — Notifiche scadenze
- `agents/supervisor/` — Tipo iscrizione INPS e dati contribuente
