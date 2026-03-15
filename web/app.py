#!/usr/bin/env python3
"""FiscalAI Web UI — interfaccia per gestione P.IVA forfettaria.

Usage:
    pip install flask
    python3 web/app.py

Opens at http://127.0.0.1:5001
"""

from __future__ import annotations

import json
import sys
import uuid
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from pathlib import Path

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
from agents.agent8_invoicing.invoice_generator import crea_fattura, genera_xml
from agents.agent8_invoicing.models import DatiCliente
from agents.agent8_invoicing.numbering import prossimo_numero
from agents.supervisor.persistence import SupervisorStore

app = Flask(__name__, template_folder="templates", static_folder="static")
store = SupervisorStore()


def _load_ateco() -> dict:
    with open(_ROOT / "shared" / "ateco_coefficients.json") as f:
        data = json.load(f)
    return data["coefficients"]


ATECO_CODES = _load_ateco()


# ─── HELPERS ──────────────────────────────────────────

def _get_ana(pid: str) -> tuple[dict | None, dict | None]:
    """Get profile and anagrafica, or (None, None)."""
    profile = store.get_profile(pid)
    if not profile:
        return None, None
    return profile, profile.get("anagrafica", profile)


def _profile_summary(pid: str) -> dict:
    """Build a summary dict for a profile."""
    p = store.get_profile(pid)
    if not p:
        return {}
    ana = p.get("anagrafica", p)
    return {
        "id": pid,
        "nome": f"{ana.get('nome', '')} {ana.get('cognome', '')}",
        "cf": ana.get("codice_fiscale", ""),
        "ateco": ana.get("ateco_principale", ""),
        "gestione": ana.get("gestione_inps", ""),
    }


# ─── LANDING ──────────────────────────────────────────

@app.route("/")
def index():
    profiles = store.list_profiles()
    profile_data = [_profile_summary(pid) for pid in profiles]
    profile_data = [p for p in profile_data if p]
    return render_template("landing.html", profiles=profile_data)


# ─── WIZARD ───────────────────────────────────────────

@app.route("/wizard")
def wizard():
    return render_template("wizard.html")


@app.route("/wizard/salva", methods=["POST"])
def wizard_salva():
    form = request.form
    primo_anno = form.get("primo_anno") == "1"

    # Map gestione from wizard
    gestione = form.get("gestione_inps", "separata")

    profilo = ProfiloContribuente(
        contribuente_id=str(uuid.uuid4()),
        nome=form.get("nome", ""),
        cognome=form.get("cognome", ""),
        codice_fiscale=form.get("codice_fiscale", "").upper(),
        comune_residenza="",
        data_apertura_piva=date.today(),
        primo_anno=primo_anno,
        ateco_principale=form.get("ateco_principale", "62.01.00"),
        ateco_secondari=[],
        regime_agevolato=primo_anno,  # 5% if primo anno
        gestione_inps=gestione,
        riduzione_inps_35=False,
        rivalsa_inps_4=form.get("rivalsa_inps_4") == "1",
    )
    store.save_from_agent0(asdict(profilo))
    return redirect(url_for("apertura", pid=profilo.contribuente_id))


# ─── APERTURA ─────────────────────────────────────────

@app.route("/apertura/<pid>")
def apertura(pid):
    profile, ana = _get_ana(pid)
    if not profile:
        return redirect(url_for("index"))
    gestione = ana.get("gestione_inps", "separata")
    return render_template("apertura.html", pid=pid, gestione=gestione)


# ─── DASHBOARD ────────────────────────────────────────

