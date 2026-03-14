# Agent5 — Declaration Generator

## Responsabilità
- Compilare Modello Redditi PF
- Compilare Quadro LM (reddito forfettario)
- Compilare Quadro RS (dati statistici)
- Firmare digitalmente con credenziali archiviate da Agent0
- Trasmettere via intermediario abilitato (da scegliere)

## Input
- Calcoli validati da Agent3b
- Dati anagrafici dell'utente dal Supervisor
- Credenziali firma digitale da Agent0
- Storico anni precedenti dal Supervisor

## Output
- Modello Redditi PF compilato e firmato digitalmente
- File pronto per invio telematico
- Ricevuta di trasmissione archiviata nel Supervisor

## Integrazioni
- `integrations/firma_digitale/` — Firma digitale del documento
- `integrations/invio_telematico/` — Trasmissione via intermediario abilitato
- `integrations/agenzia_entrate/` — Specifiche tecniche modello
- `agents/supervisor/` — Dati contribuente e archiviazione ricevuta

## Note
- L'invio telematico avviene SEMPRE tramite intermediario abilitato ex art. 3 DPR 322/98
- L'intermediario specifico è ancora da scegliere (vedi `integrations/invio_telematico/`)
