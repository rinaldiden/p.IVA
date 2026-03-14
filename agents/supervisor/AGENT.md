# Supervisor — Profilo Contribuente & Coordinamento

## Responsabilità
- **Fonte di verità unica** per tutti i dati del contribuente
- Mantiene il profilo completo: anagrafica, P.IVA, ATECO, tipo INPS, regime, credenziali firma
- Gestisce lo **storico pluriennale**: ricavi, imposte pagate, dichiarazioni inviate, F24, anno per anno
- Coordina il flusso tra agenti: sa chi ha fatto cosa e quando
- Tiene traccia dello stato corrente del ciclo fiscale annuale
- Archivia ogni documento generato (F24, dichiarazioni, ricevute)
- Espone i dati agli altri agenti in modo strutturato

## Profilo Contribuente (schema)
```
{
  "anagrafica": { nome, cognome, cf, residenza, ... },
  "piva": { numero, data_apertura, ateco, coefficiente_redditivita },
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
  "f24_generati": [ { data, importo, codice_tributo, stato } ],
  "eventi": [ { data, tipo, descrizione } ]
}
```

## Input
- Dati iniziali da Agent0 (onboarding)
- Transazioni classificate da Agent2
- Calcoli validati da Agent3b
- F24 da Agent6
- Dichiarazioni da Agent5
- Alert e notifiche da Agent4, Agent7, Agent9

## Output
- Profilo contribuente completo per qualsiasi agente che lo richieda
- Storico pluriennale per calcolo acconti e analisi trend
- Dashboard stato ciclo fiscale corrente
- Audit trail completo di ogni operazione

## Integrazioni
- Tutti gli agenti leggono e scrivono nel Supervisor
- Database PostgreSQL per persistenza
- Encryption at rest per dati sensibili (credenziali firma, dati bancari)
