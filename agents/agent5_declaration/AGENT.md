# Agent5 — Declaration Generator

## Responsabilità
- Compilare Modello Redditi PF
- Compilare Quadro LM (reddito forfettario) — **con supporto multi-ATECO** (righi separati per codice attività)
- Compilare Quadro RS (dati statistici)
- Firmare digitalmente tramite Vault (credenziali archiviate da Agent0)
- Trasmettere via intermediario abilitato (da scegliere)

## Input
- Calcoli validati da Agent3b (per ATECO e aggregati)
- Dati anagrafici dell'utente dal Supervisor
- Firma digitale dal Vault
- Storico anni precedenti dal Supervisor
- Crediti d'imposta dal Supervisor

## Output
- Modello Redditi PF compilato e firmato digitalmente
- File pronto per invio telematico
- Ricevuta di trasmissione archiviata nel Supervisor

## Integrazioni
- `integrations/vault/` — Accesso credenziali firma digitale
- `integrations/invio_telematico/` — Trasmissione via intermediario abilitato
- `integrations/agenzia_entrate/` — Specifiche tecniche modello
- `agents/supervisor/` — Dati contribuente e archiviazione ricevuta

## Note
- L'invio telematico avviene SEMPRE tramite intermediario abilitato ex art. 3 DPR 322/98
- Il Quadro LM supporta più righi per contribuenti con più codici ATECO
