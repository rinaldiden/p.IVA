# Schema API FastAPI — Endpoint Minimi

**Versione**: v1
**Base URL**: `/api/v1`
**Autenticazione**: Bearer token JWT (emesso dopo login SPID via Vault)

---

## Onboarding (Agent0)

### `POST /api/v1/contribuente/onboarding/start`
Avvia il processo di onboarding per un nuovo contribuente.

**Agente**: Agent0 Wizard
**Auth**: Nessuna (primo accesso)

**Request body**:
```json
{
  "nome": "Mario",
  "cognome": "Rossi",
  "codice_fiscale": "RSSMRA85M01H501Z",
  "email": "mario@example.com",
  "telefono": "+393331234567"
}
```

**Response** `201 Created`:
```json
{
  "contribuente_id": "uuid",
  "onboarding_session_id": "uuid",
  "next_step": 1,
  "total_steps": 6,
  "steps": [
    { "step": 1, "title": "Dati anagrafici completi" },
    { "step": 2, "title": "Scelta codice ATECO" },
    { "step": 3, "title": "Configurazione INPS" },
    { "step": 4, "title": "Firma digitale" },
    { "step": 5, "title": "Collegamento banca (PSD2)" },
    { "step": 6, "title": "Riepilogo e conferma" }
  ]
}
```

---

### `POST /api/v1/contribuente/onboarding/step/{step_number}`
Completa uno step dell'onboarding.

**Agente**: Agent0 Wizard
**Auth**: Session token onboarding

**Request body** (varia per step):
```json
// Step 2 — ATECO
{
  "onboarding_session_id": "uuid",
  "data": {
    "ateco_codes": [
      { "codice": "62.01", "descrizione": "Sviluppo software" }
    ],
    "fatturato_stimato_annuo": 40000
  }
}
```

**Response** `200 OK`:
```json
{
  "step_completed": 2,
  "next_step": 3,
  "simulazione": {
    "reddito_imponibile_stimato": 26800,
    "imposta_sostitutiva_stimata": 1340,
    "contributi_inps_stimati": 6987,
    "totale_stimato": 8327,
    "accantonamento_mensile_consigliato": 694
  }
}
```

---

## Profilo contribuente (Supervisor)

### `GET /api/v1/contribuente/{id}/profilo`
Restituisce il profilo completo del contribuente.

**Agente**: Supervisor
**Auth**: Bearer JWT (contribuente autenticato)

**Response** `200 OK`:
```json
{
  "contribuente_id": "uuid",
  "anagrafica": { "nome": "Mario", "cognome": "Rossi", "codice_fiscale": "..." },
  "piva": { "numero": "12345678901", "ateco_codes": [...], "stato": "attiva" },
  "regime": { "tipo": "forfettario", "aliquota": 0.05 },
  "inps": { "gestione": "separata", "rivalsa_inps_4": true },
  "ricavi_anno_corrente": { "totale": 28500, "per_ateco": [...] },
  "prossima_scadenza": { "data": "2026-06-30", "tipo": "saldo + 1° acconto", "importo_stimato": 1540 },
  "stato_consent_psd2": "attivo",
  "stato_ciclo_fiscale": "in_corso"
}
```

---

### `GET /api/v1/contribuente/{id}/simulazione`
Simulazione fiscale in tempo reale basata sui dati correnti.

**Agente**: Agent3 Calculator
**Auth**: Bearer JWT

**Response** `200 OK`:
```json
{
  "anno": 2026,
  "ricavi_attuali": 28500,
  "proiezione_fine_anno": 45000,
  "reddito_imponibile_stimato": 30150,
  "imposta_sostitutiva_stimata": 1507.50,
  "contributi_inps_stimati": 7855,
  "crediti_da_anno_precedente": 0,
  "totale_dovuto_stimato": 9362.50,
  "soglia_forfettario": { "attuale": 28500, "limite": 85000, "percentuale": 33.5 }
}
```

---

## Fatturazione (Agent8)

### `POST /api/v1/fatture/emetti`
Emette una nuova fattura elettronica.

**Agente**: Agent8 Invoicing
**Auth**: Bearer JWT

**Request body**:
```json
{
  "contribuente_id": "uuid",
  "cliente": {
    "denominazione": "Acme SRL",
    "partita_iva": "98765432109",
    "codice_sdi": "A1B2C3D",
    "indirizzo": { "via": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM" }
  },
  "prestazione": {
    "descrizione": "Sviluppo applicazione web — marzo 2026",
    "importo": 3000.00,
    "codice_ateco": "62.01"
  }
}
```

**Response** `201 Created`:
```json
{
  "fattura_id": "uuid",
  "numero": "FE-2026-0015",
  "stato_sdi": "trasmessa",
  "dettaglio": {
    "compenso": 3000.00,
    "rivalsa_inps_4": 120.00,
    "bollo": 2.00,
    "totale_documento": 3122.00
  },
  "xml_ref": "storage://fatture/2026/FE-2026-0015.xml",
  "pdf_cortesia_url": "/api/v1/fatture/uuid/pdf"
}
```

