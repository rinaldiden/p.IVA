#!/usr/bin/env python3
"""FiscalAI Web UI — interfaccia per gestione P.IVA forfettaria.

Usage:
    pip install flask
    python3 web/app.py

Opens at http://127.0.0.1:5001
"""

from __future__ import annotations

import hashlib
import json
import sys
import uuid
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from functools import wraps
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash

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
app.secret_key = "fiscalai-dev-key-change-in-prod"
store = SupervisorStore()

# ─── AUTH ────────────────────────────────────────────

_USERS_FILE = _ROOT / "data" / "users.json"


def _load_users() -> dict:
    if _USERS_FILE.exists():
        return json.loads(_USERS_FILE.read_text())
    return {}


def _save_users(users: dict) -> None:
    _USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _USERS_FILE.write_text(json.dumps(users, indent=2))


def _hash_pw(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_email" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def _user_owns_profile(pid: str) -> bool:
    """Check that logged-in user owns this profile."""
    email = session.get("user_email", "")
    users = _load_users()
    user = users.get(email, {})
    return pid in user.get("profiles", [])


@app.route("/registrati", methods=["GET", "POST"])
def registrati():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        nome = request.form.get("nome", "").strip()

        if not email or not password or not nome:
            flash("Compila tutti i campi.", "error")
            return render_template("auth.html", mode="registrati")

        users = _load_users()
        if email in users:
            flash("Email già registrata. Accedi.", "error")
            return redirect(url_for("login"))

        users[email] = {
            "nome": nome,
            "password": _hash_pw(password),
            "profiles": [],
        }
        _save_users(users)
        session["user_email"] = email
        session["user_nome"] = nome
        flash(f"Benvenuto {nome}!", "success")
        return redirect(url_for("index"))

    return render_template("auth.html", mode="registrati")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        users = _load_users()
        user = users.get(email)
        if not user or user["password"] != _hash_pw(password):
            flash("Email o password errati.", "error")
            return render_template("auth.html", mode="login")

        session["user_email"] = email
        session["user_nome"] = user.get("nome", "")
        return redirect(url_for("index"))

    return render_template("auth.html", mode="login")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def _link_profile_to_user(pid: str) -> None:
    """Associate a profile with the logged-in user."""
    email = session.get("user_email", "")
    if not email:
        return
    users = _load_users()
    if email in users:
        if pid not in users[email].get("profiles", []):
            users[email].setdefault("profiles", []).append(pid)
            _save_users(users)


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


def _build_profilo(pid: str, ana: dict) -> ProfiloContribuente:
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


def _calc_spese_totali(profile: dict) -> tuple[float, float]:
    """Return (totale_annuo, totale_mensile) from saved expenses."""
    spese = profile.get("spese", [])
    totale = sum(float(s.get("importo_annuo", 0)) for s in spese)
    return totale, round(totale / 12, 2)


# ─── LANDING ──────────────────────────────────────────

@app.route("/")
@login_required
def index():
    email = session.get("user_email", "")
    users = _load_users()
    user_profiles = users.get(email, {}).get("profiles", [])
    profile_data = [_profile_summary(pid) for pid in user_profiles]
    profile_data = [p for p in profile_data if p]
    return render_template("landing.html", profiles=profile_data, user_nome=session.get("user_nome", ""))


# ─── WIZARD ───────────────────────────────────────────

@app.route("/wizard")
@login_required
def wizard():
    return render_template("wizard.html")


@app.route("/wizard/salva", methods=["POST"])
@login_required
def wizard_salva():
    form = request.form
    primo_anno = form.get("primo_anno") == "1"
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
        regime_agevolato=primo_anno,
        gestione_inps=gestione,
        riduzione_inps_35=False,
        rivalsa_inps_4=form.get("rivalsa_inps_4") == "1",
    )
    store.save_from_agent0(asdict(profilo))
    _link_profile_to_user(profilo.contribuente_id)
    return redirect(url_for("apertura", pid=profilo.contribuente_id))


# ─── APERTURA ─────────────────────────────────────────

@app.route("/apertura/<pid>")
@login_required
def apertura(pid):
    profile, ana = _get_ana(pid)
    if not profile:
        return redirect(url_for("index"))
    gestione = ana.get("gestione_inps", "separata")
    return render_template("apertura.html", pid=pid, gestione=gestione)


# ─── DASHBOARD ────────────────────────────────────────

