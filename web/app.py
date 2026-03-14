#!/usr/bin/env python3
"""FiscalAI Web UI — interfaccia per test operativo.

Usage:
    pip install flask
    python3 web/app.py

Opens at http://localhost:5001
"""

from __future__ import annotations

import json
import sys
import uuid
import xml.etree.ElementTree as ET
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from pathlib import Path

# Ensure project root is on path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from flask import Flask, render_template, request, jsonify, redirect, url_for

from agents.agent0_wizard.models import ProfiloContribuente
from agents.agent0_wizard.simulator import simulate
from agents.agent3_calculator.calculator import calcola
from agents.agent3_calculator.models import ContribuenteInput
from agents.agent3b_validator.models import InputFiscale
from agents.agent3b_validator.validator import validate
from agents.agent6_scheduler.scheduler import genera_piano_annuale
from agents.agent8_invoicing.invoice_generator import crea_fattura, genera_xml, gestisci_esito_sdi
from agents.agent8_invoicing.models import DatiCliente, EsitoSDI
from agents.agent8_invoicing.numbering import prossimo_numero
from agents.supervisor.persistence import SupervisorStore

app = Flask(__name__, template_folder="templates", static_folder="static")
store = SupervisorStore()


def _load_ateco() -> dict:
    with open(_ROOT / "shared" / "ateco_coefficients.json") as f:
        data = json.load(f)
    return data["coefficients"]


ATECO_CODES = _load_ateco()


class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return str(o)
        if isinstance(o, date):
            return o.isoformat()
        return super().default(o)


# ─── ROUTES ───────────────────────────────────────────


@app.route("/")
def index():
    profiles = store.list_profiles()
    profile_data = []
    for pid in profiles:
        p = store.get_profile(pid)
        if p:
            ana = p.get("anagrafica", p)
            profile_data.append({
                "id": pid,
                "nome": f"{ana.get('nome', '')} {ana.get('cognome', '')}",
                "cf": ana.get("codice_fiscale", ""),
                "ateco": ana.get("ateco_principale", ""),
                "gestione": ana.get("gestione_inps", ""),
            })
    return render_template("index.html", profiles=profile_data)


@app.route("/nuova-piva", methods=["GET", "POST"])
def nuova_piva():
    if request.method == "GET":
        return render_template("nuova_piva.html", ateco_codes=ATECO_CODES)

    # POST — create profile
    form = request.form
    profilo = ProfiloContribuente(
        contribuente_id=str(uuid.uuid4()),
        nome=form["nome"],
        cognome=form["cognome"],
        codice_fiscale=form["codice_fiscale"].upper(),
        comune_residenza=form["comune_residenza"],
        data_apertura_piva=date.fromisoformat(form["data_apertura"]),
        primo_anno=form.get("primo_anno") == "on",
        ateco_principale=form["ateco_principale"],
        ateco_secondari=[a.strip() for a in form.get("ateco_secondari", "").split(",") if a.strip()],
        regime_agevolato=form.get("regime_agevolato") == "on",
        gestione_inps=form["gestione_inps"],
        riduzione_inps_35=form.get("riduzione_35") == "on",
        rivalsa_inps_4=form.get("rivalsa_4") == "on",
    )
    store.save_from_agent0(asdict(profilo))
    return redirect(url_for("profilo_detail", pid=profilo.contribuente_id))


@app.route("/profilo/<pid>")
def profilo_detail(pid):
    profile = store.get_profile(pid)
    if not profile:
        return "Profilo non trovato", 404
    ana = profile.get("anagrafica", profile)
    return render_template("profilo.html", profile=profile, ana=ana, pid=pid)


@app.route("/profilo/<pid>/delete", methods=["POST"])
def profilo_delete(pid):
    store.delete_profile(pid)
    return redirect(url_for("index"))


