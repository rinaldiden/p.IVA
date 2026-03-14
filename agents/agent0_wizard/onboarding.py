"""OnboardingWizard — 6-step data collection."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Callable

from . import explainer
from .models import ATECOSuggestion, ProfiloContribuente, SimulationResult
from .simulator import simulate


def _parse_date(s: str) -> date:
    return datetime.strptime(s.strip(), "%Y-%m-%d").date()


def _parse_decimal(s: str) -> Decimal:
    return Decimal(s.strip().replace(",", "."))


def _si_no(s: str) -> bool:
    return s.strip().lower() in ("si", "sì", "s", "y", "yes")


class OnboardingWizard:
    """6-step onboarding wizard. Collects data and runs simulation."""

    def __init__(
        self,
        input_fn: Callable[[str], str] | None = None,
        print_fn: Callable[[str], None] | None = None,
        use_claude: bool = True,
    ):
        self._input = input_fn or input
        self._print = print_fn or print
        self._use_claude = use_claude
        self.profilo: ProfiloContribuente | None = None
        self.ricavi_per_ateco: dict[str, Decimal] = {}
        self.imposta_anno_prec: Decimal = Decimal("0")
        self.simulation: SimulationResult | None = None

    def _ask(self, prompt: str) -> str:
        return self._input(prompt)

    def _say(self, text: str) -> None:
        self._print(text)

    # --- STEP 1: Dati base ---
    def step1_dati_base(self) -> dict:
        self._say("\n═══ STEP 1/6 — Dati base ═══\n")
        nome = self._ask("Nome: ")
        cognome = self._ask("Cognome: ")
        codice_fiscale = self._ask("Codice fiscale: ").upper()
        comune = self._ask("Comune di residenza: ")
        data_str = self._ask("Data apertura P.IVA (YYYY-MM-DD): ")
        data_apertura = _parse_date(data_str)

        anno_corrente = date.today().year
        primo_anno = data_apertura.year == anno_corrente

        self._say(
            f"\n→ Primo anno di attività: {'Sì' if primo_anno else 'No'}"
            f" (apertura: {data_apertura})"
        )

        return {
            "nome": nome,
            "cognome": cognome,
            "codice_fiscale": codice_fiscale,
            "comune_residenza": comune,
            "data_apertura_piva": data_apertura,
            "primo_anno": primo_anno,
        }

    # --- STEP 2: Attività ---
    def step2_attivita(self) -> dict:
        self._say("\n═══ STEP 2/6 — Attività ═══\n")
        descrizione = self._ask("Descrivi la tua attività in poche parole: ")

        suggerimenti: list[ATECOSuggestion] = []
        if self._use_claude:
            self._say("\nCerco i codici ATECO più adatti...")
            suggerimenti = explainer.suggest_ateco(descrizione)

        if suggerimenti:
            self._say("\nSuggerimenti ATECO:")
            for i, s in enumerate(suggerimenti, 1):
                self._say(
                    f"  {i}. {s.codice} — {s.descrizione} "
                    f"(coeff. {s.coefficiente})\n"
                    f"     {s.motivazione}"
                )
            scelta = self._ask(
                "\nScegli (1/2/3) o inserisci codice ATECO manuale: "
            )
            if scelta.strip() in ("1", "2", "3"):
                ateco_principale = suggerimenti[int(scelta) - 1].codice
            else:
                ateco_principale = scelta.strip()
        else:
            ateco_principale = self._ask("Codice ATECO principale: ")

        ateco_secondari: list[str] = []
        if _si_no(self._ask("\nHai attività secondarie (multi-ATECO)? (s/n): ")):
            while True:
                cod = self._ask("Codice ATECO secondario (vuoto per terminare): ")
                if not cod.strip():
                    break
                ateco_secondari.append(cod.strip())

        return {
            "ateco_principale": ateco_principale,
            "ateco_secondari": ateco_secondari,
        }

    # --- STEP 3: Stima ricavi ---
    def step3_ricavi(
        self, ateco_principale: str, ateco_secondari: list[str], primo_anno: bool
    ) -> dict:
        self._say("\n═══ STEP 3/6 — Stima ricavi ═══\n")

        ricavi: dict[str, Decimal] = {}
        tutti_ateco = [ateco_principale] + ateco_secondari

        for cod in tutti_ateco:
            importo_str = self._ask(f"Fatturato annuale stimato per {cod} (€): ")
            ricavi[cod] = _parse_decimal(importo_str)

        totale = sum(ricavi.values())
        self._say(f"\n→ Totale ricavi stimati: {totale:,.2f} €")

        if totale >= Decimal("70000"):
            self._say(
                "\n⚠ ATTENZIONE: ricavi stimati vicini alla soglia 85.000€.\n"
                "  Agent4 monitorerà il fatturato durante l'anno."
            )

        # Causa ostativa: redditi da lavoro dipendente
        if _si_no(self._ask("\nHai redditi da lavoro dipendente? (s/n): ")):
            reddito_dip = _parse_decimal(
                self._ask("Reddito lordo da lavoro dipendente (€): ")
            )
            if reddito_dip > Decimal("30000"):
                self._say(
                    "\n⛔ CAUSA OSTATIVA: reddito dipendente > 30.000€.\n"
                    "  Non puoi accedere al regime forfettario."
                )

        imposta_anno_prec = Decimal("0")
        if not primo_anno:
            imposta_str = self._ask(
                "\nImposta sostitutiva anno precedente (€, per calcolo acconti): "
            )
            imposta_anno_prec = _parse_decimal(imposta_str)

        return {
            "ricavi_per_ateco": ricavi,
            "imposta_anno_prec": imposta_anno_prec,
        }

    # --- STEP 4: INPS ---
    def step4_inps(self) -> dict:
        self._say("\n═══ STEP 4/6 — INPS ═══\n")

        if self._use_claude:
            self._say(explainer.explain_inps_options(
                self.profilo.ateco_principale if self.profilo else "consulenza"
            ))
            self._say("")

        # Casse professionali
        if _si_no(self._ask("Sei iscritto a una cassa professionale? (s/n): ")):
            self._say(
                "→ I contributi alla cassa professionale sostituiscono la gestione INPS.\n"
                "  Questa funzionalità sarà integrata nella fase 2."
            )

        gestione = self._ask(
            "Gestione INPS (separata/artigiani/commercianti): "
        ).strip().lower()

        riduzione_35 = False
        if gestione in ("artigiani", "commercianti"):
            riduzione_35 = _si_no(self._ask(
                "Vuoi richiedere la riduzione contributiva 35%? (s/n): "
            ))
            if riduzione_35:
                self._say(
                    "→ La riduzione 35% va richiesta entro il 28/02 di ogni anno."
                )

        rivalsa_4 = False
        if gestione == "separata":
            rivalsa_4 = _si_no(self._ask(
                "Vuoi applicare la rivalsa INPS 4% in fattura? (s/n): "
            ))
            if rivalsa_4:
                self._say(
                    "→ Addebiterai il 4% al cliente — è denaro tuo, non del fisco."
                )

        return {
            "gestione_inps": gestione,
            "riduzione_inps_35": riduzione_35,
            "rivalsa_inps_4": rivalsa_4,
        }

    # --- STEP 5: Simulazione ---
    def step5_simulazione(self) -> SimulationResult:
        self._say("\n═══ STEP 5/6 — Simulazione fiscale ═══\n")

        assert self.profilo is not None
        sim = simulate(
            profilo=self.profilo,
            ricavi_per_ateco=self.ricavi_per_ateco,
            imposta_anno_prec=self.imposta_anno_prec,
        )

        aliquota_pct = int(sim.aliquota * 100)
        totale = sim.imposta_sostitutiva + sim.contributo_inps

        # Format coefficients for display
        coeff_display = ""
        for d in sim.dettaglio_ateco:
            coeff_pct = int(Decimal(d["coefficiente"]) * 100)
            coeff_display += f"│ ATECO {d['codice']}: coeff. {coeff_pct}%, reddito {Decimal(d['reddito']):>12,.2f} €    │\n"

        self._say(
            f"┌─────────────────────────────────────────┐\n"
            f"│ SIMULAZIONE FISCALE ANNO {sim.anno_fiscale}           │\n"
            f"├─────────────────────────────────────────┤\n"
            f"│ Ricavi stimati:        {sim.ricavi_totali:>12,.2f} €  │\n"
            f"{coeff_display}"
            f"│ Reddito imponibile:    {sim.reddito_imponibile:>12,.2f} €  │\n"
            f"│ Aliquota:                    {aliquota_pct}%       │\n"
            f"│ Imposta sostitutiva:   {sim.imposta_sostitutiva:>12,.2f} €  │\n"
            f"│ Contributi INPS:       {sim.contributo_inps:>12,.2f} €  │\n"
            f"│ TOTALE da pagare:      {totale:>12,.2f} €  │\n"
            f"│ Metti da parte/mese:   {sim.rata_mensile_da_accantonare:>12,.2f} €  │\n"
            f"├─────────────────────────────────────────┤\n"
        )

        if sim.profilo.primo_anno:
            self._say("│ Primo anno → nessun acconto             │")
        else:
            self._say(
                f"│ Acconto 1ª rata (giu): {sim.acconto_prima_rata:>12,.2f} €  │\n"
                f"│ Acconto 2ª rata (nov): {sim.acconto_seconda_rata:>12,.2f} €  │"
            )

        self._say("└─────────────────────────────────────────┘")

        # Regime comparison
        forf = sim.confronto_regimi.get("forfettario", {})
        ordi = sim.confronto_regimi.get("ordinario_stimato", {})
        self._say(
            f"\n📊 Confronto regimi:\n"
            f"  Forfettario: {Decimal(forf.get('totale', '0')):,.2f} €\n"
            f"  Ordinario:   {Decimal(ordi.get('totale', '0')):,.2f} €\n"
            f"  Risparmio:   {sim.risparmio_vs_ordinario:,.2f} €"
        )

        # Scadenzario
        if sim.scadenze_anno_corrente:
            self._say("\n📅 Scadenzario:")
            for s in sim.scadenze_anno_corrente:
                self._say(f"  {s.data}  {s.descrizione}: {s.importo:,.2f} €")

        # Warnings
        for w in sim.warnings:
            self._say(f"\n⚠ {w}")

        self.simulation = sim
        return sim

    # --- STEP 6: Spiegazione e configurazione ---
    def step6_spiegazione(self) -> dict:
        self._say("\n═══ STEP 6/6 — Spiegazione e configurazione ═══\n")

        if self._use_claude and self.simulation:
            spiegazione = explainer.explain_simulation(self.simulation)
            self._say(spiegazione)
            self._say("")

        canale = self._ask(
            "Canale ricezione scontrini (app/email/web): "
        ).strip().lower()

        banca = self._ask(
            "Nome banca per collegamento (connessione reale in fase 2): "
        ).strip()

        return {
            "canale_scontrini": canale,
            "banca_collegata": banca,
        }

    def run(self) -> ProfiloContribuente:
        """Execute the full 6-step onboarding."""
        self._say("\n╔═══════════════════════════════════════════╗")
        self._say("║       FiscalAI — Onboarding Wizard        ║")
        self._say("╚═══════════════════════════════════════════╝")

        # Step 1
        dati_base = self.step1_dati_base()

        # Step 2
        attivita = self.step2_attivita()

        # Build partial profile for step 3+
        self.profilo = ProfiloContribuente(
            contribuente_id=str(uuid.uuid4()),
            nome=dati_base["nome"],
            cognome=dati_base["cognome"],
            codice_fiscale=dati_base["codice_fiscale"],
            comune_residenza=dati_base["comune_residenza"],
            data_apertura_piva=dati_base["data_apertura_piva"],
            primo_anno=dati_base["primo_anno"],
            ateco_principale=attivita["ateco_principale"],
            ateco_secondari=attivita["ateco_secondari"],
        )

        # Step 3
        ricavi_data = self.step3_ricavi(
            attivita["ateco_principale"],
            attivita["ateco_secondari"],
            dati_base["primo_anno"],
        )
        self.ricavi_per_ateco = ricavi_data["ricavi_per_ateco"]
        self.imposta_anno_prec = ricavi_data["imposta_anno_prec"]

        # Step 4
        inps_data = self.step4_inps()
        self.profilo.gestione_inps = inps_data["gestione_inps"]
        self.profilo.riduzione_inps_35 = inps_data["riduzione_inps_35"]
        self.profilo.rivalsa_inps_4 = inps_data["rivalsa_inps_4"]

        regime_str = self._ask(
            "\nAliquota agevolata 5% (primi 5 anni)? (s/n): "
        )
        self.profilo.regime_agevolato = _si_no(regime_str)

        # Step 5
        self.step5_simulazione()

        # Step 6
        config = self.step6_spiegazione()
        self.profilo.canale_scontrini = config["canale_scontrini"]
        self.profilo.banca_collegata = config["banca_collegata"]

        # Finalize
        self.profilo.stato = "attivo"
        self._say(f"\n✅ Profilo creato: {self.profilo.contribuente_id}")
        self._say(f"   {self.profilo.nome} {self.profilo.cognome}")
        self._say(f"   ATECO: {self.profilo.ateco_principale}")
        self._say(f"   Stato: {self.profilo.stato}")

        return self.profilo
