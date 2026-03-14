# Agent4 — Compliance Checker

## Responsabilità
- Verificare soglia ricavi 85.000€ con alert proattivi a 70k, 80k, 84k
- Controllare cause ostative al regime forfettario
- Verificare esclusioni: partecipazione in società, redditi da lavoro dipendente > 30k, ecc.
- Se rileva rischio uscita dal regime, avvisare e attivare Agent7

## Input
- Contatore ricavi in tempo reale da Agent2
- Dati anagrafici e situazione contributiva dell'utente
- Normativa vigente sul regime forfettario

## Output
- Alert proattivi su soglia ricavi
- Segnalazione cause ostative
- Attivazione Agent7 in caso di rischio uscita dal regime

## Integrazioni
- `agents/agent7_advisor/` — Attivazione in caso di rischio
- `agents/agent9_notifier/` — Invio alert all'utente
