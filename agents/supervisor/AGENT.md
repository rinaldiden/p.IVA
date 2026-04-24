# Supervisor — Profilo Contribuente & Coordinamento

## Responsabilità
- **Fonte di verità unica** per tutti i dati del contribuente
- Mantiene il profilo completo: anagrafica, P.IVA, ATECO, tipo INPS, regime, credenziali firma
- Gestisce lo **storico pluriennale**: ricavi, imposte pagate, dichiarazioni inviate, F24, anno per anno
- Coordina il flusso tra agenti: sa chi ha fatto cosa e quando
- Tiene traccia dello stato corrente del ciclo fiscale annuale
- Archivia ogni documento generato (F24, dichiarazioni, ricevute)
- Espone i dati agli altri agenti in modo strutturato
- Gestisce il **ciclo di vita completo** della P.IVA inclusa la cessazione:
  - Stato "in_chiusura": checklist pre-chiusura in corso
  - Stato "cessata_adempimenti_pendenti": P.IVA chiusa, ma dichiarazione finale e saldi da completare l'anno successivo
  - Stato "cessata_completata": tutti gli adempimenti post-chiusura completati, sistema disattivabile
- Mantiene lo **scadenzario post-cessazione** attivo fino al completamento di tutti gli adempimenti residui

## Profilo Contribuente (schema)
```
{
  "anagrafica": { nome, cognome, cf, residenza, ... },
  "piva": { numero, data_apertura, data_cessazione, stato, ateco, coefficiente_redditivita },
  // stato: "attiva" | "in_chiusura" | "cessata_adempimenti_pendenti" | "cessata_completata"
  "regime": { tipo, aliquota, anno_inizio, riduzione_contributiva_35 },
  "inps": { gestione, tipo_iscrizione, minimale_annuo },
  "firma_digitale": { provider, credenziali_encrypted, scadenza },
  "banca": { iban, provider_psd2, consent_id },
  "canali_notifica": { email, telefono, app },
  "canali_documenti": { google_drive_folder, google_photos_album, email }
}
```

## Storico Annuale (schema)
```
{
  "anno": 2026,
  "ricavi_totali": 45000,
  "reddito_imponibile": 35100,  // ricavi × coefficiente
  "imposta_sostitutiva": { importo, aliquota, pagato },
  "contributi_inps": { fissi, percentuali, totale, pagato },
  "acconti_versati": [ { data, importo, codice_tributo } ],
  "saldo": { importo, data_versamento },
  "dichiarazione": { file, data_invio, ricevuta },
  "f24_generati": [ { data, importo, codice_tributo, stato, quietanza } ],
  "f24_pagati": [ { data, importo, codice_tributo, quietanza_psd2 } ],
  "fatture_emesse": [ { numero, data, cliente, importo, bollo_virtuale, stato_sdi, ricevuta } ],
  "bollo_virtuale": { totale_annuo, versamenti_trimestrali: [ { trimestre, importo, codice_tributo, pagato } ] },
  "crediti_imposta": { residuo_anno_precedente, utilizzato_in_compensazione, residuo_fine_anno },
  "cessazione": {
    "data_cessazione": null,
    "motivo": null,
    "checklist_pre_chiusura": { fatture_chiuse, saldi_calcolati, crediti_gestiti, bollo_versato, conferma_utente },
    "adempimenti_post_chiusura": {
      "dichiarazione_finale": { dovuta, inviata, data_invio },
      "saldo_imposta": { importo, pagato, data_pagamento },
      "saldo_inps": { importo, pagato, data_pagamento },
      "saldo_bollo_virtuale": { importo, pagato, data_pagamento }
    },
    "completata": false
  },
  "eventi": [ { data, tipo, descrizione } ]
}
```

## Input
- Dati iniziali da Agent0 (onboarding)
- Transazioni classificate da Agent2
- Calcoli validati da Agent3b
- F24 da Agent6
- Dichiarazioni da Agent5
- Fatture emesse e quietanze F24 da Agent8
- Alert e notifiche da Agent4, Agent7, Agent9

## Output
- Profilo contribuente completo per qualsiasi agente che lo richieda
- Storico pluriennale per calcolo acconti e analisi trend
- Crediti d'imposta residui per compensazione in F24
- Dashboard stato ciclo fiscale corrente
- Audit trail completo di ogni operazione

## Checkpoint di Conferma Utente
Il Supervisor gestisce un sistema di conferma pre-invio configurabile:
- **Dichiarazione**: sempre conferma manuale (Agent5 invia riepilogo via Agent9, attende OK)
- **F24 > soglia**: conferma manuale (soglia configurabile dall'utente, default €500)
- **F24 <= soglia**: auto-approvazione (configurabile)
- **Fatture**: configurabile (auto/manuale per singola fattura)
- Ogni conferma e relativo esito vengono loggati nell'audit trail

## Integrazioni
- Tutti gli agenti leggono e scrivono nel Supervisor
- Database PostgreSQL per persistenza
- Encryption at rest per dati sensibili (credenziali firma, dati bancari)
