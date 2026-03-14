# Agent5 — Declaration Generator

## Responsabilità
- Compilare Modello Redditi PF
- Compilare Quadro LM (reddito forfettario)
- Compilare Quadro RS (dati statistici)
- Firmare digitalmente con credenziali ottenute da Agent0

## Input
- Calcoli validati da Agent3b
- Dati anagrafici dell'utente
- Firma digitale da Agent0

## Output
- Modello Redditi PF compilato e firmato digitalmente
- File pronto per invio telematico

## Integrazioni
- `integrations/firma_digitale/` — Firma digitale del documento
- `integrations/invio_telematico/` — Trasmissione via Entratel
- `integrations/agenzia_entrate/` — Specifiche tecniche modello
