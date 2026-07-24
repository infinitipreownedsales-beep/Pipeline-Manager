/* ===================== wiring ===================== */
/* Loaner Intelligence depreciation history: parse once, analyze under the chosen
   recency weight, and expose window.DEPR so the loaner economics can price a
   candidate's resale from real history. */
window.DEPR = { sales:null, a:null, active:false, halfLife:24 };
function buildDepr(text, halfLife){
  var st=document.getElementById("deprStat");
  try{
    if(text!=null) window.DEPR.sales = window.LoanerIntel.loadCSV(text);
    window.DEPR.halfLife = halfLife || window.DEPR.halfLife || 24;
    if(window.DEPR.sales && window.DEPR.sales.length){
      window.DEPR.a = window.LoanerIntel.analyze(window.DEPR.sales, window.DEPR.halfLife);
      window.DEPR.active = true;
      if(st){ var m=window.DEPR.a.meta; st.className="foot okmsg";
        st.textContent="✓ "+m.infiniti_rows.toLocaleString()+" Infiniti sales · "+m.loaner_rows+" past loaners · half-life "+window.DEPR.halfLife+"mo"; }
    }
  }catch(e){ window.DEPR.active=false; if(st){ st.className="foot err"; st.textContent="History problem: "+e.message; } }
}
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
    prove_bar:2, swap_threshold:90, rate_cap:5.0, paperweight_dts:90, wholesale_min_age:60, stall_days:120, aged_days:60, seasonality_shrink_k:6,
    smooth_base:true, anticipate_demo_returns:true, trades:readTrades(),
    demo_pick_max_dts:45, demo_pick_min_total:2, demo_pick_min_r180:2, demo_picks_per_model:3, demo_vins_per_combo:2, loaner_picks_per_model:6,
    loaner_fleet_target:numVal("lfleet",20),
    loaner_icv:{QX80:numVal("licv80",0),QX60:numVal("licv60",0),QX65:numVal("licv65",0)},
    loaner_depr_pct:numVal("ldepr",1.25), loaner_depr_base:document.getElementById("lbase").value,
    loaner_min_months:numVal("lmin",3), loaner_max_months:numVal("lmax",7), loaner_service_months:numVal("lsvc",3),
    loaner_mile_cap:numVal("lcap",10000), loaner_velocity_bonus:numVal("lbonus",2500),
    loaner_miles_per_month:numVal("lmpm",1200), loaner_recon:numVal("lrecon",0),
    rebates:{QX80:numVal("reb80",0),QX60:numVal("reb60",0),QX65:numVal("reb65",0)},
    preowned_price_pct:numVal("lret",0.80), order_unit_decay:numVal("ldecay",1.0),
    loaner_hold_per_day:numVal("lhold",0), incentives:readIncentives(),
    writedown_method:(document.getElementById("lwdmethod")||{}).value||"pct", writedown_flat:numVal("lwdflat",0),
    color_map:readColorMap(),
    service_need:((document.getElementById("serviceNeed")||{}).value||"").trim()===""?null:numVal("serviceNeed",0), new_retail_gross:numVal("lnewgross",1500),
    loaner_units:readFleet(), preowned_sales:readPreowned() }; }
function numVal(id,def){ let el=document.getElementById(id); if(!el) return def; let v=parseFloat(el.value); return isNaN(v)?def:v; }
const LOANCFG_IDS=["lfleet","licv80","licv60","licv65","reb80","reb60","reb65","ldepr","lwdmethod","lwdflat","lbase","lmin","lmax","lsvc","lcap","lbonus","lmpm","lrecon","lret","ldecay","lhold","lnewgross"];
function persistLoanCfg(){ try{ let o={}; LOANCFG_IDS.forEach(id=>o[id]=document.getElementById(id).value); localStorage.setItem("pm_loancfg",JSON.stringify(o)); }catch(e){} }
function restoreLoanCfg(){ try{ let o=JSON.parse(localStorage.getItem("pm_loancfg")||"null"); if(!o) return;
  LOANCFG_IDS.forEach(id=>{ if(o[id]!==undefined&&document.getElementById(id)) document.getElementById(id).value=o[id]; }); }catch(e){} }

