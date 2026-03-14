# Agent3b — Validator (doppio controllo deterministico)

## Responsabilità
- Ricalcolare tutto indipendentemente da Agent3 usando **logica deterministica pura** (Python, zero LLM)
- Implementazione scritta **separatamente** da Agent3, stessa logica, codice diverso
- Verificare in particolare:
  - Correttezza della deduzione contributi INPS dal reddito imponibile
  - Calcoli separati per ciascun codice ATECO
  - Aggregazione multi-ATECO
  - Aliquota corretta (5% vs 15%)
  - Acconti basati su anno precedente corretto
  - Compensazione crediti d'imposta
- Confrontare risultati campo per campo: se coincidono passa avanti, se divergono **anche di 1 centesimo** blocca il flusso
- Nessun F24 viene generato senza validazione superata

## Architettura
```
Agent3 (deterministico, impl. A) ──┐
                                    ├──▶ Comparatore ──▶ OK / BLOCCO
Agent3b (deterministico, impl. B) ──┘
```

Entrambi sono Python puro. La garanzia è che due implementazioni indipendenti della stessa logica fiscale producano lo stesso risultato. Se non lo fanno, c'è un bug da fixare prima di procedere.

## Checklist di validazione
- [ ] `reddito_imponibile = Σ(ricavi_ATECO_i × coeff_ATECO_i) − contributi_INPS_versati`
- [ ] `imposta = reddito_imponibile × aliquota`
- [ ] Aliquota corretta (5% se primi 5 anni, 15% altrimenti)
- [ ] Acconti calcolati su imposta anno precedente (non anno corrente)
- [ ] Crediti anno precedente correttamente compensati
- [ ] Codici tributo corretti per tipo gestione INPS
- [ ] Importi arrotondati all'unità di euro (regola F24)

## Input
- Stessi dati grezzi di Agent3 (ricavi per ATECO, contributi versati, parametri INPS, storico)
- Output di Agent3 per confronto campo per campo

## Output
- Validazione OK → flusso prosegue verso Agent6
- Validazione KO → blocco flusso + alert via Agent9 con dettaglio divergenza (quale campo, quale valore atteso vs calcolato)
- Report di confronto dettagliato

## Integrazioni
- `shared/ateco_coefficients.json` — Coefficienti di redditività
- `shared/inps_rates.json` — Aliquote INPS per anno
- `shared/f24_tax_codes.json` — Verifica codici tributo
- `agents/agent9_notifier/` — Alert in caso di divergenza
- `agents/supervisor/` — Log validazione nello storico
