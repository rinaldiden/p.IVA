# Agent0 — Wizard & Bootstrap

## Responsabilità
- **Firma digitale**: guida l'utente passo-passo nel processo di ottenimento (Camera di Commercio, SPID, o provider certificato). Una volta ottenuta, archivia le credenziali nel Vault per uso automatico successivo
- **Credenziali SPID/CIE**: acquisisce e archivia nel Vault le credenziali per accesso ai servizi AdE e INPS
- **Apertura P.IVA**: compila il modello AA9/12 e lo trasmette tramite intermediario abilitato (da definire)
- **Multi-ATECO**: supporta registrazione di più codici ATECO con identificazione del primario
- **Iscrizione CCIAA** via ComUnica (se attività commerciale/artigiana), tramite intermediario
- **Iscrizione INPS** gestione separata o artigiani/commercianti, tramite intermediario
- **SUAP telematico** se richiesto dall'ATECO
- **Riduzione contributiva 35%**: se artigiano/commerciante, guida nella richiesta entro il 28/02 di ogni anno
- Simulare imposta attesa sul fatturato stimato (15% o 5% per primi 5 anni)
- Spiegare scadenze, accantonamenti mensili, funzionamento del regime
- Configurare: banca collegata (Open Banking PSD2), canali ricezione documenti
- **Attivare conservazione sostitutiva** gratuita AdE
- Inizializzare profilo contribuente nel Supervisor

## Input
- Dati anagrafici dell'utente
- Codici ATECO desiderati (uno o più)
- Fatturato stimato annuo (per ATECO se multi)
- Preferenze canali comunicazione (app/email)
- Dati bancari per collegamento PSD2
- Credenziali SPID/CIE per processo firma digitale e accesso servizi

## Output
- Credenziali firma digitale archiviate nel Vault
- Credenziali SPID archiviate nel Vault
- P.IVA aperta e registrata (tramite intermediario abilitato)
- Iscrizione CCIAA completata se applicabile
- Iscrizione INPS completata
- Conservazione sostitutiva AdE attivata
- Configurazione iniziale del sistema (banca, canali, parametri fiscali)
- Report di onboarding con stima imposte e scadenzario
- Profilo contribuente inizializzato nel Supervisor (con tutti i codici ATECO)

## Integrazioni
- `integrations/vault/` — Archiviazione sicura credenziali (firma, SPID, PSD2)
- `integrations/firma_digitale/` — Guida ottenimento firma
- `integrations/agenzia_entrate/` — Invio AA9/12 via intermediario + attivazione conservazione
- `integrations/cciaa_comunica/` — Iscrizione ComUnica via intermediario
- `integrations/inps/` — Iscrizione gestione separata/artigiani
- `integrations/open_banking/` — Configurazione PSD2
- `integrations/invio_telematico/` — Intermediario abilitato (da scegliere)
- `agents/supervisor/` — Inizializzazione profilo contribuente

## Note
- La firma digitale NON viene ottenuta automaticamente: richiede riconoscimento de visu o SPID/CIE livello 2+. Agent0 guida l'utente e poi archivia le credenziali nel Vault
- L'apertura P.IVA passa tramite intermediario abilitato
- Tutte le credenziali sensibili vanno SOLO nel Vault, mai nel Supervisor in chiaro
