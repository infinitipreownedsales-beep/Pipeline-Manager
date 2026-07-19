# Elite Pipeline Manager

A new-car inventory **ordering engine** for a single INFINITI store (QX80, QX60,
QX65), ported out of Excel into a small, deterministic Python program.

> **The one hard requirement:** the app **recomputes everything from the two raw
> exports on every run** — no hidden state, no stale caches, no frozen cells.
> That reliability is the entire reason for the rebuild. Run it twice on the same
> inputs and you get byte-identical output; change one number in an export and
> everything downstream moves.

It ingests the two dealer exports → runs the engine → emits five clean tables.

## Easiest: the double-click app (no install, no terminal)

Open **`Pipeline-Manager.html`** (in the repo root) by double-clicking it — it
runs the entire engine in your web browser, fully offline. Paste your two
exports, pick the order month, click **Compute**, and all five tables appear.
Nothing is installed and nothing leaves your computer. Regenerate it after
changing the engine with `python3 build/gen_pipeline_html.py`.

Everything below is the same engine as a command-line tool, for scripting.

## Quick start

```bash
# runs against the bundled sample exports
python -m pipeline_manager

# your own exports, ordering in September as a CPO factory order
python -m pipeline_manager -i inventory.csv -s speed_to_sell.csv -m SEP --mode CPO

# machine-readable
python -m pipeline_manager --format json -o report.json
```

Inputs may be `.csv` or `.xlsx`. No third-party packages are needed for CSV; the
one optional dependency, `openpyxl`, is used only to read `.xlsx` inputs.

```
python -m pipeline_manager --help
```

| flag | meaning |
|------|---------|
| `-i, --inventory` | Inventory Summary export (16 cols) |
| `-s, --sales` | Speed-to-Sell export (sales history) |
| `-m, --order-month` | month you **place** the order (`1..12` or `JAN..DEC`) |
| `--mode` | `CPO` (future factory order) · `PPO` · `MID-MONTH` (both = right-now) |
| `-c, --config` | optional `config.json` (control lists — see `config.example.json`) |
| `--today` | override "today" (`YYYY-MM-DD`) for reproducible runs |
| `--format` | `text` (default) or `json` |

## The two inputs

1. **Inventory Summary** — `Stock#, Serial, Status, MY, Model Line, Model Code,
   Description, Trans, Ext, Int, MSRP, Inv, Location, DIS, ETA, Production Month`.
   `Location = DLR-INV` is on-lot; `SIT`/`ONS`/`NNA-INV` are inbound pipeline.
2. **Speed-to-Sell** — `Sales Month, Stock#, Model, VIN, DAYS TO SELL, MODEL CODE,
   EXT CODE, INT CODE`, ~23 months of history.

Everything a human turns to steer the engine — order month, mode, allocations,
the suppress/demote/override lists, the demo roster, aged-unit brakes, the
outbound dealer **trade log** — is *control state*, not data. It lives in
`config.json` (see `config.example.json`), defaulting to the state the source
workbook shipped with. Each outbound trade (`{date, code, ext, int, days}`) is a
sale out the other door: its days-in-stock grades that config's speed to enter
and exit inventory exactly like a showroom sale (a 15-day trade reads fast, a
115-day trade slow), feeding DTS, recent demand, and the sell/wholesale rate.
The app has an editable trade-log panel; the CLI reads it from `config.json`.

## The five outputs

1. **Order Priority** — ranked `✓ BUILD` / `↑ alt` / `○ option` worklist with
   NEED per config, cut over by each model's allocation.
2. **Overstock / Wholesale** — over-target configs, wholesale-now counts, aged flags.
3. **Wholesale VIN sheet** — printable, VIN-led list of aged eligible units.
4. **Demo Dashboard** — units pulled from sellable inventory, ages, swap flags.
5. **Pace Check** — actual vs predicted 60-day pace per model, with a read.

The app also has an editable **demo roster** (add a Stock# to pull a unit for an
exec, set its start date and a driver/reason note, or ↩ Return it), a
**previous-loaner** list (enter when a unit was taken out as a demo and when it
returned; the engine subtracts only that hidden demo stretch from days-in-stock,
so real market time = DMS − days-out stays true — and demos and previous loaners
are never wholesale-listed because of the miles), a **print selector** (🖨 Print
→ choose which dashboards go on the page), and **collapsible sections** (click
any header to fold it away). **Roster control** lets you suppress discontinued
combos (a bare code drops the whole trim — they leave the order suggestions but
their stock still counts and still shows in overstock) and add orderable combos
the engine doesn't carry.

Plus an **Executive Demo Board** — per model, the best *proven fast-moving*
combos to put executives into (short days-to-sell so a demo still resells
quickly once it has miles; repeat demand only, never a one-off), VIN-led where
in stock and flagged to order when not.

