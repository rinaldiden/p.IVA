"""Tests for Agent6 Payment Scheduler — 14 test cases."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from agents.agent6_scheduler.models import F24, F24Entry, PianoAnnuale, ScadenzaFiscale
from agents.agent6_scheduler.scheduler import genera_piano_annuale


class TestF24Model:
    def test_calcola_totali(self):
        righe = [
            F24Entry(sezione="erario", importo_debito=Decimal("1000"), importo_credito=Decimal("200")),
            F24Entry(sezione="erario", importo_debito=Decimal("500"), importo_credito=Decimal("0")),
        ]
        f24 = F24(
            contribuente_cf="RSSMRA85M41H501Z",
            contribuente_nome="Maria",
            contribuente_cognome="Rossi",
            data_versamento=date(2025, 6, 30),
            scadenza_id="test",
            anno_fiscale=2024,
            righe=righe,
        )
        f24.calcola_totali()
        assert f24.totale_debito == Decimal("1500")
        assert f24.totale_credito == Decimal("200")
        assert f24.saldo == Decimal("1300")


class TestPianoSeparata:
    """Piano annuale for gestione separata (consulente forfettario)."""

    def test_primo_anno_solo_saldo(self):
        piano = genera_piano_annuale(
            contribuente_id="test-001",
            contribuente_cf="RSSMRA85M41H501Z",
            contribuente_nome="Maria",
            contribuente_cognome="Rossi",
            anno_fiscale=2024,
            gestione_inps="separata",
            primo_anno=True,
            imposta_sostitutiva=Decimal("1500.00"),
            contributo_inps=Decimal("3960.00"),
            da_versare=Decimal("1500.00"),
            marche_bollo_totale=Decimal("20.00"),
        )
        ids = [s.id for s in piano.scadenze]
        # Primo anno: no acconti, only saldo imposta + saldo INPS + bollo
        assert "saldo_imposta_2024" in ids
        assert "saldo_inps_gs_2024" in ids
        assert "bollo_2024" in ids
        assert "acconto1_imposta_2024" not in ids
        assert "acconto2_imposta_2024" not in ids
        # Saldo goes to next year for primo anno
        saldo = next(s for s in piano.scadenze if s.id == "saldo_imposta_2024")
        assert saldo.data == date(2025, 6, 30)

    def test_secondo_anno_con_acconti(self):
        piano = genera_piano_annuale(
            contribuente_id="test-002",
            contribuente_cf="RSSMRA85M41H501Z",
            contribuente_nome="Maria",
            contribuente_cognome="Rossi",
            anno_fiscale=2024,
            gestione_inps="separata",
            primo_anno=False,
            imposta_sostitutiva=Decimal("2000.00"),
            contributo_inps=Decimal("5000.00"),
            da_versare=Decimal("2000.00"),
            acconto_prima_rata=Decimal("800.00"),
            acconto_seconda_rata=Decimal("1200.00"),
            marche_bollo_totale=Decimal("10.00"),
        )
        ids = [s.id for s in piano.scadenze]
        assert "acconto1_imposta_2024" in ids
        assert "acconto2_imposta_2024" in ids
        acc1 = next(s for s in piano.scadenze if s.id == "acconto1_imposta_2024")
        acc2 = next(s for s in piano.scadenze if s.id == "acconto2_imposta_2024")
        assert acc1.codice_tributo == "1790"
        assert acc2.codice_tributo == "1791"
        assert acc1.data == date(2024, 6, 30)
        assert acc2.data == date(2024, 11, 30)

    def test_compensazione_crediti(self):
        piano = genera_piano_annuale(
            contribuente_id="test-003",
            contribuente_cf="RSSMRA85M41H501Z",
            contribuente_nome="Maria",
            contribuente_cognome="Rossi",
            anno_fiscale=2024,
            gestione_inps="separata",
            primo_anno=True,
            imposta_sostitutiva=Decimal("1000.00"),
            contributo_inps=Decimal("2000.00"),
            da_versare=Decimal("1000.00"),
            crediti_precedenti=Decimal("300.00"),
        )
        assert piano.crediti_compensati == Decimal("300.00")
        saldo = next(s for s in piano.scadenze if s.id == "saldo_imposta_2024")
        assert saldo.importo == Decimal("700.00")

    def test_inps_separata_acconti(self):
        piano = genera_piano_annuale(
            contribuente_id="test-004",
            contribuente_cf="RSSMRA85M41H501Z",
            contribuente_nome="Maria",
            contribuente_cognome="Rossi",
            anno_fiscale=2024,
            gestione_inps="separata",
            primo_anno=False,
            imposta_sostitutiva=Decimal("1000.00"),
            contributo_inps=Decimal("5000.00"),
            da_versare=Decimal("1000.00"),
        )
        ids = [s.id for s in piano.scadenze]
        assert "acconto1_inps_gs_2024" in ids
        assert "acconto2_inps_gs_2024" in ids
        acc1 = next(s for s in piano.scadenze if s.id == "acconto1_inps_gs_2024")
        acc2 = next(s for s in piano.scadenze if s.id == "acconto2_inps_gs_2024")
        assert acc1.importo == Decimal("2000.00")  # 5000 * 40%
        assert acc2.importo == Decimal("3000.00")  # 5000 * 60%

    def test_scadenze_ordinate(self):
        piano = genera_piano_annuale(
            contribuente_id="test-005",
            contribuente_cf="RSSMRA85M41H501Z",
            contribuente_nome="Maria",
            contribuente_cognome="Rossi",
            anno_fiscale=2024,
            gestione_inps="separata",
            primo_anno=False,
            imposta_sostitutiva=Decimal("2000.00"),
            contributo_inps=Decimal("5000.00"),
            da_versare=Decimal("2000.00"),
            acconto_prima_rata=Decimal("800.00"),
            acconto_seconda_rata=Decimal("1200.00"),
            marche_bollo_totale=Decimal("20.00"),
        )
        date_list = [s.data for s in piano.scadenze]
        assert date_list == sorted(date_list)


class TestPianoArtigiani:
    """Piano annuale for gestione artigiani/commercianti."""

    def test_rate_fisse_trimestrali(self):
        piano = genera_piano_annuale(
            contribuente_id="test-art-001",
            contribuente_cf="VRDLGI80A01H501X",
            contribuente_nome="Luigi",
            contribuente_cognome="Verdi",
            anno_fiscale=2024,
            gestione_inps="artigiani",
            primo_anno=False,
            imposta_sostitutiva=Decimal("3000.00"),
            contributo_inps=Decimal("5000.00"),
            da_versare=Decimal("3000.00"),
            contributo_fisso_trimestrale=Decimal("1050.00"),
        )
        fissi = [s for s in piano.scadenze if "rata fissa" in s.descrizione]
        assert len(fissi) == 4
        assert all(s.importo == Decimal("1050.00") for s in fissi)
        assert all(s.causale == "AF" for s in fissi)

    def test_eccedenza_minimale(self):
        piano = genera_piano_annuale(
            contribuente_id="test-art-002",
            contribuente_cf="VRDLGI80A01H501X",
            contribuente_nome="Luigi",
            contribuente_cognome="Verdi",
            anno_fiscale=2024,
            gestione_inps="artigiani",
            primo_anno=False,
            imposta_sostitutiva=Decimal("2000.00"),
            contributo_inps=Decimal("6000.00"),
            da_versare=Decimal("2000.00"),
            contributo_fisso_trimestrale=Decimal("1000.00"),
        )
        ecc = [s for s in piano.scadenze if "eccedenza" in s.descrizione]
        assert len(ecc) == 1
        assert ecc[0].importo == Decimal("2000.00")  # 6000 - 4*1000
        assert ecc[0].causale == "APR"

    def test_commercianti_causali(self):
        piano = genera_piano_annuale(
            contribuente_id="test-com-001",
            contribuente_cf="VRDLGI80A01H501X",
            contribuente_nome="Luigi",
            contribuente_cognome="Verdi",
            anno_fiscale=2024,
            gestione_inps="commercianti",
            primo_anno=False,
            imposta_sostitutiva=Decimal("1000.00"),
            contributo_inps=Decimal("5000.00"),
            da_versare=Decimal("1000.00"),
            contributo_fisso_trimestrale=Decimal("1000.00"),
        )
        fissi = [s for s in piano.scadenze if "rata fissa" in s.descrizione]
        assert all(s.causale == "CF" for s in fissi)
        ecc = [s for s in piano.scadenze if "eccedenza" in s.descrizione]
        assert ecc[0].causale == "CPR"

    def test_nessuna_eccedenza_se_fisso_copre(self):
        piano = genera_piano_annuale(
            contribuente_id="test-art-003",
            contribuente_cf="VRDLGI80A01H501X",
            contribuente_nome="Luigi",
            contribuente_cognome="Verdi",
            anno_fiscale=2024,
            gestione_inps="artigiani",
            primo_anno=False,
            imposta_sostitutiva=Decimal("1000.00"),
            contributo_inps=Decimal("4000.00"),
            da_versare=Decimal("1000.00"),
            contributo_fisso_trimestrale=Decimal("1000.00"),
        )
        ecc = [s for s in piano.scadenze if "eccedenza" in s.descrizione]
        assert len(ecc) == 0


class TestPianoBollo:
    def test_bollo_presente(self):
        piano = genera_piano_annuale(
            contribuente_id="test-bollo",
            contribuente_cf="RSSMRA85M41H501Z",
            contribuente_nome="Maria",
            contribuente_cognome="Rossi",
            anno_fiscale=2024,
            gestione_inps="separata",
            primo_anno=True,
            imposta_sostitutiva=Decimal("500"),
            contributo_inps=Decimal("1000"),
            da_versare=Decimal("500"),
            marche_bollo_totale=Decimal("30.00"),
        )
        bollo = next(s for s in piano.scadenze if s.id == "bollo_2024")
        assert bollo.importo == Decimal("30.00")
        assert bollo.codice_tributo == "2501"
        assert bollo.data == date(2025, 1, 30)

    def test_no_bollo_se_zero(self):
        piano = genera_piano_annuale(
            contribuente_id="test-nobollo",
            contribuente_cf="RSSMRA85M41H501Z",
            contribuente_nome="Maria",
            contribuente_cognome="Rossi",
            anno_fiscale=2024,
            gestione_inps="separata",
            primo_anno=True,
            imposta_sostitutiva=Decimal("500"),
            contributo_inps=Decimal("1000"),
            da_versare=Decimal("500"),
            marche_bollo_totale=Decimal("0"),
        )
        bollo = [s for s in piano.scadenze if "bollo" in s.id]
        assert len(bollo) == 0
