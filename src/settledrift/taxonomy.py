"""The R1-R6 reconciliation-drift taxonomy.

Every ledger/settlement pair that isn't an exact match is classified into
exactly one of these. R6 is the only class that can never be auto-resolved —
it means one side genuinely has no counterpart on the other.
"""

from enum import StrEnum


class DriftClass(StrEnum):
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"
    R4 = "R4"
    R5 = "R5"
    R6 = "R6"
    CLEAN = "CLEAN"  # exact deterministic match, not a drift class at all


DESCRIPTIONS: dict[DriftClass, str] = {
    DriftClass.CLEAN: "exact match (order id + amount within fee tolerance)",
    DriftClass.R1: "fee/GST rounding drift (sub-rupee difference)",
    DriftClass.R2: "timing lag (settlement date != order date)",
    DriftClass.R3: "partial refund not fully reflected in net amount",
    DriftClass.R4: "split settlement (one ledger entry, 2+ settlement rows)",
    DriftClass.R5: "duplicate entry on one side",
    DriftClass.R6: "missing counterpart — true exception, human review required",
}

# R6 can never be auto-accepted by the confidence gate, regardless of the
# agent's stated confidence — there is nothing on the other side to confirm
# a match against.
NEVER_AUTO_RESOLVABLE = {DriftClass.R6}
