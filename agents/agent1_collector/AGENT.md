# Agent1 — Collector

## Responsabilità
- Aggregare flussi da tre canali in modo continuo (non solo a fine anno)
- Polling automatico fatture elettroniche XML da SDI (emesse e ricevute)
- Polling movimenti bancari via Open Banking PSD2
- Coordinare OCR Subagent per scontrini e ricevute via app, email, Google Drive, Google Foto
- **Gestire il ciclo completo del consent PSD2** (vedi sezione dedicata)
- **Attivare il servizio di conservazione sostitutiva gratuito dell'Agenzia delle Entrate** e archiviare automaticamente tutte le fatture (emesse e ricevute)
- **Gestire notifiche SDI in ricezione** (vedi sezione dedicata)

## Consent PSD2 — Re-consent automatico

Il consent Open Banking scade ogni 90 giorni per direttiva PSD2. Agent1 gestisce l'intero ciclo:

| Momento | Azione |
|---------|--------|
| **T-7 giorni** | Agent9 invia SMS + email con **link diretto al re-consent** del provider PSD2. Messaggio: "Il collegamento con la tua banca scade tra 7 giorni. Rinnova ora: [link]" |
| **T-3 giorni** | Secondo alert con **urgenza elevata**. Messaggio: "URGENTE — il collegamento bancario scade tra 3 giorni. Senza rinnovo perderai l'aggiornamento automatico dei movimenti." |
| **T-0 (scadenza)** | Terzo alert + **sospensione polling bancario** + flag `WARNING:CONSENT_EXPIRED` sul profilo contribuente nel Supervisor. Messaggio: "Il collegamento bancario è scaduto. I movimenti non vengono più aggiornati." |
| **Dopo scadenza** | Agent1 **continua a raccogliere da SDI e OCR** normalmente, ma i movimenti bancari sono fermi. Ogni transazione nel Supervisor è marcata con `bank_data_stale_since: [data scadenza]` |
| **Al rinnovo** | Agent1 fa **backfill automatico**: interroga la banca per tutti i movimenti dal giorno di scadenza consent a oggi, li normalizza e li invia ad Agent2. Rimuove il flag WARNING dal Supervisor. |

## Gestione notifiche SDI in ricezione

Quando Agent1 riceve una fattura da un fornitore tramite SDI:

1. **Verifica autenticità e integrità** del file XML (firma digitale, formato conforme)
2. **Accetta automaticamente** (notifica AT) le fatture con dati corretti
3. **Flagga per revisione** le fatture con dati anomali:
   - Importo insolitamente alto rispetto allo storico fornitore
   - Fornitore mai visto prima
   - Dati fiscali incoerenti (P.IVA non valida, CF non corrispondente)
4. **Logga tutti gli esiti** nel Supervisor per lo storico documentale
5. Invia la fattura ricevuta ad Agent2 per classificazione

## Conservazione sostitutiva
- Attiva il servizio gratuito di conservazione dell'AdE (Fatture e Corrispettivi)
- Archivia automaticamente fatture emesse (da Agent8) e ricevute (da SDI)
- Verifica periodicamente che tutte le fatture siano in conservazione
- Il servizio AdE conserva a norma per 15 anni

## Input
- Fatture elettroniche XML dal canale SDI (emesse e ricevute)
- Movimenti bancari dal canale PSD2
- Foto scontrini/ricevute da app mobile, email, Google Drive, Google Foto
- Fatture emesse da Agent8 (per conservazione)
- Stato consent PSD2 dal Supervisor

## Output
- Flusso normalizzato di transazioni verso Agent2
- Documenti archiviati con metadati estratti
- Aggiornamento stato nel Supervisor (incluso flag consent PSD2)
- Alert re-consent PSD2 verso Agent9 (T-7, T-3, T-0)
- Fatture ricevute verificate e loggate nel Supervisor
- Backfill movimenti bancari post-rinnovo consent

## Integrazioni
- `integrations/sdi/` — Polling fatture elettroniche + verifica autenticità
- `integrations/open_banking/` — Polling movimenti bancari + gestione consent + backfill
- `integrations/agenzia_entrate/` — Servizio conservazione sostitutiva
- `agents/agent1_collector/ocr_subagent/` — Elaborazione immagini scontrini
- `agents/agent8_invoicing/` — Fatture emesse da conservare
- `agents/supervisor/` — Aggiornamento profilo contribuente + flag consent + log SDI
- `agents/agent9_notifier/` — Alert scadenza consent PSD2 + fatture anomale