@app.route("/dashboard/<pid>")
@login_required
def dashboard(pid):
    profile, ana = _get_ana(pid)
    if not profile:
        return redirect(url_for("index"))

    welcome = request.args.get("welcome") or (
        not profile.get("_visited_dashboard")
    )
    if welcome and not profile.get("_visited_dashboard"):
        profile["_visited_dashboard"] = True
        store.save_profile(pid, profile)

    fatture = profile.get("fatture", [])
    n_fatture = len(fatture)
    fatturato_anno = sum(float(f.get("ricavo_netto", 0)) for f in fatture)

    anno = date.today().year
    da_accantonare_mese = Decimal("0")
    scadenze = []
    prossima = None

    if fatturato_anno > 0 or n_fatture > 0:
        try:
            ateco_p = ana.get("ateco_principale", "62.01.00")
            ricavi = {ateco_p: Decimal(str(fatturato_anno))}
            profilo_obj = _build_profilo(pid, ana)
            sim = simulate(profilo=profilo_obj, ricavi_per_ateco=ricavi, anno_fiscale=2025)
            da_accantonare_mese = sim.rata_mensile_da_accantonare
            scadenze = [
                {"data": s.data, "descrizione": s.descrizione, "importo": s.importo}
                for s in sim.scadenze_anno_corrente
            ]
        except Exception:
            pass

    if scadenze:
        prossima = scadenze[0]

    # Spese
    spese = profile.get("spese", [])
    spese_anno, spese_mese = _calc_spese_totali(profile)
    tasse_inps = float(da_accantonare_mese * 12)
    netto_reale_anno = fatturato_anno - tasse_inps - spese_anno
    netto_reale_mese = round(netto_reale_anno / 12, 2) if fatturato_anno > 0 else 0

    return render_template("dashboard.html",
                           pid=pid, ana=ana, welcome=welcome,
                           fatturato_anno=fatturato_anno,
                           da_accantonare_mese=da_accantonare_mese,
                           prossima_scadenza=prossima,
                           n_fatture=n_fatture,
                           fatture=fatture[-10:],
                           scadenze=scadenze,
                           anno=anno,
                           spese=spese,
                           spese_anno=spese_anno,
                           spese_mese=spese_mese,
                           netto_reale_anno=netto_reale_anno,
                           netto_reale_mese=netto_reale_mese,
                           tasse_inps_anno=tasse_inps)


# ─── PROFILO ──────────────────────────────────────────

@app.route("/profilo/<pid>")
@login_required
def profilo_detail(pid):
    profile, ana = _get_ana(pid)
    if not profile:
        return redirect(url_for("index"))
    return render_template("profilo.html", profile=profile, ana=ana, pid=pid)


@app.route("/profilo/<pid>/delete", methods=["POST"])
@login_required
def profilo_delete(pid):
    store.delete_profile(pid)
    return redirect(url_for("index"))


# ─── SIMULAZIONE ──────────────────────────────────────

