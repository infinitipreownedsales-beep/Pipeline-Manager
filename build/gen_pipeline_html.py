#!/usr/bin/env python3
"""Generate the self-contained Pipeline-Manager.html dashboard.

The whole engine (ported 1:1 from the Python package) plus a rich, workbook-style
dashboard is inlined into one HTML file with no external dependencies, so a
non-technical user can double-click it and run everything in a browser — offline,
nothing installed, nothing leaves the machine.

    python3 build/gen_pipeline_html.py   ->  ./Pipeline-Manager.html
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ROSTER = json.load(open(os.path.join(ROOT, "pipeline_manager", "roster_default.json")))
DEFAULTS = {
    "suppress": [],
    "demote": [{"model": "", "ext": "", "int": "N"}],
    "overrides": [{"key": "QX60|8411|QBE|K", "qty": 8}],
    "demo_stocks": ["N15106", "N15118", "N15126", "N15145"],
    "demo_starts": {"N15106": "2026-05-08", "N15118": "2026-04-29",
                    "N15126": "2026-05-07", "N15145": "2026-06-07"},
}
SAMPLE_INV = open(os.path.join(ROOT, "pipeline_manager", "sample_data", "inventory.csv")).read()
SAMPLE_SALES = open(os.path.join(ROOT, "pipeline_manager", "sample_data", "sales.csv")).read()

HTML = open(os.path.join(HERE, "app_template.html"), encoding="utf-8").read()
REPO = open(os.path.join(HERE, "repository.js"), encoding="utf-8").read()
LEARNING = open(os.path.join(HERE, "learning_engine.js"), encoding="utf-8").read()
ENGINE = open(os.path.join(HERE, "app_engine.js"), encoding="utf-8").read()
RENDER = open(os.path.join(HERE, "app_render.js"), encoding="utf-8").read()
WIRING = open(os.path.join(HERE, "app_wiring.js"), encoding="utf-8").read()

# Loaner Intelligence depreciation engine, wrapped so its internals can't collide
# with the main app's globals; only window.LoanerIntel is exposed.
LOANER_ENGINE_SRC = open(os.path.join(HERE, "loaner_engine.js"), encoding="utf-8").read()
LOANER_ENGINE = (
    ";(function(){\n"
    + LOANER_ENGINE_SRC.replace('"use strict";', '"use strict";', 1)
    + "\nfunction predictResale(a,model,trim,ext,age){ if(!a||!a.predictor) return null;"
      " var r=a.predictor(model,trim||null,null,ext||null,null,age); return (r&&r.ok)?r:null; }"
    + "\nwindow.LoanerIntel={loadCSV:loadCSV,analyze:analyze,predictResale:predictResale,AGE_BUCKETS:AGE_BUCKETS};"
    + "\n})();"
)
LOANER_HISTORY = open(os.path.join(ROOT, "pipeline_manager", "sample_data",
                                   "loaner_history.csv"), encoding="utf-8-sig").read()

out = (HTML
       .replace("__REPO__", REPO)
       .replace("__LEARNING_ENGINE__", LEARNING)
       .replace("__LOANER_ENGINE__", LOANER_ENGINE)
       .replace("__ENGINE__", ENGINE)
       .replace("__RENDER__", RENDER)
       .replace("__WIRING__", WIRING)
       .replace("__ROSTER__", json.dumps(ROSTER, separators=(",", ":")))
       .replace("__DEFAULTS__", json.dumps(DEFAULTS, separators=(",", ":")))
       .replace("__SAMPLE_INV__", json.dumps(SAMPLE_INV))
       .replace("__SAMPLE_SALES__", json.dumps(SAMPLE_SALES))
       .replace("__LOANER_HISTORY_JSON__", json.dumps(LOANER_HISTORY)))
open(os.path.join(ROOT, "Pipeline-Manager.html"), "w", encoding="utf-8").write(out)
print("wrote Pipeline-Manager.html (%d KB)" % (len(out) // 1024))
