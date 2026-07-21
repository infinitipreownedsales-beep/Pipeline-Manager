"""Read the two dealer exports into clean, typed records.

Inputs (see the brief §2):
  A. Inventory Summary  — 16 columns, current on-lot + inbound pipeline.
  B. Speed-to-Sell      — ~23 months of sales history.

Both are accepted as .csv or .xlsx.  All numeric fields are coerced immediately
(they routinely arrive as text), and every row is reduced to a config key so the
engine never has to think about raw codes again.
"""

from __future__ import annotations

import csv
import datetime as _dt
import os
import re
from dataclasses import dataclass, field

from .keys import (
    build_key,
    coerce_num,
    digits_only,
    key_from_sales_code,
    model_from_code,
    model_year_from_code,
)

_MONTHS = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]


# --------------------------------------------------------------------------- #
# Records
# --------------------------------------------------------------------------- #
@dataclass
class InventoryUnit:
    stock: str
    serial: str
    status: str
    my: str
    model: str            # QX80 / QX60 / QX65
    model_code: str       # raw 5-digit
    description: str
    trans: str
    ext: str
    interior: str
    msrp: float
    inv_cost: float
    location: str
    dis: float            # days-in-stock (coerced to number)
    eta: str
    production_month: str
    key: str
    arrival_month: int    # calendar month 1..12 an inbound unit lands, 0 if on lot
    model_year: int | None
    # Set during the run for a unit flagged as a returned loaner: its real days
    # on the retail market (from re-entry), which overrides the inflated DMS
    # days-in-stock for all aging/wholesale math.
    prev_loaner: bool = False
    retail_dis: float | None = None

    @property
    def eff_dis(self) -> float:
        """Days-in-stock to use for aging: the retail clock for a returned
        loaner (hidden from the public until it reappeared), else raw DIS."""
        return self.retail_dis if self.retail_dis is not None else self.dis

    @property
    def is_dlr_inv(self) -> bool:
        return self.location.strip().upper() == "DLR-INV"

    @property
    def is_inbound(self) -> bool:
        # SIT / ONS / NNA-INV (anything not on the lot) is pipeline.
        return not self.is_dlr_inv


@dataclass
class Sale:
    sales_month: int      # YYYYMM
    stock: str
    model_desc: str
    vin: str
    days_to_sell: float | None
    model_code: str       # 4-digit
    ext: str
    interior: str
    model: str            # QX80 / QX60 / QX65
    key: str
    midx: int             # year*12 + month
    first_vin: bool = field(default=True)


# --------------------------------------------------------------------------- #
# Generic tabular loader (csv or xlsx)
# --------------------------------------------------------------------------- #
def _read_rows(path: str) -> list[list]:
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xlsm"):
        import openpyxl  # imported lazily so csv-only users need no dependency
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        ws = wb.active
        return [list(r) for r in ws.iter_rows(values_only=True)]
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return [row for row in csv.reader(fh)]


def _find_header(rows: list[list], must_have: list[str]) -> int:
    """Return the index of the header row (matched case-insensitively)."""
    want = {w.lower() for w in must_have}
    for i, row in enumerate(rows):
        cells = {str(c).strip().lower() for c in row if c not in (None, "")}
        if want <= cells:
            return i
    raise ValueError(f"Could not find a header row containing {must_have} in the file.")


def _colmap(header: list) -> dict:
    return {str(c).strip().lower(): i for i, c in enumerate(header) if c not in (None, "")}


def _cell(row: list, idx: int):
    return row[idx] if idx is not None and idx < len(row) else None


# --------------------------------------------------------------------------- #
# ETA -> arrival calendar month
# --------------------------------------------------------------------------- #
def parse_arrival_month(location: str, eta) -> int:
    """Month (1..12) an inbound unit is expected to land; 0 if already on lot."""
    if location.strip().upper() == "DLR-INV":
        return 0
    if eta is None or str(eta).strip() == "":
        return 0
    if isinstance(eta, _dt.datetime) or isinstance(eta, _dt.date):
        return eta.month
    s = str(eta).strip()
    # "Month of August"
    m = re.search(r"month of\s+([a-z]+)", s, re.I)
    if m and m.group(1).lower() in _MONTHS:
        return _MONTHS.index(m.group(1).lower()) + 1
    # Any explicit calendar date, optionally prefixed with "Week of".
    s2 = re.sub(r"week of", "", s, flags=re.I).strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%m-%d-%Y"):
        try:
            return _dt.datetime.strptime(s2, fmt).month
        except ValueError:
            pass
    # Bare month name.
    if s.lower() in _MONTHS:
        return _MONTHS.index(s.lower()) + 1
    return 0


