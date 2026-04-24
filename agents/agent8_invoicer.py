"""
Agent8 — Invoicer & Payment Executor

Genera fatture elettroniche XML conformi FatturaPA v1.2.2.
Applica marca da bollo virtuale, regime forfettario RF19.

Output: data/fatture/ANNO/fattura_NNN.xml + fattura_NNN.json

Per ora genera il file XML localmente.
L'invio al SDI sara' integrato quando disponibile il canale.
"""

import json
import logging
import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from pathlib import Path
from xml.dom import minidom

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from config import settings
from agents.supervisor import carica_profilo, carica_storico, registra_fattura, registra_evento

LOGS_DIR = settings.LOGS_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOGS_DIR / "agent8.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("agent8")


def prossimo_numero_fattura(anno: int) -> int:
    storico = carica_storico(anno)
    fatture = storico.get("fatture_emesse", [])
    if not fatture:
        return 1
    numeri = [f.get("numero", 0) for f in fatture]
    return max(numeri) + 1


def genera_xml_fattura(
    cliente: dict,
    prestazioni: list[dict],
    data_fattura: str = None,
    anno: int = None,
) -> dict:
    """
    Genera fattura elettronica XML FatturaPA per forfettario.

    cliente: {denominazione, piva|cf, indirizzo, cap, comune, provincia, pec|codice_sdi}
    prestazioni: [{descrizione, importo, quantita}]
    """
    if anno is None:
        anno = date.today().year
    if data_fattura is None:
        data_fattura = date.today().isoformat()

    profilo = carica_profilo()
    numero = prossimo_numero_fattura(anno)
    progressivo = f"{anno}{numero:04d}"

    ana = profilo["anagrafica"]
    piva_info = profilo["piva"]

    # Calcolo importi
    totale_imponibile = sum(
        p["importo"] * p.get("quantita", 1) for p in prestazioni
    )
    totale_imponibile = round(totale_imponibile, 2)

    # Bollo virtuale
    bollo_applicato = totale_imponibile > settings.REGIME["bollo_virtuale_soglia"]
    bollo_importo = settings.REGIME["bollo_virtuale_importo"] if bollo_applicato else 0

    # --- Costruzione XML FatturaPA ---
    ns = "http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2"
    root = ET.Element("p:FatturaElettronica", {
        "xmlns:p": ns,
        "xmlns:ds": "http://www.w3.org/2000/09/xmldsig#",
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "versione": settings.FATTURA["formato"],
    })

    # Header
    header = ET.SubElement(root, "FatturaElettronicaHeader")

    # DatiTrasmissione
    dati_trasm = ET.SubElement(header, "DatiTrasmissione")
    id_trasm = ET.SubElement(dati_trasm, "IdTrasmittente")
    ET.SubElement(id_trasm, "IdPaese").text = "IT"
    ET.SubElement(id_trasm, "IdCodice").text = ana["codice_fiscale"]
    ET.SubElement(dati_trasm, "ProgressivoInvio").text = progressivo
    ET.SubElement(dati_trasm, "FormatoTrasmissione").text = "FPR12"
    ET.SubElement(dati_trasm, "CodiceDestinatario").text = cliente.get("codice_sdi", "0000000")

    # CedentePrestatore (noi)
    cedente = ET.SubElement(header, "CedentePrestatore")
    dati_anag_ced = ET.SubElement(cedente, "DatiAnagrafici")
    id_fisc_ced = ET.SubElement(dati_anag_ced, "IdFiscaleIVA")
    ET.SubElement(id_fisc_ced, "IdPaese").text = "IT"
    ET.SubElement(id_fisc_ced, "IdCodice").text = piva_info.get("numero", "")
    ET.SubElement(dati_anag_ced, "CodiceFiscale").text = ana["codice_fiscale"]
    anag_ced = ET.SubElement(dati_anag_ced, "Anagrafica")
    ET.SubElement(anag_ced, "Nome").text = ana["nome"]
    ET.SubElement(anag_ced, "Cognome").text = ana["cognome"]
    ET.SubElement(dati_anag_ced, "RegimeFiscale").text = settings.FATTURA["regime_fiscale"]

    sede_ced = ET.SubElement(cedente, "Sede")
    ET.SubElement(sede_ced, "Indirizzo").text = ana.get("residenza", "")
    ET.SubElement(sede_ced, "CAP").text = "00000"
    ET.SubElement(sede_ced, "Comune").text = ana.get("comune_nascita", "")
    ET.SubElement(sede_ced, "Nazione").text = "IT"

    # CessionarioCommittente (cliente)
    cessionario = ET.SubElement(header, "CessionarioCommittente")
    dati_anag_cess = ET.SubElement(cessionario, "DatiAnagrafici")
    if cliente.get("piva"):
        id_fisc_cess = ET.SubElement(dati_anag_cess, "IdFiscaleIVA")
        ET.SubElement(id_fisc_cess, "IdPaese").text = "IT"
        ET.SubElement(id_fisc_cess, "IdCodice").text = cliente["piva"]
    if cliente.get("cf"):
        ET.SubElement(dati_anag_cess, "CodiceFiscale").text = cliente["cf"]
    anag_cess = ET.SubElement(dati_anag_cess, "Anagrafica")
    ET.SubElement(anag_cess, "Denominazione").text = cliente["denominazione"]

    sede_cess = ET.SubElement(cessionario, "Sede")
    ET.SubElement(sede_cess, "Indirizzo").text = cliente.get("indirizzo", "")
    ET.SubElement(sede_cess, "CAP").text = cliente.get("cap", "00000")
    ET.SubElement(sede_cess, "Comune").text = cliente.get("comune", "")
    ET.SubElement(sede_cess, "Provincia").text = cliente.get("provincia", "")
    ET.SubElement(sede_cess, "Nazione").text = "IT"

    # Body
    body = ET.SubElement(root, "FatturaElettronicaBody")

    # DatiGenerali
    dati_gen = ET.SubElement(body, "DatiGenerali")
    dati_gen_doc = ET.SubElement(dati_gen, "DatiGeneraliDocumento")
    ET.SubElement(dati_gen_doc, "TipoDocumento").text = "TD01"
    ET.SubElement(dati_gen_doc, "Divisa").text = "EUR"
    ET.SubElement(dati_gen_doc, "Data").text = data_fattura
    ET.SubElement(dati_gen_doc, "Numero").text = str(numero)
    ET.SubElement(dati_gen_doc, "ImportoTotaleDocumento").text = f"{totale_imponibile:.2f}"

    if bollo_applicato:
        dati_bollo = ET.SubElement(dati_gen_doc, "DatiBollo")
        ET.SubElement(dati_bollo, "BolloVirtuale").text = "SI"
        ET.SubElement(dati_bollo, "ImportoBollo").text = f"{bollo_importo:.2f}"

    causale = ET.SubElement(dati_gen_doc, "Causale")
    causale.text = settings.FATTURA["dicitura_obbligatoria"]

    # DatiBeniServizi
    dati_beni = ET.SubElement(body, "DatiBeniServizi")
    for i, prest in enumerate(prestazioni, 1):
        linea = ET.SubElement(dati_beni, "DettaglioLinee")
        ET.SubElement(linea, "NumeroLinea").text = str(i)
        ET.SubElement(linea, "Descrizione").text = prest["descrizione"]
        ET.SubElement(linea, "Quantita").text = f"{prest.get('quantita', 1):.2f}"
        ET.SubElement(linea, "PrezzoUnitario").text = f"{prest['importo']:.2f}"
        totale_linea = prest["importo"] * prest.get("quantita", 1)
        ET.SubElement(linea, "PrezzoTotale").text = f"{totale_linea:.2f}"
        ET.SubElement(linea, "AliquotaIVA").text = "0.00"
        ET.SubElement(linea, "Natura").text = settings.FATTURA["natura_operazione"]

    riepilogo = ET.SubElement(dati_beni, "DatiRiepilogo")
    ET.SubElement(riepilogo, "AliquotaIVA").text = "0.00"
    ET.SubElement(riepilogo, "Natura").text = settings.FATTURA["natura_operazione"]
    ET.SubElement(riepilogo, "ImponibileImporto").text = f"{totale_imponibile:.2f}"
    ET.SubElement(riepilogo, "Imposta").text = "0.00"
    ET.SubElement(riepilogo, "RiferimentoNormativo").text = settings.FATTURA["dicitura_obbligatoria"]

    # Salva XML
    xml_str = minidom.parseString(ET.tostring(root, encoding="unicode")).toprettyxml(indent="  ")
    fatture_dir = settings.DATA_FATTURE / str(anno)
    fatture_dir.mkdir(parents=True, exist_ok=True)

    xml_file = fatture_dir / f"fattura_{numero:04d}.xml"
    with open(xml_file, "w", encoding="utf-8") as f:
        f.write(xml_str)

    # Record JSON
    record = {
        "numero": numero,
        "progressivo": progressivo,
        "data": data_fattura,
        "cliente": cliente["denominazione"],
        "cliente_piva": cliente.get("piva", ""),
        "importo": totale_imponibile,
        "bollo_virtuale": bollo_applicato,
        "bollo_importo": bollo_importo,
        "stato_sdi": "da_inviare",
        "file_xml": str(xml_file),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    json_file = fatture_dir / f"fattura_{numero:04d}.json"
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)

    # Registra nel supervisor
    registra_fattura(anno, record)
    registra_evento(anno, "fattura_emessa",
                    f"Fattura {numero} a {cliente['denominazione']}: €{totale_imponibile}")

    logger.info("Fattura %d generata: %s — €%.2f (bollo: %s)",
                numero, cliente["denominazione"], totale_imponibile,
                "SI" if bollo_applicato else "NO")

    return record


if __name__ == "__main__":
    # Demo: genera una fattura di esempio
    cliente_demo = {
        "denominazione": "Acme S.r.l.",
        "piva": "01234567890",
        "codice_sdi": "ABCDEFG",
        "indirizzo": "Via Roma 1",
        "cap": "20100",
        "comune": "Milano",
        "provincia": "MI",
    }
    prestazioni_demo = [
        {"descrizione": "Sviluppo software controllo motori — fase 1", "importo": 2500.00, "quantita": 1},
        {"descrizione": "Prototipazione 3D componenti meccanici", "importo": 800.00, "quantita": 2},
    ]

    result = genera_xml_fattura(cliente_demo, prestazioni_demo)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\nFattura XML: {result['file_xml']}")
