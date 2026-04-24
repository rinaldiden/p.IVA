# Agent6 — Payment Scheduler

## Responsabilità
- Generare F24 precompilati usando template da `shared/f24_template.json`
- Popolare con codici tributo da `shared/f24_tax_codes.json` e importi validati da Agent3b
- Costruire scadenzario annuale completo (imposta sostitutiva + contributi INPS + bollo virtuale trimestrale)
- Gestire scadenze diverse per gestione separata vs artigiani/commercianti
- Calcolare rate se l'utente sceglie il pagamento rateizzato (con interessi)
- Alimentare Agent9 con date e importi per notifiche
- Inviare F24 precompilati ad **Agent8** per esecuzione pagamento via PSD2
- **Ravvedimento operoso**: se un pagamento risulta in ritardo, calcolare automaticamente sanzione ridotta + interessi legali e generare F24 integrativo con codici tributo 8913 (sanzione) e 1992 (interessi)
- Includere nello scadenzario anche le **scadenze bollo virtuale trimestrale** (codici 2501-2504) ricevute da Agent8
- Gestire **compensazione crediti d'imposta** in F24 (crediti comunicati da Agent5 via Supervisor)

## Input
- Importi validati da Agent3b
- Codici tributo da `shared/f24_tax_codes.json`
- Template F24 da `shared/f24_template.json`
- Calendario fiscale da `shared/tax_calendar.json`
- Tipo iscrizione INPS dal Supervisor

## Output
- F24 precompilati inviati ad Agent8 per esecuzione pagamento
- Scadenzario annuale completo personalizzato (imposte + INPS + bollo virtuale)
- Piano rateizzazione se richiesto
- F24 ravvedimento operoso se pagamento in ritardo
- Feed scadenze verso Agent9

## Integrazioni
- `shared/tax_calendar.json` — Calendario scadenze fiscali
- `shared/f24_tax_codes.json` — Codici tributo (inclusi ravvedimento operoso e bollo virtuale)
- `shared/f24_template.json` — Template modello F24
- `agents/agent8_invoicer/` — Esecuzione pagamento F24 e scadenze bollo virtuale
- `agents/agent9_notifier/` — Notifiche scadenze
- `agents/supervisor/` — Tipo iscrizione INPS, dati contribuente, crediti d'imposta