/* ---- paint color-code map (translate inventory codes to generic colors) ---- */
const COLOR_MAP_DEFAULT=[["XKJ","WHITE"],["QBE","WHITE"],["KCN","GRAY"],["KAD","GRAY"],["KH3","BLACK"],["GAT","BLACK"]];
const COLOR_CHOICES=["WHITE","BLACK","GRAY","SILVER","BLUE","RED","BROWN","GREEN","GOLD","OTHER"];
function rawColorMap(){ let out=[]; document.querySelectorAll("#colorRows .colorrow").forEach(row=>{
  if(row.classList.contains("thead")) return;
  out.push({code:row.querySelector(".c-code").value.trim().toUpperCase(), color:row.querySelector(".c-color").value}); }); return out; }
function addColorRow(d){ d=d||{}; let row=document.createElement("div"); row.className="colorrow";
  row.innerHTML="<input class='c-code' placeholder='code' value='"+attrq(d.code||"")+"' style='text-transform:uppercase'>"+
    "<select class='c-color'>"+COLOR_CHOICES.map(c=>"<option"+((d.color||"WHITE")===c?" selected":"")+">"+c+"</option>").join("")+"</select>"+
    "<button class='del' title='remove'>✕</button>";
  row.querySelector(".del").addEventListener("click",function(){ row.remove(); liveRecompute(); persistColorMap(); });
  row.querySelectorAll("input,select").forEach(inp=>inp.addEventListener("change",function(){ liveRecompute(); persistColorMap(); }));
  document.getElementById("colorRows").appendChild(row); return row; }
function readColorMap(){ let m={}; rawColorMap().forEach(r=>{ if(r.code) m[r.code]=r.color; }); return m; }
function persistColorMap(){ try{ localStorage.setItem("pm_colormap",JSON.stringify(rawColorMap())); }catch(e){} }
function restoreColorMap(){ let saved=null; try{ saved=JSON.parse(localStorage.getItem("pm_colormap")||"null"); }catch(e){}
  if(saved&&saved.length) saved.forEach(addColorRow);
  else COLOR_MAP_DEFAULT.forEach(pair=>addColorRow({code:pair[0],color:pair[1]})); }

/* ---- centralized incentive table (Enh 1+2: by model / year / month) ---- */
function rawInc(){ let out=[];
  document.querySelectorAll("#incRows .increw").forEach(row=>{
    if(row.classList.contains("thead")) return;
    out.push({year:row.querySelector(".i-year").value.trim(), model:row.querySelector(".i-model").value,
      month:row.querySelector(".i-month").value, rebate:row.querySelector(".i-reb").value.trim(),
      icv:row.querySelector(".i-icv").value.trim(), dealer_cash:row.querySelector(".i-dc").value.trim(),
      velocity_bonus:row.querySelector(".i-velo").value.trim()}); });
  return out; }
function addIncentiveRow(d){ d=d||{};
  let row=document.createElement("div"); row.className="increw";
  let mopts="<option value='0'>Any</option>"+MONTHS.map((m,i)=>"<option value='"+(i+1)+"'"+((d.month==i+1)?" selected":"")+">"+m+"</option>").join("");
  let modopts=MODELS.map(m=>"<option"+((d.model===m)?" selected":"")+">"+m+"</option>").join("");
  row.innerHTML =
    "<input type='number' class='i-year' placeholder='2026' value='"+(d.year!=null?attrq(d.year):"")+"'>"+
    "<select class='i-model'>"+modopts+"</select>"+
    "<select class='i-month'>"+mopts+"</select>"+
    "<input type='number' class='i-reb' placeholder='rebate' value='"+(d.rebate!=null?attrq(d.rebate):"")+"'>"+
    "<input type='number' class='i-icv' placeholder='ICV' value='"+(d.icv!=null?attrq(d.icv):"")+"'>"+
    "<input type='number' class='i-dc' placeholder='dealer cash' value='"+(d.dealer_cash!=null?attrq(d.dealer_cash):"")+"'>"+
    "<input type='number' class='i-velo' placeholder='velocity' value='"+(d.velocity_bonus!=null?attrq(d.velocity_bonus):"")+"'>"+
    "<button class='del' title='remove program'>✕</button>";
  row.querySelector(".del").addEventListener("click",function(){ row.remove(); liveRecompute(); persistInc(); });
  row.querySelectorAll("input,select").forEach(inp=>inp.addEventListener("change",function(){ liveRecompute(); persistInc(); }));
  document.getElementById("incRows").appendChild(row); return row; }
