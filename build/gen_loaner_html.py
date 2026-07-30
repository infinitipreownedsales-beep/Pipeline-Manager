#!/usr/bin/env python3
"""Generate the self-contained Loaner-Intelligence.html dashboard.

Mirrors gen_pipeline_html.py: the JS engine (a 1:1 port of
pipeline_manager/loaner_intel.py), the dashboard renderer, and the historical
sales CSV are inlined into one offline HTML file.

    python3 build/gen_loaner_html.py   ->  ./Loaner-Intelligence.html
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

HTML = open(os.path.join(HERE, "loaner_template.html"), encoding="utf-8").read()
ENGINE = open(os.path.join(HERE, "loaner_engine.js"), encoding="utf-8").read()
RENDER = open(os.path.join(HERE, "loaner_render.js"), encoding="utf-8").read()
DATA = open(os.path.join(ROOT, "pipeline_manager", "sample_data",
                         "loaner_history.csv"), encoding="utf-8-sig").read()

out = (HTML
       .replace("__ENGINE__", ENGINE)
       .replace("__RENDER__", RENDER)
       .replace("__DATA_JSON__", json.dumps(DATA)))
open(os.path.join(ROOT, "Loaner-Intelligence.html"), "w", encoding="utf-8").write(out)
print("wrote Loaner-Intelligence.html (%d KB)" % (len(out) // 1024))
