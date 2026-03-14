# Agent7 — Advisor

## Responsabilità
- Analisi proattiva: avviso avvicinamento soglia, suggerimenti ottimizzazioni temporali
- Valutare se conviene passare a regime ordinario o aprire SRL
- Pianificazione fiscale per l'anno successivo
- Simulazioni what-if su scenari di fatturato

## Input
- Dati ricavi e trend da Agent2
- Alert da Agent4 in caso di rischio uscita dal regime
- Storico fiscale dell'utente

## Output
- Raccomandazioni di ottimizzazione fiscale
- Analisi comparativa forfettario vs ordinario vs SRL
- Piano fiscale anno successivo

## Integrazioni
- `agents/agent4_compliance/` — Riceve alert rischio uscita
- `agents/agent9_notifier/` — Invia raccomandazioni all'utente
