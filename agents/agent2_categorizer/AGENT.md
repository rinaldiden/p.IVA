# Agent2 — Categorizer

## Responsabilità
- Classificare ricavi per tipo
- Archiviare spese per documentazione gestionale (nel forfettario non abbattono l'imponibile)
- Flaggare anomalie e movimenti non classificati
- Tenere il contatore ricavi aggiornato in tempo reale
- Monitorare andamento fatturazione e alimentare Agent4 con trend

## Input
- Flusso normalizzato di transazioni da Agent1
- Coefficienti ATECO da `shared/ateco_coefficients.json`
- Storico anni precedenti dal Supervisor

## Output
- Transazioni classificate e archiviate
- Contatore ricavi aggiornato in tempo reale
- Trend fatturazione (proiezione annuale basata su andamento corrente)
- Alert anomalie verso Agent4 e Agent9

## Integrazioni
- `shared/ateco_coefficients.json` — Coefficienti di redditività
- `shared/models/` — Modelli di classificazione
- `agents/supervisor/` — Lettura storico e aggiornamento stato
