/* Loaner Intelligence — dashboard render + wiring. Consumes analyze() output. */
"use strict";
const STATE = { sales: null, a: null, halfLife: 24 };
const MODEL_COLORS = ["#5eead4","#fb923c","#4c8dff","#f472b6","#a3e635","#fbbf24","#f87171"];
const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

function esc(s){ return String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }
function fmt$(n){ if(n==null) return "—"; n=Math.round(n); return (n<0?"-$":"$")+Math.abs(n).toLocaleString(); }
function pct(x){ return x==null?"—":Math.round(x*100)+"%"; }
function signMoney(n){ if(n==null) return "—"; return (n>=0?"+":"−")+"$"+Math.abs(Math.round(n)).toLocaleString(); }

/* ---------- tiny SVG chart helpers (self-contained) ---------- */
function svgLineMulti(series, opts){
  opts=opts||{}; let W=opts.w||660, H=opts.h||280, pl=52, pr=16, pt=16, pb=42;
  let cats=opts.cats||[]; let n=cats.length; if(!n) return "";
  let ymin=opts.ymin!=null?opts.ymin:0, ymax=opts.ymax!=null?opts.ymax:1.05;
  let x=i=>pl+(n<=1?0:(W-pl-pr)*i/(n-1)), y=v=>pt+(H-pt-pb)*(1-(v-ymin)/(ymax-ymin));
  let g=["<svg viewBox='0 0 "+W+" "+H+"' width='100%' style='max-width:"+W+"px'>"];
  // gridlines + y labels
  for(let k=0;k<=4;k++){ let v=ymin+(ymax-ymin)*k/4, yy=y(v);
    g.push("<line x1='"+pl+"' y1='"+yy+"' x2='"+(W-pr)+"' y2='"+yy+"' stroke='#273448' stroke-width='1'/>");
    g.push("<text x='"+(pl-8)+"' y='"+(yy+4)+"' fill='#8492a6' font-size='11' text-anchor='end'>"+(opts.yfmt?opts.yfmt(v):Math.round(v*100)+"%")+"</text>"); }
  // x labels
  cats.forEach((c,i)=>g.push("<text x='"+x(i)+"' y='"+(H-pb+20)+"' fill='#9dabbf' font-size='11' text-anchor='middle'>"+esc(c)+"</text>"));
  series.forEach(s=>{ let pts=s.points.map((v,i)=>v==null?null:[x(i),y(v)]).filter(Boolean);
    if(pts.length>1) g.push("<polyline fill='none' stroke='"+s.color+"' stroke-width='2.5' points='"+pts.map(p=>p[0].toFixed(1)+","+p[1].toFixed(1)).join(" ")+"'/>");
    s.points.forEach((v,i)=>{ if(v==null) return; g.push("<circle cx='"+x(i)+"' cy='"+y(v)+"' r='3.4' fill='"+s.color+"'/>"); }); });
  g.push("</svg>");
  return g.join("");
}
function legend(series){ return "<div class='lg'>"+series.map(s=>"<span class='lgi'><i style='background:"+s.color+"'></i>"+esc(s.name)+"</span>").join("")+"</div>"; }

function heatCell(idx){ // idx around 1.0 -> diverging teal(high)/red(low)
  if(idx==null) return ["#161f2e","#8492a6"];
  let d=Math.max(-0.12,Math.min(0.12,idx-1))/0.12; // -1..1
  if(d>=0){ let a=0.12+0.5*d; return ["rgba(94,234,212,"+a.toFixed(2)+")", d>0.5?"#062e2b":"#d3dbe7"]; }
  let a=0.12+0.5*(-d); return ["rgba(248,113,113,"+a.toFixed(2)+")", -d>0.5?"#3a0d0d":"#d3dbe7"];
}
function barRow(label, val, maxAbs, opts){
  opts=opts||{}; let w=maxAbs>0?Math.min(100,Math.abs(val)/maxAbs*100):0;
  let pos=val>=0, col=pos?"var(--teal)":"var(--bad)";
  return "<div class='br'><div class='brl'>"+esc(label)+"</div>"+
    "<div class='brt'><div class='brf' style='width:"+w+"%;background:"+col+";"+(pos?"":"margin-left:auto")+"'></div></div>"+
    "<div class='brv' style='color:"+col+"'>"+(opts.money?signMoney(val):val)+"</div></div>";
}