@app.route("/simulazione/<pid>", methods=["GET", "POST"])
def simulazione(pid):
    profile = store.get_profile(pid)
    if not profile:
        return "Profilo non trovato", 404
    ana = profile.get("anagrafica", profile)

    ricavi_input = {}
    anno = 2024
    sim_result = None
    validation = None
    piano = None

    if request.method == "POST":
        anno = int(request.form.get("anno", 2024))
        # Collect ricavi per ATECO
        ateco_p = ana.get("ateco_principale", "")
        ricavi_str = request.form.get("ricavi_principale", "0")
        ricavi_input[ateco_p] = Decimal(ricavi_str) if ricavi_str else Decimal("0")

        for sec in ana.get("ateco_secondari", []):
            r = request.form.get(f"ricavi_{sec}", "0")
            if r:
                ricavi_input[sec] = Decimal(r)

        # Build profilo for simulate
        profilo = ProfiloContribuente(
            contribuente_id=pid,
            nome=ana.get("nome", ""),
            cognome=ana.get("cognome", ""),
            codice_fiscale=ana.get("codice_fiscale", ""),
            comune_residenza=ana.get("comune_residenza", ""),
            data_apertura_piva=date.fromisoformat(ana.get("data_apertura_piva", "2024-01-01")),
            primo_anno=ana.get("primo_anno", True),
            ateco_principale=ateco_p,
            ateco_secondari=ana.get("ateco_secondari", []),
            regime_agevolato=ana.get("regime_agevolato", True),
            gestione_inps=ana.get("gestione_inps", "separata"),
            riduzione_inps_35=ana.get("riduzione_inps_35", False),
            rivalsa_inps_4=ana.get("rivalsa_inps_4", False),
        )

        sim_result = simulate(profilo=profilo, ricavi_per_ateco=ricavi_input, anno_fiscale=anno)

        # Validation via Agent3b
        a3_input = ContribuenteInput(
            contribuente_id=pid, anno_fiscale=anno,
            primo_anno=profilo.primo_anno,
            ateco_ricavi=ricavi_input,
            rivalsa_inps_applicata=Decimal("0"),
            regime_agevolato=profilo.regime_agevolato,
            gestione_inps=profilo.gestione_inps,
            riduzione_inps_35=profilo.riduzione_inps_35,
            contributi_inps_versati=Decimal("0"),
            imposta_anno_precedente=Decimal("0"),
            acconti_versati=Decimal("0"),
            crediti_precedenti=Decimal("0"),
        )
        a3_result = calcola(a3_input)
        a3_out = {
            "reddito_lordo": str(a3_result.reddito_lordo),
            "reddito_imponibile": str(a3_result.reddito_imponibile),
            "imposta_sostitutiva": str(a3_result.imposta_sostitutiva),
            "acconti_dovuti": str(a3_result.acconti_dovuti),
            "acconto_prima_rata": str(a3_result.acconto_prima_rata),
            "acconto_seconda_rata": str(a3_result.acconto_seconda_rata),
            "da_versare": str(a3_result.da_versare),
            "credito_anno_prossimo": str(a3_result.credito_anno_prossimo),
            "contributo_inps_calcolato": str(a3_result.contributo_inps_calcolato),
            "checksum": a3_result.checksum,
        }
        a3b_in = InputFiscale(
            id_contribuente=pid, anno=anno,
            is_primo_anno=profilo.primo_anno,
            ricavi_per_ateco=ricavi_input,
            rivalsa_4_percento=Decimal("0"),
            aliquota_agevolata=profilo.regime_agevolato,
            tipo_gestione_inps=profilo.gestione_inps,
            ha_riduzione_35=profilo.riduzione_inps_35,
            inps_gia_versati=Decimal("0"),
            imposta_anno_prima=Decimal("0"),
            acconti_gia_versati=Decimal("0"),
            crediti_da_prima=Decimal("0"),
        )
        validation = validate(a3b_in, a3_out)

        # F24 plan
        piano = genera_piano_annuale(
            contribuente_id=pid,
            contribuente_cf=profilo.codice_fiscale,
            contribuente_nome=profilo.nome,
            contribuente_cognome=profilo.cognome,
            anno_fiscale=anno,
            gestione_inps=profilo.gestione_inps,
            primo_anno=profilo.primo_anno,
            imposta_sostitutiva=sim_result.imposta_sostitutiva,
            contributo_inps=sim_result.contributo_inps,
            da_versare=sim_result.imposta_sostitutiva,
            acconto_prima_rata=sim_result.acconto_prima_rata if hasattr(sim_result, "acconto_prima_rata") else Decimal("0"),
            acconto_seconda_rata=sim_result.acconto_seconda_rata if hasattr(sim_result, "acconto_seconda_rata") else Decimal("0"),
        )

    return render_template("simulazione.html",
                           ana=ana, pid=pid, anno=anno,
                           ricavi_input=ricavi_input,
                           sim=sim_result, validation=validation, piano=piano)


@app.route("/fattura/<pid>", methods=["GET", "POST"])
def fattura(pid):
    profile = store.get_profile(pid)
    if not profile:
        return "Profilo non trovato", 404
    ana = profile.get("anagrafica", profile)

    result = None
    xml_str = None
    xml_preview = None

    if request.method == "POST":
        # Build cliente
        cliente = DatiCliente(
            denominazione=request.form["cliente_denominazione"],
            partita_iva=request.form.get("cliente_piva", ""),
            codice_fiscale=request.form.get("cliente_cf", ""),
            indirizzo=request.form.get("cliente_indirizzo", ""),
            cap=request.form.get("cliente_cap", ""),
            comune=request.form.get("cliente_comune", ""),
            provincia=request.form.get("cliente_provincia", ""),
            codice_sdi=request.form.get("cliente_sdi", "0000000"),
        )

        # Build linee
        linee = []
        desc_list = request.form.getlist("linea_desc")
        qty_list = request.form.getlist("linea_qty")
        price_list = request.form.getlist("linea_prezzo")
        for desc, qty, price in zip(desc_list, qty_list, price_list):
            if desc and price:
                linea = {"descrizione": desc, "prezzo_unitario": price}
                if qty and qty != "1":
                    linea["quantita"] = qty
                linee.append(linea)

        if linee:
            anno_fattura = int(request.form.get("anno_fattura", 2024))
            numero = prossimo_numero(anno_fattura)
            data_fattura = date.fromisoformat(request.form.get("data_fattura", str(date.today())))

            f = crea_fattura(
                numero=numero,
                data_fattura=data_fattura,
                cedente_piva=ana.get("partita_iva", "12345678901"),
                cedente_cf=ana.get("codice_fiscale", ""),
                cedente_denominazione=f"{ana.get('nome', '')} {ana.get('cognome', '')}",
                cliente=cliente,
                linee=linee,
                rivalsa_inps_4=ana.get("rivalsa_inps_4", False),
                gestione_inps=ana.get("gestione_inps", "separata"),
            )
            xml_str = genera_xml(f)
            xml_preview = xml_str[:3000]
            result = f

    return render_template("fattura.html", ana=ana, pid=pid,
                           result=result, xml_str=xml_str, xml_preview=xml_preview)


@app.route("/api/ateco")
def api_ateco():
    return jsonify(ATECO_CODES)


# ─── MAIN ─────────────────────────────────────────────

if __name__ == "__main__":
    print("\n  FiscalAI Web UI")
    print("  http://localhost:5001\n")
    app.run(host="0.0.0.0", port=5001, debug=True)
