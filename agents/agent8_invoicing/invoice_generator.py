"""Invoice generator — creates FatturaPA XML for SDI."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from xml.dom import minidom

from .models import DatiCliente, EsitoSDI, Fattura, LineaFattura, NotaCredito

_SOGLIA_BOLLO = Decimal("77.47")
_IMPORTO_BOLLO = Decimal("2.00")
_ALIQUOTA_RIVALSA = Decimal("0.04")

_NS = "http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2"


def _round(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def crea_fattura(
    numero: str,
    data_fattura: date,
    cedente_piva: str,
    cedente_cf: str,
    cedente_denominazione: str,
    cliente: DatiCliente,
    linee: list[dict[str, Any]],
    rivalsa_inps_4: bool = False,
    gestione_inps: str = "separata",
    iban: str = "",
    scadenza_pagamento: date | None = None,
    cedente_indirizzo: str = "",
    cedente_cap: str = "",
    cedente_comune: str = "",
    cedente_provincia: str = "",
) -> Fattura:
    """Create a complete Fattura from input data.

    Handles:
    - Line items with totals
    - Rivalsa INPS 4% (only gestione separata)
    - Marca da bollo virtuale (> 77.47 EUR)
    - All required forfettario declarations
    """
    anno = data_fattura.year

    # Build line items
    fattura_linee: list[LineaFattura] = []
    imponibile = Decimal("0")
    for i, linea in enumerate(linee, 1):
        l = LineaFattura(
            numero_linea=i,
            descrizione=linea["descrizione"],
            quantita=Decimal(str(linea.get("quantita", "1"))),
            prezzo_unitario=Decimal(str(linea["prezzo_unitario"])),
        )
        fattura_linee.append(l)
        imponibile += l.prezzo_totale

    imponibile = _round(imponibile)

    # Rivalsa INPS 4% (solo gestione separata)
    importo_rivalsa = Decimal("0")
    apply_rivalsa = rivalsa_inps_4 and gestione_inps == "separata"
    if apply_rivalsa:
        importo_rivalsa = _round(imponibile * _ALIQUOTA_RIVALSA)

    # Marca da bollo
    bollo = imponibile > _SOGLIA_BOLLO
    importo_bollo = _IMPORTO_BOLLO if bollo else Decimal("0")

    # Totale documento
    totale = _round(imponibile + importo_rivalsa + importo_bollo)

    # PA format
    formato = "FPA12" if cliente.is_pa else "FPR12"

    fattura = Fattura(
        numero=numero,
        data=data_fattura,
        anno=anno,
        cedente_piva=cedente_piva,
        cedente_cf=cedente_cf,
        cedente_denominazione=cedente_denominazione,
        cedente_indirizzo=cedente_indirizzo,
        cedente_cap=cedente_cap,
        cedente_comune=cedente_comune,
        cedente_provincia=cedente_provincia,
        cliente=cliente,
        linee=fattura_linee,
        rivalsa_inps_4=apply_rivalsa,
        importo_rivalsa=importo_rivalsa,
        bollo_applicato=bollo,
        importo_bollo=importo_bollo,
        imponibile=imponibile,
        totale_documento=totale,
        formato_trasmissione=formato,
        iban=iban,
        scadenza_pagamento=scadenza_pagamento,
    )

    return fattura


def genera_xml(fattura: Fattura) -> str:
    """Generate FatturaPA XML string from a Fattura object."""
    root = ET.Element("p:FatturaElettronica", {
        "versione": fattura.formato_trasmissione,
        "xmlns:ds": "http://www.w3.org/2000/09/xmldsig#",
        "xmlns:p": _NS,
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
    })

    # === Header ===
    header = ET.SubElement(root, "FatturaElettronicaHeader")

    # DatiTrasmissione
    dati_trasm = ET.SubElement(header, "DatiTrasmissione")
    id_trasm = ET.SubElement(dati_trasm, "IdTrasmittente")
    ET.SubElement(id_trasm, "IdPaese").text = "IT"
    ET.SubElement(id_trasm, "IdCodice").text = fattura.cedente_cf
    ET.SubElement(dati_trasm, "ProgressivoInvio").text = fattura.numero.replace("/", "")
    ET.SubElement(dati_trasm, "FormatoTrasmissione").text = fattura.formato_trasmissione

    if fattura.cliente.is_pa:
        ET.SubElement(dati_trasm, "CodiceDestinatario").text = fattura.cliente.codice_ufficio_pa
    else:
        ET.SubElement(dati_trasm, "CodiceDestinatario").text = fattura.cliente.codice_sdi
        if fattura.cliente.pec:
            ET.SubElement(dati_trasm, "PECDestinatario").text = fattura.cliente.pec

    # CedentePrestatore
    cedente = ET.SubElement(header, "CedentePrestatore")
    dati_anag = ET.SubElement(cedente, "DatiAnagrafici")
    id_fiscale = ET.SubElement(dati_anag, "IdFiscaleIVA")
    ET.SubElement(id_fiscale, "IdPaese").text = "IT"
    ET.SubElement(id_fiscale, "IdCodice").text = fattura.cedente_piva
    ET.SubElement(dati_anag, "CodiceFiscale").text = fattura.cedente_cf
    anag = ET.SubElement(dati_anag, "Anagrafica")
    ET.SubElement(anag, "Denominazione").text = fattura.cedente_denominazione
    ET.SubElement(dati_anag, "RegimeFiscale").text = fattura.regime_fiscale

    sede_ced = ET.SubElement(cedente, "Sede")
    ET.SubElement(sede_ced, "Indirizzo").text = fattura.cedente_indirizzo or "Via non specificata"
    ET.SubElement(sede_ced, "CAP").text = fattura.cedente_cap or "00000"
    ET.SubElement(sede_ced, "Comune").text = fattura.cedente_comune or "Roma"
    ET.SubElement(sede_ced, "Provincia").text = fattura.cedente_provincia or "RM"
    ET.SubElement(sede_ced, "Nazione").text = "IT"

    # CessionarioCommittente
    cessionario = ET.SubElement(header, "CessionarioCommittente")
    dati_anag_c = ET.SubElement(cessionario, "DatiAnagrafici")
    if fattura.cliente.partita_iva:
        id_fisc_c = ET.SubElement(dati_anag_c, "IdFiscaleIVA")
        ET.SubElement(id_fisc_c, "IdPaese").text = fattura.cliente.nazione
        ET.SubElement(id_fisc_c, "IdCodice").text = fattura.cliente.partita_iva
    if fattura.cliente.codice_fiscale:
        ET.SubElement(dati_anag_c, "CodiceFiscale").text = fattura.cliente.codice_fiscale
    anag_c = ET.SubElement(dati_anag_c, "Anagrafica")
    ET.SubElement(anag_c, "Denominazione").text = fattura.cliente.denominazione

    sede_c = ET.SubElement(cessionario, "Sede")
    ET.SubElement(sede_c, "Indirizzo").text = fattura.cliente.indirizzo or "Via non specificata"
    ET.SubElement(sede_c, "CAP").text = fattura.cliente.cap or "00000"
    ET.SubElement(sede_c, "Comune").text = fattura.cliente.comune or "Roma"
    ET.SubElement(sede_c, "Provincia").text = fattura.cliente.provincia or "RM"
    ET.SubElement(sede_c, "Nazione").text = fattura.cliente.nazione

    # === Body ===
    body = ET.SubElement(root, "FatturaElettronicaBody")

    # DatiGenerali
    dati_gen = ET.SubElement(body, "DatiGenerali")
    dati_gen_doc = ET.SubElement(dati_gen, "DatiGeneraliDocumento")
    ET.SubElement(dati_gen_doc, "TipoDocumento").text = "TD01"  # fattura
    ET.SubElement(dati_gen_doc, "Divisa").text = "EUR"
    ET.SubElement(dati_gen_doc, "Data").text = fattura.data.isoformat()
    ET.SubElement(dati_gen_doc, "Numero").text = fattura.numero
    ET.SubElement(dati_gen_doc, "Causale").text = fattura.dicitura_forfettario

    if fattura.bollo_applicato:
        dati_bollo = ET.SubElement(dati_gen_doc, "DatiBollo")
        ET.SubElement(dati_bollo, "BolloVirtuale").text = "SI"
        ET.SubElement(dati_bollo, "ImportoBollo").text = str(fattura.importo_bollo)

    ET.SubElement(dati_gen_doc, "ImportoTotaleDocumento").text = str(fattura.totale_documento)

    # DatiBeniServizi
    dati_beni = ET.SubElement(body, "DatiBeniServizi")

    for linea in fattura.linee:
        det = ET.SubElement(dati_beni, "DettaglioLinee")
        ET.SubElement(det, "NumeroLinea").text = str(linea.numero_linea)
        ET.SubElement(det, "Descrizione").text = linea.descrizione
        ET.SubElement(det, "Quantita").text = str(linea.quantita)
        ET.SubElement(det, "PrezzoUnitario").text = str(linea.prezzo_unitario)
        ET.SubElement(det, "PrezzoTotale").text = str(linea.prezzo_totale)
        ET.SubElement(det, "AliquotaIVA").text = "0.00"
        ET.SubElement(det, "Natura").text = linea.natura
        ET.SubElement(det, "RiferimentoNormativo").text = "Art.1, c.54-89, L.190/2014"

    # Rivalsa INPS 4% as additional line
    if fattura.rivalsa_inps_4 and fattura.importo_rivalsa > 0:
        det_riv = ET.SubElement(dati_beni, "DettaglioLinee")
        ET.SubElement(det_riv, "NumeroLinea").text = str(len(fattura.linee) + 1)
        ET.SubElement(det_riv, "Descrizione").text = "Contributo INPS 4% ex art. 1, c. 212, L. 662/96"
        ET.SubElement(det_riv, "Quantita").text = "1"
        ET.SubElement(det_riv, "PrezzoUnitario").text = str(fattura.importo_rivalsa)
        ET.SubElement(det_riv, "PrezzoTotale").text = str(fattura.importo_rivalsa)
        ET.SubElement(det_riv, "AliquotaIVA").text = "0.00"
        ET.SubElement(det_riv, "Natura").text = "N2.2"

    # DatiRiepilogo
    riepilogo = ET.SubElement(dati_beni, "DatiRiepilogo")
    ET.SubElement(riepilogo, "AliquotaIVA").text = "0.00"
    ET.SubElement(riepilogo, "Natura").text = "N2.2"
    ET.SubElement(riepilogo, "ImponibileImporto").text = str(
        fattura.imponibile + fattura.importo_rivalsa
    )
    ET.SubElement(riepilogo, "Imposta").text = "0.00"
    ET.SubElement(riepilogo, "RiferimentoNormativo").text = "Art.1, c.54-89, L.190/2014"

    # DatiPagamento
    dati_pag = ET.SubElement(body, "DatiPagamento")
    ET.SubElement(dati_pag, "CondizioniPagamento").text = "TP02"  # completo
    det_pag = ET.SubElement(dati_pag, "DettaglioPagamento")
    ET.SubElement(det_pag, "ModalitaPagamento").text = fattura.modalita_pagamento
    ET.SubElement(det_pag, "ImportoPagamento").text = str(fattura.totale_documento)
    if fattura.scadenza_pagamento:
        ET.SubElement(det_pag, "DataScadenzaPagamento").text = fattura.scadenza_pagamento.isoformat()
    if fattura.iban:
        ET.SubElement(det_pag, "IBAN").text = fattura.iban

    # Pretty print
    rough = ET.tostring(root, encoding="unicode", xml_declaration=False)
    dom = minidom.parseString(rough)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + dom.toprettyxml(indent="  ").split("\n", 1)[1]


def gestisci_esito_sdi(esito: EsitoSDI) -> EsitoSDI:
    """Process an SDI response and determine the action."""
    if esito.codice == "RC":
        esito.descrizione = "Fattura consegnata con successo"
        esito.azione_automatica = "archivia_ricevuta"
        esito.richiede_intervento = False

    elif esito.codice == "MC":
        esito.descrizione = "Mancata consegna — disponibile nel cassetto fiscale del cliente"
        esito.azione_automatica = "alert_mancata_consegna"
        esito.richiede_intervento = False

    elif esito.codice == "NS":
        esito.descrizione = f"Fattura scartata dal SDI — errore: {esito.codice_errore}"
        esito.azione_automatica = "correzione_e_riemissione"
        esito.richiede_intervento = True

    elif esito.codice == "EC":
        esito.descrizione = "Esito committente PA"
        esito.azione_automatica = "verifica_accettazione_pa"
        esito.richiede_intervento = True

    elif esito.codice == "AT":
        esito.descrizione = "Attestazione di trasmissione — silenzio-assenso PA"
        esito.azione_automatica = "archivia_attestazione"
        esito.richiede_intervento = False

    return esito
