# Agent8 — Invoicer & Payment Executor

## Responsabilità

### Fatturazione Attiva
- Compilare fattura elettronica in formato XML conforme alle specifiche SDI (FatturaPA v1.2.2)
- Applicare automaticamente **marca da bollo virtuale €2** su fatture con importo > €77.47 (campo `<DatiBollo>` nell'XML)
- Firmare digitalmente la fattura con credenziali archiviate da Agent0
- Trasmettere la fattura al **Sistema di Interscambio (SDI)**
- Monitorare lo stato di consegna (ricevuta di consegna, notifica di scarto, mancata consegna)
- Archiviare fattura + ricevuta nel Supervisor
- Gestire numerazione progressiva fatture (anno/numero)
- Inserire automaticamente i dati del regime forfettario nella fattura:
  - `<RegimeFiscale>` = RF19
  - Nessuna IVA esposta (natura operazione: N2.2)
  - Dicitura obbligatoria: "Operazione effettuata ai sensi dell'art. 1, commi 54-89, L. 190/2014"
- Gestire fatture verso PA (split payment, CIG, CUP)

### Marca da Bollo Virtuale €2
- Applicazione automatica nel campo `<DatiBollo>` dell'XML quando importo > €77.47
- Addebito in fattura al cliente (o assorbimento, a scelta dell'utente)
- Calcolo e versamento cumulativo annuale dell'imposta di bollo virtuale tramite F24 (codice tributo 2501-2504)
- Scadenze versamento bollo virtuale: trimestrale (entro ultimo giorno del mese successivo al trimestre)

### Pagamento Effettivo F24
- Ricevere F24 precompilati da Agent6
- Eseguire il pagamento via **Open Banking PSD2** (addebito diretto su IBAN configurato)
- Confermare l'avvenuto pagamento e archiviare la quietanza
- Gestire pagamenti rateizzati secondo il piano di Agent6
- Gestire il pagamento con compensazione crediti (se presenti nel Supervisor)
- Se il pagamento PSD2 fallisce: retry + alert via Agent9

### Checkpoint di Conferma Utente
- Prima dell'invio di ogni fattura: riepilogo al contribuente via Agent9, attesa conferma (configurabile: auto/manuale)
- Prima dell'esecuzione di ogni F24: riepilogo importo e scadenza, attesa conferma (configurabile: auto/manuale)
- L'utente può impostare soglie di auto-approvazione (es. "approva automaticamente F24 sotto i €500")

## Input
- Dati cliente e prestazione dall'utente (o da template salvati)
- F24 precompilati da Agent6
- Credenziali firma digitale da Agent0 (via Supervisor)
- IBAN e consent PSD2 dal Supervisor
- Soglie auto-approvazione dall'utente

## Output
- Fatture elettroniche XML firmate e trasmesse al SDI
- Ricevute di consegna/scarto archiviate
- Quietanze F24 pagati
- Aggiornamento contatore ricavi in tempo reale verso Agent2
- Log di ogni operazione nel Supervisor

## Integrazioni
- `integrations/sdi/` — Invio fatture elettroniche e ricezione notifiche
- `integrations/open_banking/` — Esecuzione pagamenti F24 via PSD2
- `integrations/firma_digitale/` — Firma digitale fatture
- `agents/agent0_wizard/` — Credenziali firma digitale
- `agents/agent2_categorizer/` — Aggiornamento ricavi dopo emissione fattura
- `agents/agent6_scheduler/` — Ricezione F24 precompilati
- `agents/agent9_notifier/` — Conferma utente pre-invio e alert errori
- `agents/supervisor/` — Archiviazione documenti e log

## Note
- La fattura forfettaria NON espone IVA: il campo IVA è a 0% con natura N2.2
- La marca da bollo virtuale è obbligatoria per legge su fatture > €77.47 esenti IVA
- Il regime fiscale RF19 deve essere indicato in ogni fattura
- Il pagamento F24 via PSD2 richiede SCA (Strong Customer Authentication) — il flusso deve gestire l'eventuale 2FA
- L'imposta di bollo virtuale sulle fatture elettroniche va versata trimestralmente con F24 (codici tributo 2501 Q1, 2502 Q2, 2503 Q3, 2504 Q4)