function readIncentives(){ let out=[]; rawInc().forEach(r=>{ if(r.model) out.push({year:parseInt(r.year,10)||0,model:r.model,
  month:parseInt(r.month,10)||0,rebate:r.rebate,icv:r.icv,dealer_cash:r.dealer_cash,velocity_bonus:r.velocity_bonus}); }); return out; }
function persistInc(){ try{ localStorage.setItem("pm_inc",JSON.stringify(rawInc())); }catch(e){} }
function restoreInc(){ try{ JSON.parse(localStorage.getItem("pm_inc")||"[]").forEach(addIncentiveRow); }catch(e){} }

/* ---- in-service loaner fleet (editable) ---- */
function rawFleet(){ let out=[];
  document.querySelectorAll("#fleetRows .fleetrow").forEach(row=>{
    if(row.classList.contains("thead")) return;
    out.push({stock:row.querySelector(".f-stock").value.trim(), model:row.querySelector(".f-model").value.trim(),
              ext:row.querySelector(".f-ext").value.trim(), start:row.querySelector(".f-start").value,
              miles:row.querySelector(".f-miles").value.trim(), note:row.querySelector(".f-note").value.trim(),
              code:row.getAttribute("data-code")||"", year:row.getAttribute("data-year")||""}); });
  return out; }
function addFleetRow(d){ d=d||{};
  let row=document.createElement("div"); row.className="fleetrow";
  if(d.code) row.setAttribute("data-code",d.code);
  if(d.year) row.setAttribute("data-year",d.year);
  row.innerHTML =
    "<input class='f-stock' placeholder='Stock#' value=\""+attrq(d.stock)+"\">"+
    "<input class='f-model' placeholder='Model' value=\""+attrq(d.model||"")+"\">"+
    "<input class='f-ext' placeholder='color' title='exterior color or paint code' value=\""+attrq(d.ext||"")+"\">"+
    "<input type='date' class='f-start' title='date it went into service' value='"+(d.start||"")+"'>"+
    "<input type='number' class='f-miles' min='0' placeholder='miles' value='"+(d.miles!=null?attrq(d.miles):"")+"'>"+
    "<input class='f-note' placeholder='reason / assignment' value=\""+attrq(d.note)+"\">"+
    "<button class='del' title='pull from the loaner fleet'>✕</button>";
  row.querySelector(".del").addEventListener("click",function(){ row.remove(); liveRecompute(); persistFleet(); });
  row.querySelectorAll("input").forEach(inp=>inp.addEventListener("change",function(){ liveRecompute(); persistFleet(); }));
  document.getElementById("fleetRows").appendChild(row); return row; }
