"""Command-line entry point.

    python -m pipeline_manager --inventory inv.csv --sales sts.csv \
        --order-month SEP --mode CPO

Reads the two exports (+ optional config.json), runs the engine from scratch,
and prints the five worklists.  Nothing is written back; run it again and it
recomputes from the same inputs — deterministically — every time.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys

from . import reports
from .config import MONTH_NAMES, Settings, month_num
from .engine import run
from .ingest import load_inventory, load_sales

_PKG = os.path.dirname(os.path.abspath(__file__))


# --------------------------------------------------------------------------- #
# Text rendering helpers
# --------------------------------------------------------------------------- #
def _table(headers, rows, aligns=None):
    cols = list(zip(*([headers] + rows))) if rows else [[h] for h in headers]
    widths = [max(len(str(c)) for c in col) for col in cols]
    aligns = aligns or ["<"] * len(headers)
    def fmt(row):
        return "  ".join(f"{str(v):{a}{w}}" for v, w, a in zip(row, widths, aligns))
    line = fmt(headers)
    sep = "  ".join("-" * w for w in widths)
    return "\n".join([line, sep] + [fmt(r) for r in rows])


def _fmt_dts(d):
    return "—" if d in (None, "") else str(int(d))


def render_text(res, rep) -> str:
    s = res.settings
    tb = res.time
    out = []
    W = 78
    out.append("=" * W)
    out.append("ELITE PIPELINE MANAGER".center(W))
    out.append(f"order month: {MONTH_NAMES[s.order_month - 1]}    mode: {s.mode}"
               f"    as of: {tb.today.isoformat()}".center(W))
    out.append("=" * W)
    latest = f"{tb.latest_midx // 12}-{tb.latest_midx % 12:02d}"
    out.append(f"Sales history: {rep['data_health']['span_months']} months "
               f"(newest {latest}{', OPEN/partial' if tb.latest_open else ''}); "
               f"90-day window spans {rep['data_health']['window_90_spans']} mo elapsed.")
    out.append(f"Learned configs: {rep['data_health']['learned_configs']}    "
               f"Roster combos: {len(s.roster)}    "
               f"Sold-but-unrostered: {len(rep['data_health']['orphans'])}")
    if s.mode == "CPO" and res.arrival_windows:
        leads = "   ".join(f"{m} {res.arrival_windows[m]:.1f}mo"
                           for m in ("QX80", "QX60", "QX65"))
        out.append(f"Arrival lead (production->lot, data-driven): {leads}")
    out.append("")

    # 1. Order Priority
    out.append("#" * W)
    out.append("1) ORDER PRIORITY — ranked BUILD / alt / option worklist")
    out.append("#" * W)
    for model in ("QX80", "QX60", "QX65"):
        blk = rep["order_priority"][model]
        out.append(f"\n{model}   (allocated this window: {blk['allocation']}   "
                   f"total real NEED: {blk['total_need']})")
        rows = [[r["rank"], r["tier"], r["trim"], r["ext"], r["int"],
                 _fmt_dts(r["dts"]), r["mom"], r["need"], r["cumulative"]]
                for r in blk["rows"]]
        out.append(_table(
            ["#", "BUILD?", "TRIM", "EXT", "INT", "DTS", "MOMENTUM", "NEED", "CUM"],
            rows, aligns=["<", "<", "<", "<", "<", ">", "<", ">", ">"]))

    # 1b. Supply feasibility — which workflows can currently satisfy each shortage
    sf = rep.get("supply_feasibility", [])
    if sf:
        cyc = sf[0].get("cycle_position", "")
        out.append("\n" + "#" * W)
        out.append(f"1b) SUPPLY FEASIBILITY — workflows that can satisfy each shortage now ({cyc} of cycle)")
        out.append("#" * W)
        rows = []
        for r in sf:
            feas = ", ".join(r["feasible"]) or "none in time"
            infeas = "   ".join(f"{w['workflow']}: {w['reason']}"
                                for w in r["workflows"] if not w["feasible"])
            rows.append([r["model"], r["trim"], r["ext"], r["int"], r["need"],
                         r["demand_open_month"], feas, infeas])
        out.append(_table(
            ["MODEL", "TRIM", "EXT", "INT", "NEED", "NEEDED", "FEASIBLE NOW", "NOT FEASIBLE (why)"],
            rows, aligns=["<", "<", "<", "<", ">", "<", "<", "<"]))

    # 2. Overstock / Wholesale
    out.append("\n" + "#" * W)
    out.append("2) OVERSTOCK / WHOLESALE — over-target metal (order slower, don't dump)")
    out.append("#" * W)
    rows = [[r["model"], r["trim"], r["ext"], r["int"], r["on_hand"], r["target"],
             r["over"], r["wholesale_now"], r["inbound"], _fmt_dts(r["dts"]), r["aged"]]
            for r in rep["overstock"]]
    out.append(_table(
        ["MODEL", "TRIM", "EXT", "INT", "ONHAND", "TGT", "OVER", "WHOLE", "INB", "DTS", "AGED"],
        rows, aligns=["<", "<", "<", "<", ">", ">", ">", ">", ">", ">", ">"]) if rows
        else "  (nothing over target)")

    # 3. Wholesale VIN sheet
    out.append("\n" + "#" * W)
    out.append("3) WHOLESALE NOW — VIN sheet (aged, over-target, non-demo — print & send)")
    out.append("#" * W)
    rows = [[r["num"], r["stock"], r["vin_last6"], r["year"], r["model"],
             r["trim"], r["ext_int"], r["days_in_stock"]] for r in rep["wholesale_vins"]]
    out.append(_table(
        ["#", "STOCK", "VIN(6)", "YR", "MODEL", "TRIM", "EXT/INT", "DIS"], rows,
        aligns=["<", "<", "<", "<", "<", "<", "<", ">"]) if rows
        else "  (no units past their selling window)")

    # Executive Demo Board
    out.append("\n" + "#" * W)
    out.append("EXECUTIVE DEMO BOARD — best proven fast-movers to put execs in (VIN-led)")
    out.append("#" * W)
    for model in ("QX80", "QX60", "QX65"):
        picks = rep["executive_demos"][model]
        out.append(f"\n{model}")
        if not picks:
            out.append("  (no proven fast combo yet)")
        for i, p in enumerate(picks, 1):
            out.append(f"  {i}. {p['trim']} {p['ext']}/{p['int']}  "
                       f"[{p['reason']}]  on-lot {p['onlot']}")
            if p["units"]:
                for u in p["units"]:
                    msrp = f"  ${int(u['msrp']):,}" if u["msrp"] else ""
                    out.append(f"       VIN …{u['vin_last6']}  {u['year']} "
                               f"{u['ext_int']}  {u['dis']}d{msrp}")
            else:
                out.append("       (none in stock — order / allocate one)")

    # 4. Demo Dashboard
    out.append("\n" + "#" * W)
    out.append("4) DEMO DASHBOARD — units pulled from sellable inventory")
    out.append("#" * W)
    rows = [[r["stock"], r["vehicle"], r["days_in_stock"], r["days_as_demo"], r["swap"]]
            for r in rep["demo_dashboard"]]
    out.append(_table(["STOCK", "VEHICLE", "DIS", "DAYS-DEMO", "SWAP?"], rows,
                      aligns=["<", "<", ">", ">", "<"]) if rows else "  (no demos listed)")

    # 5. Pace Check
    out.append("\n" + "#" * W)
    out.append("5) PACE CHECK — actual vs predicted 60-day pace")
    out.append("#" * W)
    rows = [[r["model"], r["actual_90"], r["act_60_pace"], r["pred_60_pace"],
             f"{r['variance']:+}", r["read"], f"{r['coverage']*100:.0f}%"]
            for r in rep["pace_check"]]
    out.append(_table(
        ["MODEL", "ACT90", "ACT60", "PRED60", "VAR", "READ", "COV"], rows,
        aligns=["<", ">", ">", ">", ">", "<", ">"]))

    if rep["data_health"]["orphans"]:
        out.append("\n" + "-" * W)
        out.append("DATA HEALTH — sold but not on the order roster (unseen by ordering):")
        top = rep["data_health"]["orphans"][:12]
        out.append("  " + ",  ".join(f"{o['key']} ({o['sales']})" for o in top))
        if len(rep["data_health"]["orphans"]) > 12:
            out.append(f"  ... and {len(rep['data_health']['orphans']) - 12} more "
                       f"(many are discontinued/legacy configs — expected).")
    out.append("")
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# JSON rendering
# --------------------------------------------------------------------------- #
def _jsonable(rep, res):
    return {
        "generated": res.time.today.isoformat(),
        "settings": {"order_month": MONTH_NAMES[res.settings.order_month - 1],
                     "mode": res.settings.mode,
                     "allocations": res.settings.allocations,
                     "cpo_windows": res.settings.cpo_windows},
        "time_base": {"latest_month": rep["data_health"]["latest_month"],
                      "span_months": rep["data_health"]["span_months"],
                      "part_frac": rep["data_health"]["part_frac"]},
        **rep,
    }


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="pipeline_manager",
        description="Deterministic new-car ordering engine — recomputes everything "
                    "from the two dealer exports on every run.")
    p.add_argument("--inventory", "-i",
                   default=os.path.join(_PKG, "sample_data", "inventory.csv"),
                   help="Inventory Summary export (.csv or .xlsx).")
    p.add_argument("--sales", "-s",
                   default=os.path.join(_PKG, "sample_data", "sales.csv"),
                   help="Speed-to-Sell export (.csv or .xlsx).")
    p.add_argument("--config", "-c", default=None,
                   help="Optional config.json with settings + control lists.")
    p.add_argument("--order-month", "-m", default=None,
                   help="Month you place the order (1..12 or JAN..DEC). "
                        "Overrides config.")
    p.add_argument("--mode", default=None, choices=["CPO", "PPO", "MID-MONTH"],
                   help="CPO (future factory order) / PPO / MID-MONTH. Overrides config.")
    p.add_argument("--today", default=None,
                   help="Override 'today' (YYYY-MM-DD) for reproducible runs.")
    p.add_argument("--format", "-f", default="text",
                   choices=["text", "json"], help="Output format.")
    p.add_argument("--output", "-o", default=None, help="Write output to a file.")
    args = p.parse_args(argv)

    settings = Settings.load(args.config)
    if args.order_month is not None:
        settings.order_month = month_num(args.order_month)
    if args.mode is not None:
        settings.mode = args.mode
    today = _dt.date.fromisoformat(args.today) if args.today else None

    try:
        inventory = load_inventory(args.inventory)
        sales = load_sales(args.sales)
    except (FileNotFoundError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    res = run(inventory, sales, settings, today=today)
    rep = reports.build_all(res)

    text = json.dumps(_jsonable(rep, res), indent=2, default=str) \
        if args.format == "json" else render_text(res, rep)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print(f"wrote {args.output}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