And a **Loaner / ICV Program** dashboard — which units to cycle through the
courtesy fleet without losing money on the *preowned* side, done as three math
problems: **(1)** the true cost per combo (invoice); **(2)** the used value — what
a comparable current / 1-model-year-old unit sells for, modeled until you paste
real data as **80% of the cheapest new price**, where cheapest-new = *invoice −
rebate* (what a customer can buy a new one for); **(3)** the result — the one-time
ICV allowance, the 1.25%/month write-down, and the $2,500 velocity bonus reduce
the cost basis *only when the unit retires from the fleet*, and **preowned gross =
used value − that adjusted cost** tells you whether the resale profits or is
**upside down** (cost above street/auction value — you'd re-buy it cheaper). The
board ranks candidates by that gross, flags upside-down units, checks the bonus
window, and shows the in-service fleet with each unit's age, miles, ICV earned
and a cascading release schedule to hold the fleet target. Used velocity and price
come from your own used sales and public wholesale/auction comps when pasted;
otherwise the 80% floor stands in. All rebate / ICV / write-down / bonus / price
figures are editable.

## How the engine thinks (the short version)

Every unit and every sale is reduced to one **config key**: `Model | 4-digit Code
| Ext | Int` (e.g. `QX80|8381|QBE|D`). From the sales history it computes, per
config: average **DTS**, lifetime **TOTAL**, **R90/R180** (recent windows), and
**PRATE** — the backtested blend of the 90- and 180-day pace, each divided by
*elapsed* time and expressed per 60 days. PRATE drives a velocity **floor**
(gated by the 90-day "paperweight veto"), momentum bumps it to a **base**, and a
merit-tested, momentum-earned **seasonality** multiplier (computed live per
model) turns base into a **target** at the arrival month. **NEED** is the target
minus what you'll actually hold when the order lands (a mode-dependent
projection), plus loaner add-ons and manual overrides.

Design notes that matter (learned the hard way, preserved here):

- **Numeric fields arrive as text** — everything is coerced before comparison.
- **Demo Stock#s are mangled** (real stock# + driver name) — matched by prefix.
- **Not-found ≠ error.** A genuinely new combo → base 1 (stock one, watch it); a
  known combo the math zeroes → base 0 (never order off nothing). Kept separate.
- **Recent pace, not lifetime average** — sales counts measure supply, not demand.
- **Seasonality must be earned by momentum**, or peak season inflates dead configs.
- **Legacy QX50/QX55** feed QX65 at the model level only; they never drag the
  fast new QX65 configs over the paperweight line.

## Validating against the source workbook

The engine is validated cell-for-cell against the original workbook
(recalculated 2026-07-17). With the workbook's own settings it reproduces, with
zero mismatches: every per-config metric, both seasonality curves, on-lot,
projection-at-arrival, target, NEED, and the full ranked Order Priority list.

```bash
python pipeline_manager/tests/test_engine.py     # or: pytest pipeline_manager/tests
```

### One deliberate difference from the workbook

- **CPO arrival window** is, by default, `"auto"`: a continuous, trend-weighted
  production→arrival lead measured from each unit's production month and arrival
  date (inbound = planned ETA − production; on-lot = realized). Because it is
  fractional, seasonality at arrival is *interpolated* between months rather than
  snapping onto a single peak month — which is what otherwise inflates a build.
  `order_lead_pad` adds any order→production slotting time the exports can't see.
  Pin it manually with `cpo_windows` (e.g. `{"QX80":3,"QX60":2,"QX65":2}` for the
  brief's fixed months, or `{"QX80":5,"QX60":5,"QX65":1}` to reproduce the
  workbook's exact numbers — the engine validates against those cell-for-cell).
- **Wholesale eligibility** uses the brief's `MAX(60, DTS)` age floor (the
  workbook used 45); young inventory is never wholesale-flagged.
- **Continuous base** (`smooth_base`, default on): the 60-day pace is carried as
  a continuous value and rounded only once, at the final order number. The
  workbook rounded the pace into an integer floor *early*, which let a config
  sitting on a rounding boundary flip its base by a whole unit day-to-day (and
  seasonality then amplified it). Set `smooth_base: false` for the legacy
  behavior (its parity tests pin it off).

## Files

```
pipeline_manager/
  keys.py       key construction, model mapping, text→number coercion, Excel round
  ingest.py     read inventory + sales (.csv/.xlsx), coerce, build keys
  engine.py     the recompute: metrics → seasonality → position → base/target/NEED
  loaner.py     ICV/courtesy-fleet economics: preowned velocity + write-down P&L
  reports.py    the output tables
  cli.py        argparse entry point + text/JSON rendering
  config.py     Settings + control-state defaults + roster loader
  roster_default.json   the orderable combo roster (74 configs)
  config.example.json   documented control-state template
  sample_data/  inventory.csv, sales.csv (a real anonymised snapshot)
  tests/        validation against the workbook reference
```
