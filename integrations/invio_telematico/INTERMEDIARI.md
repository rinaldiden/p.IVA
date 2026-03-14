# Valutazione Intermediari Abilitati

> **STATO: BLOCCANTE** — La scelta dell'intermediario è prerequisito per Agent0 (apertura P.IVA), Agent5 (invio dichiarazione) e tutto il ciclo telematico.

## Contesto

Per trasmettere dichiarazioni fiscali all'Agenzia delle Entrate serve un intermediario abilitato ai sensi dell'art. 3 del DPR 322/98. FiscalAI non può auto-abilitarsi — deve appoggiarsi a un soggetto terzo con canale Entratel attivo.

## Candidati in valutazione

| Candidato | Specializzazione | Note |
|-----------|-----------------|------|
| **Abletech** (abletech.it) | Specializzato dichiarativi | Verifica disponibilità API REST e sandbox |
| **TeamSystem** | ERP italiano completo | API commerciali, valutare costo per invio singolo |
| **Zucchetti** | Diffuso tra commercialisti | Valutare apertura API a terze parti |
| **Wolters Kluwer** (Adempimenti) | Software fiscale enterprise | Valutare |

## Criteri di selezione

Per ciascun candidato vanno verificati:

- [ ] **API REST disponibile** (no SOAP — complessità di integrazione troppo alta)
- [ ] **Sandbox/ambiente di test** disponibile per sviluppo e validazione
- [ ] **Costo per singolo invio** o canone annuale (impatta il pricing per l'utente finale)
- [ ] **SLA garantito** nei periodi di scadenza (giugno/novembre = picco traffico Entratel)
- [ ] **Supporto firma digitale remota** (no richiesta smartcard fisica — il sistema opera in cloud)
- [ ] **Documentazione pubblica** disponibile e aggiornata
- [ ] **Copertura servizi**: solo dichiarativi o anche apertura P.IVA, ComUnica, F24?
- [ ] **Supporto tecnico** reattivo per integrazioni API

## Prossimi passi

1. Contattare ciascun candidato per verifica disponibilità API e sandbox
2. Ottenere listino prezzi e condizioni contrattuali
3. Testare sandbox con invio dichiarativo di prova
4. Valutare SLA e affidabilità in periodo di scadenza
5. Scegliere e integrare

Vedi GitHub Issue: **[BLOCKING] Selezione intermediario telematico abilitato ex art.3 DPR 322/98**
