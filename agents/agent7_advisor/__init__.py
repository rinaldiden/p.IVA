"""Agent7 — Fiscal Advisor for Italian forfettario regime."""

from .advisor import (
    AdvisoryReport,
    ConfrontoRegimi,
    MultiAtecoAdvice,
    RegimeDetail,
    TimingAdvice,
    WhatIfResult,
    advise,
    confronto_regimi,
    ottimizza_multi_ateco,
    simulate_what_if,
    soglia_convenienza,
)

__all__ = [
    "AdvisoryReport",
    "ConfrontoRegimi",
    "MultiAtecoAdvice",
    "RegimeDetail",
    "TimingAdvice",
    "WhatIfResult",
    "advise",
    "confronto_regimi",
    "ottimizza_multi_ateco",
    "simulate_what_if",
    "soglia_convenienza",
]