# --------------------------------------------------------------------------- #
# Inventory
# --------------------------------------------------------------------------- #
def load_inventory(path: str) -> list[InventoryUnit]:
    rows = _read_rows(path)
    h = _find_header(rows, ["Stock#", "Model Code", "Location"])
    cm = _colmap(rows[h])

    def col(*names):
        for n in names:
            if n.lower() in cm:
                return cm[n.lower()]
        return None

    ci = {
        "stock": col("Stock#", "Stock"),
        # Serial IS the VIN in these exports; accept whatever the report labels it
        # so the Wholesale sheet always has a vehicle identifier to act on.
        "serial": col("Serial", "VIN", "Vin", "VIN#", "Vin#", "Serial#", "Serial Number"),
        "status": col("Status"),
        "my": col("MY"),
        "model_line": col("Model Line"),
        "model_code": col("Model Code"),
        "desc": col("Description"),
        "trans": col("Trans"),
        "ext": col("Ext"),
        "int": col("Int"),
        "msrp": col("MSRP"),
        "inv": col("Inv"),
        "loc": col("Location"),
        "dis": col("DIS"),
        "eta": col("ETA"),
        "prod": col("Production Month"),
    }

    units: list[InventoryUnit] = []
    for row in rows[h + 1:]:
        code = _cell(row, ci["model_code"])
        model_line = _cell(row, ci["model_line"])
        if code in (None, "") and (model_line in (None, "")):
            continue
        model = model_from_code(code) or (str(model_line).strip() if model_line else "")
        ext = (str(_cell(row, ci["ext"]) or "").strip())
        interior = (str(_cell(row, ci["int"]) or "").strip())
        location = str(_cell(row, ci["loc"]) or "").strip()
        eta = _cell(row, ci["eta"])
        units.append(
            InventoryUnit(
                stock=str(_cell(row, ci["stock"]) or "").strip(),
                serial=str(_cell(row, ci["serial"]) or "").strip(),
                status=str(_cell(row, ci["status"]) or "").strip(),
                my=str(_cell(row, ci["my"]) or "").strip(),
                model=model,
                model_code=digits_only(code),
                description=str(_cell(row, ci["desc"]) or "").strip(),
                trans=str(_cell(row, ci["trans"]) or "").strip(),
                ext=ext,
                interior=interior,
                msrp=coerce_num(_cell(row, ci["msrp"])),
                inv_cost=coerce_num(_cell(row, ci["inv"])),
                location=location,
                dis=coerce_num(_cell(row, ci["dis"])),
                eta="" if eta is None else str(eta).strip(),
                production_month=str(_cell(row, ci["prod"]) or "").strip(),
                key=build_key(model, code, ext, interior),
                arrival_month=parse_arrival_month(location, eta),
                model_year=model_year_from_code(code),
            )
        )
    return units


# --------------------------------------------------------------------------- #
# Speed-to-Sell (sales history)
# --------------------------------------------------------------------------- #
def load_sales(path: str) -> list[Sale]:
    rows = _read_rows(path)
    h = _find_header(rows, ["Sales Month", "VIN", "MODEL CODE"])
    cm = _colmap(rows[h])

    def col(*names):
        for n in names:
            if n.lower() in cm:
                return cm[n.lower()]
        return None

    ci = {
        "smonth": col("Sales Month"),
        "stock": col("Stock#", "Stock"),
        "model": col("Model"),
        "vin": col("VIN"),
        "dts": col("DAYS TO SELL", "Days to Sell"),
        "code": col("MODEL CODE", "Model Code"),
        "ext": col("EXT CODE", "Ext Code"),
        "int": col("INT CODE", "Int Code"),
    }

    seen_vins: set[str] = set()
    sales: list[Sale] = []
    for row in rows[h + 1:]:
        raw_month = _cell(row, ci["smonth"])
        if raw_month in (None, ""):
            continue
        try:
            smonth = int(round(coerce_num(raw_month)))
        except (TypeError, ValueError):
            continue
        if smonth < 100000:  # not a YYYYMM value
            continue
        year, month = divmod(smonth, 100)
        if not (1 <= month <= 12):
            continue
        code = _cell(row, ci["code"])
        ext = str(_cell(row, ci["ext"]) or "").strip()
        interior = str(_cell(row, ci["int"]) or "").strip()
        vin = str(_cell(row, ci["vin"]) or "").strip()
        dts_raw = _cell(row, ci["dts"])
        dts = coerce_num(dts_raw, default=None) if dts_raw not in (None, "") else None
        first_vin = True
        if vin:
            first_vin = vin not in seen_vins
            seen_vins.add(vin)
        sales.append(
            Sale(
                sales_month=smonth,
                stock=str(_cell(row, ci["stock"]) or "").strip(),
                model_desc=str(_cell(row, ci["model"]) or "").strip(),
                vin=vin,
                days_to_sell=dts,
                model_code=digits_only(code),
                ext=ext,
                interior=interior,
                model=model_from_code(code),
                key=key_from_sales_code(code, ext, interior),
                midx=year * 12 + month,
                first_vin=first_vin,
            )
        )
    return sales
