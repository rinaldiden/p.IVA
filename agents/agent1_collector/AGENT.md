# Agent1 — Collector

## Responsabilità
- Aggregare flussi da tre canali in modo continuo (non solo a fine anno)
- Polling automatico fatture elettroniche XML da SDI
- Polling movimenti bancari via Open Banking PSD2
- Coordinare OCR Subagent per scontrini e ricevute

## Input
- Fatture elettroniche XML dal canale SDI
- Movimenti bancari dal canale PSD2
- Foto scontrini/ricevute da app mobile, WhatsApp, email, upload web

## Output
- Flusso normalizzato di transazioni verso Agent2
- Documenti archiviati con metadati estratti (importo, data, fornitore, categoria)

## Integrazioni
- `integrations/sdi/` — Polling fatture elettroniche
- `integrations/open_banking/` — Polling movimenti bancari
- `agents/agent1_collector/ocr_subagent/` — Elaborazione immagini scontrini
