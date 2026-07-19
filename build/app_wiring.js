/* ===================== wiring ===================== */
function getSettings(){
  let manual=document.getElementById("wmode").value==="manual";
  let cw = manual ? {QX80:parseFloat(document.getElementById("w80").value||3),
                     QX60:parseFloat(document.getElementById("w60").value||2),
                     QX65:parseFloat(document.getElementById("w65").value||2)}
                  : {QX80:"auto",QX60:"auto",QX65:"auto"};
  return { order_month: parseInt(document.getElementById("ordmonth").value,10),
    mode: document.getElementById("mode").value,
    allocations:{QX80:parseInt(document.getElementById("a80").value||0,10),
      QX60:parseInt(document.getElementById("a60").value||0,10), QX65:parseInt(document.getElementById("a65").value||0,10)},
    cpo_windows:cw, min_cpo_window:1, order_lead_pad:parseFloat(document.getElementById("wpad").value||0), lead_halflife:6,
    suppress:readSuppress(), roster_add:readAdds(), demote:DEFAULTS.demote, overrides:DEFAULTS.overrides,
    demo_stocks:readDemos().demo_stocks, demo_starts:readDemos().demo_starts, demo_notes:readDemos().demo_notes, prev_loaners:readLoaners(), aged_memory:[],
    prove_bar:2, swap_threshold:90, rate_cap:5.0, paperweight_dts:90, wholesale_min_age:60, stall_days:120, aged_days:60,
    smooth_base:true, anticipate_demo_returns:true, trades:readTrades(),
    demo_pick_max_dts:45, demo_pick_min_total:2, demo_pick_min_r180:2, demo_picks_per_model:3, demo_vins_per_combo:2,
    loaner_fleet_target:numVal("lfleet",20),
    loaner_icv:{QX80:numVal("licv80",0),QX60:numVal("licv60",0),QX65:numVal("licv65",0)},
    loaner_depr_pct:numVal("ldepr",1.25), loaner_depr_base:document.getElementById("lbase").value,
    loaner_min_months:numVal("lmin",3), loaner_max_months:numVal("lmax",7), loaner_service_months:numVal("lsvc",3),
    loaner_mile_cap:numVal("lcap",10000), loaner_velocity_bonus:numVal("lbonus",2500),
    loaner_miles_per_month:numVal("lmpm",1200), loaner_recon:numVal("lrecon",0),
    rebates:{QX80:numVal("reb80",0),QX60:numVal("reb60",0),QX65:numVal("reb65",0)},
    preowned_price_pct:numVal("lret",0.80), loaner_units:readFleet(), preowned_sales:readPreowned() }; }
function numVal(id,def){ let el=document.getElementById(id); if(!el) return def; let v=parseFloat(el.value); return isNaN(v)?def:v; }
const LOANCFG_IDS=["lfleet","licv80","licv60","licv65","reb80","reb60","reb65","ldepr","lbase","lmin","lmax","lsvc","lcap","lbonus","lmpm","lrecon","lret"];
function persistLoanCfg(){ try{ let o={}; LOANCFG_IDS.forEach(id=>o[id]=document.getElementById(id).value); localStorage.setItem("pm_loancfg",JSON.stringify(o)); }catch(e){} }
function restoreLoanCfg(){ try{ let o=JSON.parse(localStorage.getItem("pm_loancfg")||"null"); if(!o) return;
  LOANCFG_IDS.forEach(id=>{ if(o[id]!==undefined&&document.getElementById(id)) document.getElementById(id).value=o[id]; }); }catch(e){} }

/* ---- in-service loaner fleet (editable) ---- */
function rawFleet(){ let out=[];
  document.querySelectorAll("#fleetRows .fleetrow").forEach(row=>{
    if(row.classList.contains("thead")) return;
    out.push({stock:row.querySelector(".f-stock").value.trim(), start:row.querySelector(".f-start").value,
              miles:row.querySelector(".f-miles").value.trim(), note:row.querySelector(".f-note").value.trim()}); });
  return out; }
