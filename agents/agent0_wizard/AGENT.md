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

### Chiusura P.IVA (ciclo di vita completo)
- **Avvio procedura di chiusura** su richiesta dell'utente o su indicazione di Agent7 (es. passaggio a SRL/ordinario)
- **Pre-chiusura — checklist obbligatoria** prima di procedere:
  1. Verificare che tutte le fatture emesse siano state consegnate e incassate (Agent8 + Agent1)
  2. Verificare che non ci siano fatture passive pendenti (Agent1)
  3. Calcolare il saldo imposte + INPS maturato fino alla data di cessazione (Agent3 + Agent3b)
  4. Generare gli F24 di saldo finali (Agent6)
  5. Verificare bollo virtuale residuo da versare (Agent8)
  6. Verificare crediti d'imposta residui — scelta: rimborso o perdita (Agent5)
  7. Conferma esplicita dell'utente via Agent9 con riepilogo completo di tutti gli adempimenti residui
- **Esecuzione chiusura**:
  - Compilare e trasmettere modello **AA9/12 cessazione** all'Agenzia delle Entrate (entro 30 giorni dalla cessazione effettiva)
  - Cancellazione dalla **CCIAA** via ComUnica (se iscritto) tramite intermediario
  - Chiusura posizione **INPS** (comunicazione cessazione)
  - Chiusura canale **SDI** (cessazione codice destinatario)
  - Revoca consent **PSD2** (Open Banking)
- **Post-chiusura — adempimenti anno successivo** (il sistema resta attivo!):
  - Il Supervisor mantiene lo stato "cessata" con data chiusura e flag adempimenti residui
  - Agent6 genera scadenzario post-chiusura: saldo imposta + saldo INPS entro il 30/06 anno successivo
  - Agent5 compila e trasmette la **dichiarazione Redditi PF finale** (anno successivo, entro il 30/11)
  - Agent8 esegue i pagamenti F24 di saldo finali
  - Agent9 continua le notifiche fino al completamento di tutti gli adempimenti
  - Solo dopo l'invio della dichiarazione finale e il pagamento dell'ultimo F24, il sistema si disattiva
- **Avviso all'utente**: spiegare chiaramente che la chiusura della P.IVA NON estingue i debiti fiscali — l'anno dopo deve comunque presentare la dichiarazione e pagare saldo imposte + INPS

## Input
- Dati anagrafici dell'utente
- Codice ATECO desiderato
- Fatturato stimato annuo
- Preferenze canali comunicazione (app/email/Google Drive)
- Dati bancari per collegamento PSD2
- Credenziali SPID/CIE per processo firma digitale

## Output

### Apertura
- Credenziali firma digitale archiviate in modo sicuro (riutilizzate da tutti gli agenti)
- P.IVA aperta e registrata (tramite intermediario abilitato)
- Iscrizione CCIAA completata se applicabile (tramite intermediario)
- Iscrizione INPS completata (tramite intermediario)
- Configurazione iniziale del sistema (banca, canali, parametri fiscali)
- Report di onboarding con stima imposte e scadenzario
- Profilo contribuente inizializzato nel Supervisor

### Chiusura
- Checklist pre-chiusura completata (fatture, saldi, crediti)
- Modello AA9/12 cessazione trasmesso all'Agenzia delle Entrate
- Cancellazione CCIAA completata (se applicabile)
- Posizione INPS chiusa
- Canali SDI/PSD2 revocati
- Profilo contribuente aggiornato nel Supervisor con stato "cessata" e scadenzario post-chiusura
- Report di chiusura con riepilogo adempimenti residui (dichiarazione + saldi anno successivo)

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
- La chiusura va comunicata entro **30 giorni** dalla cessazione effettiva dell'attività
- Dopo la chiusura il sistema FiscalAI resta attivo in modalità "post-cessazione" fino al completamento di tutti gli adempimenti residui (dichiarazione finale + saldo imposte/INPS anno successivo)
- L'Agenzia delle Entrate può effettuare controlli retroattivi per **5 anni** dalla chiusura (7 in caso di omessa dichiarazione)