---

### `GET /api/v1/fatture/{id}/stato`
Stato corrente della fattura e esito SDI.

**Agente**: Agent8 Invoicing
**Auth**: Bearer JWT

**Response** `200 OK`:
```json
{
  "fattura_id": "uuid",
  "numero": "FE-2026-0015",
  "stato_sdi": "RC",
  "stato_descrizione": "Ricevuta di consegna — fattura consegnata con successo",
  "data_trasmissione": "2026-03-14T10:30:00Z",
  "data_esito": "2026-03-14T10:31:15Z",
  "ricevuta_ref": "storage://ricevute/2026/RC-FE-2026-0015.xml"
}
```

---

## Scadenze e pagamenti (Agent6)

### `GET /api/v1/scadenze/{contribuente_id}`
Scadenzario completo del contribuente.

**Agente**: Agent6 Scheduler
**Auth**: Bearer JWT

**Response** `200 OK`:
```json
{
  "contribuente_id": "uuid",
  "anno": 2026,
  "scadenze": [
    {
      "id": "uuid",
      "data": "2026-06-30",
      "tipo": "saldo_imposta_sostitutiva",
      "codice_tributo": "1792",
      "importo": 172.50,
      "stato": "da_pagare",
      "f24_ref": "storage://f24/2026/F24-2026-06-30-1792.pdf",
      "giorni_mancanti": 108
    },
    {
      "id": "uuid",
      "data": "2026-06-30",
      "tipo": "primo_acconto_imposta",
      "codice_tributo": "1790",
      "importo": 469.00,
      "stato": "da_pagare",
      "f24_ref": "storage://f24/2026/F24-2026-06-30-1790.pdf",
      "giorni_mancanti": 108
    }
  ],
  "totale_anno": 9362.50,
  "prossima_scadenza": "2026-06-30",
  "importo_prossima_scadenza": 641.50
}
```

---

## Calcolo fiscale (Agent3 + Agent3b)

### `GET /api/v1/calcolo/{contribuente_id}/ultimo`
Ultimo calcolo fiscale validato.

**Agente**: Agent3 Calculator + Agent3b Validator
**Auth**: Bearer JWT

**Response** `200 OK`:
```json
{
  "contribuente_id": "uuid",
  "anno": 2026,
  "data_calcolo": "2026-03-14T09:00:00Z",
  "validato": true,
  "ricavi": {
    "per_ateco": [
      { "codice": "62.01", "ricavi": 28500, "coefficiente": 0.67, "reddito": 19095 }
    ],
    "totale_ricavi": 28500,
    "totale_reddito_lordo": 19095
  },
  "contributi_inps_versati": 3500,
  "reddito_imponibile": 15595,
  "aliquota": 0.05,
  "imposta_dovuta": 779.75,
  "acconti_versati": 0,
  "saldo": 779.75,
  "crediti_disponibili": 0
}
```

---

### `POST /api/v1/calcolo/{contribuente_id}/ricalcola`
Forza un ricalcolo con validazione Agent3b.

**Agente**: Agent3 Calculator → Agent3b Validator
**Auth**: Bearer JWT

**Response** `200 OK`:
```json
{
  "calcolo_id": "uuid",
  "stato": "validato",
  "validazione": { "agent3_agent3b_match": true, "divergenze": [] }
}
```

**Response** `409 Conflict` (divergenza):
```json
{
  "calcolo_id": "uuid",
  "stato": "bloccato",
  "validazione": {
    "agent3_agent3b_match": false,
    "divergenze": [
      { "campo": "imposta_dovuta", "agent3": 779.75, "agent3b": 780.00, "delta": 0.25 }
    ]
  },
  "messaggio": "Calcolo bloccato — divergenza rilevata. Il team tecnico è stato notificato."
}
```

---

## Notifiche (Agent9)

### `GET /api/v1/notifiche/{contribuente_id}/pending`
Notifiche pendenti (non ancora lette/confermate).

**Agente**: Agent9 Notifier
**Auth**: Bearer JWT

**Response** `200 OK`:
```json
{
  "contribuente_id": "uuid",
  "pending": [
    {
      "notifica_id": "uuid",
      "data": "2026-03-14T08:00:00Z",
      "priorita": "normale",
      "sorgente": "agent6_scheduler",
      "titolo": "Scadenza fiscale tra 7 giorni",
      "messaggio": "Il 30 giugno scade il saldo imposta sostitutiva: € 172,50 (codice tributo 1792)",
      "canali_inviati": ["email", "sms"],
      "letto": false
    }
  ],
  "totale_pending": 1
}
```