function readFleet(){ let out=[]; rawFleet().forEach(r=>{ if(r.stock) out.push({stock:r.stock,model:(r.model||"").toUpperCase(),ext:r.ext,start:r.start,miles:r.miles,note:r.note,code:r.code,year:r.year}); }); return out; }
function persistFleet(){ try{ localStorage.setItem("pm_fleet",JSON.stringify(rawFleet())); }catch(e){} }
function restoreFleet(){ try{ JSON.parse(localStorage.getItem("pm_fleet")||"[]").forEach(addFleetRow); }catch(e){} }
// Import a DMS "vehicles" export as the current service loaner fleet. Forgiving on
// column names/case; only Courtesy/loaner-program rows are taken. Replaces the table.
function importFleet(){
  let ta=document.getElementById("fleetImport"), st=document.getElementById("status");
  let text=(ta&&ta.value)||""; if(!text.trim()){ if(st){st.className="foot err";st.textContent="Paste the DMS vehicle export first.";} return; }
  let rows; try{ rows=parseTable(text); }catch(e){ if(st){st.className="foot err";st.textContent="Couldn't read that paste.";} return; }
  if(!rows.length) return;
  // header
  let hi=-1,cm=null;
  for(let i=0;i<rows.length;i++){ let m={}; rows[i].forEach((c,j)=>{ let k=String(c==null?"":c).trim().toLowerCase(); if(k) m[k]=j; });
    if(("vin" in m)||("stock_number" in m)||("stock #" in m)||("stock#" in m)){ hi=i; cm=m; break; } }
  if(hi<0){ if(st){st.className="foot err";st.textContent="No header row with VIN / stock number found.";} return; }
  function pk(){ for(let i=0;i<arguments.length;i++){ let n=arguments[i].toLowerCase(); if(n in cm) return cm[n]; } return null; }
  let ci={stock:pk("stock_number","stock #","stock#","stock"),vin:pk("vin"),model:pk("model"),code:pk("model code","model_code","modelcode"),
    ext:pk("exterior code","exterior_code","ext code","exterior color","ext"),year:pk("year","my"),
    program:pk("program"),status:pk("status"),miles:pk("odometer_value","odometer","miles"),
    start:pk("in_service_date","in service date","in_service","in-service start","start")};
  let added=0, skipped=0;
  document.getElementById("fleetRows").innerHTML="";
  for(let r=hi+1;r<rows.length;r++){ let row=rows[r]; if(!row||!row.length) continue;
    let prog=ci.program!=null?String(row[ci.program]||"").toLowerCase():"courtesy";
    if(prog && !/courtes|loaner|service|demo/.test(prog)){ skipped++; continue; }
    let stat=ci.status!=null?String(row[ci.status]||"").toLowerCase():"";
    if(/dispos|sold|wholesal/.test(stat)){ skipped++; continue; }   // already gone
    let stock=ci.stock!=null?String(row[ci.stock]||"").trim():"";
    let vin=ci.vin!=null?String(row[ci.vin]||"").trim():"";
    if(!stock && vin) stock=vin.slice(-8);
    if(!stock && !vin) continue;
    let start=ci.start!=null?String(row[ci.start]||"").trim():"";
    let d=start.match(/(\d{4})-(\d{2})-(\d{2})/); if(d) start=d[1]+"-"+d[2]+"-"+d[3];
    else { let d2=start.match(/(\d{1,2})\/(\d{1,2})\/(\d{4})/); if(d2) start=d2[3]+"-"+("0"+d2[1]).slice(-2)+"-"+("0"+d2[2]).slice(-2); else start=""; }
    let miles=ci.miles!=null?String(row[ci.miles]||"").replace(/[^0-9.]/g,""):"";
    let model=ci.model!=null?String(row[ci.model]||"").trim().toUpperCase():"";
    let code=ci.code!=null?String(row[ci.code]||"").trim():"";
    if(!model && code) model=modelFromCode(digitsOnly(code));
    let ext=ci.ext!=null?String(row[ci.ext]||"").trim().toUpperCase():"";
    let year=ci.year!=null?String(row[ci.year]||"").trim():"";
    let note=(vin?("VIN "+vin.slice(-6)):"")+(prog&&prog!=="courtesy"?(" · "+prog):"");
    addFleetRow({stock:stock,model:model,ext:ext,start:start,miles:miles,note:note,code:code,year:year}); added++; }
  persistFleet(); if(HAS_RUN) liveRecompute();
  if(st){ st.className="foot okmsg"; st.textContent="✓ imported "+added+" loaner unit"+(added===1?"":"s")+(skipped?(" ("+skipped+" non-loaner rows skipped)"):""); }
}

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
/* ---- outbound dealer trade log ----
   The vehicle is captured as explicit Model + Code + Ext + Int fields, so ANY
   paint code (present or future) is accepted — no roster membership check and no
   fixed-length assumption that would silently reject a valid trade. */
