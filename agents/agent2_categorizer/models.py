"""Data models for Agent2 Categorizer."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


class ExpenseCategory:
    """Standard expense categories for forfettario regime.

    Note: In regime forfettario, expenses are NOT deductible (the coefficient
    already accounts for them). However, tracking them is useful for:
    - Understanding real net income
    - Multi-ATECO categorization
    - Reconciliation
    """
    MATERIALE = "materiale"           # Raw materials, supplies
    SERVIZI = "servizi"               # Professional services
    AFFITTO = "affitto"               # Rent
    UTENZE = "utenze"                 # Utilities
    TRASPORTO = "trasporto"           # Transport, travel
    ATTREZZATURE = "attrezzature"     # Equipment
    SOFTWARE = "software"             # Software, subscriptions
    FORMAZIONE = "formazione"         # Training, courses
    ASSICURAZIONE = "assicurazione"   # Insurance
    TELECOMUNICAZIONI = "telecomunicazioni"  # Phone, internet
    CANCELLERIA = "cancelleria"       # Office supplies
    RAPPRESENTANZA = "rappresentanza" # Entertainment, meals
    CONTRIBUTI = "contributi"         # INPS, cassa previdenza
    TRIBUTI = "tributi"               # Taxes, F24
    BANCARIE = "bancarie"             # Bank fees
    ALTRO = "altro"                   # Other

    ALL = [
        MATERIALE, SERVIZI, AFFITTO, UTENZE, TRASPORTO, ATTREZZATURE,
        SOFTWARE, FORMAZIONE, ASSICURAZIONE, TELECOMUNICAZIONI,
        CANCELLERIA, RAPPRESENTANZA, CONTRIBUTI, TRIBUTI, BANCARIE, ALTRO,
    ]

    # Keywords for automatic suggestion
    KEYWORDS: dict[str, list[str]] = {
        MATERIALE: ["materiale", "materie prime", "forniture", "consumabili", "carta", "inchiostro", "toner"],
        SERVIZI: ["consulenza", "servizio", "prestazione", "collaborazione", "professionista"],
        AFFITTO: ["affitto", "locazione", "canone locazione", "pigione", "coworking"],
        UTENZE: ["bolletta", "enel", "gas", "acqua", "energia", "luce"],
        TRASPORTO: ["treno", "aereo", "taxi", "benzina", "carburante", "autostrada", "pedaggio", "uber", "italo", "trenitalia"],
        ATTREZZATURE: ["computer", "stampante", "monitor", "scrivania", "sedia", "attrezzatura", "hardware"],
        SOFTWARE: ["software", "licenza", "abbonamento", "subscription", "saas", "cloud", "hosting", "dominio", "aws", "google cloud"],
        FORMAZIONE: ["corso", "formazione", "libro", "ebook", "conferenza", "workshop", "webinar", "udemy", "coursera"],
        ASSICURAZIONE: ["assicurazione", "polizza", "premio assicurativo", "rc professionale"],
        TELECOMUNICAZIONI: ["telefono", "cellulare", "internet", "fibra", "tim", "vodafone", "wind", "iliad", "fastweb"],
        CANCELLERIA: ["cancelleria", "penne", "quaderni", "cartucce", "buste", "plichi"],
        RAPPRESENTANZA: ["pranzo", "cena", "ristorante", "bar", "caffè", "regalo", "omaggio"],
        CONTRIBUTI: ["inps", "contributi", "cassa", "previdenza", "gestione separata"],
        TRIBUTI: ["f24", "tributo", "imposta", "tassa", "agenzia entrate", "imu", "tari"],
        BANCARIE: ["commissione", "canone conto", "spese bancarie", "bollo conto"],
    }


@dataclass
class CategorizedTransaction:
    """A transaction enriched with categorization data."""
    original: dict = field(default_factory=dict)
    ateco_code: str = ""
    ateco_description: str = ""
    category: str = ""  # ExpenseCategory value or "ricavo"
    confidence: float = 0.0  # 0.0 to 1.0
    rule_applied: str = ""  # description of the rule that matched
    is_ricavo: bool = False
    is_spesa: bool = False


@dataclass
class AtecoRevenueDetail:
    """Revenue detail for a single ATECO code."""
    ateco_code: str = ""
    description: str = ""
    coefficient: Decimal = Decimal("0")
    total_revenue: Decimal = Decimal("0")
    transaction_count: int = 0


@dataclass
class RevenueCounter:
    """Revenue counter with per-ATECO breakdown and threshold monitoring."""
    anno: int = 0
    per_ateco: list[AtecoRevenueDetail] = field(default_factory=list)
    grand_total: Decimal = Decimal("0")
    soglia_85k: Decimal = Decimal("85000")
    soglia_85k_percentage: Decimal = Decimal("0")
    over_threshold: bool = False
    proiezione_annuale: Decimal = Decimal("0")

    def add_revenue(self, ateco_code: str, amount: Decimal, description: str = "", coefficient: Decimal = Decimal("0")) -> None:
        """Add revenue to a specific ATECO code."""
        for detail in self.per_ateco:
            if detail.ateco_code == ateco_code:
                detail.total_revenue += amount
                detail.transaction_count += 1
                break
        else:
            self.per_ateco.append(AtecoRevenueDetail(
                ateco_code=ateco_code,
                description=description,
                coefficient=coefficient,
                total_revenue=amount,
                transaction_count=1,
            ))
        self.grand_total += amount
        self._update_threshold()

    def _update_threshold(self) -> None:
        if self.soglia_85k > 0:
            self.soglia_85k_percentage = (self.grand_total / self.soglia_85k * 100).quantize(Decimal("0.01"))
            self.over_threshold = self.grand_total > self.soglia_85k


@dataclass
class ReconciliationMatch:
    """Result of matching an invoice with a bank movement."""
    fattura_id: str = ""
    fattura_numero: str = ""
    fattura_importo: Decimal = Decimal("0")
    movimento_id: str = ""
    movimento_importo: Decimal = Decimal("0")
    movimento_data: str = ""
    days_difference: int = 0
    amount_match: bool = False
    confidence: float = 0.0
