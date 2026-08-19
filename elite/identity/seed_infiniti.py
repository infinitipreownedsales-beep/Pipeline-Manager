"""Source-backed seed of the Translation & Identity layer for the INFINITI pilot.

Every mapping below is transcribed DIRECTLY from an authoritative Order Preference chart (proof_ref names the
exact chart + observation date) — nothing is inferred or remembered. Colors, trims, drivetrains and packages
were re-audited against the QX60 / QX65 / QX80 charts dated 2026-08-19. This seed only asserts what those
charts show; genuinely-new tokens still arrive as `proposed` observations for a person to approve.
"""
from __future__ import annotations

from .translation import (SemanticMapping, VariantRow, FamilyKey, PreferredOrderPolicy, TranslationStore,
                          derive_orderability)

PORTAL = "NNA_ORDER_PORTAL"
FR = "INFINITI"
QX80_CHART = "Order_Preference_Details__QX80.pdf@2026-08-19"
QX60_CHART = "Order_Preference_Details__QX60.pdf@2026-08-19"
QX65_CHART = "Order_Preference_Details__QX65.pdf@2026-08-19"

# model-line SAME_AS (first two digits of the order/model code -> model line). 86 is QX80 (new generation).
MODEL_LINE = [("81", "QX50"), ("82", "QX55"), ("83", "QX80"), ("84", "QX60"), ("85", "QX65"), ("86", "QX80")]

# exterior SAME_AS, verified from the QX80 chart legend (2T = two-tone roof; a real distinction).
QX80_EXTERIOR = [("XLF", "2T Dynamic Metal"), ("XKJ", "2T Radiant White"), ("KH3", "Black Obsidian"),
                 ("KCN", "Dynamic Metal"), ("GAT", "Mineral Black"), ("QBE", "Radiant White")]

# interior SAME_AS — CONTEXT-SCOPED: interior `P` is Sepia Brown on QX80 but Saddle Brown on QX60.
INTERIOR = [("G", "Graphite", ""), ("A", "Burgundy", "QX80"), ("P", "Sepia Brown", "QX80"),
            ("P", "Saddle Brown", "QX60"), ("K", "Stone Gray", ""), ("N", "Vermilion Red", "QX65")]


def seed(store: TranslationStore, *, as_of="2026-08-19"):
    """Idempotently install the source-backed pilot mappings, families, variant rows and default BASE policies."""
    for code2, model in MODEL_LINE:
        store.upsert_semantic(SemanticMapping(PORTAL, "model_code", code2, model, model, "", "approved",
                                              (QX80_CHART,)))
    for raw, name in QX80_EXTERIOR:
        store.upsert_semantic(SemanticMapping(PORTAL, "exterior", raw, raw, name, "QX80", "approved", (QX80_CHART,)))
    for raw, name, scope in INTERIOR:
        proof = {"QX80": QX80_CHART, "QX60": QX60_CHART, "QX65": QX65_CHART}.get(scope, QX80_CHART)
        store.upsert_semantic(SemanticMapping(PORTAL, "interior", raw, raw, name, scope, "approved", (proof,)))

    # ---- QX80 families with both generations (83 prior/current + 86 new, pending) ----
    def row(model, trim, drive, code, gen, pkg, base, priced, chart, seen="seen_latest"):
        fam = FamilyKey(FR, model, trim, drive)
        return VariantRow(fam, code, gen, pkg, base, seen, priced,
                          derive_orderability(seen, priced), (chart,))

    rows = [
        # QX80 LUXE 2WD — 86 new-gen pending ($0 -> unresolved); 83317 priced but only observed as PA1 (no BASE)
        row("QX80", "LUXE", "2WD", "86317", "86", "BASE", True, False, QX80_CHART),
        row("QX80", "LUXE", "2WD", "86317", "86", "PA1", False, False, QX80_CHART),
        row("QX80", "LUXE", "2WD", "86317", "86", "SEA", False, False, QX80_CHART),
        row("QX80", "LUXE", "2WD", "86317", "86", "PA1+SEA", False, False, QX80_CHART),
        row("QX80", "LUXE", "2WD", "83317", "83", "PA1", False, True, QX80_CHART),
        # QX80 PURE 2WD — 86117 new-gen pending; historical 8311 seen previously (inventory/history), not latest
        row("QX80", "PURE", "2WD", "86117", "86", "BASE", True, False, QX80_CHART),
        row("QX80", "PURE", "2WD", "8311", "83", "BASE", True, False, QX80_CHART, seen="seen_previously"),
        # QX80 SPORT 4WD — 86417 new-gen packages (pending); 83417 priced BASE (orderable)
        row("QX80", "SPORT", "4WD", "86417", "86", "BASE", True, False, QX80_CHART),
        row("QX80", "SPORT", "4WD", "86417", "86", "DBI", False, False, QX80_CHART),
        row("QX80", "SPORT", "4WD", "86417", "86", "SEA", False, False, QX80_CHART),
        row("QX80", "SPORT", "4WD", "86417", "86", "PA2", False, False, QX80_CHART),
        row("QX80", "SPORT", "4WD", "86417", "86", "DBI+PA2+SEA", False, False, QX80_CHART),
        row("QX80", "SPORT", "4WD", "83417", "83", "BASE", True, True, QX80_CHART),
        # QX80 PURE 4WD — distinct family from PURE 2WD (drivetrain differs): 83017 priced, 86017 new-gen pending
        row("QX80", "PURE", "4WD", "83017", "83", "BASE", True, True, QX80_CHART),
        row("QX80", "PURE", "4WD", "86017", "86", "BASE", True, False, QX80_CHART),
        # QX60 AUTOGRAPH AWD — single generation, BASE + TPA both priced/orderable
        row("QX60", "AUTOGRAPH", "AWD", "84617", "84", "BASE", True, True, QX60_CHART),
        row("QX60", "AUTOGRAPH", "AWD", "84617", "84", "TPA", False, True, QX60_CHART),
    ]
    for r in rows:
        store.add_variant_row(r)
        store.record_observation(PORTAL, "model_code", r.raw_code, as_of=as_of, proof_ref=r.proof_refs[0],
                                 seen_state=r.seen_state)

    for fam in {r.family.as_str() for r in rows}:
        store.set_policy(PreferredOrderPolicy(FamilyKey.parse(fam)))     # default: prefer BASE