function addFleetRow(d){ d=d||{};
  let row=document.createElement("div"); row.className="fleetrow";
  row.innerHTML =
    "<input class='f-stock' placeholder='Stock#' value=\""+attrq(d.stock)+"\">"+
    "<input type='date' class='f-start' title='date it went into service' value='"+(d.start||"")+"'>"+
    "<input type='number' class='f-miles' min='0' placeholder='miles' value='"+(d.miles!=null?attrq(d.miles):"")+"'>"+
    "<input class='f-note' placeholder='reason / assignment' value=\""+attrq(d.note)+"\">"+
    "<button class='del' title='pull from the loaner fleet'>✕</button>";
  row.querySelector(".del").addEventListener("click",function(){ row.remove(); liveRecompute(); persistFleet(); });
  row.querySelectorAll("input").forEach(inp=>inp.addEventListener("change",function(){ liveRecompute(); persistFleet(); }));
  document.getElementById("fleetRows").appendChild(row); return row; }
function readFleet(){ let out=[]; rawFleet().forEach(r=>{ if(r.stock) out.push({stock:r.stock,start:r.start,miles:r.miles,note:r.note}); }); return out; }
function persistFleet(){ try{ localStorage.setItem("pm_fleet",JSON.stringify(rawFleet())); }catch(e){} }
function restoreFleet(){ try{ JSON.parse(localStorage.getItem("pm_fleet")||"[]").forEach(addFleetRow); }catch(e){} }

/* ---- preowned sales paste (optional) ---- */
function readPreowned(){
  let text=(document.getElementById("pre")||{}).value||""; if(!text.trim()) return [];
  let rows; try{ rows=parseTable(text); }catch(e){ return []; }
  if(!rows.length) return [];
  // Forgiving: find a header row that has something model-ish and a code-ish column.
  let hi=-1,cm=null;
  for(let i=0;i<rows.length;i++){ let m={}; rows[i].forEach((c,j)=>{ let k=String(c==null?"":c).trim().toLowerCase(); if(k) m[k]=j; });
    let hasCode=("model code" in m)||("modelcode" in m)||("code" in m), hasModel=("model" in m)||("model line" in m)||("series" in m);
    if(hasCode||hasModel){ hi=i; cm=m; break; } }
  if(hi<0) return [];
  function pk(){ for(let i=0;i<arguments.length;i++){ let n=arguments[i].toLowerCase(); if(n in cm) return cm[n]; } return null; }
  let ci={model:pk("model","model line","series"),code:pk("model code","modelcode","code"),
    days:pk("days to sell","days to sell (used)","days","days in stock","dis","age"),
    price:pk("price","sale price","retail","sold price","sales price"),gross:pk("gross","front gross","total gross")};
  let out=[];
  for(let r=hi+1;r<rows.length;r++){ let row=rows[r];
    let codeRaw=ci.code!=null?row[ci.code]:null, modelRaw=ci.model!=null?row[ci.model]:null;
    let code=digitsOnly(codeRaw), model=String(modelRaw||"").trim().toUpperCase();
    if(!model && code) model=modelFromCode(code);
    if(!code && model){ /* no code: skip, trim-level modeling can't hang on this */ }
    if(!model||!code) continue;
    out.push({model:model,code:code.slice(0,4),
      days:ci.days!=null?row[ci.days]:"", price:ci.price!=null?row[ci.price]:"", gross:ci.gross!=null?row[ci.gross]:""}); }
  return out; }
