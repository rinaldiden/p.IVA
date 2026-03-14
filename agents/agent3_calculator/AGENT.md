# Agent3 — Calculator (deterministico)

## Responsabilità
- **Calcolo interamente deterministico** — Python puro, zero LLM, solo aritmetica e tabelle
- Calcolare reddito imponibile per ciascun codice ATECO: `ricavi_ATECO × coefficiente_ATECO`
- **Dedurre i contributi INPS versati nell'anno** dal reddito imponibile complessivo (unica deduzione ammessa nel forfettario): `reddito_imponibile = Σ(ricavi_ATECO × coeff_ATECO) − contributi_INPS_versati`
- Calcolare imposta sostitutiva: `reddito_imponibile × aliquota (15% ordinaria, 5% primi 5 anni)`
- Calcolare contributi INPS: gestione separata (% sul reddito da `shared/inps_rates.json`) o artigiani/commercianti (fisso + % sul reddito eccedente il minimale)
- Calcolare riduzione contributiva 35% se applicabile
- Calcolare acconti (giugno/luglio e novembre) e saldo basandosi su anno precedente
- **Gestire crediti d'imposta**: se acconti versati > imposta dovuta, calcolare credito da compensare in F24 anno successivo
- Generare importi F24 con codici tributo corretti da `shared/f24_tax_codes.json`
- Supportare **multi-ATECO**: calcoli separati per codice, poi aggregazione

## Formula completa
```
Per ciascun ATECO_i:
  reddito_ATECO_i = ricavi_ATECO_i × coefficiente_ATECO_i

Reddito lordo = Σ reddito_ATECO_i
Reddito imponibile = Reddito lordo − contributi_INPS_versati_anno
  (se negativo → reddito imponibile = 0, no perdite riportabili nel forfettario)

Imposta sostitutiva = Reddito imponibile × aliquota (5% o 15%)

Acconti dovuti = 100% dell'imposta anno precedente
  - 1° acconto (giugno): 40% degli acconti dovuti
  - 2° acconto (novembre): 60% degli acconti dovuti

Saldo = Imposta anno corrente − acconti già versati
  - Se negativo → credito da compensare in F24 anno successivo
```

## Input
- Ricavi classificati da Agent2, **separati per codice ATECO**
- Codici ATECO e coefficienti di redditività
- Anno di apertura P.IVA (per determinare aliquota 5% o 15%)
- Contributi INPS effettivamente versati nell'anno (dal Supervisor)
- Parametri INPS correnti da `shared/inps_rates.json`
- Storico anno precedente dal Supervisor (per calcolo acconti)
- Eventuali crediti d'imposta da anni precedenti (dal Supervisor)

## Output
- Calcolo reddito imponibile dettagliato (per ATECO + aggregato)
- Calcolo imposta sostitutiva con evidenza deduzione INPS
- Calcolo contributi INPS (fissi + percentuali, con/senza riduzione 35%)
- Importi F24 con codici tributo, incluse eventuali compensazioni crediti
- Piano acconti e saldo con importi esatti
- Tutto inviato ad Agent3b per validazione

## Integrazioni
- `shared/ateco_coefficients.json` — Coefficienti di redditività
- `shared/tax_calendar.json` — Scadenze fiscali
- `shared/f24_tax_codes.json` — Codici tributo
- `shared/inps_rates.json` — Aliquote INPS per anno
- `agents/supervisor/` — Storico contribuente, contributi versati, crediti

## Note architetturali
- Agent3 è **deterministico come Agent3b** — entrambi puro Python, zero LLM
- La differenza: sono due implementazioni indipendenti della stessa logica, scritte separatamente
- L'LLM viene usato solo a valle, per comunicare i risultati all'utente in linguaggio naturale (tramite Agent9)
- Se Agent3 e Agent3b divergono anche di 1 centesimo, il flusso si blocca
