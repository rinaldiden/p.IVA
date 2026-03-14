"""Tests for Agent8 Invoicing — 12 test cases."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal

import pytest

from agents.agent8_invoicing.invoice_generator import (
    crea_fattura,
    genera_xml,
    gestisci_esito_sdi,
)
from agents.agent8_invoicing.models import DatiCliente, EsitoSDI, Fattura
from agents.agent8_invoicing.numbering import prossimo_numero, ultimo_numero


@pytest.fixture
def cliente_base() -> DatiCliente:
    return DatiCliente(
        denominazione="Acme S.r.l.",
        partita_iva="09876543210",
        codice_fiscale="09876543210",
        indirizzo="Via Milano 42",
        cap="20100",
        comune="Milano",
        provincia="MI",
        codice_sdi="ABCDEFG",
    )


@pytest.fixture
def linee_base() -> list[dict]:
    return [
        {
            "descrizione": "Sviluppo applicazione web — marzo 2024",
            "quantita": "1",
            "prezzo_unitario": "3000.00",
        }
    ]


class TestCreaFattura:
    def test_fattura_base(self, cliente_base, linee_base):
        f = crea_fattura(
            numero="2024/001",
            data_fattura=date(2024, 3, 15),
            cedente_piva="12345678901",
            cedente_cf="RSSMRA85M41H501Z",
            cedente_denominazione="Maria Rossi",
            cliente=cliente_base,
            linee=linee_base,
        )
        assert f.imponibile == Decimal("3000.00")
        assert f.bollo_applicato is True
        assert f.importo_bollo == Decimal("2.00")
        assert f.rivalsa_inps_4 is False
        assert f.totale_documento == Decimal("3002.00")
        assert f.regime_fiscale == "RF19"

    def test_bollo_sotto_soglia(self, cliente_base):
        linee = [{"descrizione": "Consulenza breve", "prezzo_unitario": "50.00"}]
        f = crea_fattura(
            numero="2024/002",
            data_fattura=date(2024, 3, 15),
            cedente_piva="12345678901",
            cedente_cf="RSSMRA85M41H501Z",
            cedente_denominazione="Maria Rossi",
            cliente=cliente_base,
            linee=linee,
        )
        assert f.bollo_applicato is False
        assert f.importo_bollo == Decimal("0")
        assert f.totale_documento == Decimal("50.00")

    def test_rivalsa_inps_4(self, cliente_base, linee_base):
        f = crea_fattura(
            numero="2024/003",
            data_fattura=date(2024, 3, 15),
            cedente_piva="12345678901",
            cedente_cf="RSSMRA85M41H501Z",
            cedente_denominazione="Maria Rossi",
            cliente=cliente_base,
            linee=linee_base,
            rivalsa_inps_4=True,
            gestione_inps="separata",
        )
        assert f.rivalsa_inps_4 is True
        assert f.importo_rivalsa == Decimal("120.00")  # 3000 * 4%
        # Totale = imponibile + rivalsa + bollo
        assert f.totale_documento == Decimal("3122.00")
        # Ricavo netto (senza rivalsa, senza bollo)
        assert f.ricavo_netto == Decimal("3000.00")

    def test_rivalsa_non_applicata_artigiani(self, cliente_base, linee_base):
        """Rivalsa INPS 4% only for gestione separata."""
        f = crea_fattura(
            numero="2024/004",
            data_fattura=date(2024, 3, 15),
            cedente_piva="12345678901",
            cedente_cf="RSSMRA85M41H501Z",
            cedente_denominazione="Maria Rossi",
            cliente=cliente_base,
            linee=linee_base,
            rivalsa_inps_4=True,
            gestione_inps="artigiani",
        )
        assert f.rivalsa_inps_4 is False
        assert f.importo_rivalsa == Decimal("0")

    def test_multi_linee(self, cliente_base):
        linee = [
            {"descrizione": "Sviluppo frontend", "quantita": "2", "prezzo_unitario": "1500.00"},
            {"descrizione": "Consulenza UX", "prezzo_unitario": "800.00"},
        ]
        f = crea_fattura(
            numero="2024/005",
            data_fattura=date(2024, 4, 1),
            cedente_piva="12345678901",
            cedente_cf="RSSMRA85M41H501Z",
            cedente_denominazione="Maria Rossi",
            cliente=cliente_base,
            linee=linee,
        )
        assert f.imponibile == Decimal("3800.00")  # 3000 + 800
        assert len(f.linee) == 2

    def test_fattura_pa(self, linee_base):
        cliente_pa = DatiCliente(
            denominazione="Comune di Roma",
            codice_fiscale="02438750586",
            is_pa=True,
            codice_ufficio_pa="UFG4AB",
        )
        f = crea_fattura(
            numero="2024/006",
            data_fattura=date(2024, 3, 15),
            cedente_piva="12345678901",
            cedente_cf="RSSMRA85M41H501Z",
            cedente_denominazione="Maria Rossi",
            cliente=cliente_pa,
            linee=linee_base,
        )
        assert f.formato_trasmissione == "FPA12"


class TestGeneraXML:
    def test_xml_valid(self, cliente_base, linee_base):
        f = crea_fattura(
            numero="2024/001",
            data_fattura=date(2024, 3, 15),
            cedente_piva="12345678901",
            cedente_cf="RSSMRA85M41H501Z",
            cedente_denominazione="Maria Rossi",
            cliente=cliente_base,
            linee=linee_base,
        )
        xml = genera_xml(f)
        assert '<?xml version="1.0"' in xml
        assert "RF19" in xml
        assert "N2.2" in xml
        assert "BolloVirtuale" in xml
        assert "3002.00" in xml

    def test_xml_parseable(self, cliente_base, linee_base):
        f = crea_fattura(
            numero="2024/001",
            data_fattura=date(2024, 3, 15),
            cedente_piva="12345678901",
            cedente_cf="RSSMRA85M41H501Z",
            cedente_denominazione="Maria Rossi",
            cliente=cliente_base,
            linee=linee_base,
        )
        xml = genera_xml(f)
        # Must parse without errors
        root = ET.fromstring(xml)
        assert root.tag.endswith("FatturaElettronica")

    def test_xml_con_rivalsa(self, cliente_base, linee_base):
        f = crea_fattura(
            numero="2024/001",
            data_fattura=date(2024, 3, 15),
            cedente_piva="12345678901",
            cedente_cf="RSSMRA85M41H501Z",
            cedente_denominazione="Maria Rossi",
            cliente=cliente_base,
            linee=linee_base,
            rivalsa_inps_4=True,
            gestione_inps="separata",
        )
        xml = genera_xml(f)
        assert "Contributo INPS 4%" in xml
        assert "120.00" in xml


class TestEsitoSDI:
    def test_rc_consegnata(self):
        esito = gestisci_esito_sdi(EsitoSDI(
            fattura_numero="2024/001", codice="RC",
        ))
        assert esito.richiede_intervento is False
        assert "consegnata" in esito.descrizione

    def test_ns_scartata(self):
        esito = gestisci_esito_sdi(EsitoSDI(
            fattura_numero="2024/001", codice="NS", codice_errore="00200",
        ))
        assert esito.richiede_intervento is True
        assert "scartata" in esito.descrizione.lower()

    def test_mc_mancata_consegna(self):
        esito = gestisci_esito_sdi(EsitoSDI(
            fattura_numero="2024/001", codice="MC",
        ))
        assert esito.richiede_intervento is False
        assert "cassetto fiscale" in esito.descrizione


class TestNumerazione:
    def test_progressiva(self, tmp_path, monkeypatch):
        import agents.agent8_invoicing.numbering as num
        monkeypatch.setattr(num, "_DATA_DIR", tmp_path)
        monkeypatch.setattr(num, "_COUNTER_FILE", tmp_path / "invoice_counter.json")

        n1 = prossimo_numero(2024)
        n2 = prossimo_numero(2024)
        n3 = prossimo_numero(2024)
        assert n1 == "2024/001"
        assert n2 == "2024/002"
        assert n3 == "2024/003"
        assert ultimo_numero(2024) == 3

    def test_anno_diverso_riparte(self, tmp_path, monkeypatch):
        import agents.agent8_invoicing.numbering as num
        monkeypatch.setattr(num, "_DATA_DIR", tmp_path)
        monkeypatch.setattr(num, "_COUNTER_FILE", tmp_path / "invoice_counter.json")

        prossimo_numero(2024)
        prossimo_numero(2024)
        n = prossimo_numero(2025)
        assert n == "2025/001"
