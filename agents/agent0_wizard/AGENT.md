# Agent0 — Wizard & Bootstrap

## Responsabilità
- **Firma digitale**: guida l'utente passo-passo nel processo di ottenimento (Camera di Commercio, SPID, o provider certificato). Una volta ottenuta, incamera le credenziali di firma per operare in automatico da quel momento in poi
- **Apertura P.IVA**: compila il modello AA9/12 e lo trasmette tramite intermediario abilitato (da definire). Se l'AdE aprirà API pubbliche in futuro, le integriamo
- **Iscrizione CCIAA** via ComUnica (se attività commerciale/artigiana), tramite intermediario
- **Iscrizione INPS** gestione separata o artigiani/commercianti, tramite intermediario
- **SUAP telematico** se richiesto dall'ATECO
- **Riduzione contributiva 35%**: se artigiano/commerciante, guida nella richiesta entro il 28/02 di ogni anno
- Simulare imposta attesa sul fatturato stimato (15% o 5% per primi 5 anni)
- Spiegare scadenze, accantonamenti mensili, funzionamento del regime
- Configurare: banca collegata (Open Banking PSD2), canali ricezione documenti (app/email/Google Drive/Google Foto)
- Le credenziali di firma ottenute qui vengono riutilizzate da tutti gli agenti successivi

## Input
- Dati anagrafici dell'utente
- Codice ATECO desiderato
- Fatturato stimato annuo
- Preferenze canali comunicazione (app/email/Google Drive)
- Dati bancari per collegamento PSD2
- Credenziali SPID/CIE per processo firma digitale

## Output
- Credenziali firma digitale archiviate in modo sicuro (riutilizzate da tutti gli agenti)
- P.IVA aperta e registrata (tramite intermediario abilitato)
- Iscrizione CCIAA completata se applicabile (tramite intermediario)
- Iscrizione INPS completata (tramite intermediario)
- Configurazione iniziale del sistema (banca, canali, parametri fiscali)
- Report di onboarding con stima imposte e scadenzario
- Profilo contribuente inizializzato nel Supervisor

## Integrazioni
- `integrations/firma_digitale/` — Guida ottenimento + archiviazione credenziali
- `integrations/agenzia_entrate/` — Invio modello AA9/12 via intermediario
- `integrations/cciaa_comunica/` — Iscrizione ComUnica via intermediario
- `integrations/inps/` — Iscrizione gestione separata/artigiani
- `integrations/open_banking/` — Configurazione PSD2
- `integrations/invio_telematico/` — Intermediario abilitato (da scegliere)
- `agents/supervisor/` — Inizializzazione profilo contribuente

## Note
- La firma digitale NON viene ottenuta automaticamente: richiede riconoscimento de visu o SPID/CIE livello 2+. Agent0 guida l'utente nel processo e poi conserva le credenziali per uso automatico successivo
- L'apertura P.IVA passa tramite intermediario abilitato fino a quando l'AdE non esporrà API pubbliche