@app.route("/simulazione/<pid>", methods=["GET", "POST"])
@login_required
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
@login_required
def fattura(pid):
    profile, ana = _get_ana(pid)
    if not profile:
        return redirect(url_for("index"))

    result = None
    xml_str = None
    xml_preview = None

    if request.method == "POST":
        # Build client from form (handles both azienda and privato)
        tipo_cliente = request.form.get("tipo_cliente", "azienda")
        if tipo_cliente == "privato":
            denominazione = f"{request.form.get('cliente_nome', '')} {request.form.get('cliente_cognome', '')}"
            piva = ""
            cf = request.form.get("cliente_cf", "")
            sdi = "0000000"
        else:
            denominazione = request.form.get("cliente_denominazione", "")
            piva = request.form.get("cliente_piva", "")
            cf = request.form.get("cliente_cf", "")
            sdi = request.form.get("cliente_sdi", "0000000")

        cliente = DatiCliente(
            denominazione=denominazione,
            partita_iva=piva,
            codice_fiscale=cf,
            indirizzo=request.form.get("cliente_indirizzo", ""),
            cap=request.form.get("cliente_cap", ""),
            comune=request.form.get("cliente_comune", ""),
            provincia=request.form.get("cliente_provincia", ""),
            codice_sdi=sdi,
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
            anno_fattura = int(request.form.get("anno_fattura", date.today().year))
            numero = prossimo_numero(anno_fattura)
            data_fattura = date.fromisoformat(
                request.form.get("data_fattura", str(date.today()))
            )

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

            if "fatture" not in profile:
                profile["fatture"] = []
            profile["fatture"].append({
                "numero": f.numero,
                "data": str(f.data),
                "cliente": cliente.denominazione,
                "importo": str(f.totale_documento),
                "ricavo_netto": str(f.ricavo_netto),
                "stato_sdi": "AT",
                "xml": xml_str,
            })
            store.save_profile(pid, profile)

    return render_template("fattura.html", ana=ana, pid=pid,
                           result=result, xml_str=xml_str, xml_preview=xml_preview,
                           today=str(date.today()))


# ─── STORICO FATTURE ──────────────────────────────────

@app.route("/fatture/<pid>")
@login_required
def storico_fatture(pid):
    profile, ana = _get_ana(pid)
    if not profile:
        return redirect(url_for("index"))
    fatture = profile.get("fatture", [])
    totale_importo = sum(float(f.get("importo", 0)) for f in fatture)
    totale_netto = sum(float(f.get("ricavo_netto", 0)) for f in fatture)
    return render_template("storico_fatture.html", pid=pid, ana=ana,
                           fatture=fatture, totale_importo=totale_importo,
                           totale_netto=totale_netto, anno=date.today().year)


@app.route("/fattura/<pid>/xml/<int:idx>")
@login_required
def download_xml(pid, idx):
    profile, _ = _get_ana(pid)
    if not profile:
        return redirect(url_for("index"))
    fatture = profile.get("fatture", [])
    if idx < 0 or idx >= len(fatture):
        return redirect(url_for("storico_fatture", pid=pid))
    xml = fatture[idx].get("xml", "")
    numero = fatture[idx].get("numero", "fattura")
    from flask import Response
    return Response(
        xml,
        mimetype="application/xml",
        headers={"Content-Disposition": f"attachment; filename={numero}.xml"},
    )


# ─── API ──────────────────────────────────────────────

@app.route("/api/ateco")
def api_ateco():
    return jsonify(ATECO_CODES)


@app.route("/api/suggerisci-ateco")
def api_suggerisci_ateco():
    query = request.args.get("q", "").strip().lower()
    if not query:
        return jsonify([])

    results = []
    query_words = [w for w in query.split() if len(w) >= 3]
    for code, info in ATECO_CODES.items():
        desc = info["description"].lower()
        keywords = [k.lower() for k in info.get("keywords", [])]
        coeff = info["coefficient"]
        score = 0

        for kw in keywords:
            if query in kw or kw in query:
                score += 20
                break

        for word in query_words:
            if word in desc:
                score += 10
            for kw in keywords:
                if word in kw:
                    score += 8
                    break
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
                "gestione_inps": info.get("gestione_inps", "separata"),
                "motivazione": f"Coefficiente di redditivita: {int(float(coeff) * 100)}%",
                "score": score,
            })

    results.sort(key=lambda x: x["score"], reverse=True)

    if not results:
        try:
            from agents.agent0_wizard.explainer import suggest_ateco
            suggestions = suggest_ateco(query)
            results = [
                {
                    "codice": s.codice,
                    "descrizione": s.descrizione,
                    "coefficiente": str(s.coefficiente),
                    "gestione_inps": ATECO_CODES.get(s.codice, {}).get("gestione_inps", "separata"),
                    "motivazione": s.motivazione,
                }
                for s in suggestions
            ]
        except Exception:
            results = [
                {
                    "codice": code,
                    "descrizione": info["description"],
                    "coefficiente": info["coefficient"],
                    "gestione_inps": info.get("gestione_inps", "separata"),
                    "motivazione": "",
                }
                for code, info in list(ATECO_CODES.items())[:5]
            ]

    return jsonify(results[:3])


@app.route("/api/simula")
def api_simula():
    try:
        ricavi = int(request.args.get("ricavi", 30000))
        ateco = request.args.get("ateco", "62.01.00")
        primo_anno = request.args.get("primo_anno", "true").lower() == "true"
        gestione = request.args.get("gestione", "separata")

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
            gestione_inps=gestione,
        )

        ricavi_dict = {ateco: Decimal(str(ricavi))}
        sim = simulate(profilo=profilo, ricavi_per_ateco=ricavi_dict, anno_fiscale=2025)

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


@app.route("/api/spese/<pid>", methods=["GET"])
def api_get_spese(pid):
    profile, _ = _get_ana(pid)
    if not profile:
        return jsonify({"error": "Profile not found"}), 404
    spese = profile.get("spese", [])
    totale_anno = sum(float(s.get("importo_annuo", 0)) for s in spese)
    return jsonify({"spese": spese, "totale_anno": totale_anno, "totale_mese": round(totale_anno / 12, 2)})


