"""Source-backed seed of the Translation & Identity layer for the INFINITI pilot.

Every mapping below is transcribed DIRECTLY from an authoritative Order Preference chart (proof_ref names the
exact chart + observation date) — nothing is inferred or remembered. Colours, trims, drivetrains and packages
are transcribed from the reviewed QX60 / QX65 / QX80 charts. This seed only asserts what those charts show.

Governance law (Translation/Identity closure):
  * DETERMINISTIC IDENTITY auto-resolves — colour/model-line/interior SAME_AS and the family (model+trim+
    drivetrain) of an exact order code the chart explicitly states are approved on seed (a visible audit record
    is written; no operator click needed).
  * RELATIONSHIPS THAT CHANGE DEMAND SHARING are NOT auto-activated — cross-generation SAME FAMILY, predecessor/
    successor lineage, and package demand-sharing stay review-gated (see identity.lineage).
Model-scoped colour law is preserved: a code is model-scoped whenever its meaning differs by model (interior
`P` = Saddle Brown on QX60 but Sepia Brown on QX80); exteriors are transcribed per reviewed chart, model-scoped.
"""
from __future__ import annotations

from .translation import (SemanticMapping, VariantRow, FamilyKey, PreferredOrderPolicy, TranslationStore,
                          derive_orderability)

PORTAL = "NNA_ORDER_PORTAL"
FR = "INFINITI"
QX80_CHART = "Order_Preference_Details__QX80.pdf@2026-08-19"
QX60_CHART = "Order_Preference_Details__QX60.pdf@2026-08-19"
QX65_CHART = "Order_Preference_Details__QX65.pdf@2026-08-19"

# model-line SAME_AS (first two digits of the order/model code -> model line). 83/86 are QX80 (two generations).
MODEL_LINE = [("81", "QX50"), ("82", "QX55"), ("83", "QX80"), ("84", "QX60"), ("85", "QX65"), ("86", "QX80")]

# exterior SAME_AS — transcribed per reviewed chart, MODEL-SCOPED (2T = two-tone roof, a real distinction).
QX80_EXTERIOR = [("XLF", "2T Dynamic Metal"), ("XKJ", "2T Radiant White"), ("KH3", "Black Obsidian"),
                 ("KCN", "Dynamic Metal"), ("GAT", "Mineral Black"), ("QBE", "Radiant White")]
QX60_EXTERIOR = [("YCF", "2T Deep Emerald"), ("GAQ", "2T Graphite Shadow"), ("XJU", "2T Moonbow Blue"),
                 ("XKJ", "2T Radiant White"), ("DAT", "Deep Emerald"), ("RCJ", "Grand Blue"),
                 ("KAD", "Graphite Shadow"), ("KBY", "Harbor Gray"), ("GAT", "Mineral Black"),
                 ("KCG", "Moonbow Blue"), ("QBE", "Radiant White")]
QX65_EXTERIOR = [("YCF", "2T Deep Emerald"), ("XHQ", "2T Grand Blue"), ("GAQ", "2T Graphite Shadow"),
                 ("XEX", "2T Harbor Gray"), ("XJU", "2T Moonbow Blue"), ("XKJ", "2T Radiant White"),
                 ("YCT", "2T Sun Red"), ("KH3", "Black Obsidian"), ("DAT", "Deep Emerald"),
                 ("RCJ", "Grand Blue"), ("KAD", "Graphite Shadow"), ("KBY", "Harbor Gray"),
                 ("GAT", "Mineral Black"), ("KCG", "Moonbow Blue"), ("QBE", "Radiant White")]

# interior SAME_AS — G/K share meaning across models (global); P/N/A are model-specific (never globalized).
INTERIOR = [("G", "Graphite", ""), ("K", "Stone Gray", ""),
            ("P", "Saddle Brown", "QX60"), ("P", "Sepia Brown", "QX80"),
            ("N", "Vermilion Red", "QX65"), ("A", "Burgundy", "QX80")]

# Commercial family of an EXACT order code, transcribed from the reviewed charts (deterministic identity).
# (model, trim, drivetrain, order_code, generation, priced, chart). Generation = first two digits of the code.
# `priced` carries the ORDERABILITY evidence (a priced BASE is orderable; a $0/pending BASE is unresolved) — a
# SEPARATE concern from identity (item 18). Identity auto-resolves regardless of `priced`.
FAMILY_CODES = [
    # QX60 — 2027 chart (only AUTOGRAPH AWD has a priced BASE in the reviewed evidence)
    ("QX60", "LUXE", "FWD", "84317", "84", False, QX60_CHART),
    ("QX60", "SPORT", "AWD", "84417", "84", False, QX60_CHART),
    ("QX60", "LUXE", "AWD", "84217", "84", False, QX60_CHART),
    ("QX60", "AUTOGRAPH", "AWD", "84617", "84", True, QX60_CHART),
    # QX65 — 2027 chart (identity established; BASE orderability not evidenced -> unresolved)
    ("QX65", "AUTOGRAPH", "AWD", "85217", "85", False, QX65_CHART),
    ("QX65", "LUXE", "AWD", "85017", "85", False, QX65_CHART),
    ("QX65", "SPORT", "AWD", "85117", "85", False, QX65_CHART),
    # QX80 — new generation ($0/pending BASE -> unresolved orderability, unchanged from the reviewed evidence)
    ("QX80", "AUTOGRAPH", "4WD", "86617", "86", False, QX80_CHART),
    ("QX80", "SPORT", "4WD", "86417", "86", False, QX80_CHART),
    ("QX80", "LUXE", "2WD", "86317", "86", False, QX80_CHART),
    ("QX80", "LUXE", "4WD", "86217", "86", False, QX80_CHART),
    ("QX80", "PURE", "2WD", "86117", "86", False, QX80_CHART),
    ("QX80", "PURE", "4WD", "86017", "86", False, QX80_CHART),
    # QX80 — older generation explicitly visible on the chart (priced BASE where the reviewed evidence shows it)
    ("QX80", "AUTOGRAPH", "4WD", "83617", "83", False, QX80_CHART),
    ("QX80", "SPORT", "4WD", "83417", "83", True, QX80_CHART),
    ("QX80", "LUXE", "2WD", "83317", "83", False, QX80_CHART),
    ("QX80", "PURE", "4WD", "83017", "83", True, QX80_CHART),
]