/* ---------- sections ---------- */
function kpiOverview(a){
  let m=a.meta, lv=a.loaner_vs_retail.overall;
  let span=(m.date_min&&m.date_max)?(m.date_min.getFullYear()+"–"+m.date_max.getFullYear()):"—";
  let H=["<div class='kpis'>"];
  H.push(kpi("Sales analyzed", m.rows.toLocaleString(), span+" · all makes","var(--muted)"));
  H.push(kpi("Infiniti units", m.infiniti_rows.toLocaleString(), "the analysis focus","var(--accent)"));
  H.push(kpi("Loaner cohort", m.loaner_rows.toLocaleString(), "LP/LNP + VIN lineage","var(--teal)"));
  let gd=lv.loaner.gross-lv.retail.gross;
  H.push(kpi("Loaner gross edge", signMoney(gd), "vs ordinary used", gd>=0?"var(--teal)":"var(--bad)"));
  H.push("</div>");
  return H.join("");
}
function kpi(lab,big,sub,col){ return "<div class='kpi'><span class='edge' style='background:"+(col||"var(--accent)")+"'></span>"+
  "<div class='lab'>"+esc(lab)+"</div><div class='big' style='color:"+(col||"var(--ink)")+"'>"+big+"</div><div class='sub'>"+esc(sub)+"</div></div>"; }

function secLoanerVsRetail(a){
  let lv=a.loaner_vs_retail, o=lv.overall;
  function col(t,d,accent){ return "<div class='lvcol"+(accent?" acc":"")+"'><div class='lvh'>"+t+"</div>"+
    "<div class='lvrow'><span>Units sold</span><b>"+d.n+"</b></div>"+
    "<div class='lvrow'><span>Median price</span><b>"+fmt$(d.price)+"</b></div>"+
    "<div class='lvrow'><span>Median gross</span><b>"+fmt$(d.gross)+"</b></div>"+
    "<div class='lvrow'><span>Days to sell</span><b>"+(d.dts==null?"—":d.dts)+"</b></div>"+
    "<div class='lvrow'><span>Age at sale</span><b>"+(d.avg_age_mo==null?"—":d.avg_age_mo+" mo")+"</b></div></div>"; }
  let H=["<div class='hint'>What actually happens to a vehicle after it serves as a loaner — measured against ordinary used Infiniti stock, recency-weighted.</div>"];
  H.push("<div class='lvwrap'>"+col("Out-of-service loaners",o.loaner,true)+col("Ordinary used Infiniti",o.retail,false)+"</div>");
  // per-model
  let rows=Object.keys(lv.per_model).map(m=>{ let p=lv.per_model[m];
    return "<tr><td><b>"+esc(m)+"</b></td><td class='c'>"+p.loaner.n+"</td><td class='c'>"+fmt$(p.loaner.price)+"</td><td class='c'>"+fmt$(p.loaner.gross)+"</td>"+
      "<td class='c'>"+(p.loaner.dts==null?"—":p.loaner.dts)+"d</td><td class='c dim'>"+fmt$(p.retail.gross)+"</td>"+
      "<td class='c "+(p.loaner.gross-p.retail.gross>=0?"pos":"neg")+"'>"+signMoney(p.loaner.gross-p.retail.gross)+"</td></tr>"; }).join("");
  H.push("<table class='tbl'><thead><tr><th>Model</th><th class='c'>Loaner n</th><th class='c'>Loaner price</th><th class='c'>Loaner gross</th><th class='c'>Loaner DTS</th><th class='c'>Retail gross</th><th class='c'>Gross edge</th></tr></thead><tbody>"+rows+"</tbody></table>");
  return H.join("");
}