@app.route("/api/spese/<pid>", methods=["POST"])
def api_save_spese(pid):
    profile, ana = _get_ana(pid)
    if not profile:
        return jsonify({"error": "Profile not found"}), 404

    data = request.get_json(silent=True) or {}
    categoria = data.get("categoria", "")
    importo_annuo = float(data.get("importo_annuo", 0))

    if not categoria:
        return jsonify({"error": "Missing categoria"}), 400

    spese = profile.get("spese", [])

    # Update existing or add new
    found = False
    for s in spese:
        if s["categoria"] == categoria:
            s["importo_annuo"] = importo_annuo
            found = True
            break
    if not found:
        spese.append({"categoria": categoria, "importo_annuo": importo_annuo})

    profile["spese"] = spese
    store.save_profile(pid, profile)

    totale_anno = sum(float(s.get("importo_annuo", 0)) for s in spese)
    return jsonify({"spese": spese, "totale_anno": totale_anno, "totale_mese": round(totale_anno / 12, 2)})


@app.route("/api/spese/<pid>/delete", methods=["POST"])
def api_delete_spesa(pid):
    profile, _ = _get_ana(pid)
    if not profile:
        return jsonify({"error": "Profile not found"}), 404

    data = request.get_json(silent=True) or {}
    categoria = data.get("categoria", "")

    spese = profile.get("spese", [])
    profile["spese"] = [s for s in spese if s["categoria"] != categoria]
    store.save_profile(pid, profile)

    totale = sum(float(s.get("importo_annuo", 0)) for s in profile["spese"])
    return jsonify({"spese": profile["spese"], "totale_anno": totale, "totale_mese": round(totale / 12, 2)})


@app.route("/api/netto-reale/<pid>")
def api_netto_reale(pid):
    profile, ana = _get_ana(pid)
    if not profile:
        return jsonify({"error": "Profile not found"}), 404

    fatture = profile.get("fatture", [])
    fatturato = sum(float(f.get("ricavo_netto", 0)) for f in fatture)
    spese_anno, spese_mese = _calc_spese_totali(profile)

    tasse_inps = 0
    if fatturato > 0:
        try:
            profilo_obj = _build_profilo(pid, ana)
            ateco_p = ana.get("ateco_principale", "62.01.00")
            sim = simulate(profilo=profilo_obj,
                           ricavi_per_ateco={ateco_p: Decimal(str(fatturato))},
                           anno_fiscale=2025)
            tasse_inps = float(sim.imposta_sostitutiva + sim.contributo_inps)
        except Exception:
            pass

    netto = fatturato - tasse_inps - spese_anno
    return jsonify({
        "fatturato_stimato": fatturato,
        "tasse_inps": tasse_inps,
        "totale_spese": spese_anno,
        "netto_reale_anno": round(netto, 2),
        "netto_reale_mese": round(netto / 12, 2) if fatturato > 0 else 0,
    })


@app.route("/api/lookup-piva")
def api_lookup_piva():
    piva = request.args.get("piva", "").strip()
    if not piva or len(piva) != 11 or not piva.isdigit():
        return jsonify({"trovata": False})

    # Try VIES API (EU VAT validation, free, no auth)
    try:
        import urllib.request
        url = f"https://ec.europa.eu/taxation_customs/vies/rest-api/ms/IT/vat/{piva}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            if data.get("isValid"):
                name = data.get("name", "")
                addr = data.get("address", "")
                return jsonify({
                    "trovata": True,
                    "ragione_sociale": name,
                    "indirizzo": addr,
                    "cap": "",
                    "comune": "",
                    "provincia": "",
                    "codice_sdi": "0000000",
                })
    except Exception:
        pass

    # Fallback: vatcomply
    try:
        import urllib.request
        url = f"https://api.vatcomply.com/vat?vat_number=IT{piva}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            if data.get("valid"):
                return jsonify({
                    "trovata": True,
                    "ragione_sociale": data.get("name", ""),
                    "indirizzo": data.get("address", ""),
                    "cap": "",
                    "comune": "",
                    "provincia": "",
                    "codice_sdi": "0000000",
                })
    except Exception:
        pass

    return jsonify({"trovata": False})


# ─── MAIN ─────────────────────────────────────────────

if __name__ == "__main__":
    print("\n  FiscalAI Web UI")
    print("  http://127.0.0.1:5001\n")
    app.run(host="0.0.0.0", port=5001, debug=True)
