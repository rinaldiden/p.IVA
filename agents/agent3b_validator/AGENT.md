# Agent3b — Validator (doppio controllo)

## Responsabilità
- Ricalcolare tutto indipendentemente da Agent3 usando logica separata
- Confrontare risultati: se coincidono passa avanti, se divergono blocca il flusso
- Inviare alert all'utente in caso di divergenza
- Nessun F24 viene generato senza validazione superata

## Input
- Stessi dati di input di Agent3 (ricavi, ATECO, parametri INPS)
- Output di Agent3 per confronto

## Output
- Validazione OK → flusso prosegue verso Agent6
- Validazione KO → blocco flusso + alert via Agent9
- Report di confronto dettagliato

## Integrazioni
- `shared/ateco_coefficients.json` — Coefficienti di redditività (implementazione indipendente)
- `agents/agent9_notifier/` — Alert in caso di divergenza