function secCurves(a){
  let keys=Object.keys(a.age_curves).sort((x,y)=>{ let ox=STATE.a.model_perf.models.findIndex(m=>m.model===x),oy=STATE.a.model_perf.models.findIndex(m=>m.model===y); return ox-oy; });
  let top=keys.filter(k=>a.age_curves[k].points.reduce((s,p)=>s+p.n,0)>=40).slice(0,5);
  let cats=["0–6mo","6–12mo","1yr","1.5yr","2yr","3yr","4yr","5yr","7yr+"];
  let edges=[0,6,12,18,24,36,48,60,84];
  let series=top.map((k,i)=>({name:k,color:MODEL_COLORS[i%MODEL_COLORS.length],
    points:edges.map(e=>{ let p=a.age_curves[k].points.find(pp=>pp.age===e); return p?p.retention_smooth:null; })}));
  let H=["<div class='hint'>Value retention vs vehicle age — the dealership's own Infiniti depreciation curve (age axis; no odometer in the source). Each model's resale value as a share of its as-new resale.</div>"];
  H.push(legend(series));
  H.push("<div class='chartbox'>"+svgLineMulti(series,{cats:cats,ymin:0,ymax:1.05})+"</div>");
  // $ table for the leading model
  let lead=top[0]; if(lead){ let pts=a.age_curves[lead].points;
    H.push("<div class='subttl'>"+esc(lead)+" — median resale by age</div>");
    H.push("<table class='tbl'><thead><tr><th>Age</th>"+pts.map(p=>"<th class='c'>"+esc(p.label)+"</th>").join("")+"</tr></thead><tbody>"+
      "<tr><td>Resale</td>"+pts.map(p=>"<td class='c'>"+fmt$(p.price_smooth)+"</td>").join("")+"</tr>"+
      "<tr><td>Retention</td>"+pts.map(p=>"<td class='c'>"+pct(p.retention_smooth)+"</td>").join("")+"</tr>"+
      "<tr><td class='dim'>Sample</td>"+pts.map(p=>"<td class='c dim'>"+p.n+"</td>").join("")+"</tr></tbody></table>"); }
  return H.join("");
}

function secPredictor(a){
  let models=a.model_perf.models.map(m=>m.model);
  let colorsByModel={}; for(let m in a.color) colorsByModel[m]=a.color[m].colors.map(c=>c.color);
  let trimsByModel={}; for(let m in a.trim) trimsByModel[m]=a.trim[m].map(t=>t.trim);
  let H=["<div class='hint'>Ask the engine: put a spec into service and see what your own history says it resells for. Pure lookup on the recency-weighted age curve, nudged by color &amp; season — no mileage input (not in the source).</div>"];
  H.push("<div class='calc'>");
  H.push(fld("Model","pc_model",models.map(m=>[m,m])));
  H.push(fld("Trim","pc_trim",[]));
  H.push(fld("Exterior color","pc_color",[]));
  H.push(fld("Sale month","pc_month",MONTHS.map((m,i)=>[String(i+1),m])));
  H.push("<div class='cfld'><label>Vehicle age</label><input type='range' id='pc_age' min='0' max='72' step='6' value='6'><div class='agev' id='pc_agev'>6 mo</div></div>");
  H.push("</div>");
  H.push("<div id='pc_out' class='predout'></div>");
  window.__PC = {colorsByModel, trimsByModel};
  return H.join("");
}
function fld(lab,id,opts){ return "<div class='cfld'><label>"+esc(lab)+"</label><select id='"+id+"'>"+
  opts.map(o=>"<option value='"+esc(o[0])+"'>"+esc(o[1])+"</option>").join("")+"</select></div>"; }

