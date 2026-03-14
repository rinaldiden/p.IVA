# Agent3 — Calculator

## Responsabilità
- Calcolare imposta sostitutiva: coefficiente di redditività per codice ATECO × ricavi × aliquota (15% ordinaria, 5% primi 5 anni)
- Calcolare contributi INPS: gestione separata (% sul reddito) o artigiani/commercianti (fisso + % sul reddito eccedente il minimale)
- Calcolare riduzione contributiva 35% se applicabile (artigiani/commercianti forfettari)
- Calcolare acconti (giugno/luglio e novembre) e saldo basandosi su anno precedente
- Generare importi F24 con codici tributo corretti da `shared/f24_tax_codes.json`

## Input
- Ricavi classificati da Agent2
- Codice ATECO e coefficiente di redditività
- Anno di apertura P.IVA (per determinare aliquota 5% o 15%)
- Parametri INPS correnti
- Storico anno precedente dal Supervisor (per calcolo acconti)

## Output
- Calcolo imposta sostitutiva dettagliato
- Calcolo contributi INPS (fissi + percentuali)
- Importi F24 con codici tributo da `shared/f24_tax_codes.json`
- Piano acconti e saldo con importi esatti
- Tutto inviato ad Agent3b per validazione

## Integrazioni
- `shared/ateco_coefficients.json` — Coefficienti di redditività
- `shared/tax_calendar.json` — Scadenze fiscali
- `shared/f24_tax_codes.json` — Codici tributo
- `agents/supervisor/` — Lettura storico contribuente
