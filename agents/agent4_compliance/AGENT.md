# Agent4 — Compliance Checker

## Responsabilità
- Monitorare andamento fatturazione in tempo reale con proiezione annuale
- **Soglia 85.000€**: alert proattivi a 70k, 80k, 84k. Se superata, uscita dal regime forfettario dall'anno successivo
- **Soglia 100.000€**: CRITICA — uscita immediata dal regime in corso d'anno con obbligo retroattivo di applicazione IVA dal momento del superamento
- Spiegare all'utente le conseguenze concrete di ogni soglia:
  - A 70k: "Stai andando bene, tieni d'occhio la soglia"
  - A 80k: "Ti avvicini — se superi 85k l'anno prossimo passi al regime ordinario"
  - A 84k: "ATTENZIONE — valuta se rinviare fatture al prossimo anno"
  - A 85k: "Hai superato la soglia — dal 1 gennaio prossimo sei in regime ordinario. Attivato Agent7 per pianificazione"
  - A 95k: "PERICOLO — se arrivi a 100k esci SUBITO dal forfettario con IVA retroattiva"
  - A 100k: "SUPERAMENTO CRITICO — uscita immediata, devi applicare IVA da oggi e regolarizzare le fatture precedenti"
- Controllare cause ostative al regime forfettario
- Verificare esclusioni: partecipazione in società, redditi da lavoro dipendente > 30k, fatturato prevalente verso ex datore di lavoro (ultimi 2 anni)
- Se rileva rischio uscita dal regime, avvisare e attivare Agent7
- Verificare che Agent8 applichi correttamente la **marca da bollo virtuale €2** su ogni fattura emessa con importo > €77.47
- Monitorare il versamento trimestrale dell'imposta di bollo virtuale (codici tributo 2501-2504)

## Input
- Contatore ricavi in tempo reale e trend da Agent2
- Dati anagrafici e situazione contributiva dell'utente dal Supervisor
- Normativa vigente sul regime forfettario
- Log fatture emesse da Agent8 (per verifica marca da bollo)

## Output
- Alert proattivi su soglie ricavi (70k, 80k, 84k, 85k, 95k, 100k)
- Proiezione di fine anno basata su trend corrente
- Segnalazione cause ostative
- Attivazione Agent7 in caso di rischio uscita dal regime
- Spiegazione chiara e concreta delle conseguenze per l'utente
- Alert se marca da bollo mancante su fattura > €77.47
- Alert se versamento bollo virtuale trimestrale in scadenza/scaduto

## Integrazioni
- `agents/agent7_advisor/` — Attivazione in caso di rischio
- `agents/agent9_notifier/` — Invio alert all'utente
- `agents/supervisor/` — Lettura profilo e storico contribuente
