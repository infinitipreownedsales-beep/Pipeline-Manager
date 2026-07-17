#!/usr/bin/env python3
"""Generate the self-contained Pipeline-Manager.html app.

The whole engine (ported 1:1 from the Python package) is inlined into one HTML
file with no external dependencies, so a non-technical user can double-click it
and run everything in a browser — no terminal, no install, no internet.

    python3 build/gen_pipeline_html.py

writes ./Pipeline-Manager.html
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ROSTER = json.load(open(os.path.join(ROOT, "pipeline_manager", "roster_default.json")))

# Default control state (mirrors config.py defaults / the source workbook).
DEFAULTS = {
    "suppress": [],
    "demote": [{"model": "", "ext": "", "int": "N"}],
    "overrides": [{"key": "QX60|8411|QBE|K", "qty": 8}],
    "demo_stocks": ["N15106", "N15118", "N15126", "N15145"],
    "demo_starts": {"N15106": "2026-05-08", "N15118": "2026-04-29",
                    "N15126": "2026-05-07", "N15145": "2026-06-07"},
    "allocations": {"QX80": 50, "QX60": 100, "QX65": 100},
    "cpo_windows": {"QX80": 3, "QX60": 2, "QX65": 2},
}

SAMPLE_INV = open(os.path.join(ROOT, "pipeline_manager", "sample_data", "inventory.csv")).read()
SAMPLE_SALES = open(os.path.join(ROOT, "pipeline_manager", "sample_data", "sales.csv")).read()

HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Elite Pipeline Manager</title>
<style>
  :root{
    --bg:#0d1117; --panel:#161b22; --panel2:#1c2330; --ink:#e6edf3; --muted:#8b949e;
    --line:#30363d; --accent:#3b82f6; --accent2:#1f6feb; --good:#2ea043; --warn:#d29922;
    --bad:#f85149; --build:#238636; --alt:#9e6a03; --opt:#1f6feb;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
    font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;}
  header{background:linear-gradient(120deg,#0b1a3a,#111827);border-bottom:1px solid var(--line);
    padding:20px 24px;position:sticky;top:0;z-index:10}
  header h1{margin:0;font-size:20px;letter-spacing:.5px}
  header .sub{color:var(--muted);font-size:13px;margin-top:4px}
  .wrap{max-width:1180px;margin:0 auto;padding:22px}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px;margin-bottom:18px}
  .card h2{margin:0 0 4px;font-size:16px}
  .card .hint{color:var(--muted);font-size:13px;margin-bottom:12px}
  .grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
  @media(max-width:820px){.grid2{grid-template-columns:1fr}}
  label{display:block;font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.4px;margin-bottom:6px}
  textarea{width:100%;height:150px;background:var(--panel2);color:var(--ink);border:1px solid var(--line);
    border-radius:8px;padding:10px;font:12px/1.4 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;resize:vertical}
  textarea.ok{border-color:var(--good)}
  select,input[type=date],input[type=number]{background:var(--panel2);color:var(--ink);
    border:1px solid var(--line);border-radius:8px;padding:8px 10px;font-size:14px}
  .row{display:flex;gap:16px;flex-wrap:wrap;align-items:flex-end}
  .row .fld{flex:0 0 auto}
  .filerow{display:flex;gap:10px;align-items:center;margin-top:8px;color:var(--muted);font-size:12px}
  button{cursor:pointer;border:none;border-radius:9px;font-size:15px;font-weight:600;padding:12px 22px}
  .primary{background:var(--accent2);color:#fff}
  .primary:hover{background:var(--accent)}
  .ghost{background:transparent;color:var(--muted);border:1px solid var(--line);font-weight:500;padding:8px 14px;font-size:13px}
  .ghost:hover{color:var(--ink)}
  .bigbtn{display:flex;gap:12px;align-items:center;margin-top:6px}
  .status{font-size:13px;color:var(--muted)}
  .err{color:var(--bad)}
  section.out{margin-top:8px}
  .outhead{display:flex;align-items:baseline;gap:10px;border-bottom:2px solid var(--accent2);padding-bottom:6px;margin:26px 0 12px}
  .outhead .n{background:var(--accent2);color:#fff;border-radius:6px;padding:2px 9px;font-weight:700;font-size:13px}
  .outhead h2{margin:0;font-size:17px}
  .outhead .meta{margin-left:auto;color:var(--muted);font-size:12px}
  table{width:100%;border-collapse:collapse;font-size:13px;margin-bottom:6px}
  th,td{text-align:left;padding:6px 9px;border-bottom:1px solid var(--line);white-space:nowrap}
  th{color:var(--muted);text-transform:uppercase;font-size:11px;letter-spacing:.4px;position:sticky}
  td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
  .modelband{background:var(--panel2);font-weight:700;padding:8px 9px;border-radius:6px;margin:14px 0 4px}
  .tier-build{color:#3fb950;font-weight:700}
  .tier-alt{color:#d29922;font-weight:700}
  .tier-opt{color:#58a6ff}
  .pill{border-radius:20px;padding:1px 9px;font-size:11px;font-weight:600}
  .m-ACCEL{background:#132e1a;color:#3fb950}
  .m-steady{background:#0d2440;color:#58a6ff}
  .m-cooling{background:#3a1d1d;color:#f85149}
  .m-oncadence{background:#2a2410;color:#d29922}
  .m-dormant{background:#21262d;color:#8b949e}
  .swap{color:var(--bad);font-weight:700}
  .read-AHEAD{color:#3fb950;font-weight:600}
  .read-ON{color:#58a6ff;font-weight:600}
  .read-BEHIND{color:#f85149;font-weight:600}
  .tblwrap{overflow-x:auto}
  .tag{display:inline-block;background:var(--panel2);border:1px solid var(--line);border-radius:6px;
    padding:1px 7px;font-size:11px;color:var(--muted);margin-right:6px}
  details summary{cursor:pointer;color:var(--muted);font-size:13px;margin-top:8px}
  .footnote{color:var(--muted);font-size:12px;margin-top:10px}
  @media print{
    header,.card,.noprint{display:none!important}
    body{background:#fff;color:#000}
    .outhead h2,.outhead .n{color:#000}
    #print-only-vin{display:block!important}
  }
  #print-only-vin{display:none}
</style>
</head>
<body>
<header>
  <h1>ELITE PIPELINE MANAGER</h1>
  <div class="sub">New-car ordering engine — recomputes everything from your two exports, every time. No install, no internet.</div>
</header>

<div class="wrap">

  <div class="card noprint">
    <h2>Step 1 — Paste your two exports</h2>
    <div class="hint">In your inventory / sales report, select all the cells (including the header row) and copy, then paste into the matching box below. You can also choose a saved <b>.csv</b> file. Nothing leaves your computer.</div>
    <div class="grid2">
      <div>
        <label>Inventory Summary</label>
        <textarea id="inv" placeholder="Paste the vehicle inventory export here (with its header row)…"></textarea>
        <div class="filerow"><input type="file" id="invfile" accept=".csv,.txt,.tsv"><span id="invstat"></span></div>
      </div>
      <div>
        <label>Speed-to-Sell (sales history)</label>
        <textarea id="sales" placeholder="Paste the Speed-to-Sell export here (with its header row)…"></textarea>
        <div class="filerow"><input type="file" id="salesfile" accept=".csv,.txt,.tsv"><span id="salesstat"></span></div>
      </div>
    </div>
    <div style="margin-top:10px"><button class="ghost" id="loadsample">Load sample data</button>
      <button class="ghost" id="clearall">Clear</button></div>
  </div>

  <div class="card noprint">
    <h2>Step 2 — Set the order</h2>
    <div class="row">
      <div class="fld"><label>Order month (when you place it)</label>
        <select id="ordmonth"></select></div>
      <div class="fld"><label>Mode</label>
        <select id="mode">
          <option value="CPO">CPO — future factory order</option>
          <option value="PPO">PPO — right-now</option>
          <option value="MID-MONTH">Mid-month — right-now</option>
        </select></div>
      <div class="fld"><label>As-of date</label><input type="date" id="today"></div>
      <div class="fld"><label>QX80 alloc</label><input type="number" id="a80" value="50" style="width:80px"></div>
      <div class="fld"><label>QX60 alloc</label><input type="number" id="a60" value="100" style="width:80px"></div>
      <div class="fld"><label>QX65 alloc</label><input type="number" id="a65" value="100" style="width:80px"></div>
    </div>
    <div class="bigbtn"><button class="primary" id="run">Compute order ▶</button>
      <span class="status" id="status"></span></div>
    <details><summary>Advanced — CPO arrival window (months)</summary>
      <div class="row" style="margin-top:8px">
        <div class="fld"><label>QX80</label><input type="number" id="w80" value="3" style="width:70px"></div>
        <div class="fld"><label>QX60</label><input type="number" id="w60" value="2" style="width:70px"></div>
        <div class="fld"><label>QX65</label><input type="number" id="w65" value="2" style="width:70px"></div>
        <span class="footnote">The brief's canonical windows. Set 5 / 5 / 1 to match the old workbook exactly.</span>
      </div>
    </details>
  </div>

  <div id="results"></div>
</div>

<script>
"use strict";
const ROSTER = __ROSTER__;
const DEFAULTS = __DEFAULTS__;
const SAMPLE = { inv: __SAMPLE_INV__, sales: __SAMPLE_SALES__ };
const MONTHS = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"];
const MODELS = ["QX80","QX60","QX65"];

/* ===================== keys / coercion ===================== */
function coerceNum(v, def){ def = def===undefined?0:def;
  if(v===null||v===undefined) return def;
  if(typeof v==="number") return v;
  let s=String(v).trim().replace(/,/g,""); if(s==="") return def;
  let n=parseFloat(s); return isNaN(n)?def:n; }
function digitsOnly(v){ if(v===null||v===undefined) return ""; return String(v).replace(/[^0-9]/g,""); }
function xround(v,d){ d=d||0; if(v===null||v===undefined) return null;
  let f=Math.pow(10,d), s=v*f;
  let r = s>=0 ? Math.floor(s+0.5) : Math.ceil(s-0.5);
  return r/f; }
const PREFIX={ "83":"QX80","84":"QX60","85":"QX65","81":"QX65","82":"QX65" };
function modelFromCode(c){ let d=digitsOnly(c); return d.length>=2?(PREFIX[d.slice(0,2)]||""):""; }
function code4(c){ let d=digitsOnly(c); return d.length>=4?d.slice(0,4):d; }
function modelYear(c){ let d=digitsOnly(c); return d.length===5?2020+parseInt(d[4],10):null; }
function normalizeCode(model,raw){ let d=digitsOnly(raw);
  if(model==="QX80"&&d.slice(0,3)==="834") return "8381";
  if(model==="QX60"&&d.slice(0,4)==="8461") return "8481";
  return code4(raw); }
function normalizeInt(model,code,ext,intr){ intr=(intr||"").trim();
  if(model==="QX80"&&code==="8381"&&(intr==="G"||intr==="D")) return "D"; return intr; }
function buildKey(model,raw,ext,intr){ if(!model) return "";
  let code=normalizeCode(model,raw);
  ext = ext!==null&&ext!==undefined ? String(ext).trim() : "";
  intr = normalizeInt(model,code,ext,intr);
  if(!code) return ""; return model+"|"+code+"|"+ext+"|"+intr; }

/* ===================== table parsing ===================== */
function parseCsvLine(line){ let out=[],cur="",q=false;
  for(let i=0;i<line.length;i++){ let ch=line[i];
    if(q){ if(ch==='"'){ if(line[i+1]==='"'){cur+='"';i++;} else q=false; } else cur+=ch; }
    else { if(ch==='"') q=true; else if(ch===","){ out.push(cur); cur=""; } else cur+=ch; } }
  out.push(cur); return out; }
function parseTable(text){
  text=text.replace(/\r\n/g,"\n").replace(/\r/g,"\n");
  let lines=text.split("\n").filter(l=>l.trim()!=="");
  if(!lines.length) return [];
  let hasTab = lines[0].indexOf("\t")>=0;
  return lines.map(l=> hasTab ? l.split("\t") : parseCsvLine(l));
}
function findHeader(rows, must){
  let want = must.map(x=>x.toLowerCase());
  for(let i=0;i<rows.length;i++){
    let cells = rows[i].map(c=>String(c==null?"":c).trim().toLowerCase());
    if(want.every(w=>cells.indexOf(w)>=0)) return i;
  }
  throw new Error("Could not find a header row with: "+must.join(", ")+". Make sure you copied the header row too.");
}
function colmap(header){ let m={}; header.forEach((c,i)=>{ let k=String(c==null?"":c).trim().toLowerCase(); if(k) m[k]=i; }); return m; }
function pick(cm){ for(let i=1;i<arguments.length;i++){ let n=arguments[i].toLowerCase(); if(n in cm) return cm[n]; } return null; }
function cell(row,idx){ return (idx!==null&&idx<row.length)?row[idx]:null; }

/* ===================== ingest ===================== */
const MONTHNAMES=["january","february","march","april","may","june","july","august","september","october","november","december"];
function parseArrivalMonth(location, eta){
  if(String(location).trim().toUpperCase()==="DLR-INV") return 0;
  if(eta===null||eta===undefined||String(eta).trim()==="") return 0;
  let s=String(eta).trim();
  let m=s.match(/month of\s+([a-z]+)/i);
  if(m && MONTHNAMES.indexOf(m[1].toLowerCase())>=0) return MONTHNAMES.indexOf(m[1].toLowerCase())+1;
  let s2=s.replace(/week of/i,"").trim();
  let d=new Date(s2);
  if(!isNaN(d.getTime()) && /\d/.test(s2)) return d.getMonth()+1;
  if(MONTHNAMES.indexOf(s.toLowerCase())>=0) return MONTHNAMES.indexOf(s.toLowerCase())+1;
  return 0;
}
function loadInventory(text){
  let rows=parseTable(text);
  let h=findHeader(rows,["Stock#","Model Code","Location"]);
  let cm=colmap(rows[h]);
  let ci={ stock:pick(cm,"Stock#","Stock"), serial:pick(cm,"Serial"), status:pick(cm,"Status"),
    my:pick(cm,"MY"), modelLine:pick(cm,"Model Line"), code:pick(cm,"Model Code"),
    desc:pick(cm,"Description"), trans:pick(cm,"Trans"), ext:pick(cm,"Ext"), int:pick(cm,"Int"),
    msrp:pick(cm,"MSRP"), inv:pick(cm,"Inv"), loc:pick(cm,"Location"), dis:pick(cm,"DIS"),
    eta:pick(cm,"ETA"), prod:pick(cm,"Production Month") };
  let units=[];
  for(let r=h+1;r<rows.length;r++){
    let row=rows[r];
    let code=cell(row,ci.code), ml=cell(row,ci.modelLine);
    if((code==null||code==="")&&(ml==null||ml==="")) continue;
    let model=modelFromCode(code)|| (ml?String(ml).trim():"");
    let ext=String(cell(row,ci.ext)||"").trim();
    let intr=String(cell(row,ci.int)||"").trim();
    let loc=String(cell(row,ci.loc)||"").trim();
    let eta=cell(row,ci.eta);
    units.push({ stock:String(cell(row,ci.stock)||"").trim(), serial:String(cell(row,ci.serial)||"").trim(),
      status:String(cell(row,ci.status)||"").trim(), my:String(cell(row,ci.my)||"").trim(),
      model:model, code:digitsOnly(code), desc:String(cell(row,ci.desc)||"").trim(),
      ext:ext, int:intr, msrp:coerceNum(cell(row,ci.msrp)), loc:loc,
      dis:coerceNum(cell(row,ci.dis)), key:buildKey(model,code,ext,intr),
      arr:parseArrivalMonth(loc,eta), myear:modelYear(code),
      isDlr: loc.toUpperCase()==="DLR-INV" });
  }
  return units;
}
function loadSales(text){
  let rows=parseTable(text);
  let h=findHeader(rows,["Sales Month","VIN","MODEL CODE"]);
  let cm=colmap(rows[h]);
  let ci={ smonth:pick(cm,"Sales Month"), stock:pick(cm,"Stock#","Stock"), model:pick(cm,"Model"),
    vin:pick(cm,"VIN"), dts:pick(cm,"DAYS TO SELL","Days to Sell"), code:pick(cm,"MODEL CODE","Model Code"),
    ext:pick(cm,"EXT CODE","Ext Code"), int:pick(cm,"INT CODE","Int Code") };
  let seen={}, sales=[];
  for(let r=h+1;r<rows.length;r++){
    let row=rows[r], raw=cell(row,ci.smonth);
    if(raw==null||raw==="") continue;
    let sm=Math.round(coerceNum(raw,-1)); if(sm<100000) continue;
    let year=Math.floor(sm/100), month=sm%100; if(month<1||month>12) continue;
    let code=cell(row,ci.code), ext=String(cell(row,ci.ext)||"").trim(), intr=String(cell(row,ci.int)||"").trim();
    let vin=String(cell(row,ci.vin)||"").trim();
    let dtsRaw=cell(row,ci.dts);
    let dts=(dtsRaw==null||dtsRaw==="")?null:coerceNum(dtsRaw,null);
    let firstVin=true; if(vin){ firstVin = !seen[vin]; seen[vin]=true; }
    sales.push({ sm:sm, model:modelFromCode(code), code:digitsOnly(code), ext:ext, int:intr,
      vin:vin, dts:dts, key:buildKey(modelFromCode(code),code,ext,intr),
      midx:year*12+month, firstVin:firstVin, stock:String(cell(row,ci.stock)||"").trim(),
      desc:String(cell(row,ci.model)||"").trim() });
  }
  return sales;
}

/* ===================== engine ===================== */
function daysInMonth(d){ return new Date(d.getFullYear(), d.getMonth()+1, 0).getDate(); }
function timeBase(sales, today){
  let midxs=sales.filter(s=>s.midx>0).map(s=>s.midx);
  let cur=today.getFullYear()*12+(today.getMonth()+1);
  if(!midxs.length) return {latest:0,earliest:0,cur:cur,part:1,span:1,el90:3,el180:6,open:false,today:today};
  let latest=Math.max.apply(null,midxs), earliest=Math.min.apply(null,midxs);
  let open = latest===cur;
  let part = open ? Math.max(0.05, today.getDate()/daysInMonth(today)) : 1;
  let span = Math.max(0.25,(latest-earliest+1)-(1-part));
  return {latest:latest,earliest:earliest,cur:cur,part:part,span:span,el90:2+part,el180:5+part,open:open,today:today};
}
function computeMetrics(sales, tb, roster){
  let M={};
  sales.forEach(s=>{
    if(!s.firstVin||!s.key||!s.model) return;
    let m=M[s.key]; if(!m){ m={key:s.key,model:s.model,code:s.code.slice(0,4),ext:s.ext,int:s.int,
      total:0,dtsSum:0,dtsCnt:0,r90:0,r180:0,dts:null,hist60:0,prate:0,momentum:"dormant",floor:0,base:0}; M[s.key]=m; }
    m.total++;
    if(s.dts!==null){ m.dtsSum+=s.dts; m.dtsCnt++; }
    if(s.midx>tb.latest-3) m.r90++;
    if(s.midx>tb.latest-6) m.r180++;
  });
  roster.forEach(c=>{ let k=c.model+"|"+c.code+"|"+c.ext+"|"+c.int;
    if(!M[k]) M[k]={key:k,model:c.model,code:c.code,ext:c.ext,int:c.int,total:0,dtsSum:0,dtsCnt:0,r90:0,r180:0,
      dts:null,hist60:0,prate:0,momentum:"dormant",floor:0,base:0}; });
  Object.values(M).forEach(m=>{
    m.dts = m.dtsCnt ? xround(m.dtsSum/m.dtsCnt,0) : null;
    m.hist60 = xround(m.total/tb.span*2,2);
    m.prate = m.r90/tb.el90 + m.r180/tb.el180;
    let recent60=m.r90/tb.el90*2, dtsOk60=(m.dts!==null&&m.dts<=60);
    if(m.r90>=2 && recent60>m.hist60*1.15 && dtsOk60) m.momentum="ACCEL";
    else if(m.r90===0 && m.r180>0) m.momentum="on cadence";
    else if(m.r90>0 && recent60<m.hist60*0.6) m.momentum="cooling";
    else if(m.r90>0) m.momentum="steady";
    else m.momentum="dormant";
    if(m.prate>=0.5 && m.dts!==null && m.dts<=90) m.floor=Math.max(1,xround(m.prate,0));
    else if(m.dts!==null && m.dts<=60 && m.r180>0) m.floor=1;
    else m.floor=0;
    let adj = m.momentum==="ACCEL"?1:(m.momentum==="cooling"?-1:0);
    m.base = m.floor===0?0:Math.max(1,m.floor+adj);
  });
  return M;
}
function computeSeasonality(sales, tb){
  let latestCalm = tb.latest?((tb.latest-1)%12)+1:0, out={};
  MODELS.forEach(model=>{
    let byMonth=new Array(12).fill(0);
    sales.forEach(s=>{ if(s.firstVin&&s.model===model&&s.midx>0) byMonth[(s.midx-1)%12]++; });
    let rates=[];
    for(let m=1;m<=12;m++){
      let occ=Math.max(1, Math.floor((tb.latest-m)/12)-Math.ceil((tb.earliest-m)/12)+1);
      occ = occ - (latestCalm===m?(1-tb.part):0); occ=Math.max(0.1,occ);
      rates.push(byMonth[m-1]/occ);
    }
    let avg=rates.reduce((a,b)=>a+b,0)/12;
    out[model]=rates.map(r=> avg===0?1:r/avg);
  });
  return out;
}
function isDemo(stock, prefixes){ return prefixes.some(p=>p&&stock.indexOf(p)===0); }
function computePositions(inv, metrics, s){
  let P={};
  inv.forEach(u=>{ if(!u.key) return;
    let p=P[u.key]; if(!p){ p={onlot:0,inbound:0,arrivals:{},stalled:0,aged:[],whole:[]}; P[u.key]=p; }
    let demo=isDemo(u.stock,s.demo_stocks);
    if(u.isDlr){
      if(demo) return;
      p.onlot++;
      if(u.dis>=s.stall_days) p.stalled++;
      if(u.dis>s.aged_days) p.aged.push(u);
      let met=metrics[u.key], dts=(met&&met.dts!==null)?met.dts:9999;
      if(u.dis>Math.max(s.wholesale_min_age,dts)) p.whole.push(u);
    } else {
      p.inbound++;
      if(u.arr) p.arrivals[u.arr]=(p.arrivals[u.arr]||0)+1;
    }
  });
  return P;
}
function projRate(m,dts,s){ let ph=m?m.prate/2:0; let dr=(m&&m.r90>0&&dts&&dts>0)?30.4/dts:0; return Math.min(s.rate_cap,Math.max(ph,dr)); }
function projectAtArrival(model,pos,metric,seas,s){
  let om=s.order_month, dts=metric?metric.dts:null, rate=projRate(metric,dts,s);
  function arr(off){ let cal=((om-1+off)%12)+1; return pos.arrivals[cal]||0; }
  if(s.mode!=="CPO"){ let pr=pos.onlot+pos.inbound; return [xround(pr,1),pr]; }
  let later=0; for(let k=1;k<=5;k++) later+=arr(k);
  let proj=[pos.onlot+Math.max(0,pos.inbound-later)];
  for(let k=1;k<=5;k++){ let sm=seas[model][((om-1+(k-1))%12)]; let drawn=proj[k-1]-rate*sm; proj.push(Math.max(pos.stalled,drawn)+arr(k)); }
  let w=Math.max(s.min_cpo_window, s.cpo_windows[model]!==undefined?s.cpo_windows[model]:2);
  return [xround(proj[w],1), proj[0]];
}
function baseForOrder(key, metrics){ let m=metrics[key]; return m?[m.base,true]:[1,false]; }
function momFactor(m,dts){
  let r90=m?m.r90:0, r180=m?m.r180:0, accel=m?m.momentum==="ACCEL":false, base;
  if(r90>=2||accel) base=1.0; else if(r90===1) base=0.6;
  else if(r90===0&&r180>=2) base=0.35; else if(r90===0&&r180===1) base=0.25; else base=0.15;
  let pen = dts===null?1.0:(dts>90?0.6:(dts>60?0.85:1.0));
  return Math.min(1.0, base*pen);
}
function dtsBand(dts){ if(dts===null) return 0; if(dts<=20)return 4; if(dts<=40)return 3; if(dts<=70)return 2; if(dts<=100)return 1; return 0; }
function matchesDemote(e,model,ext,intr,key){
  function ok(fv,act){ fv=String(fv||"").trim(); return fv===""||fv===act; }
  let has=["model","code","ext","int"].some(f=>String(e[f]||"").trim());
  let code=key.indexOf("|")>=0?key.split("|")[1]:"";
  return has && ok(e.model,model)&&ok(e.code,code)&&ok(e.ext,ext)&&ok(e.int,intr);
}
function suppressed(code,ext,intr,s){
  if(code==="8461") return true;
  return s.suppress.some(e=> String(e.code||"").trim().slice(0,4)===code &&
    String(e.ext||"").trim()===ext && String(e.int||"").trim()===intr);
}
function buildLines(s,metrics,seas,positions,agedBrakes,overrideMap){
  let lines=[];
  ROSTER.forEach((c,i)=>{
    let model=c.model,code=c.code,ext=c.ext,intr=c.int,key=model+"|"+code+"|"+ext+"|"+intr;
    let metric=metrics[key]||null, pos=positions[key]||{onlot:0,inbound:0,arrivals:{},stalled:0,aged:[],whole:[]};
    let dts=metric?metric.dts:null;
    let bf=baseForOrder(key,metrics), base=bf[0], found=bf[1];
    let mf=momFactor(metric,dts);
    let seasOrder=seas[model][(s.order_month-1)%12];
    let win = s.mode==="CPO" ? Math.max(s.min_cpo_window, s.cpo_windows[model]!==undefined?s.cpo_windows[model]:2) : 0;
    let seasArr=seas[model][(s.order_month-1+win)%12];
    let pj=projectAtArrival(model,pos,metric,seas,s), proj=pj[0];
    let sup=suppressed(code,ext,intr,s);
    let dem=s.demote.some(e=>matchesDemote(e,model,ext,intr,key));
    let r90=metric?metric.r90:0, effDem = dem && r90<s.prove_bar;
    let needFloor = base===0?0:1;
    let orderTarget=Math.max(needFloor, xround(base*(1+(seasArr-1)*mf),0));
    let overstockTarget=Math.max(needFloor, xround(base*seasOrder,0));
    let agedBrake=agedBrakes[key]||0, ov=overrideMap[key]||0;
    let need = (sup||effDem) ? 0 : Math.max(0, xround(orderTarget-proj-agedBrake,0))+ov;
    let rate=projRate(metric,dts,s);
    let excess=Math.max(0, xround(pos.onlot+pos.inbound-3*rate-overstockTarget,0));
    let wholeNow = sup?0:Math.min(excess,pos.whole.length);
    let mom = metric?metric.momentum:"dormant";
    let prio=priority(dts,mom,need,proj,orderTarget,seasArr,effDem,i);
    lines.push({model:model,code:code,ext:ext,int:intr,trim:c.trim,key:key,dts:dts,mom:mom,
      onlot:pos.onlot,inbound:pos.inbound,proj:proj,base:base,found:found,mf:mf,
      orderTarget:orderTarget,overstockTarget:overstockTarget,need:need,suppressed:sup,
      demoted:dem,effDem:effDem,priority:prio,wholeNow:wholeNow,pos:pos});
  });
  return lines;
}
function priority(dts,mom,need,proj,orderTgt,seasArr,effDem,idx){
  let momBand={ACCEL:4,steady:2,"on cadence":1}[mom]||0, db=dtsBand(dts);
  let seasBand=seasArr>=1.3?2:(seasArr>=1?1:0), tb=idx/100000;
  if(need>0){ let pb=proj===0?4:(proj<orderTgt?2:0); return 1000+db+momBand+pb+seasBand-1000*effDem-tb; }
  if((mom==="ACCEL"||mom==="steady"||mom==="on cadence")&&dts!==null&&dts<=90) return db+momBand+seasBand-1000*effDem-tb;
  return -1;
}
function findOrphans(sales,roster){
  let rk={}; roster.forEach(c=>rk[c.model+"|"+c.code+"|"+c.ext+"|"+c.int]=1);
  let seen={};
  sales.forEach(s=>{ if(s.firstVin&&s.key&&!rk[s.key]) seen[s.key]=(seen[s.key]||0)+1; });
  return Object.keys(seen).map(k=>({key:k,sales:seen[k]})).sort((a,b)=>b.sales-a.sales);
}
function runEngine(inv,sales,s,today){
  let tb=timeBase(sales,today);
  let metrics=computeMetrics(sales,tb,ROSTER);
  let seas=computeSeasonality(sales,tb);
  let positions=computePositions(inv,metrics,s);
  let agedBrakes={}; (s.aged_memory||[]).forEach(e=>{ if(e.active===undefined||e.active===1||e.active===true||e.active==="1") agedBrakes[e.key]=(agedBrakes[e.key]||0)+1; });
  let overrideMap={}; s.overrides.forEach(e=>{ overrideMap[e.key]=(overrideMap[e.key]||0)+parseInt(e.qty||0,10); });
  let lines=buildLines(s,metrics,seas,positions,agedBrakes,overrideMap);
  let demoUnits=inv.filter(u=>u.isDlr&&isDemo(u.stock,s.demo_stocks));
  let orphans=findOrphans(sales,ROSTER);
  return {settings:s,tb:tb,metrics:metrics,seas:seas,positions:positions,lines:lines,demoUnits:demoUnits,sales:sales,orphans:orphans};
}

/* ===================== reports ===================== */
function orderPriority(res){
  let s=res.settings,out={};
  MODELS.forEach(model=>{
    let ranked=res.lines.filter(l=>l.model===model&&l.priority>-1).sort((a,b)=>b.priority-a.priority);
    let alloc=s.allocations[model]||0, cum=0, rows=[];
    ranked.forEach((l,i)=>{ cum+=l.need;
      let tier = l.need===0?"option":(cum<=alloc?"build":"alt");
      rows.push({rank:i+1,trim:l.trim,ext:l.ext,int:l.int,dts:l.dts,mom:l.mom,need:l.need,cum:cum,tier:tier}); });
    out[model]={alloc:alloc,rows:rows,totalNeed:res.lines.filter(l=>l.model===model).reduce((a,l)=>a+l.need,0)};
  });
  return out;
}
function overstock(res){
  let rows=[];
  res.lines.forEach(l=>{ let over=l.onlot-l.overstockTarget;
    if(l.suppressed||over<1) return;
    rows.push({model:l.model,trim:l.trim,ext:l.ext,int:l.int,onhand:l.onlot,target:l.overstockTarget,
      over:over,wholeNow:l.wholeNow,inbound:l.inbound,dts:l.dts,aged:l.pos.aged.length}); });
  rows.sort((a,b)=> (MODELS.indexOf(a.model)-MODELS.indexOf(b.model))|| (b.over-a.over)||(b.wholeNow-a.wholeNow));
  return rows;
}
function wholesaleVins(res){
  let rows=[];
  res.lines.forEach(l=>{ if(l.wholeNow<=0) return;
    let units=l.pos.whole.slice().sort((a,b)=>b.dis-a.dis).slice(0,l.wholeNow);
    units.forEach(u=>{ let vin=u.serial||u.stock;
      rows.push({stock:u.stock||"—",vin:vin,vin6:vin?vin.slice(-6):"—",year:u.myear||u.my||"",
        model:u.model,trim:l.trim||u.desc,ei:u.ext+"/"+u.int,dis:Math.round(u.dis)}); }); });
  rows.sort((a,b)=>b.dis-a.dis); rows.forEach((r,i)=>r.num=i+1); return rows;
}
function demoDashboard(res){
  let s=res.settings, rows=[];
  res.demoUnits.forEach(u=>{ let dis=Math.round(u.dis), asDemo=dis;
    for(let pref in s.demo_starts){ if(pref&&u.stock.indexOf(pref)===0){
      let d0=new Date(s.demo_starts[pref]); if(!isNaN(d0.getTime())) asDemo=Math.round((res.tb.today-d0)/86400000); break; } }
    rows.push({stock:u.stock,vehicle:u.desc,dis:dis,asDemo:asDemo,swap:asDemo>s.swap_threshold}); });
  rows.sort((a,b)=>b.asDemo-a.asDemo); return rows;
}
function paceCheck(res){
  let tb=res.tb, rows=[];
  MODELS.forEach(model=>{
    let ms=res.sales.filter(s=>s.firstVin&&s.model===model);
    let a90=ms.filter(s=>s.midx>tb.latest-3).length;
    let a60=xround(a90/tb.el90*2,1);
    let p60=xround(Object.values(res.metrics).filter(m=>m.model===model).reduce((a,m)=>a+m.hist60,0),1);
    let vr=xround(a60-p60,1), band=Math.max(2,0.25*p60);
    let read = vr>band?"AHEAD":(vr<-band?"BEHIND":"ON TARGET");
    let total=ms.length, mapped=ms.filter(s=>res.metrics[s.key]).length, cov=total?mapped/total:1;
    rows.push({model:model,a90:a90,a60:a60,p60:p60,vr:vr,read:read,cov:cov});
  });
  return rows;
}

/* ===================== rendering ===================== */
function esc(v){ return String(v==null?"":v).replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c])); }
function momPill(m){ let cls="m-"+m.replace(/\s/g,""); if(m==="on cadence")cls="m-oncadence"; return '<span class="pill '+cls+'">'+esc(m)+'</span>'; }
function fdts(d){ return d===null||d===undefined||d===""?"—":String(Math.round(d)); }
function tbl(head,aligns,rows){
  let h="<div class='tblwrap'><table><thead><tr>"+head.map((x,i)=>"<th class='"+(aligns[i]==="r"?"num":"")+"'>"+esc(x)+"</th>").join("")+"</tr></thead><tbody>";
  h+=rows.map(r=>"<tr>"+r.map((c,i)=>"<td class='"+(aligns[i]==="r"?"num":"")+"'>"+(c&&c.html?c.html:esc(c))+"</td>").join("")+"</tr>").join("");
  return h+"</tbody></table></div>";
}
function render(res){
  let rep={op:orderPriority(res),over:overstock(res),vins:wholesaleVins(res),demo:demoDashboard(res),pace:paceCheck(res)};
  let s=res.settings,tb=res.tb, H=[];
  let latest = tb.latest?(Math.floor(tb.latest/12)+"-"+String(tb.latest%12).padStart(2,"0")):"—";
  H.push("<div class='card'><b>Recomputed "+tb.today.toISOString().slice(0,10)+"</b> · order month <b>"+MONTHS[s.order_month-1]+
    "</b> · mode <b>"+s.mode+"</b><div class='footnote'>Sales history "+tb.span.toFixed(1)+" months (newest "+latest+
    (tb.open?", still open/partial":"")+"). "+Object.keys(res.metrics).length+" learned configs, "+ROSTER.length+" roster combos, "+res.orphans.length+" sold-but-unrostered.</div></div>");

  // 1 Order Priority
  H.push(outhead(1,"Order Priority","ranked build / bench worklist — NEED per config"));
  MODELS.forEach(model=>{ let b=rep.op[model];
    H.push("<div class='modelband'>"+model+" &nbsp; <span class='tag'>allocated "+b.alloc+"</span> <span class='tag'>total NEED "+b.totalNeed+"</span></div>");
    let rows=b.rows.map(r=>{ let tierhtml={build:"<span class='tier-build'>✓ BUILD</span>",alt:"<span class='tier-alt'>↑ alt</span>",option:"<span class='tier-opt'>○ option</span>"}[r.tier];
      return [r.rank,{html:tierhtml},esc(r.trim),esc(r.ext),esc(r.int),fdts(r.dts),{html:momPill(r.mom)},r.need,r.cum]; });
    H.push(tbl(["#","Build?","Trim","Ext","Int","DTS","Momentum","NEED","Cum"],["l","l","l","l","l","r","l","r","r"],rows));
  });

  // 2 Overstock
  H.push(outhead(2,"Overstock / Wholesale","over-target metal — order slower, don't dump"));
  if(rep.over.length){ H.push(tbl(["Model","Trim","Ext","Int","OnHand","Tgt","Over","Whole","Inb","DTS","Aged"],
    ["l","l","l","l","r","r","r","r","r","r","r"],
    rep.over.map(r=>[r.model,esc(r.trim),r.ext,r.int,r.onhand,r.target,r.over,r.wholeNow,r.inbound,fdts(r.dts),r.aged]))); }
  else H.push("<div class='footnote'>Nothing over target.</div>");

  // 3 Wholesale VINs
  H.push(outhead(3,"Wholesale Now — VIN sheet","aged, over-target, non-demo — print & send to other dealers"));
  if(rep.vins.length){ H.push("<div id='print-only-vin'><h2>WHOLESALE VIN SHEET — "+tb.today.toISOString().slice(0,10)+"</h2></div>");
    H.push(tbl(["#","Stock #","VIN (last 6)","Year","Model","Trim","Ext/Int","Days in Stock"],
    ["l","l","l","l","l","l","l","r"],
    rep.vins.map(r=>[r.num,esc(r.stock),esc(r.vin6),r.year,r.model,esc(r.trim),esc(r.ei),r.dis])));
    H.push("<button class='ghost noprint' onclick='window.print()'>🖨 Print this VIN sheet</button>"); }
  else H.push("<div class='footnote'>No units past their selling window.</div>");

  // 4 Demo
  H.push(outhead(4,"Demo Dashboard","units pulled from sellable inventory"));
  if(rep.demo.length){ H.push(tbl(["Stock","Vehicle","Days in Stock","Days as Demo","Swap?"],["l","l","r","r","l"],
    rep.demo.map(r=>[esc(r.stock),esc(r.vehicle),r.dis,r.asDemo,{html:r.swap?"<span class='swap'>⚠ SWAP</span>":"OK"}]))); }
  else H.push("<div class='footnote'>No demos listed.</div>");

  // 5 Pace
  H.push(outhead(5,"Pace Check","actual vs predicted 60-day pace"));
  H.push(tbl(["Model","Actual 90d","Act 60d pace","Pred 60d pace","Variance","Read","Coverage"],
    ["l","r","r","r","r","l","r"],
    rep.pace.map(r=>{ let rc=r.read==="AHEAD"?"read-AHEAD":(r.read==="BEHIND"?"read-BEHIND":"read-ON");
      let rl=r.read==="AHEAD"?"AHEAD of forecast":(r.read==="BEHIND"?"BEHIND forecast":"ON TARGET");
      return [r.model,r.a90,r.a60,r.p60,(r.vr>=0?"+":"")+r.vr,{html:"<span class='"+rc+"'>"+rl+"</span>"},Math.round(r.cov*100)+"%"]; })));

  if(res.orphans.length){
    let top=res.orphans.slice(0,14).map(o=>o.key+" ("+o.sales+")").join(",  ");
    H.push("<details class='card noprint'><summary>Data health — "+res.orphans.length+" configs sold but not on the order roster (ordering can't see them; many are discontinued/legacy — expected)</summary><div class='footnote'>"+esc(top)+(res.orphans.length>14?" …":"")+"</div></details>");
  }
  document.getElementById("results").innerHTML=H.join("");
}
function outhead(n,title,meta){ return "<div class='outhead'><span class='n'>"+n+"</span><h2>"+esc(title)+"</h2><span class='meta'>"+esc(meta)+"</span></div>"; }

/* ===================== wiring ===================== */
function getSettings(){
  return { order_month: parseInt(document.getElementById("ordmonth").value,10),
    mode: document.getElementById("mode").value,
    allocations:{QX80:parseInt(document.getElementById("a80").value||0,10),
      QX60:parseInt(document.getElementById("a60").value||0,10),
      QX65:parseInt(document.getElementById("a65").value||0,10)},
    cpo_windows:{QX80:parseInt(document.getElementById("w80").value||3,10),
      QX60:parseInt(document.getElementById("w60").value||2,10),
      QX65:parseInt(document.getElementById("w65").value||2,10)},
    min_cpo_window:1, suppress:DEFAULTS.suppress, demote:DEFAULTS.demote, overrides:DEFAULTS.overrides,
    demo_stocks:DEFAULTS.demo_stocks, demo_starts:DEFAULTS.demo_starts, aged_memory:[],
    prove_bar:2, swap_threshold:90, rate_cap:5.0, paperweight_dts:90, wholesale_min_age:60,
    stall_days:120, aged_days:60 };
}
function markFilled(){
  document.getElementById("inv").classList.toggle("ok", document.getElementById("inv").value.trim()!=="");
  document.getElementById("sales").classList.toggle("ok", document.getElementById("sales").value.trim()!=="");
}
function compute(){
  let st=document.getElementById("status"); st.className="status"; st.textContent="";
  let invText=document.getElementById("inv").value, salesText=document.getElementById("sales").value;
  if(!invText.trim()||!salesText.trim()){ st.className="status err"; st.textContent="Paste both exports first."; return; }
  try{
    let inv=loadInventory(invText), sales=loadSales(salesText);
    let s=getSettings();
    let td=document.getElementById("today").value;
    let today = td? new Date(td+"T00:00:00") : new Date();
    let res=runEngine(inv,sales,s,today);
    render(res);
    st.textContent="Done — "+inv.length+" inventory units, "+sales.length+" sales rows read.";
    try{ localStorage.setItem("pm_inv",invText); localStorage.setItem("pm_sales",salesText);
      localStorage.setItem("pm_set",JSON.stringify({m:s.order_month,mode:s.mode})); }catch(e){}
    document.getElementById("results").scrollIntoView({behavior:"smooth"});
  }catch(e){ st.className="status err"; st.textContent="Problem: "+e.message; }
}
function initMonths(){
  let sel=document.getElementById("ordmonth"); let now=new Date().getMonth();
  MONTHS.forEach((m,i)=>{ let o=document.createElement("option"); o.value=i+1; o.textContent=m;
    if(i===now) o.selected=true; sel.appendChild(o); });
  document.getElementById("today").value=new Date().toISOString().slice(0,10);
}
function wireFile(inputId,taId,statId){
  document.getElementById(inputId).addEventListener("change",function(e){
    let f=e.target.files[0]; if(!f) return; let rd=new FileReader();
    rd.onload=function(){ document.getElementById(taId).value=rd.result; markFilled();
      document.getElementById(statId).textContent=f.name; }; rd.readAsText(f); });
}
window.addEventListener("DOMContentLoaded",function(){
  initMonths();
  document.getElementById("run").addEventListener("click",compute);
  document.getElementById("loadsample").addEventListener("click",function(){
    document.getElementById("inv").value=SAMPLE.inv; document.getElementById("sales").value=SAMPLE.sales;
    document.getElementById("ordmonth").value=9; markFilled(); });
  document.getElementById("clearall").addEventListener("click",function(){
    document.getElementById("inv").value=""; document.getElementById("sales").value=""; markFilled();
    document.getElementById("results").innerHTML=""; });
  document.getElementById("inv").addEventListener("input",markFilled);
  document.getElementById("sales").addEventListener("input",markFilled);
  wireFile("invfile","inv","invstat"); wireFile("salesfile","sales","salesstat");
  try{ let i=localStorage.getItem("pm_inv"), sa=localStorage.getItem("pm_sales");
    if(i) document.getElementById("inv").value=i; if(sa) document.getElementById("sales").value=sa;
    let set=JSON.parse(localStorage.getItem("pm_set")||"null");
    if(set){ document.getElementById("ordmonth").value=set.m; document.getElementById("mode").value=set.mode; } }catch(e){}
  markFilled();
});
</script>
</body>
</html>
"""

out = (HTML
       .replace("__ROSTER__", json.dumps(ROSTER, separators=(",", ":")))
       .replace("__DEFAULTS__", json.dumps(DEFAULTS, separators=(",", ":")))
       .replace("__SAMPLE_INV__", json.dumps(SAMPLE_INV))
       .replace("__SAMPLE_SALES__", json.dumps(SAMPLE_SALES)))
open(os.path.join(ROOT, "Pipeline-Manager.html"), "w", encoding="utf-8").write(out)
print("wrote Pipeline-Manager.html (%d KB)" % (len(out) // 1024))
