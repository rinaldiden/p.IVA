"""Agent5 — Declaration Generator: Modello Redditi PF per regime forfettario."""

from .declaration import (
    compile_quadro_lm,
    compile_quadro_rr,
    genera_riepilogo,
    generate_declaration,
    submit_declaration,
    validate_declaration,
)

__all__ = [
    "generate_declaration",
    "compile_quadro_lm",
    "compile_quadro_rr",
    "genera_riepilogo",
    "submit_declaration",
    "validate_declaration",
]