function renderPrediction(){
  let a=STATE.a; if(!a) return;
  let model=val("pc_model"), trim=val("pc_trim")||null, color=val("pc_color")||null, month=+val("pc_month")||null, age=+val("pc_age");
  document.getElementById("pc_agev").textContent = age+" mo"+(age>=12?" ("+(age/12).toFixed(age%12?1:0)+"yr)":"");
  let r=a.predictor(model,trim,null,color,month,age);
  let out=document.getElementById("pc_out"); if(!r.ok){ out.innerHTML="<div class='dim'>"+esc(r.reason||"no data")+"</div>"; return; }
  let cbars=Math.round(r.confidence*5);
  out.innerHTML=
    "<div class='predgrid'>"+
      "<div class='pcard big'><div class='pl'>Expected resale</div><div class='pv'>"+fmt$(r.price)+"</div><div class='pr'>range "+fmt$(r.price_low)+" – "+fmt$(r.price_high)+"</div></div>"+
      "<div class='pcard'><div class='pl'>Expected gross</div><div class='pv'>"+fmt$(r.gross)+"</div></div>"+
      "<div class='pcard'><div class='pl'>Days to sell</div><div class='pv'>"+(r.dts==null?"—":r.dts)+"</div></div>"+
      "<div class='pcard'><div class='pl'>Confidence</div><div class='pv'>"+"●".repeat(cbars)+"<span class='dim'>"+"○".repeat(5-cbars)+"</span></div><div class='pr'>"+r.n+" comps</div></div>"+
    "</div>"+
    "<div class='foot'>Color factor "+r.color_factor.toFixed(2)+"× · season factor "+r.season_factor.toFixed(2)+"×. "+
    (r.confidence<0.5?"<b style='color:var(--warn)'>Thin sample — treat as directional.</b>":"")+"</div>";
}
function val(id){ let e=document.getElementById(id); return e?e.value:""; }

function refreshPredictorOpts(){
  let model=val("pc_model"), pc=window.__PC||{};
  let ts=(pc.trimsByModel||{})[model]||[], cs=(pc.colorsByModel||{})[model]||[];
  fillSel("pc_trim",[["","(any trim)"]].concat(ts.map(t=>[t,t])));
  fillSel("pc_color",[["","(any color)"]].concat(cs.map(c=>[c,c])));
}
function fillSel(id,opts){ let e=document.getElementById(id); if(!e) return;
  e.innerHTML=opts.map(o=>"<option value='"+esc(o[0])+"'>"+esc(o[1])+"</option>").join(""); }

function secColor(a){
  let models=Object.keys(a.color).sort((x,y)=>a.color[y].colors.length-a.color[x].colors.length);
  let H=["<div class='hint'>Does color move the needle on resale? Gross premium is each color vs the model's own weighted average (exterior only — interior color isn't in the source).</div>"];
  H.push("<div class='cfld inline'><label>Model</label><select id='clr_model'>"+models.map(m=>"<option>"+esc(m)+"</option>").join("")+"</select></div>");
  H.push("<div id='clr_out'></div>");
  return H.join("");
}
function renderColor(){
  let a=STATE.a, model=val("clr_model")||Object.keys(a.color)[0]; let d=a.color[model]; if(!d){ document.getElementById("clr_out").innerHTML=""; return; }
  let maxAbs=Math.max.apply(null,d.colors.map(c=>Math.abs(c.gross_prem||0)).concat([1]));
  let bars=d.colors.map(c=>barRow(c.color+"  ("+c.n+")",c.gross_prem||0,maxAbs,{money:true})).join("");
  let rows=d.colors.map(c=>"<tr><td>"+esc(c.color)+"</td><td class='c'>"+c.n+"</td><td class='c'>"+fmt$(c.price)+"</td><td class='c'>"+fmt$(c.gross)+"</td>"+
    "<td class='c "+((c.gross_prem||0)>=0?"pos":"neg")+"'>"+signMoney(c.gross_prem)+"</td><td class='c "+((c.dts_delta||0)<=0?"pos":"neg")+"'>"+(c.dts_delta==null?"—":(c.dts_delta>0?"+":"")+c.dts_delta+"d")+"</td></tr>").join("");
  document.getElementById("clr_out").innerHTML=
    "<div class='subttl'>Gross premium vs "+esc(model)+" average ("+fmt$(d.baseline.gross)+")</div><div class='bars'>"+bars+"</div>"+
    "<table class='tbl'><thead><tr><th>Color</th><th class='c'>n</th><th class='c'>Price</th><th class='c'>Gross</th><th class='c'>Gross Δ</th><th class='c'>DTS Δ</th></tr></thead><tbody>"+rows+"</tbody></table>";
}