# Package variants explicitly present on the reviewed charts (variant identity auto-resolves; demand-sharing
# across packages is review-gated — see identity.lineage). (order_code, package, priced).
QX80_PACKAGES = [
    ("86317", "PA1", False), ("86317", "SEA", False), ("86317", "PA1+SEA", False),
    ("86417", "DBI", False), ("86417", "SEA", False), ("86417", "PA2", False), ("86417", "DBI+PA2+SEA", False),
    ("83317", "PA1", True),
]
QX60_PACKAGES = [("84617", "TPA", True)]


def seed(store: TranslationStore, *, as_of="2026-08-19", actor="system", auto_resolve_identity=True):
    """Governed, IDEMPOTENT initialization from the reviewed charts.

      * raw OBSERVATIONS (source truth) — immutable;
      * literal SAME_AS mappings (colour/model-line/interior the chart states) -> APPROVED (deterministic);
      * family / package VARIANT identity of an exact order code -> APPROVED when auto_resolve_identity (the
        default) because the chart states it deterministically; demand-SHARING relationships are NOT created
        here (they are review-gated in identity.lineage).

    Insert-if-absent everywhere; a re-run never reverts a human (or prior auto) decision. Returns counts."""
    counts = {"observations": 0, "approved_mappings": 0, "variant_identities": 0, "auto_approved_identities": 0}

    def obs(stype, raw, chart):
        store.record_observation(PORTAL, stype, raw, as_of=as_of, proof_ref=chart, actor=actor)
        counts["observations"] += 1

    def sem(stype, raw, name, scope, chart):
        obs(stype, raw, chart)
        if store.import_semantic(SemanticMapping(PORTAL, stype, raw, raw, name, scope, "approved", (chart,)),
                                 actor=actor, at=as_of):
            counts["approved_mappings"] += 1

    for code2, model in MODEL_LINE:
        if store.import_semantic(SemanticMapping(PORTAL, "model_code", code2, model, model, "", "approved",
                                                 (QX80_CHART,)), actor=actor, at=as_of):
            counts["approved_mappings"] += 1
    for raw, name in QX80_EXTERIOR:
        sem("exterior", raw, name, "QX80", QX80_CHART)
    for raw, name in QX60_EXTERIOR:
        sem("exterior", raw, name, "QX60", QX60_CHART)
    for raw, name in QX65_EXTERIOR:
        sem("exterior", raw, name, "QX65", QX65_CHART)
    for raw, name, scope in INTERIOR:
        proof = {"QX80": QX80_CHART, "QX60": QX60_CHART, "QX65": QX65_CHART}.get(scope, QX80_CHART)
        sem("interior", raw, name, scope, proof)

    # ---- family / variant identity (deterministic from the exact order code) ----
    def add_row(model, trim, drive, code, gen, pkg, base, priced, chart):
        fam = FamilyKey(FR, model, trim, drive)
        store.record_observation(PORTAL, "model_code", code, as_of=as_of, proof_ref=chart, actor=actor)
        counts["observations"] += 1
        r = VariantRow(fam, code, gen, pkg, base, "seen_latest", priced, derive_orderability("seen_latest", priced),
                       (chart,))
        if store.add_variant_row(r, actor=actor, at=as_of):
            counts["variant_identities"] += 1
        if auto_resolve_identity:
            # deterministic identity from the reviewed chart -> approve automatically (audited by the store)
            if store.approve_variant(fam, code, gen, pkg, actor=f"{actor}:auto-resolve-identity", at=as_of):
                counts["auto_approved_identities"] += 1

    for model, trim, drive, code, gen, priced, chart in FAMILY_CODES:
        add_row(model, trim, drive, code, gen, "BASE", True, priced, chart)
    # package variants (identity only; demand-sharing is review-gated elsewhere)
    _fam_of = {code: (m, t, d, g, ch) for (m, t, d, code, g, _p, ch) in FAMILY_CODES}
    for code, pkg, priced in QX80_PACKAGES + QX60_PACKAGES:
        if code in _fam_of:
            m, t, d, g, ch = _fam_of[code]
            add_row(m, t, d, code, g, pkg, False, priced, ch)

    for fam in {FamilyKey(FR, m, t, d).as_str() for (m, t, d, *_x) in FAMILY_CODES}:
        store.set_policy(PreferredOrderPolicy(FamilyKey.parse(fam)), actor=actor, at=as_of, only_if_absent=True)
    # legacy count aliases kept for existing callers/tests
    counts["proposed_interpretations"] = counts["variant_identities"] - counts["auto_approved_identities"]
    return counts
