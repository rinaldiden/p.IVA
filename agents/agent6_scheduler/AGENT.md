# Agent6 — Payment Scheduler

## Responsabilità
- Generare F24 precompilati usando template da `shared/f24_template.json`
- Popolare con codici tributo da `shared/f24_tax_codes.json` e importi validati da Agent3b
- **Gestire compensazione crediti d'imposta** in F24 (importi a credito vs importi a debito)
- Costruire scadenzario annuale completo (imposta sostitutiva + contributi INPS)
- Gestire scadenze diverse per gestione separata vs artigiani/commercianti
- Calcolare rate se l'utente sceglie il pagamento rateizzato (con interessi da codice 1668)
- Includere **versamento marche da bollo virtuali** (codice 2501, scadenza 30/01 anno successivo)
- Alimentare Agent9 con date e importi per notifiche

## Compensazione crediti
Se Agent3/Agent3b rilevano un credito d'imposta da anno precedente:
- Il credito viene inserito nella colonna "importi a credito" dell'F24
- Viene compensato con i debiti dello stesso F24
- Se il credito supera i debiti, l'eccedenza si riporta ai versamenti successivi
- Crediti > 5.000€ richiedono visto di conformità (Agent4 deve segnalarlo)

## Input
- Importi validati da Agent3b
- Codici tributo da `shared/f24_tax_codes.json`
- Template F24 da `shared/f24_template.json`
- Calendario fiscale da `shared/tax_calendar.json`
- Tipo iscrizione INPS dal Supervisor
- Crediti d'imposta da anni precedenti (dal Supervisor)
- Totale marche da bollo virtuali dell'anno (da Agent8)

## Output
- F24 precompilati pronti per il pagamento (con compensazioni se applicabili)
- Scadenzario annuale completo personalizzato
- Piano rateizzazione se richiesto
- Feed scadenze verso Agent9

## Integrazioni
- `shared/tax_calendar.json` — Calendario scadenze fiscali
- `shared/f24_tax_codes.json` — Codici tributo
- `shared/f24_template.json` — Template modello F24
- `agents/agent8_invoicing/` — Totale marche da bollo da versare
- `agents/agent9_notifier/` — Notifiche scadenze
- `agents/supervisor/` — Tipo INPS, crediti d'imposta, dati contribuente
