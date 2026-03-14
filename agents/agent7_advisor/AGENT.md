# Agent7 — Advisor

## Responsabilità
- Analisi proattiva: avviso avvicinamento soglie, suggerimenti ottimizzazioni temporali
- Valutare se conviene passare a regime ordinario o aprire SRL
- Simulazione comparativa: quanto pagheresti in forfettario vs ordinario vs SRL a parità di fatturato
- Pianificazione fiscale per l'anno successivo
- Suggerire timing fatturazione per ottimizzare il carico fiscale (es. rinviare fatture a gennaio)
- Simulazioni what-if su scenari di fatturato
- **Multi-ATECO**: analizzare se conviene spostare attività tra ATECO diversi per ottimizzare il mix coefficienti

## Input
- Dati ricavi e trend da Agent2 (per ATECO e aggregati)
- Alert da Agent4 in caso di rischio uscita dal regime
- Storico fiscale pluriennale dal Supervisor
- Proiezione fatturato da Agent4

## Output
- Raccomandazioni di ottimizzazione fiscale
- Analisi comparativa forfettario vs ordinario vs SRL con numeri concreti
- Piano fiscale anno successivo
- Simulazioni what-if con importi dettagliati

## Integrazioni
- `agents/agent4_compliance/` — Riceve alert rischio uscita
- `agents/agent9_notifier/` — Invia raccomandazioni all'utente
- `agents/supervisor/` — Lettura storico pluriennale
