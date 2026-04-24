# Agent5 — Declaration Generator

## Responsabilità
- Compilare Modello Redditi PF
- Compilare **Quadro LM** (reddito forfettario: ricavi, coefficiente redditività, reddito imponibile, imposta sostitutiva, acconti versati)
- Compilare **Quadro RS** (dati statistici: informazioni su spese sostenute, dati per la trasparenza)
- Compilare **Quadro RX** (compensazioni e rimborsi: gestione eccedenze di versamento, crediti d'imposta da anni precedenti, scelta tra rimborso e compensazione in F24)
- Gestire **crediti d'imposta** da anni precedenti: leggere dal Supervisor lo storico crediti e riportarli nel Quadro RX per compensazione o rimborso
- Firmare digitalmente con credenziali archiviate da Agent0
- Trasmettere via intermediario abilitato (da scegliere)
- Inviare riepilogo dichiarazione all'utente via Agent9 per **conferma pre-invio** prima della trasmissione

## Input
- Calcoli validati da Agent3b
- Dati anagrafici dell'utente dal Supervisor
- Credenziali firma digitale da Agent0
- Storico anni precedenti dal Supervisor (inclusi crediti d'imposta residui)
- Eccedenze di versamento dall'anno precedente (per Quadro RX)
- Conferma utente pre-invio via Agent9

## Output
- Modello Redditi PF compilato (Quadri LM + RS + RX) e firmato digitalmente
- Crediti d'imposta aggiornati nel Supervisor (per compensazione in F24 tramite Agent8)
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