@app.route("/dashboard/<pid>")
def dashboard(pid):
    profile, ana = _get_ana(pid)
    if not profile:
        return redirect(url_for("index"))

    # Check if first visit (welcome)
    welcome = request.args.get("welcome") or (
        not profile.get("_visited_dashboard")
    )
    if welcome and not profile.get("_visited_dashboard"):
        profile["_visited_dashboard"] = True
        store.save_profile(pid, profile)

    # Fatture from profile (stored when emitted)
    fatture = profile.get("fatture", [])
    n_fatture = len(fatture)
    fatturato_anno = sum(float(f.get("ricavo_netto", 0)) for f in fatture)

    # Simulation for accantonamento
    anno = date.today().year
    da_accantonare_mese = Decimal("0")
    scadenze = []
    prossima = None

    if fatturato_anno > 0 or n_fatture > 0:
        try:
            ateco_p = ana.get("ateco_principale", "62.01.00")
            ricavi = {ateco_p: Decimal(str(fatturato_anno))}
            profilo_obj = _build_profilo(pid, ana)
            sim = simulate(profilo=profilo_obj, ricavi_per_ateco=ricavi, anno_fiscale=2024)
            da_accantonare_mese = sim.rata_mensile_da_accantonare
            scadenze = [
                {"data": s.data, "descrizione": s.descrizione, "importo": s.importo}
                for s in sim.scadenze_anno_corrente
            ]
        except Exception:
            pass

    if scadenze:
        prossima = scadenze[0]

    return render_template("dashboard.html",
                           pid=pid, ana=ana, welcome=welcome,
                           fatturato_anno=fatturato_anno,
                           da_accantonare_mese=da_accantonare_mese,
                           prossima_scadenza=prossima,
                           n_fatture=n_fatture,
                           fatture=fatture[-10:],
                           scadenze=scadenze,
                           anno=anno)


# ─── PROFILO ──────────────────────────────────────────

@app.route("/profilo/<pid>")
def profilo_detail(pid):
    profile, ana = _get_ana(pid)
    if not profile:
        return redirect(url_for("index"))
    return render_template("profilo.html", profile=profile, ana=ana, pid=pid)


@app.route("/profilo/<pid>/delete", methods=["POST"])
def profilo_delete(pid):
    store.delete_profile(pid)
    return redirect(url_for("index"))


# ─── SIMULAZIONE ──────────────────────────────────────

@app.route("/simulazione/<pid>", methods=["GET", "POST"])
def simulazione(pid):
    profile, ana = _get_ana(pid)
    if not profile:
        return redirect(url_for("index"))

    ricavi_input = {}
    anno = 2024
    sim_result = None
    validation = None
    piano = None

    if request.method == "POST":
        anno = int(request.form.get("anno", 2024))
        ateco_p = ana.get("ateco_principale", "")
        ricavi_str = request.form.get("ricavi_principale", "0")
        ricavi_input[ateco_p] = Decimal(ricavi_str) if ricavi_str else Decimal("0")

        for sec in ana.get("ateco_secondari", []):
            r = request.form.get(f"ricavi_{sec}", "0")
            if r:
                ricavi_input[sec] = Decimal(r)

        profilo_obj = _build_profilo(pid, ana)
        sim_result = simulate(profilo=profilo_obj, ricavi_per_ateco=ricavi_input, anno_fiscale=anno)

        # Validation
        a3_input = ContribuenteInput(
            contribuente_id=pid, anno_fiscale=anno,
            primo_anno=profilo_obj.primo_anno,
            ateco_ricavi=ricavi_input,
            rivalsa_inps_applicata=Decimal("0"),
            regime_agevolato=profilo_obj.regime_agevolato,
            gestione_inps=profilo_obj.gestione_inps,
            riduzione_inps_35=profilo_obj.riduzione_inps_35,
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
            is_primo_anno=profilo_obj.primo_anno,
            ricavi_per_ateco=ricavi_input,
            rivalsa_4_percento=Decimal("0"),
            aliquota_agevolata=profilo_obj.regime_agevolato,
            tipo_gestione_inps=profilo_obj.gestione_inps,
            ha_riduzione_35=profilo_obj.riduzione_inps_35,
            inps_gia_versati=Decimal("0"),
            imposta_anno_prima=Decimal("0"),
            acconti_gia_versati=Decimal("0"),
            crediti_da_prima=Decimal("0"),
        )
        validation = validate(a3b_in, a3_out)

        # F24 plan
        piano = genera_piano_annuale(
            contribuente_id=pid,
            contribuente_cf=profilo_obj.codice_fiscale,
            contribuente_nome=profilo_obj.nome,
            contribuente_cognome=profilo_obj.cognome,
            anno_fiscale=anno,
            gestione_inps=profilo_obj.gestione_inps,
            primo_anno=profilo_obj.primo_anno,
            imposta_sostitutiva=sim_result.imposta_sostitutiva,
            contributo_inps=sim_result.contributo_inps,
            da_versare=sim_result.imposta_sostitutiva,
            acconto_prima_rata=getattr(sim_result, "acconto_prima_rata", Decimal("0")),
            acconto_seconda_rata=getattr(sim_result, "acconto_seconda_rata", Decimal("0")),
        )

    return render_template("simulazione.html",
                           ana=ana, pid=pid, anno=anno,
                           ricavi_input=ricavi_input,
                           sim=sim_result, validation=validation, piano=piano)


