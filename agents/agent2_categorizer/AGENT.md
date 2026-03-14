# Agent2 — Categorizer

## Responsabilità
- Classificare ricavi per tipo e **per codice ATECO** (supporto multi-ATECO)
- Archiviare spese per documentazione gestionale (nel forfettario non abbattono l'imponibile)
- Flaggare anomalie e movimenti non classificati
- Tenere il contatore ricavi aggiornato in tempo reale, **separato per ATECO**
- Monitorare andamento fatturazione e alimentare Agent4 con trend e proiezione annuale

## Multi-ATECO
Se il contribuente ha più codici ATECO:
- Ogni ricavo viene associato al codice ATECO corretto
- I contatori sono separati per ATECO
- La proiezione annuale è calcolata per ciascun ATECO e in aggregato
- Agent3 riceve i ricavi già separati per calcolare i diversi coefficienti di redditività
- Il Supervisor aggrega il tutto nel profilo contribuente

## Input
- Flusso normalizzato di transazioni da Agent1
- Fatture emesse da Agent8 (già associate all'ATECO corretto)
- Coefficienti ATECO da `shared/ateco_coefficients.json`
- Codici ATECO del contribuente dal Supervisor
- Storico anni precedenti dal Supervisor

## Output
- Transazioni classificate e archiviate, taggate per ATECO
- Contatore ricavi aggiornato per ATECO e totale
- Trend fatturazione con proiezione annuale (per ATECO e aggregato)
- Alert anomalie verso Agent4 e Agent9

## Integrazioni
- `shared/ateco_coefficients.json` — Coefficienti di redditività
- `shared/models/` — Modelli di classificazione
- `agents/supervisor/` — Lettura storico, codici ATECO, aggiornamento stato
- `agents/agent8_invoicing/` — Ricavi da fatture emesse
