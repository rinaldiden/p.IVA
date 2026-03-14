# Supervisor — Profilo Contribuente, Storico & Coordinamento

## Responsabilità
- **Fonte di verità unica** per tutti i dati del contribuente
- Mantiene il profilo completo: anagrafica, P.IVA, ATECO (supporto multi-ATECO), tipo INPS, regime, credenziali firma
- Gestisce lo **storico pluriennale**: ricavi, imposte pagate, dichiarazioni inviate, F24, anno per anno
- **Gestisce crediti d'imposta** da un anno all'altro
- Coordina il flusso tra agenti: sa chi ha fatto cosa e quando
- Tiene traccia dello stato corrente del ciclo fiscale annuale
- Archivia ogni documento generato (F24, dichiarazioni, ricevute, fatture)
- Espone i dati agli altri agenti in modo strutturato
- **Aggiornamento normativo annuale**: ogni gennaio verifica nuove circolari INPS, aggiornamenti aliquote, modifiche normative al regime forfettario e aggiorna i file in `shared/`
- Delega le operazioni di autenticazione all'Auth Agent (`integrations/vault/`)

## Profilo Contribuente (schema)
```json
{
  "anagrafica": {
    "nome": "", "cognome": "", "codice_fiscale": "",
    "data_nascita": "", "luogo_nascita": "", "residenza": {}
  },
  "piva": {
    "numero": "",
    "data_apertura": "",
    "ateco_codes": [
      { "codice": "62.01", "descrizione": "Sviluppo software", "coefficiente": 0.67 },
      { "codice": "73.11", "descrizione": "Agenzie pubblicitarie", "coefficiente": 0.78 }
    ]
  },
  "regime": {
    "tipo": "forfettario",
    "aliquota": 0.05,
    "anno_inizio": 2024,
    "anno_fine_agevolazione_5_percento": 2028,
    "riduzione_contributiva_35": true,
    "data_richiesta_riduzione": "2024-02-15"
  },
  "inps": {
    "gestione": "separata | artigiani | commercianti",
    "tipo_iscrizione": "",
    "codice_sede": "",
    "matricola": "",
    "minimale_annuo": 18415
  },
  "firma_digitale": {
    "provider": "aruba | namirial | infocert",
    "credenziali_ref": "vault://firma-digitale/user-xyz",
    "scadenza": "2027-03-14"
  },
  "auth": {
    "spid_ref": "vault://spid/user-xyz",
    "deleghe_intermediario": []
  },
  "banca": {
    "iban": "",
    "provider_psd2": "tink | yapily",
    "consent_id": "",
    "consent_scadenza": "2026-06-12"
  },
  "canali_notifica": { "email": "", "telefono": "", "push_app": true },
  "canali_documenti": { "google_drive_folder": "", "google_photos_album": "", "email": "" }
}
```

## Storico Annuale (schema)
```json
{
  "anno": 2026,
  "ricavi": {
    "per_ateco": [
      { "codice": "62.01", "ricavi": 35000, "coefficiente": 0.67, "reddito": 23450 },
      { "codice": "73.11", "ricavi": 10000, "coefficiente": 0.78, "reddito": 7800 }
    ],
    "totale_ricavi": 45000,
    "totale_reddito_lordo": 31250
  },
  "contributi_inps": {
    "versati_anno": 7800,
    "fissi": 2876,
    "percentuali": 4924,
    "riduzione_35_applicata": true
  },
  "calcolo_imposta": {
    "reddito_imponibile": 23450,
    "aliquota": 0.05,
    "imposta_dovuta": 1172.50,
    "acconti_versati": 1000,
    "saldo": 172.50,
    "credito_residuo": 0
  },
  "crediti_imposta": {
    "da_anno_precedente": 0,
    "compensati_in_f24": 0,
    "residuo_per_anno_successivo": 0
  },
  "dichiarazione": {
    "file_ref": "storage://dichiarazioni/2026_redditi_pf.xml",
    "data_invio": "2026-11-28",
    "ricevuta_ref": "storage://ricevute/2026_ricevuta.pdf"
  },
  "f24_generati": [
    { "data": "2026-06-30", "importo": 500, "codice_tributo": "1792", "stato": "pagato" },
    { "data": "2026-06-30", "importo": 400, "codice_tributo": "1790", "stato": "pagato" }
  ],
  "fatture_emesse": {
    "totale": 25,
    "marche_bollo_virtuali": 50.00
  },
  "eventi": [
    { "data": "2026-02-28", "tipo": "riduzione_35", "descrizione": "Richiesta riduzione INPS inviata" },
    { "data": "2026-06-30", "tipo": "versamento", "descrizione": "F24 saldo + 1° acconto pagato" }
  ]
}
```

## Aggiornamento normativo annuale
Ogni gennaio il Supervisor:
1. Verifica pubblicazione nuova circolare INPS → aggiorna `shared/inps_rates.json`
2. Verifica modifiche al regime forfettario (soglie, aliquote, cause ostative)
3. Verifica aggiornamento coefficienti ATECO → aggiorna `shared/ateco_coefficients.json` se necessario
4. Verifica nuovi codici tributo → aggiorna `shared/f24_tax_codes.json` se necessario
5. Se un parametro è mancante (null) per l'anno corrente → blocca i calcoli e notifica via Agent9

## Input
- Dati iniziali da Agent0 (onboarding)
- Transazioni classificate da Agent2 (per ATECO)
- Calcoli validati da Agent3b
- F24 da Agent6
- Dichiarazioni da Agent5
- Fatture emesse da Agent8
- Alert e notifiche da Agent4, Agent7, Agent9

## Output
- Profilo contribuente completo per qualsiasi agente
- Storico pluriennale per calcolo acconti e analisi trend
- Crediti d'imposta disponibili per compensazione
- Dashboard stato ciclo fiscale corrente
- Audit trail completo di ogni operazione

## Integrazioni
- Tutti gli agenti leggono e scrivono nel Supervisor
- `integrations/vault/` — Auth Agent per accesso sicuro a credenziali
- Database PostgreSQL per persistenza
- File `shared/*.json` — aggiornamento annuale parametri
