# Agent1 — Collector

## Responsabilità
- Aggregare flussi da quattro canali in modo continuo (non solo a fine anno)
- Polling automatico fatture elettroniche **passive** (ricevute) XML da SDI
- Polling movimenti bancari via Open Banking PSD2
- Coordinare OCR Subagent per scontrini e ricevute ricevuti via app, email, Google Drive, Google Foto
- Polling **cassetto previdenziale INPS** per recuperare F24 precompilati INPS (con causali e codici sede corretti)

## Input
- Fatture elettroniche XML dal canale SDI
- Movimenti bancari dal canale PSD2
- Foto scontrini/ricevute da app mobile, email, Google Drive, Google Foto

## Output
- Flusso normalizzato di transazioni verso Agent2
- Documenti archiviati con metadati estratti (importo, data, fornitore, categoria)
- F24 precompilati INPS verso Agent6 (con causali corrette dal cassetto previdenziale)
- Aggiornamento stato nel Supervisor

## Integrazioni
- `integrations/sdi/` — Polling fatture elettroniche passive
- `integrations/open_banking/` — Polling movimenti bancari
- `integrations/inps/` — Polling cassetto previdenziale per F24 precompilati
- `agents/agent1_collector/ocr_subagent/` — Elaborazione immagini scontrini
- `agents/supervisor/` — Aggiornamento profilo contribuente
