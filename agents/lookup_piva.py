"""
Lookup P.IVA — Verifica e ricerca dati aziendali

Due direzioni:
1. P.IVA → ragione sociale, indirizzo, stato (Agenzia Entrate)
2. Ragione sociale → P.IVA, indirizzo (Registro Imprese)

Fonti:
- Agenzia delle Entrate: telematici.agenziaentrate.gov.it/VerificaPIVA
- VIES (EU): ec.europa.eu/taxation_customs/vies
- Registro Imprese: registroimprese.it

Usato da Agent8 per autocompilare i dati cliente in fattura.
"""

import json
import logging
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import requests

logger = logging.getLogger("lookup_piva")

# Cache locale per non ripetere lookup
CACHE_DIR = BASE_DIR / "data" / "clienti"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_file(piva: str) -> Path:
    return CACHE_DIR / f"{piva}.json"


def _salva_cache(piva: str, dati: dict):
    with open(_cache_file(piva), "w", encoding="utf-8") as f:
        json.dump(dati, f, indent=2, ensure_ascii=False)


def _carica_cache(piva: str) -> dict | None:
    f = _cache_file(piva)
    if f.exists():
        with open(f, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return None


def valida_formato_piva(piva: str) -> bool:
    """Verifica formato P.IVA italiana: 11 cifre."""
    piva = piva.strip().replace(" ", "")
    return bool(re.match(r"^\d{11}$", piva))


def lookup_piva_ade(piva: str) -> dict:
    """
    Cerca P.IVA sull'Agenzia delle Entrate.
    Usa il servizio web pubblico di verifica.
    """
    piva = piva.strip().replace(" ", "")

    # Check cache
    cached = _carica_cache(piva)
    if cached:
        logger.info("Cache hit per P.IVA %s", piva)
        return cached

    if not valida_formato_piva(piva):
        return {"errore": "Formato P.IVA non valido (servono 11 cifre)", "piva": piva}

    try:
        # Il servizio AdE accetta POST con il numero P.IVA
        url = "https://telematici.agenziaentrate.gov.it/VerificaPIVA/ajax/VerificaAction.do"
        resp = requests.post(url, data={
            "action": "verifica",
            "piva": piva,
        }, headers={
            "User-Agent": "FiscalAI/1.0",
            "Referer": "https://telematici.agenziaentrate.gov.it/VerificaPIVA/",
        }, timeout=10)

        if resp.status_code == 200:
            text = resp.text
            # Il servizio restituisce HTML/testo con i dati
            dati = _parse_risposta_ade(text, piva)
            if dati and not dati.get("errore"):
                _salva_cache(piva, dati)
            return dati
        else:
            logger.warning("AdE risposta %d per P.IVA %s", resp.status_code, piva)
    except requests.RequestException as e:
        logger.warning("Errore connessione AdE: %s", e)

    return {"errore": "Servizio non raggiungibile", "piva": piva, "fonte": "ade"}


def _parse_risposta_ade(html: str, piva: str) -> dict:
    """Estrae dati dalla risposta HTML dell'AdE."""
    # Fallback: restituisci i dati base
    risultato = {
        "piva": piva,
        "fonte": "ade",
        "stato": "non_verificata",
        "denominazione": "",
        "indirizzo": "",
        "comune": "",
        "provincia": "",
        "cap": "",
    }

    # Cerca pattern comuni nella risposta
    if "ATTIVA" in html.upper():
        risultato["stato"] = "attiva"
    elif "CESSATA" in html.upper():
        risultato["stato"] = "cessata"

    # Cerca denominazione
    den_match = re.search(r"Denominazione[:\s]*</[^>]+>\s*<[^>]+>([^<]+)", html)
    if den_match:
        risultato["denominazione"] = den_match.group(1).strip()

    # Cerca indirizzo
    ind_match = re.search(r"Indirizzo[:\s]*</[^>]+>\s*<[^>]+>([^<]+)", html)
    if ind_match:
        risultato["indirizzo"] = ind_match.group(1).strip()

    return risultato


def lookup_piva_vies(piva: str, paese: str = "IT") -> dict:
    """
    Verifica P.IVA tramite VIES (EU).
    Usa il servizio SOAP della Commissione Europea.
    """
    piva = piva.strip().replace(" ", "")

    try:
        soap_body = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
  xmlns:urn="urn:ec.europa.eu:taxud:vies:services:checkVat:types">
  <soapenv:Body>
    <urn:checkVat>
      <urn:countryCode>{paese}</urn:countryCode>
      <urn:vatNumber>{piva}</urn:vatNumber>
    </urn:checkVat>
  </soapenv:Body>
</soapenv:Envelope>"""

        resp = requests.post(
            "https://ec.europa.eu/taxation_customs/vies/services/checkVatService",
            data=soap_body,
            headers={"Content-Type": "text/xml; charset=utf-8"},
            timeout=10,
        )

        if resp.status_code == 200:
            text = resp.text
            valida = "<valid>true</valid>" in text.lower()
            nome = ""
            indirizzo = ""

            nome_match = re.search(r"<name>([^<]*)</name>", text)
            if nome_match:
                nome = nome_match.group(1).strip()

            addr_match = re.search(r"<address>([^<]*)</address>", text)
            if addr_match:
                indirizzo = addr_match.group(1).strip()

            dati = {
                "piva": piva,
                "paese": paese,
                "fonte": "vies",
                "valida": valida,
                "denominazione": nome,
                "indirizzo": indirizzo,
                "stato": "attiva" if valida else "non_valida",
            }

            if valida and nome:
                _salva_cache(piva, dati)

            return dati
    except requests.RequestException as e:
        logger.warning("Errore VIES: %s", e)

    return {"errore": "VIES non raggiungibile", "piva": piva}


def cerca_per_nome(ragione_sociale: str) -> list[dict]:
    """
    Cerca aziende per ragione sociale.
    Usa registroimprese.it come fonte.
    Restituisce lista di risultati con P.IVA.
    """
    # Check cache locale — cerca match parziale nei file esistenti
    risultati = []
    nome_lower = ragione_sociale.lower()

    for f in CACHE_DIR.glob("*.json"):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                dati = json.load(fh)
            if nome_lower in dati.get("denominazione", "").lower():
                risultati.append(dati)
        except (json.JSONDecodeError, KeyError):
            continue

    if risultati:
        logger.info("Trovati %d risultati in cache per '%s'", len(risultati), ragione_sociale)
        return risultati

    # Tentativo via Registro Imprese (ricerca web)
    try:
        url = "https://www.registroimprese.it/api/companies/search"
        resp = requests.get(url, params={
            "q": ragione_sociale,
            "limit": 5,
        }, headers={
            "User-Agent": "FiscalAI/1.0",
        }, timeout=10)

        if resp.status_code == 200:
            data = resp.json()
            for item in data.get("results", []):
                risultati.append({
                    "denominazione": item.get("name", ""),
                    "piva": item.get("vatNumber", ""),
                    "cf": item.get("fiscalCode", ""),
                    "indirizzo": item.get("address", ""),
                    "comune": item.get("city", ""),
                    "provincia": item.get("province", ""),
                    "fonte": "registro_imprese",
                })
    except Exception as e:
        logger.info("Registro Imprese non disponibile: %s", e)

    if not risultati:
        logger.info("Nessun risultato online per '%s' — usa dati manuali", ragione_sociale)

    return risultati


def lookup(query: str) -> dict | list:
    """
    Entrypoint unico. Accetta P.IVA (11 cifre) o ragione sociale.
    """
    query = query.strip()

    # Se sono 11 cifre, e' una P.IVA
    if re.match(r"^\d{11}$", query):
        # Prima VIES (piu' affidabile), poi AdE
        risultato = lookup_piva_vies(query)
        if risultato.get("valida") and risultato.get("denominazione"):
            return risultato
        return lookup_piva_ade(query)

    # Altrimenti cerca per nome
    return cerca_per_nome(query)


def compila_cliente(piva_o_nome: str) -> dict:
    """
    Dato P.IVA o ragione sociale, restituisce un dict cliente
    pronto per Agent8 genera_xml_fattura().
    """
    risultato = lookup(piva_o_nome)

    if isinstance(risultato, list):
        if not risultato:
            return {"errore": f"Nessun risultato per '{piva_o_nome}'"}
        risultato = risultato[0]  # prendi il primo match

    # Parsing indirizzo VIES (formato: "VIA ROMA 1\n20100 MILANO MI")
    indirizzo = risultato.get("indirizzo", "")
    parti = indirizzo.split("\n") if "\n" in indirizzo else [indirizzo]
    via = parti[0] if parti else ""
    cap = ""
    comune = risultato.get("comune", "")
    provincia = risultato.get("provincia", "")

    if len(parti) > 1:
        match = re.match(r"(\d{5})\s+(.+?)(?:\s+([A-Z]{2}))?$", parti[-1].strip())
        if match:
            cap = match.group(1)
            comune = match.group(2)
            provincia = match.group(3) or ""

    return {
        "denominazione": risultato.get("denominazione", piva_o_nome),
        "piva": risultato.get("piva", ""),
        "cf": risultato.get("cf", ""),
        "codice_sdi": "0000000",  # default, l'utente puo' aggiornare
        "indirizzo": via,
        "cap": cap or "00000",
        "comune": comune,
        "provincia": provincia,
        "fonte": risultato.get("fonte", "manuale"),
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python lookup_piva.py <P.IVA o ragione sociale>")
        sys.exit(1)

    query = " ".join(sys.argv[1:])
    print(f"Cerco: {query}")
    risultato = lookup(query)
    print(json.dumps(risultato, indent=2, ensure_ascii=False))
    print("\n--- Cliente pronto per fattura ---")
    cliente = compila_cliente(query)
    print(json.dumps(cliente, indent=2, ensure_ascii=False))
