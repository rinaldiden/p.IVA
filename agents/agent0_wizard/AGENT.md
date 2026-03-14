# Agent0 — Wizard & Bootstrap

## Responsabilità
- Ottenere firma digitale via API (Aruba / Namirial / InfoCert)
- Aprire P.IVA compilando e inviando modello AA9/12 all'Agenzia delle Entrate
- Iscrivere alla CCIAA via ComUnica (se attività commerciale/artigiana)
- Iscrivere all'INPS gestione separata o artigiani/commercianti
- Gestire SUAP telematico se richiesto dall'ATECO
- Simulare imposta attesa sul fatturato stimato (15% o 5% primi 5 anni)
- Spiegare scadenze, accantonamenti mensili, funzionamento del regime
- Configurare banca collegata (Open Banking PSD2) e canali ricezione documenti

## Input
- Dati anagrafici dell'utente
- Codice ATECO desiderato
- Fatturato stimato annuo
- Preferenze canali comunicazione (app/WhatsApp/email/web)
- Dati bancari per collegamento PSD2

## Output
- Firma digitale attiva (riutilizzata da tutti gli agenti successivi)
- P.IVA aperta e registrata
- Iscrizione CCIAA completata (se applicabile)
- Iscrizione INPS completata
- Configurazione iniziale del sistema (banca, canali, parametri fiscali)
- Report di onboarding con stima imposte e scadenzario

## Integrazioni
- `integrations/firma_digitale/` — API Aruba / Namirial / InfoCert
- `integrations/agenzia_entrate/` — Invio modello AA9/12
- `integrations/cciaa_comunica/` — Iscrizione ComUnica
- `integrations/inps/` — Iscrizione gestione separata/artigiani
- `integrations/open_banking/` — Configurazione PSD2
