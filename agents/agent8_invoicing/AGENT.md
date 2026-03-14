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
- Monitorare esito SDI (accettata/scartata/mancata consegna) e ri-trasmettere se necessario
- Aggiornare il contatore ricavi in tempo reale nel Supervisor

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
- Importo
- Dati forfettario dal Supervisor (P.IVA, ATECO, regime)

## Output
- Fattura elettronica XML conforme SDI
- Ricevuta trasmissione SDI
- Aggiornamento contatore ricavi nel Supervisor
- PDF di cortesia per il cliente

## Integrazioni
- `integrations/sdi/` — Trasmissione fattura e monitoraggio esito
- `agents/supervisor/` — Dati emittente, numerazione, contatore ricavi
- `agents/agent2_categorizer/` — Classificazione automatica del ricavo emesso

## Note
- Il codice regime fiscale per forfettari è **RF19**
- Il codice natura IVA è **N2.2** (non soggetto — altri casi)
- La marca da bollo virtuale va versata con F24 entro il 30/01 dell'anno successivo per il totale delle marche dell'anno (codice tributo 2501)
- Le fatture verso PA richiedono codice univoco ufficio (non codice SDI)