function secTrim(a){
  let models=Object.keys(a.trim).sort((x,y)=>a.trim[y].length-a.trim[x].length);
  let H=[];
  models.slice(0,4).forEach(m=>{ let items=a.trim[m];
    H.push("<div class='subttl'>"+esc(m)+"</div>");
    H.push("<table class='tbl'><thead><tr><th>Trim</th><th class='c'>n</th><th class='c'>Median price</th><th class='c'>Median gross</th><th class='c'>DTS</th><th class='c'>Avg age</th></tr></thead><tbody>"+
      items.map((t,i)=>"<tr><td>"+(i===0?"★ ":"")+esc(t.trim)+"</td><td class='c'>"+t.n+"</td><td class='c'>"+fmt$(t.price)+"</td><td class='c'>"+fmt$(t.gross)+"</td><td class='c'>"+(t.dts==null?"—":t.dts)+"d</td><td class='c dim'>"+(t.avg_age_mo==null?"—":t.avg_age_mo+"mo")+"</td></tr>").join("")+
      "</tbody></table>"); });
  return H.join("");
}

function secModelPerf(a){
  let mp=a.model_perf;
  let H=["<div class='hint'>Every Infiniti model ranked, and how each compares to the whole store's used-car average (all makes) — gross and turn speed. Store: gross "+fmt$(mp.store.gross)+" · "+mp.store.dts+" days.</div>"];
  H.push("<table class='tbl'><thead><tr><th>Model</th><th class='c'>Units</th><th class='c'>Loaners</th><th class='c'>Median price</th><th class='c'>Median gross</th><th class='c'>Gross vs store</th><th class='c'>DTS</th><th class='c'>DTS vs store</th></tr></thead><tbody>");
  mp.models.forEach(m=>{ H.push("<tr><td><b>"+esc(m.model)+"</b></td><td class='c'>"+m.n+"</td><td class='c'>"+(m.loaner_n||"—")+"</td>"+
    "<td class='c'>"+fmt$(m.price)+"</td><td class='c'>"+fmt$(m.gross)+"</td>"+
    "<td class='c "+((m.gross_vs_store||0)>=0?"pos":"neg")+"'>"+signMoney(m.gross_vs_store)+"</td>"+
    "<td class='c'>"+(m.dts==null?"—":m.dts)+"d</td>"+
    "<td class='c "+((m.dts_vs_store||0)<=0?"pos":"neg")+"'>"+(m.dts_vs_store==null?"—":(m.dts_vs_store>0?"+":"")+m.dts_vs_store+"d")+"</td></tr>"); });
  H.push("</tbody></table>");
  return H.join("");
}

function secSeason(a){
  let s=a.seasonality, months=s.months;
  let valid=months.filter(m=>m.price_index!=null);
  let best=valid.reduce((a,b)=>b.price_index>a.price_index?b:a,valid[0]);
  let worst=valid.reduce((a,b)=>b.price_index<a.price_index?b:a,valid[0]);
  let H=["<div class='hint'>How the calendar month affects Infiniti resale (price index vs the annual average, recency-weighted). Discovered from your sales, not assumed.</div>"];
  H.push("<div class='heat'>"+months.map(m=>{ let hc=heatCell(m.price_index);
    return "<div class='hcell' style='background:"+hc[0]+";color:"+hc[1]+"'><div class='hm'>"+MONTHS[m.month-1]+"</div>"+
      "<div class='hi'>"+(m.price_index==null?"—":Math.round(m.price_index*100)+"%")+"</div>"+
      "<div class='hg'>"+fmt$(m.gross)+"</div><div class='hn'>"+m.n+"</div></div>"; }).join("")+"</div>");
  H.push("<div class='foot'>Strongest resale month: <b style='color:var(--teal)'>"+MONTHS[best.month-1]+"</b> ("+Math.round(best.price_index*100)+"%). "+
    "Weakest: <b style='color:var(--warn)'>"+MONTHS[worst.month-1]+"</b> ("+Math.round(worst.price_index*100)+"%). "+
    "A soft late-summer/early-fall (model-year changeover) is a signal to retire loaners before it.</div>");
  return H.join("");
}