function buildCodeList(){
  let dl=document.getElementById("codelist"); if(!dl) return; dl.innerHTML="";
  let seen={};
  ROSTER.forEach(c=>{ if(seen[c.code]) return; seen[c.code]=1;
    let o=document.createElement("option"); o.value=c.code; o.label=c.model+" "+(c.trim||""); dl.appendChild(o); });
}
function tModelOpts(sel){ return ["QX80","QX60","QX65"].map(m=>"<option "+((sel||"")===m?"selected":"")+">"+m+"</option>").join(""); }
function addTradeRow(t,prepend){ t=t||{};
  let row=document.createElement("div"); row.className="traderow";
  row.innerHTML =
    "<input type='date' class='t-date' value='"+(t.date||"")+"'>"+
    "<select class='t-model'><option value=''>—</option>"+tModelOpts(t.model)+"</select>"+
    "<input class='t-code' list='codelist' placeholder='code' value=\""+attrq(t.code||"")+"\">"+
    "<input class='t-ext' placeholder='ext' value=\""+attrq(t.ext||"")+"\">"+
    "<input class='t-int' placeholder='int' value=\""+attrq(t.int||"")+"\">"+
    "<input type='number' class='t-days' min='0' placeholder='days' value='"+(t.days!=null?t.days:"")+"'>"+
    "<button class='del' title='remove'>✕</button>";
  row.querySelector(".del").addEventListener("click",function(){ row.remove(); liveRecompute(); persistTrades(); });
  row.querySelectorAll("input,select").forEach(inp=>inp.addEventListener("change",function(){ liveRecompute(); persistTrades(); }));
  let box=document.getElementById("tradeRows");
  if(prepend && box.firstChild) box.insertBefore(row, box.firstChild); else box.appendChild(row);
  return row;
}
// Backward-compat: parse a legacy single-field combo string into parts. Forgiving
// on paint-code length; used only to migrate previously-saved trades.
function resolveCombo(label){
  label=(label||"").trim(); if(!label) return null;
  let p=label.split("|");                              // "QX80|8361|XKJ|A"
  if(p.length===4) return {model:p[0].trim(),code:digitsOnly(p[1]).slice(0,4),ext:p[2].trim().toUpperCase(),int:p[3].trim().toUpperCase()};
  let ei=label.match(/([A-Za-z0-9]{1,4})\/([A-Za-z0-9]{1,2})/);         // any EXT/INT
  let codeM=label.match(/(\d{4,5})/);                                    // 4-5 digit code
  let modelM=label.match(/QX\s?(80|60|65)/i);
  let model=modelM?("QX"+modelM[1]):(codeM?modelFromCode(codeM[1]):"");
  let code=codeM?codeM[1].slice(0,4):"";
  if(model&&code&&ei) return {model:model,code:code,ext:ei[1].toUpperCase(),int:ei[2].toUpperCase()};
  return null;
}
// Raw row contents — saved verbatim so nothing is lost until the user deletes it.
function rawTrades(){
  let out=[];
  document.querySelectorAll("#tradeRows .traderow").forEach(row=>{
    if(row.classList.contains("thead")) return;
    out.push({date:row.querySelector(".t-date").value,
              model:row.querySelector(".t-model").value,
              code:row.querySelector(".t-code").value.trim(),
              ext:row.querySelector(".t-ext").value.trim(),
              int:row.querySelector(".t-int").value.trim(),
              days:row.querySelector(".t-days").value});
  });
  return out;
}
// Gradeable trades for the engine: any row with a code (model inferred from it
// if blank) and a days value. Ext/Int are free-form and pass through untouched.
function readTrades(){
  let out=[];
  rawTrades().forEach(r=>{
    let code=digitsOnly(r.code).slice(0,4);
    if(!code || r.days==="") return;
    let model=r.model||modelFromCode(code);
    if(!model) return;
    out.push({date:r.date,model:model,code:code,ext:r.ext.toUpperCase(),int:r.int.toUpperCase(),days:parseFloat(r.days)});
  });
  return out;
}
function persistTrades(){ try{ localStorage.setItem("pm_trades",JSON.stringify(rawTrades())); }catch(e){} }
function restoreTrades(){ try{ JSON.parse(localStorage.getItem("pm_trades")||"[]").forEach(r=>{
  if(r.model!==undefined||r.code!==undefined&&r.ext!==undefined){ addTradeRow(r); }   // new format
  else { let c=resolveCombo(r.combo); addTradeRow(c?{date:r.date,model:c.model,code:c.code,ext:c.ext,int:c.int,days:r.days}:{date:r.date,days:r.days}); }
}); }catch(e){} }

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
    "<button class='del' title='return this demo to sellable stock — moves it to Previous loaners with today as the return date'>↩ Return</button>";
  // One-click swap: Return moves the demo into the Previous-loaners list (its demo
  // start becomes 'taken', today becomes 'returned'), then removes the demo row.
  row.querySelector(".del").addEventListener("click",function(){
    let stock=row.querySelector(".d-stock").value.trim();
    if(stock){
      let start=row.querySelector(".d-start").value;
      let note=row.querySelector(".d-note").value.trim();
      let today=new Date().toISOString().slice(0,10);
      let lr=addLoanerRow({stock:stock, taken:start, returned:today, note:note});
      persistLoaners();
      if(lr) lr.scrollIntoView({behavior:"smooth",block:"center"});
    }
    row.remove(); liveRecompute(); persistDemos();
  });
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
    "<input class='s-code' placeholder='code or trim (e.g. PURE)' value=\""+attrq(d.code)+"\">"+
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
/* ---- collapsible + lockable data-entry sections (P2 safety / P3 organization) ---- */
function lockDSection(sec, locked){
  sec.classList.toggle("dsec-locked", locked);
  let btn=sec.querySelector(".dsec-lock");
  if(btn) btn.innerHTML = locked ? "🔒 Locked" : "🔓 Editing";
  sec.querySelectorAll(".dsec-body input,.dsec-body select,.dsec-body textarea,.dsec-body button").forEach(function(el){ el.disabled=locked; });
}
function persistDCollapse(){ try{ let st={};
  document.querySelectorAll("#datacard .dsec").forEach(function(s){ st[s.getAttribute("data-title")]=s.classList.contains("dsec-collapsed"); });
  localStorage.setItem("pm_dcollapsed",JSON.stringify(st)); }catch(e){} }
