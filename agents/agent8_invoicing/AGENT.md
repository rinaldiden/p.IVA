# Agent8 — Invoicing (Fatturazione Attiva)

## Responsabilità
- **Emettere fatture elettroniche XML** conformi alle specifiche SDI
- Trasmettere via Sistema di Interscambio
- Applicare **marca da bollo virtuale da 2€** su fatture con importo > 77,47€
- Inserire dicitura obbligatoria forfettari: _"Operazione effettuata ai sensi dell'art. 1, commi da 54 a 89, della Legge n. 190/2014 — Regime forfettario"_
- Inserire dicitura esenzione IVA: _"Operazione senza applicazione dell'IVA ai sensi dell'art. 1, comma 58, Legge 190/2014"_
- Inserire dicitura ritenuta: _"Si richiede la non applicazione della ritenuta alla fonte a titolo d'acconto ai sensi dell'art. 1, comma 67, Legge 190/2014"_ (se applicabile, per prestazioni verso sostituti d'imposta)
- Gestire **numerazione progressiva** fatture (annuale, senza buchi)
- Supportare note di credito
- Gestire fatture verso PA (con codice CIG/CUP, split payment non applicabile ai forfettari)
- **Gestire rivalsa INPS 4%** per contribuenti in gestione separata (vedi sezione dedicata)
- **Monitorare esito SDI** con gestione completa codici di risposta (vedi sotto)
- Aggiornare il contatore ricavi in tempo reale nel Supervisor (**al netto della rivalsa 4%**)

## Rivalsa INPS 4%

I forfettari iscritti alla **gestione separata INPS** possono addebitare al cliente il 4% del compenso come rivalsa contributiva (art. 1, c. 212, L. 662/96).

- **Facoltativa**, non obbligatoria — configurata come flag `rivalsa_inps_4: bool` nel profilo contribuente (Supervisor)
- Se `rivalsa_inps_4 = true`: Agent8 aggiunge automaticamente in fattura una riga "Contributo INPS 4% ex art. 1, c. 212, L. 662/96" con importo = `compenso × 0.04`
- **La rivalsa NON è ricavo** — non entra nel calcolo dei ricavi ai fini del coefficiente forfettario
- Il contatore ricavi nel Supervisor viene aggiornato con il **compenso al netto della rivalsa**
- Agent3 riceve i ricavi **già al netto** della rivalsa 4%
- La rivalsa è **applicabile solo** ai contribuenti in gestione separata (non artigiani/commercianti)

### Esempio fattura con rivalsa
```
Compenso professionale              €  1.000,00
Contributo INPS 4% (L. 662/96)     €     40,00
Bollo (se > 77,47€)                 €      2,00
                                    ───────────
TOTALE DOCUMENTO                    €  1.042,00

Ricavo ai fini forfettario: € 1.000,00 (senza rivalsa e senza bollo)
```

## Gestione esiti SDI

Dopo la trasmissione, Agent8 monitora l'esito e reagisce automaticamente:

| Codice | Significato | Azione automatica |
|--------|-------------|-------------------|
| **RC** | Ricevuta di consegna | Fattura consegnata con successo. Archiviare ricevuta nel Supervisor. Nessuna azione ulteriore. |
| **MC** | Mancata consegna | Il destinatario non è raggiungibile. La fattura è disponibile nel cassetto fiscale del cliente. Alert via Agent9 con istruzioni: "Fattura N. XXX non consegnata via SDI — disponibile nel cassetto fiscale del cliente. Valuta invio PDF di cortesia via email." |
| **NS** | Notifica di scarto | La fattura è stata SCARTATA dal SDI per errori formali. **Alert immediato** via Agent9 con codice errore specifico. Agent8 analizza l'errore, corregge il XML e ri-emette entro 5 giorni mantenendo lo stesso numero fattura (come da normativa). |
| **EC** | Esito committente | Solo per fatture PA. Il committente ha accettato/rifiutato la fattura. Se rifiutata: alert via Agent9 con motivazione. |
| **AT** | Attestazione di trasmissione | Per fatture PA: se il committente non risponde entro 15 giorni, il SDI emette AT (silenzio-assenso). Archiviare nel Supervisor. |

### Flusso ri-emissione per scarto (NS)
```
Fattura scartata (NS)
  │
  ├── Agent8 riceve notifica NS con codice errore
  ├── Analizza codice errore (es. 00200 = file non conforme, 00305 = P.IVA cessata)
  ├── Se errore correggibile automaticamente:
  │     ├── Corregge il XML
  │     ├── Ri-trasmette con STESSO numero fattura entro 5 giorni
  │     └── Notifica utente via Agent9: "Fattura N. XXX scartata per [motivo], corretta e ri-trasmessa"
  ├── Se errore NON correggibile (es. P.IVA cliente errata):
  │     ├── Alert urgente via Agent9: "Fattura N. XXX scartata — richiede intervento manuale: [motivo]"
  │     └── Flag nel Supervisor come "da risolvere"
  └── Se non corretta entro 5 giorni:
        └── Alert CRITICO: "SCADENZA — emettere nuova fattura con nuovo numero entro 5 giorni dalla scadenza"
```

## Formato fattura XML
```xml
<FatturaElettronica versione="FPR12">
  <FatturaElettronicaHeader>
    <DatiTrasmissione>
      <CodiceDestinatario>[SDI del cliente]</CodiceDestinatario>
    </DatiTrasmissione>
    <CedentePrestatore>
      <!-- Dati forfettario da Supervisor -->
      <RegimeFiscale>RF19</RegimeFiscale>  <!-- Regime forfettario -->
    </CedentePrestatore>
  </FatturaElettronicaHeader>
  <FatturaElettronicaBody>
    <DatiGenerali>
      <DatiBollo>
        <BolloVirtuale>SI</BolloVirtuale>
        <ImportoBollo>2.00</ImportoBollo>
      </DatiBollo>
    </DatiGenerali>
    <DatiBeniServizi>
      <DettaglioLinee>
        <Natura>N2.2</Natura>  <!-- Non soggetto - altri casi -->
        <RiferimentoNormativo>Art.1, c.54-89, L.190/2014</RiferimentoNormativo>
      </DettaglioLinee>
    </DatiBeniServizi>
  </FatturaElettronicaBody>
</FatturaElettronica>
```

## Input
- Dati cliente (denominazione, P.IVA/CF, codice SDI o PEC)
- Descrizione prestazione/bene
- Importo (compenso)
- Dati forfettario dal Supervisor (P.IVA, ATECO, regime, gestione INPS, flag `rivalsa_inps_4`)
- Notifiche esito SDI (RC, MC, NS, EC, AT)

## Output
- Fattura elettronica XML conforme SDI (con rivalsa 4% se configurata)
- Ricevuta trasmissione SDI archiviata nel Supervisor
- Aggiornamento contatore ricavi nel Supervisor (**al netto della rivalsa 4%**)
- PDF di cortesia per il cliente
- Alert verso Agent9 per esiti SDI che richiedono attenzione (MC, NS, EC rifiutato)
- Ri-emissione automatica in caso di scarto (NS) se correggibile

## Integrazioni
- `integrations/sdi/` — Trasmissione fattura e ricezione esiti
- `agents/supervisor/` — Dati emittente, numerazione, contatore ricavi, archiviazione esiti
- `agents/agent2_categorizer/` — Classificazione automatica del ricavo emesso
- `agents/agent9_notifier/` — Alert esiti SDI (MC, NS, EC)

## Note
- Il codice regime fiscale per forfettari è **RF19**
- Il codice natura IVA è **N2.2** (non soggetto — altri casi)
- La marca da bollo virtuale va versata con F24 entro il 30/01 dell'anno successivo per il totale delle marche dell'anno (codice tributo 2501)
- Le fatture verso PA richiedono codice univoco ufficio (non codice SDI)
- In caso di scarto (NS), la ri-emissione con stesso numero è consentita entro 5 giorni dalla notifica di scarto
- La rivalsa INPS 4% è applicabile solo a contribuenti in gestione separata, non artigiani/commercianti