function secBenchmark(a){
  let H=["<div class='hint'>Store context — how Infiniti sits against your other franchises on used-car gross and turn.</div>"];
  H.push("<table class='tbl'><thead><tr><th>Make</th><th class='c'>Units</th><th class='c'>Median price</th><th class='c'>Median gross</th><th class='c'>Median DTS</th></tr></thead><tbody>");
  a.benchmark.forEach(b=>H.push("<tr"+(b.make.indexOf("INFINITI")>=0?" class='hl'":"")+"><td>"+esc(b.make)+"</td><td class='c'>"+b.n+"</td><td class='c'>"+fmt$(b.price)+"</td><td class='c'>"+fmt$(b.gross)+"</td><td class='c'>"+(b.dts==null?"—":b.dts)+"d</td></tr>"));
  H.push("</tbody></table>");
  return H.join("");
}

function card(num,title,sub,body){
  return "<section class='card'><div class='ch'><span class='cn'>"+esc(num)+"</span><div><h2>"+esc(title)+"</h2>"+
    (sub?"<div class='csub'>"+esc(sub)+"</div>":"")+"</div></div>"+body+"</section>";
}

function renderAll(){
  let a=STATE.a; let m=a.meta;
  let H=[];
  H.push("<div class='databar-note'>Analyzing <b>"+m.rows.toLocaleString()+"</b> sales · "+
    (m.date_min?m.date_min.toISOString().slice(0,10):"")+" → "+(m.date_max?m.date_max.toISOString().slice(0,10):"")+
    " · recency half-life <b>"+m.half_life_months+" mo</b></div>");
  H.push(kpiOverview(a));
  H.push("<div class='limits'>⚠ Source has <b>no odometer, no interior color, and no retail/wholesale flag</b>. Retention is modeled on <b>vehicle age</b> (the industry-standard axis) and measured as resale price levels &amp; gross — not %-off-MSRP. Add a mileage export later and the mileage axis slots in.</div>");
  H.push(card("1","Loaner vs Retail — the payoff",  "does loaner service pay?", secLoanerVsRetail(a)));
  H.push(card("2","Depreciation / Value Retention", "your own Infiniti curves", secCurves(a)));
  H.push(card("3","Predictive Valuation",           "what will it resell for?", secPredictor(a)));
  H.push(card("4","Color Performance",              "does color move resale?", secColor(a)));
  H.push(card("5","Trim Performance",               "which trims hold value",  secTrim(a)));
  H.push(card("6","Model Ranking & Store Benchmark","Infiniti vs the store",   secModelPerf(a)));
  H.push(card("7","Seasonality",                    "when resale is strongest", secSeason(a)));
  H.push(card("8","Store Benchmark",                "cross-brand context",     secBenchmark(a)));
  document.getElementById("results").innerHTML=H.join("");
  // wire interactive bits
  refreshPredictorOpts(); renderPrediction(); renderColor();
  document.getElementById("pc_model").addEventListener("change",()=>{refreshPredictorOpts();renderPrediction();});
  ["pc_trim","pc_color","pc_month","pc_age"].forEach(id=>{ let e=document.getElementById(id); if(e) e.addEventListener("input",renderPrediction); });
  document.getElementById("clr_model").addEventListener("change",renderColor);
}

function runAnalysis(){
  if(!STATE.sales){ return; }
  STATE.a = analyze(STATE.sales, STATE.halfLife);
  renderAll();
}

function loadFromText(text){
  STATE.sales = loadCSV(text);
  runAnalysis();
}

document.addEventListener("DOMContentLoaded",()=>{
  // recency selector
  let sel=document.getElementById("halflife");
  if(sel) sel.addEventListener("change",()=>{ STATE.halfLife=+sel.value; runAnalysis(); });
  // file import
  let fi=document.getElementById("csvfile");
  if(fi) fi.addEventListener("change",e=>{ let f=e.target.files[0]; if(!f) return;
    let r=new FileReader(); r.onload=()=>loadFromText(String(r.result)); r.readAsText(f); });
  // embedded default data
  if(window.__DATA__) loadFromText(window.__DATA__);
});
