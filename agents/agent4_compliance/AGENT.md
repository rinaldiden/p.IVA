# Agent4 — Compliance Checker

## Responsabilità
- Monitorare andamento fatturazione in tempo reale con proiezione annuale (aggregato multi-ATECO)
- **Soglia 85.000€**: unica soglia rilevante per l'uscita dal regime forfettario. Il superamento comporta **uscita dal regime dall'anno fiscale SUCCESSIVO**, mai in corso d'anno
- Spiegare all'utente le conseguenze concrete di ogni livello di alert:
  - A 70.000€: "Stai andando bene, tieni d'occhio la soglia — la proiezione annuale indica [importo stimato]"
  - A 80.000€: "Ti avvicini alla soglia — valuta la pianificazione con Agent7. Se superi 85k dal prossimo anno sei in regime ordinario"
  - A 84.000€: "ATTENZIONE — considera se rinviare la fatturazione a gennaio per restare nel forfettario quest'anno"
  - A 85.001€: "Hai superato la soglia — dal 1° gennaio del prossimo anno esci dal regime forfettario e passi al regime ordinario. Agent7 attivato per pianificazione transizione"
- Controllare cause ostative al regime forfettario
- Verificare esclusioni: partecipazione in società, redditi da lavoro dipendente > 30k, fatturato prevalente verso ex datore di lavoro (ultimi 2 anni)
- **Crediti > 5.000€**: segnalare che la compensazione in F24 richiede visto di conformità
- Se rileva rischio uscita dal regime, avvisare e attivare Agent7

> **Nota normativa**: La soglia di 100.000€ con uscita immediata e IVA retroattiva è stata abrogata. Dal 2024 (L. 197/2022 e modifiche successive) il superamento di qualsiasi importo comporta sempre l'uscita dal regime forfettario dall'anno fiscale successivo, mai in corso d'anno. Non esiste IVA retroattiva sul fatturato dell'anno in corso. Normativa aggiornata al 2024. Il sistema verifica annualmente gli aggiornamenti normativi tramite il Supervisor.

## Input
- Contatore ricavi in tempo reale e trend da Agent2 (aggregato multi-ATECO)
- Dati anagrafici e situazione contributiva dell'utente dal Supervisor
- Crediti d'imposta dal Supervisor (per soglia visto di conformità)
- Normativa vigente sul regime forfettario (verificata annualmente dal Supervisor)

## Output
- Alert proattivi su soglie ricavi (70k, 80k, 84k, 85k)
- Proiezione di fine anno basata su trend corrente
- Segnalazione cause ostative
- Segnalazione necessità visto di conformità per crediti > 5.000€
- Attivazione Agent7 in caso di rischio uscita dal regime
- Spiegazione chiara e concreta delle conseguenze per l'utente

## Integrazioni
- `agents/agent7_advisor/` — Attivazione in caso di rischio o superamento soglia
- `agents/agent9_notifier/` — Invio alert all'utente
- `agents/supervisor/` — Lettura profilo e storico contribuente
