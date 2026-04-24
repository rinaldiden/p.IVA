# Agent7 — Advisor

## Responsabilità

### Analisi proattiva
- Avviso avvicinamento soglie, suggerimenti ottimizzazioni temporali
- Suggerire timing fatturazione per ottimizzare il carico fiscale (es. rinviare fatture a gennaio)
- Simulazioni what-if su scenari di fatturato

### Simulazione comparativa regimi
- Quanto pagheresti in forfettario vs ordinario vs SRL a parità di fatturato
- Includere nel confronto: imposta sostitutiva/IRPEF, INPS, IRAP (se SRL), contributi previdenziali, costi di gestione (commercialista, bilancio, ecc.)
- Valutare se conviene passare a regime ordinario o aprire SRL

### Pianificazione fiscale
- Piano fiscale per l'anno successivo
- Stima accantonamento mensile consigliato (quanto mettere da parte ogni mese per tasse + INPS)

### Simulazione pre-chiusura P.IVA
Quando l'utente valuta la chiusura della P.IVA o quando Agent0 avvia la procedura di chiusura, Agent7 produce un **report pre-chiusura completo** con:

#### Calcolo costi totali di chiusura
- Saldo imposta sostitutiva da pagare l'anno successivo
- Saldo INPS da pagare l'anno successivo (gestione separata O artigiani eccedente)
- Bollo virtuale residuo non ancora versato
- Costi amministrativi (cancellazione CCIAA, eventuali professionisti)

#### Analisi deducibilità persa
- Calcolo dell'INPS pagato l'anno successivo che **non sarà deducibile** (nessun reddito futuro da cui scalarlo)
- Confronto con lo scenario "tengo aperta un altro anno": quanto risparmierebbe l'utente deducendo i contributi INPS dal reddito dell'anno successivo
- Esempio concreto con i numeri dell'utente:
  ```
  Chiudo a dic 2026:
    INPS pagati nel 2027: €X → deducibili da nulla → persi
    Costo effettivo INPS: €X (100%)

  Tengo aperta nel 2027:
    INPS pagati nel 2027: €X → deducibili dal reddito 2027
    Risparmio imposta: €X × 5% = €Y
    Costo effettivo INPS: €X - €Y
  ```

#### Simulazione timeline pagamenti
- Cosa paga e quando nel primo anno di attività (acconti = zero se primo anno)
- Cosa paga e quando l'anno successivo alla chiusura (saldo completo)
- Cash flow mese per mese per evitare sorprese
- Evidenziare il rischio: "nel primo anno non paghi nulla, ma l'anno dopo arriva tutto insieme"

#### Confronto gestione INPS
- Se l'utente può scegliere tra inquadramenti diversi (es. consulente IT vs installatore), simulare entrambi gli scenari:
  ```
  Gestione Separata (67%):  aliquota INPS alta, no fissi, base imponibile bassa
  Artigiani (86%, -35%):    aliquota INPS bassa, fissi trimestrali, base imponibile alta
  ```
- Calcolare il netto in tasca per entrambi con il fatturato reale dell'utente
- Evidenziare quale conviene nel caso specifico

#### Alert rischi fiscali chiusura rapida
- Se la P.IVA è aperta da meno di 12 mesi: **warning "apri e chiudi"**
  - Rischio controlli Agenzia Entrate + GdF (pattern anti-evasione)
  - Se riapre entro 12 mesi: fideiussione obbligatoria €50.000 per 3 anni
  - Sanzione possibile €3.000
  - Possibile contestazione aliquota 5% se l'attività è "mera prosecuzione" di lavoro precedente
- Se fatturato vicino alla soglia €85k: spiegare che il pattern "fatturo tanto e chiudo" è un red flag per il Fisco
- Consigliare di documentare il motivo reale della chiusura

## Input
- Dati ricavi e trend da Agent2
- Alert da Agent4 in caso di rischio uscita dal regime
- Storico fiscale pluriennale dal Supervisor
- Proiezione fatturato da Agent4
- Stato ciclo di vita P.IVA dal Supervisor (per simulazione pre-chiusura)
- Tipo gestione INPS e contributi pagati/dovuti dal Supervisor
- Data apertura P.IVA (per calcolo durata attività e rischio "apri e chiudi")

## Output
- Raccomandazioni di ottimizzazione fiscale
- Analisi comparativa forfettario vs ordinario vs SRL con numeri concreti
- Piano fiscale anno successivo
- Simulazioni what-if con importi dettagliati
- **Report pre-chiusura**: costi totali, deducibilità persa, timeline pagamenti, confronto gestioni INPS, alert rischi fiscali
- Stima accantonamento mensile consigliato

## Integrazioni
- `agents/agent0_wizard/` — Riceve richiesta di simulazione pre-chiusura
- `agents/agent4_compliance/` — Riceve alert rischio uscita
- `agents/agent9_notifier/` — Invia raccomandazioni e report all'utente
- `agents/supervisor/` — Lettura storico pluriennale, stato P.IVA, gestione INPS
