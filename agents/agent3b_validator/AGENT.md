# Agent3b — Validator (doppio controllo deterministico)

## Responsabilità
- Ricalcolare tutto indipendentemente da Agent3 usando **logica deterministica pura** (Python, zero LLM)
- Nessuna AI, nessun prompt: solo aritmetica, tabelle e regole fiscali codificate
- Confrontare risultati: se coincidono passa avanti, se divergono blocca il flusso
- Inviare alert all'utente in caso di divergenza
- Nessun F24 viene generato senza validazione superata

## Architettura
```
Agent3 (LLM-assisted) ──┐
                         ├──▶ Comparatore ──▶ OK / BLOCCO
Agent3b (deterministico) ┘
```

Agent3b è implementato come **puro codice Python** con:
- Tabelle aliquote hardcoded e verificate
- Coefficienti ATECO da file JSON
- Formule contributive INPS codificate
- Zero dipendenze da modelli linguistici

Questo garantisce un vero doppio controllo: se Agent3 (che usa LLM) sbaglia, Agent3b (che usa solo matematica) lo intercetta.

## Input
- Stessi dati grezzi di Agent3 (ricavi, ATECO, parametri INPS, storico)
- Output di Agent3 per confronto

## Output
- Validazione OK → flusso prosegue verso Agent6
- Validazione KO → blocco flusso + alert via Agent9 con dettaglio divergenza
- Report di confronto dettagliato (campo per campo)

## Integrazioni
- `shared/ateco_coefficients.json` — Coefficienti di redditività
- `shared/f24_tax_codes.json` — Verifica codici tributo
- `agents/agent9_notifier/` — Alert in caso di divergenza
- `agents/supervisor/` — Log validazione nello storico
