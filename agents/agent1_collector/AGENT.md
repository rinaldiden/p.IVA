# Agent1 — Collector

## Responsabilità
- Aggregare flussi da tre canali in modo continuo (non solo a fine anno)
- Polling automatico fatture elettroniche XML da SDI (emesse e ricevute)
- Polling movimenti bancari via Open Banking PSD2
- Coordinare OCR Subagent per scontrini e ricevute via app, email, Google Drive, Google Foto
- **Monitorare scadenza consent PSD2** e inviare alert di rinnovo 14 giorni prima della scadenza (il consent scade ogni 90 giorni)
- **Attivare il servizio di conservazione sostitutiva gratuito dell'Agenzia delle Entrate** e archiviare automaticamente tutte le fatture (emesse e ricevute)

## Consent PSD2
Il consent Open Banking scade ogni 90 giorni per direttiva PSD2. Agent1:
1. Traccia la data di scadenza del consent nel Supervisor
2. 14 giorni prima della scadenza → alert via Agent9
3. 7 giorni prima → secondo alert con istruzioni di rinnovo
4. Se scaduto → alert urgente + sospensione polling bancario + istruzioni per rinnovare

## Conservazione sostitutiva
- Attiva il servizio gratuito di conservazione dell'AdE (Fatture e Corrispettivi)
- Archivia automaticamente fatture emesse (da Agent8) e ricevute (da SDI)
- Verifica periodicamente che tutte le fatture siano in conservazione
- Il servizio AdE conserva a norma per 15 anni

## Input
- Fatture elettroniche XML dal canale SDI
- Movimenti bancari dal canale PSD2
- Foto scontrini/ricevute da app mobile, email, Google Drive, Google Foto
- Fatture emesse da Agent8 (per conservazione)

## Output
- Flusso normalizzato di transazioni verso Agent2
- Documenti archiviati con metadati estratti
- Aggiornamento stato nel Supervisor
- Alert rinnovo PSD2 verso Agent9

## Integrazioni
- `integrations/sdi/` — Polling fatture elettroniche
- `integrations/open_banking/` — Polling movimenti bancari + gestione consent
- `integrations/agenzia_entrate/` — Servizio conservazione sostitutiva
- `agents/agent1_collector/ocr_subagent/` — Elaborazione immagini scontrini
- `agents/agent8_invoicing/` — Fatture emesse da conservare
- `agents/supervisor/` — Aggiornamento profilo contribuente
- `agents/agent9_notifier/` — Alert scadenza consent PSD2