function setDCollapsed(sec, col){ sec.classList.toggle("dsec-collapsed", col); let cv=sec.querySelector(".dsec-cv"); if(cv) cv.textContent = col?"▸":"▾"; }
function setupDataSections(){
  let dc=document.getElementById("datacard"); if(!dc||dc.querySelector(".dsec")) return;
  let saved=null; try{ saved=JSON.parse(localStorage.getItem("pm_dcollapsed")||"null"); }catch(e){}
  let secs=[].slice.call(dc.children).filter(function(d){ return d.tagName==="DIV" && (d.getAttribute("style")||"").indexOf("border-top")>=0; });
  secs.forEach(function(sec){
    let label=sec.querySelector("label.top"), title="Section";
    if(label && label.firstChild && label.firstChild.nodeType===3){ title=label.firstChild.textContent.trim(); label.removeChild(label.firstChild); }
    else if(label){ title=label.textContent.trim().split("—")[0].trim(); }
    let bar=document.createElement("div"); bar.className="dsec-bar";
    bar.innerHTML="<span class='dsec-cv'>▸</span><span class='dsec-ttl'>"+title+"</span><button type='button' class='dsec-lock'>🔒 Locked</button>";
    let body=document.createElement("div"); body.className="dsec-body";
    while(sec.firstChild) body.appendChild(sec.firstChild);
    sec.className="dsec"; sec.removeAttribute("style"); sec.setAttribute("data-title",title);
    sec.appendChild(bar); sec.appendChild(body);
    setDCollapsed(sec, saved && (title in saved) ? saved[title] : true);   // default collapsed
    lockDSection(sec, true);                                                // always locked on load
    bar.addEventListener("click",function(e){ if(e.target.closest(".dsec-lock")) return;
      setDCollapsed(sec, !sec.classList.contains("dsec-collapsed")); persistDCollapse(); });
    bar.querySelector(".dsec-lock").addEventListener("click",function(e){ e.stopPropagation();
      let nowLocked=!sec.classList.contains("dsec-locked"); lockDSection(sec, nowLocked);
      if(!nowLocked){ setDCollapsed(sec, false); persistDCollapse(); } });
  });
}

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
  document.getElementById("resetsettings").addEventListener("click",function(){
    // Clear stale control-state that can silently distort the order: allocations
    // / order month / window (pm_set) and the whole loaner setup (pm_loancfg,
    // pm_fleet, pm_pre). Keeps pasted data, trade log, demos, and roster control.
    ["pm_set","pm_loancfg","pm_fleet","pm_pre"].forEach(function(k){ try{ localStorage.removeItem(k); }catch(e){} });
    location.reload();
  });
  document.getElementById("clearall").addEventListener("click",function(){
    document.getElementById("inv").value=""; document.getElementById("sales").value=""; markFilled();
    document.getElementById("results").innerHTML=""; HAS_RUN=false;
    try{ localStorage.removeItem("pm_inv"); localStorage.removeItem("pm_sales"); }catch(e){} });
  document.getElementById("inv").addEventListener("input",markFilled);
  document.getElementById("sales").addEventListener("input",markFilled);
  buildCodeList();
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
  { let ib=document.getElementById("importFleetBtn"); if(ib) ib.addEventListener("click",importFleet);
    let fi=document.getElementById("fleetImport"); if(fi) fi.addEventListener("change",function(){ try{ localStorage.setItem("pm_fleetimport",fi.value); }catch(e){} }); }
  restoreLoaners();
  document.getElementById("addSup").addEventListener("click",function(){ addSupRow(); persistSuppress(); });
  restoreSuppress();
  document.getElementById("addAdd").addEventListener("click",function(){ addAddRow(); persistAdds(); });
  restoreAdds();
  document.getElementById("addFleet").addEventListener("click",function(){ addFleetRow(); persistFleet(); });
  restoreFleet();
  try{ let fv=localStorage.getItem("pm_fleetimport"); if(fv!=null&&document.getElementById("fleetImport")) document.getElementById("fleetImport").value=fv; }catch(e){}
  document.getElementById("addInc").addEventListener("click",function(){ addIncentiveRow(); persistInc(); });
  restoreInc();
  document.getElementById("addColor").addEventListener("click",function(){ addColorRow(); persistColorMap(); });
  restoreColorMap();
  restorePreowned(); restoreLoanCfg();
  document.getElementById("pre").addEventListener("change",function(){ liveRecompute(); persistPreowned(); });
  LOANCFG_IDS.forEach(id=>document.getElementById(id).addEventListener("change",function(){ liveRecompute(); persistLoanCfg(); }));
  // depreciation history: analyze the pre-loaded export, then wire recency + re-import
  if(window.LoanerIntel && window.__LOANER_HISTORY__) buildDepr(window.__LOANER_HISTORY__, 24);
  document.getElementById("deprHalf").addEventListener("change",function(){ buildDepr(null, parseFloat(this.value)); liveRecompute(); });
  document.getElementById("deprFile").addEventListener("change",function(e){ var f=e.target.files[0]; if(!f) return;
    var rd=new FileReader(); rd.onload=function(){ buildDepr(String(rd.result), window.DEPR.halfLife); liveRecompute(); }; rd.readAsText(f); });
  // wrap control sections as collapsible + lockable (after their rows are restored)
  setupDataSections();
  document.getElementById("expandAll").addEventListener("click",function(){ document.querySelectorAll("#datacard .dsec").forEach(function(s){ setDCollapsed(s,false); }); persistDCollapse(); });
  document.getElementById("collapseAll").addEventListener("click",function(){ document.querySelectorAll("#datacard .dsec").forEach(function(s){ setDCollapsed(s,true); }); persistDCollapse(); });
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
  ["ordmonth","mode","a80","a60","a65","w80","w60","w65","today","wmode","wpad","serviceNeed"].forEach(id=>
    document.getElementById(id).addEventListener("change",liveRecompute));
  // service-loaner need updates the hero live (also on each keystroke)
  document.getElementById("serviceNeed").addEventListener("input",liveRecompute);
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