# ─── FATTURA ──────────────────────────────────────────

@app.route("/fattura/<pid>", methods=["GET", "POST"])
def fattura(pid):
    profile, ana = _get_ana(pid)
    if not profile:
        return redirect(url_for("index"))

    result = None
    xml_str = None
    xml_preview = None

    if request.method == "POST":
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

        linee = []
        for desc, qty, price in zip(
            request.form.getlist("linea_desc"),
            request.form.getlist("linea_qty"),
            request.form.getlist("linea_prezzo"),
        ):
            if desc and price:
                linea = {"descrizione": desc, "prezzo_unitario": price}
                if qty and qty != "1":
                    linea["quantita"] = qty
                linee.append(linea)

        if linee:
            anno_fattura = int(request.form.get("anno_fattura", 2024))
            numero = prossimo_numero(anno_fattura)
            data_fattura = date.fromisoformat(request.form.get("data_fattura", str(date.today())))

            cedente_nome = f"{ana.get('nome', '')} {ana.get('cognome', '')}"
            f = crea_fattura(
                numero=numero,
                data_fattura=data_fattura,
                cedente_piva=ana.get("partita_iva", "12345678901"),
                cedente_cf=ana.get("codice_fiscale", ""),
                cedente_denominazione=cedente_nome,
                cliente=cliente,
                linee=linee,
                rivalsa_inps_4=ana.get("rivalsa_inps_4", False),
                gestione_inps=ana.get("gestione_inps", "separata"),
            )
            xml_str = genera_xml(f)
            xml_preview = xml_str[:3000]
            result = f

            # Store fattura in profile
            if "fatture" not in profile:
                profile["fatture"] = []
            profile["fatture"].append({
                "numero": f.numero,
                "data": str(f.data),
                "cliente": cliente.denominazione,
                "importo": str(f.totale_documento),
                "ricavo_netto": str(f.ricavo_netto),
            })
            store.save_profile(pid, profile)

    return render_template("fattura.html", ana=ana, pid=pid,
                           result=result, xml_str=xml_str, xml_preview=xml_preview)


# ─── API ──────────────────────────────────────────────

@app.route("/api/ateco")
def api_ateco():
    return jsonify(ATECO_CODES)


