# Agent3 — Calculator

## Responsabilità
- Calcolare imposta sostitutiva: coefficiente di redditività per codice ATECO × ricavi × aliquota (15% ordinaria, 5% primi 5 anni)
- Calcolare contributi INPS: gestione separata (% sul reddito) o artigiani/commercianti (fisso + % sul reddito)
- Calcolare acconti (giugno/luglio e novembre) e saldo
- Generare importi F24 con codici tributo corretti

## Input
- Ricavi classificati da Agent2
- Codice ATECO e coefficiente di redditività
- Anno di apertura P.IVA (per determinare aliquota 5% o 15%)
- Parametri INPS correnti

## Output
- Calcolo imposta sostitutiva
- Calcolo contributi INPS
- Importi F24 con codici tributo
- Piano acconti e saldo

## Integrazioni
- `shared/ateco_coefficients.json` — Coefficienti di redditività
- `shared/tax_calendar.json` — Scadenze fiscali