function persistPreowned(){ try{ localStorage.setItem("pm_pre",(document.getElementById("pre")||{}).value||""); }catch(e){} }
function restorePreowned(){ try{ let v=localStorage.getItem("pm_pre"); if(v!=null) document.getElementById("pre").value=v; }catch(e){} }
/* ---- outbound dealer trade log ---- */
const COMBO_MAP = {};
function comboLabel(c){ return c.model+" "+(c.trim||"")+" "+c.ext+"/"+c.int+" ("+c.code+")"; }
function buildComboList(){
  let dl=document.getElementById("combolist"); dl.innerHTML="";
  ROSTER.forEach(c=>{ let label=comboLabel(c); COMBO_MAP[label]={model:c.model,code:c.code,ext:c.ext,int:c.int};
    let o=document.createElement("option"); o.value=label; dl.appendChild(o); });
}
function addTradeRow(t,prepend){ t=t||{};
  let row=document.createElement("div"); row.className="traderow";
  row.innerHTML =
    "<input type='date' class='t-date' value='"+(t.date||"")+"'>"+
    "<input class='t-combo' list='combolist' placeholder='pick a combo…' value=\""+(t.label||"")+"\">"+
    "<input type='number' class='t-days' min='0' placeholder='days' value='"+(t.days!=null?t.days:"")+"'>"+
    "<button class='del' title='remove'>✕</button>";
  row.querySelector(".del").addEventListener("click",function(){ row.remove(); liveRecompute(); persistTrades(); });
  row.querySelectorAll("input").forEach(inp=>inp.addEventListener("change",function(){ liveRecompute(); persistTrades(); }));
  let box=document.getElementById("tradeRows");
  if(prepend && box.firstChild) box.insertBefore(row, box.firstChild); else box.appendChild(row);
  return row;
}
function resolveCombo(label){
  label=(label||"").trim();
  if(COMBO_MAP[label]) return COMBO_MAP[label];
  let p=label.split("|");                              // "QX80|8361|XKJ|A"
  if(p.length===4) return {model:p[0].trim(),code:p[1].trim(),ext:p[2].trim(),int:p[3].trim()};
  let m=label.match(/^([A-Za-z0-9]+).*?([A-Za-z0-9]{2,3})\/([A-Za-z0-9])\s*\((\d{4,5})\)/); // "MODEL … EXT/INT (CODE)"
  if(m) return {model:m[1],code:m[4].slice(0,4),ext:m[2].toUpperCase(),int:m[3].toUpperCase()};
  return null;
}
// Raw row contents — everything the user typed, saved verbatim so nothing is
// ever lost until they delete the row (survives pipeline changes and reloads).
function rawTrades(){
  let out=[];
  document.querySelectorAll("#tradeRows .traderow").forEach(row=>{
    out.push({date:row.querySelector(".t-date").value,
              combo:row.querySelector(".t-combo").value,
              days:row.querySelector(".t-days").value});
  });
  return out;
}
// Parsed, gradeable trades for the engine (rows that resolve to a combo + days).
function readTrades(){
  let out=[];
  rawTrades().forEach(r=>{
    let c=resolveCombo(r.combo);
    if(!c || r.days==="") return;
    out.push({date:r.date,model:c.model,code:c.code,ext:c.ext,int:c.int,days:parseFloat(r.days),label:r.combo});
  });
  return out;
}
function persistTrades(){ try{ localStorage.setItem("pm_trades",JSON.stringify(rawTrades())); }catch(e){} }
function restoreTrades(){ try{ JSON.parse(localStorage.getItem("pm_trades")||"[]")
  .forEach(r=>addTradeRow({date:r.date,label:r.combo,days:r.days})); }catch(e){} }