@app.route("/api/suggerisci-ateco")
def api_suggerisci_ateco():
    """Suggest ATECO codes based on text description."""
    query = request.args.get("q", "").strip().lower()
    if not query:
        return jsonify([])

    # Local keyword matching (fast, no Claude needed)
    results = []
    query_words = [w for w in query.split() if len(w) >= 3]
    for code, info in ATECO_CODES.items():
        desc = info["description"].lower()
        keywords = [k.lower() for k in info.get("keywords", [])]
        coeff = info["coefficient"]
        score = 0

        # Full query match in keywords (highest priority)
        for kw in keywords:
            if query in kw or kw in query:
                score += 20
                break

        # Word-level matching
        for word in query_words:
            if word in desc:
                score += 10
            for kw in keywords:
                if word in kw:
                    score += 8
                    break
            # Prefix match (e.g. "fotograf" matches "fotografo")
            if len(word) >= 4:
                prefix = word[:4]
                if prefix in desc:
                    score += 3
                elif any(prefix in kw for kw in keywords):
                    score += 3

        if score > 0:
            results.append({
                "codice": code,
                "descrizione": info["description"],
                "coefficiente": coeff,
                "motivazione": f"Coefficiente di redditivita: {int(float(coeff) * 100)}%",
                "score": score,
            })

    # Sort by score
    results.sort(key=lambda x: x["score"], reverse=True)

    # If no local matches, try Claude
    if not results:
        try:
            from agents.agent0_wizard.explainer import suggest_ateco
            suggestions = suggest_ateco(query)
            results = [
                {
                    "codice": s.codice,
                    "descrizione": s.descrizione,
                    "coefficiente": str(s.coefficiente),
                    "motivazione": s.motivazione,
                }
                for s in suggestions
            ]
        except Exception:
            # Fallback: return all codes
            results = [
                {
                    "codice": code,
                    "descrizione": info["description"],
                    "coefficiente": info["coefficient"],
                    "motivazione": "",
                }
                for code, info in list(ATECO_CODES.items())[:5]
            ]

    return jsonify(results[:3])


@app.route("/api/simula")
def api_simula():
    """Quick simulation for the wizard slider."""
    try:
        ricavi = int(request.args.get("ricavi", 30000))
        ateco = request.args.get("ateco", "62.01.00")
        primo_anno = request.args.get("primo_anno", "true").lower() == "true"

        # Normalize ATECO (wizard may send short form)
        if ateco and len(ateco) <= 5 and ateco not in ATECO_CODES:
            for code in ATECO_CODES:
                if code.startswith(ateco):
                    ateco = code
                    break

        profilo = ProfiloContribuente(
            contribuente_id="sim-temp",
            nome="", cognome="",
            codice_fiscale="XXXXXX00A00X000X",
            comune_residenza="",
            data_apertura_piva=date.today(),
            primo_anno=primo_anno,
            ateco_principale=ateco,
            regime_agevolato=primo_anno,
            gestione_inps="separata",
        )

        ricavi_dict = {ateco: Decimal(str(ricavi))}
        sim = simulate(profilo=profilo, ricavi_per_ateco=ricavi_dict, anno_fiscale=2024)

        scadenze = [
            {
                "data": str(s.data),
                "descrizione": s.descrizione,
                "importo": f"{s.importo:,.2f} \u20ac",
            }
            for s in sim.scadenze_anno_corrente
        ]

        return jsonify({
            "imposta_sostitutiva": str(sim.imposta_sostitutiva),
            "contributo_inps": str(sim.contributo_inps),
            "rata_mensile": str(sim.rata_mensile_da_accantonare),
            "aliquota": str(sim.aliquota),
            "scadenze": scadenze,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ─── HELPERS ──────────────────────────────────────────

def _build_profilo(pid: str, ana: dict) -> ProfiloContribuente:
    """Build a ProfiloContribuente from stored anagrafica."""
    return ProfiloContribuente(
        contribuente_id=pid,
        nome=ana.get("nome", ""),
        cognome=ana.get("cognome", ""),
        codice_fiscale=ana.get("codice_fiscale", ""),
        comune_residenza=ana.get("comune_residenza", ""),
        data_apertura_piva=date.fromisoformat(ana.get("data_apertura_piva", "2024-01-01")),
        primo_anno=ana.get("primo_anno", True),
        ateco_principale=ana.get("ateco_principale", "62.01.00"),
        ateco_secondari=ana.get("ateco_secondari", []),
        regime_agevolato=ana.get("regime_agevolato", True),
        gestione_inps=ana.get("gestione_inps", "separata"),
        riduzione_inps_35=ana.get("riduzione_inps_35", False),
        rivalsa_inps_4=ana.get("rivalsa_inps_4", False),
    )


# ─── MAIN ─────────────────────────────────────────────

if __name__ == "__main__":
    print("\n  FiscalAI Web UI")
    print("  http://127.0.0.1:5001\n")
    app.run(host="0.0.0.0", port=5001, debug=True)