/* ---- demo roster (editable) ---- */
function attrq(v){ return String(v||"").replace(/"/g,"&quot;"); }
function rawDemos(){
  let out=[];
  document.querySelectorAll("#demoRows .demorow").forEach(row=>{
    out.push({stock:row.querySelector(".d-stock").value.trim(), start:row.querySelector(".d-start").value,
              note:row.querySelector(".d-note").value.trim()});
  });
  return out;
}
function addDemoRow(d){ d=d||{};
  let row=document.createElement("div"); row.className="demorow";
  row.innerHTML =
    "<input class='d-stock' placeholder='Stock# (e.g. N15106)' value=\""+attrq(d.stock)+"\">"+
    "<input type='date' class='d-start' value='"+(d.start||"")+"'>"+
    "<input class='d-note' placeholder='driver / reason' value=\""+attrq(d.note)+"\">"+
    "<button class='del' title='swap back into sellable inventory'>↩ Return</button>";
  row.querySelector(".del").addEventListener("click",function(){ row.remove(); liveRecompute(); persistDemos(); });
  row.querySelectorAll("input").forEach(inp=>inp.addEventListener("change",function(){ liveRecompute(); persistDemos(); }));
  document.getElementById("demoRows").appendChild(row);
  return row;
}
function readDemos(){
  let stocks=[], starts={}, notes={};
  rawDemos().forEach(r=>{ if(!r.stock) return; stocks.push(r.stock); if(r.start) starts[r.stock]=r.start; if(r.note) notes[r.stock]=r.note; });
  return {demo_stocks:stocks, demo_starts:starts, demo_notes:notes};
}
function persistDemos(){ try{ localStorage.setItem("pm_demos",JSON.stringify(rawDemos())); }catch(e){} }
function restoreDemos(){
  let saved=null; try{ saved=JSON.parse(localStorage.getItem("pm_demos")); }catch(e){}
  if(saved && saved.length!==undefined) saved.forEach(addDemoRow);
  else DEFAULTS.demo_stocks.forEach(s=>addDemoRow({stock:s, start:(DEFAULTS.demo_starts&&DEFAULTS.demo_starts[s])||""}));
}

/* ---- previous loaners (editable) ---- */
function rawLoaners(){
  let out=[];
  document.querySelectorAll("#loanerRows .loanrow").forEach(row=>{
    out.push({stock:row.querySelector(".d-stock").value.trim(),
              taken:row.querySelector(".l-taken").value,
              returned:row.querySelector(".l-returned").value,
              note:row.querySelector(".d-note").value.trim()});
  });
  return out;
}
function addLoanerRow(d){ d=d||{};
  let row=document.createElement("div"); row.className="loanrow";
  row.innerHTML =
    "<input class='d-stock' placeholder='Stock#' value=\""+attrq(d.stock)+"\">"+
    "<input type='date' class='l-taken' title='date taken out as a demo' value='"+(d.taken||"")+"'>"+
    "<input type='date' class='l-returned' title='date returned to sellable stock' value='"+(d.returned||"")+"'>"+
    "<input class='d-note' placeholder='driver / reason' value=\""+attrq(d.note)+"\">"+
    "<button class='del' title='remove'>✕</button>";
  row.querySelector(".del").addEventListener("click",function(){ row.remove(); liveRecompute(); persistLoaners(); });
  row.querySelectorAll("input").forEach(inp=>inp.addEventListener("change",function(){ liveRecompute(); persistLoaners(); }));
  document.getElementById("loanerRows").appendChild(row);
  return row;
}
function readLoaners(){ let out=[]; rawLoaners().forEach(r=>{ if(r.stock) out.push({stock:r.stock,taken:r.taken,returned:r.returned,note:r.note}); }); return out; }
function persistLoaners(){ try{ localStorage.setItem("pm_loaners",JSON.stringify(rawLoaners())); }catch(e){} }
function restoreLoaners(){ try{ JSON.parse(localStorage.getItem("pm_loaners")||"[]").forEach(addLoanerRow); }catch(e){} }

/* ---- roster control: suppress (discontinued) + add ---- */
function rawSuppress(){ let out=[];
  document.querySelectorAll("#supRows .suprow").forEach(row=>{
    out.push({code:row.querySelector(".s-code").value.trim(), ext:row.querySelector(".s-ext").value.trim(), int:row.querySelector(".s-int").value.trim()}); });
  return out; }
function addSupRow(d){ d=d||{};
  let row=document.createElement("div"); row.className="suprow";
  row.innerHTML =
    "<input class='s-code' placeholder='e.g. 8411' value=\""+attrq(d.code)+"\">"+
    "<input class='s-ext' placeholder='any' value=\""+attrq(d.ext)+"\">"+
    "<input class='s-int' placeholder='any' value=\""+attrq(d.int)+"\">"+
    "<button class='del' title='remove'>✕</button>";
  row.querySelector(".del").addEventListener("click",function(){ row.remove(); liveRecompute(); persistSuppress(); });
  row.querySelectorAll("input").forEach(inp=>inp.addEventListener("change",function(){ liveRecompute(); persistSuppress(); }));
  document.getElementById("supRows").appendChild(row); return row; }
function readSuppress(){ let out=[]; rawSuppress().forEach(r=>{ if(r.code) out.push({code:r.code,ext:r.ext,int:r.int}); }); return out; }
function persistSuppress(){ try{ localStorage.setItem("pm_suppress",JSON.stringify(rawSuppress())); }catch(e){} }
function restoreSuppress(){ try{ JSON.parse(localStorage.getItem("pm_suppress")||"[]").forEach(addSupRow); }catch(e){} }

function rawAdds(){ let out=[];
  document.querySelectorAll("#addRows .addrow").forEach(row=>{
    out.push({model:row.querySelector(".a-model").value, code:row.querySelector(".a-code").value.trim(),
              ext:row.querySelector(".a-ext").value.trim(), int:row.querySelector(".a-int").value.trim()}); });
  return out; }
function addAddRow(d){ d=d||{};
  let row=document.createElement("div"); row.className="addrow";
  let opts=["QX80","QX60","QX65"].map(m=>"<option "+((d.model||"QX80")===m?"selected":"")+">"+m+"</option>").join("");
  row.innerHTML =
    "<select class='a-model'>"+opts+"</select>"+
    "<input class='a-code' placeholder='4-dig' value=\""+attrq(d.code)+"\">"+
    "<input class='a-ext' placeholder='ext' value=\""+attrq(d.ext)+"\">"+
    "<input class='a-int' placeholder='int' value=\""+attrq(d.int)+"\">"+
    "<button class='del' title='remove'>✕</button>";
  row.querySelector(".del").addEventListener("click",function(){ row.remove(); liveRecompute(); persistAdds(); });
  row.querySelectorAll("input,select").forEach(inp=>inp.addEventListener("change",function(){ liveRecompute(); persistAdds(); }));
  document.getElementById("addRows").appendChild(row); return row; }
function readAdds(){ let out=[]; rawAdds().forEach(r=>{ if(r.code&&r.ext&&r.int) out.push({model:r.model,code:r.code,ext:r.ext,int:r.int}); }); return out; }
function persistAdds(){ try{ localStorage.setItem("pm_adds",JSON.stringify(rawAdds())); }catch(e){} }
function restoreAdds(){ try{ JSON.parse(localStorage.getItem("pm_adds")||"[]").forEach(addAddRow); }catch(e){} }

/* ---- print selector ---- */
function openPrintMenu(){
  let opts=document.getElementById("printopts"), dashes=window.__dashes||[], sel={};
  try{ sel=JSON.parse(localStorage.getItem("pm_print")||"{}"); }catch(e){}
  if(!dashes.length){ opts.innerHTML="<div class='foot'>Compute the dashboards first.</div>"; }
  else opts.innerHTML=dashes.map(function(d){ let on=(sel[d.key]===undefined)?true:sel[d.key];
    return "<label class='pm-opt'><input type='checkbox' data-dash='"+d.key+"' "+(on?"checked":"")+"> "+d.title+"</label>"; }).join("");
  document.getElementById("printmenu").style.display="block";
}
function doPrint(){
  let want={}, sel={};
  document.querySelectorAll("#printopts input[type=checkbox]").forEach(function(b){ want[b.getAttribute("data-dash")]=b.checked; sel[b.getAttribute("data-dash")]=b.checked; });
  document.querySelectorAll("#results .dash").forEach(function(sec){
    let k=sec.getAttribute("data-dash"); let show=(k in want)?want[k]:true;
    sec.classList.toggle("printhide", !show);
  });
  try{ localStorage.setItem("pm_print",JSON.stringify(sel)); }catch(e){}
  document.getElementById("printmenu").style.display="none";
  window.print();
}
function restorePrintHidden(){ document.querySelectorAll("#results .dash.printhide").forEach(function(s){ s.classList.remove("printhide"); }); }

function markFilled(){
  document.getElementById("inv").classList.toggle("ok", document.getElementById("inv").value.trim()!=="");
  document.getElementById("sales").classList.toggle("ok", document.getElementById("sales").value.trim()!==""); }
let HAS_RUN=false;
function compute(scroll){
  let st=document.getElementById("status"); st.className="foot";
  let invText=document.getElementById("inv").value, salesText=document.getElementById("sales").value;
  if(!invText.trim()||!salesText.trim()){ st.className="foot err"; st.textContent="Paste both exports first (or click Load sample data)."; return; }
  try{
    let inv=loadInventory(invText), sales=loadSales(salesText), s=getSettings();
    let td=document.getElementById("today").value, today=td?new Date(td+"T00:00:00"):new Date();
    render(runEngine(inv,sales,s,today));
    st.className="foot okmsg"; st.textContent="✓ recomputed — "+inv.length+" inventory, "+sales.length+" sales rows";
    HAS_RUN=true;
    try{ localStorage.setItem("pm_inv",invText); localStorage.setItem("pm_sales",salesText);
      localStorage.setItem("pm_set",JSON.stringify(readControls())); }catch(e){}
    // NOTE: never collapse the data panel here — live recomputes (from editing a
    // trade or a control) must leave the panel exactly as the user left it.
    if(scroll) document.getElementById("results").scrollIntoView({behavior:"smooth",block:"start"});
  }catch(e){ st.className="foot err"; st.textContent="Problem: "+e.message; }
}
function computeAndCollapse(){ compute(true); if(HAS_RUN) document.getElementById("datacard").style.display="none"; }
function liveRecompute(){ if(HAS_RUN) compute(false); }
function readControls(){ return {m:document.getElementById("ordmonth").value,mode:document.getElementById("mode").value,
  a80:document.getElementById("a80").value,a60:document.getElementById("a60").value,a65:document.getElementById("a65").value,
  w80:document.getElementById("w80").value,w60:document.getElementById("w60").value,w65:document.getElementById("w65").value,today:document.getElementById("today").value}; }
function wireFile(inputId,taId,statId){ document.getElementById(inputId).addEventListener("change",function(e){
  let f=e.target.files[0]; if(!f) return; let rd=new FileReader();
  rd.onload=function(){ document.getElementById(taId).value=rd.result; markFilled(); document.getElementById(statId).textContent=f.name; }; rd.readAsText(f); }); }
window.addEventListener("DOMContentLoaded",function(){
  let sel=document.getElementById("ordmonth"), now=new Date().getMonth();
  MONTHS.forEach((m,i)=>{ let o=document.createElement("option"); o.value=i+1; o.textContent=m; if(i===now) o.selected=true; sel.appendChild(o); });
  document.getElementById("today").value=new Date().toISOString().slice(0,10);
  document.getElementById("run").addEventListener("click",computeAndCollapse);
  document.getElementById("editdata").addEventListener("click",function(){ let d=document.getElementById("datacard");
    d.style.display=d.style.display==="none"?"block":"none"; if(d.style.display!=="none") d.scrollIntoView({behavior:"smooth"}); });
  document.getElementById("loadsample").addEventListener("click",function(){
    document.getElementById("inv").value=SAMPLE.inv; document.getElementById("sales").value=SAMPLE.sales;
    document.getElementById("ordmonth").value=9; markFilled(); computeAndCollapse(); });
  document.getElementById("clearall").addEventListener("click",function(){
    document.getElementById("inv").value=""; document.getElementById("sales").value=""; markFilled();
    document.getElementById("results").innerHTML=""; HAS_RUN=false;
    try{ localStorage.removeItem("pm_inv"); localStorage.removeItem("pm_sales"); }catch(e){} });
  document.getElementById("inv").addEventListener("input",markFilled);
  document.getElementById("sales").addEventListener("input",markFilled);
  buildComboList();
  document.getElementById("addTrade").addEventListener("click",function(){ addTradeRow(null,true); persistTrades(); });
  restoreTrades();
  // collapse/expand any dashboard by clicking its header
  document.getElementById("results").addEventListener("click",function(e){
    let sec=e.target.closest?e.target.closest(".sec"):null; if(!sec) return;
    let dash=sec.closest(".dash"); if(!dash) return;
    dash.classList.toggle("collapsed");
    let cols=[]; document.querySelectorAll("#results .dash.collapsed").forEach(function(d){ cols.push(d.getAttribute("data-dash")); });
    try{ localStorage.setItem("pm_collapsed",JSON.stringify(cols)); }catch(err){}
  });
  document.getElementById("addDemo").addEventListener("click",function(){ addDemoRow(); persistDemos(); });
  restoreDemos();
  document.getElementById("addLoaner").addEventListener("click",function(){ addLoanerRow(); persistLoaners(); });
  restoreLoaners();
  document.getElementById("addSup").addEventListener("click",function(){ addSupRow(); persistSuppress(); });
  restoreSuppress();
  document.getElementById("addAdd").addEventListener("click",function(){ addAddRow(); persistAdds(); });
  restoreAdds();
  document.getElementById("addFleet").addEventListener("click",function(){ addFleetRow(); persistFleet(); });
  restoreFleet();
  restorePreowned(); restoreLoanCfg();
  document.getElementById("pre").addEventListener("change",function(){ liveRecompute(); persistPreowned(); });
  LOANCFG_IDS.forEach(id=>document.getElementById(id).addEventListener("change",function(){ liveRecompute(); persistLoanCfg(); }));
  // print selector
  document.getElementById("printbtn").addEventListener("click",function(e){ e.stopPropagation();
    let m=document.getElementById("printmenu"); if(m.style.display==="block") m.style.display="none"; else openPrintMenu(); });
  document.getElementById("printmenu").addEventListener("click",function(e){ e.stopPropagation(); });
  document.getElementById("printGo").addEventListener("click",doPrint);
  document.getElementById("printAll").addEventListener("click",function(){ document.querySelectorAll("#printopts input").forEach(function(b){ b.checked=true; }); });
  document.getElementById("printNone").addEventListener("click",function(){ document.querySelectorAll("#printopts input").forEach(function(b){ b.checked=false; }); });
  document.addEventListener("click",function(){ document.getElementById("printmenu").style.display="none"; });
  window.addEventListener("afterprint",restorePrintHidden);
  function toggleManual(){ document.getElementById("manualwins").style.display =
    document.getElementById("wmode").value==="manual" ? "flex" : "none"; }
  document.getElementById("wmode").addEventListener("change",toggleManual);
  toggleManual();
  ["ordmonth","mode","a80","a60","a65","w80","w60","w65","today","wmode","wpad"].forEach(id=>
    document.getElementById(id).addEventListener("change",liveRecompute));
  wireFile("invfile","inv","invstat"); wireFile("salesfile","sales","salesstat");
  try{ let i=localStorage.getItem("pm_inv"), sa=localStorage.getItem("pm_sales");
    if(i) document.getElementById("inv").value=i; if(sa) document.getElementById("sales").value=sa;
    let set=JSON.parse(localStorage.getItem("pm_set")||"null");
    if(set){ document.getElementById("ordmonth").value=set.m; document.getElementById("mode").value=set.mode;
      if(set.a80)document.getElementById("a80").value=set.a80; if(set.a60)document.getElementById("a60").value=set.a60; if(set.a65)document.getElementById("a65").value=set.a65;
      if(set.w80)document.getElementById("w80").value=set.w80; if(set.w60)document.getElementById("w60").value=set.w60; if(set.w65)document.getElementById("w65").value=set.w65; }
    markFilled();
    if(i&&sa) computeAndCollapse();   // reload opens to the dashboard, panel collapsed
  }catch(e){}
});
