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
    suppress:DEFAULTS.suppress, demote:DEFAULTS.demote, overrides:DEFAULTS.overrides,
    demo_stocks:DEFAULTS.demo_stocks, demo_starts:DEFAULTS.demo_starts, aged_memory:[],
    prove_bar:2, swap_threshold:90, rate_cap:5.0, paperweight_dts:90, wholesale_min_age:60, stall_days:120, aged_days:60,
    anticipate_demo_returns:true, trades:readTrades(),
    demo_pick_max_dts:45, demo_pick_min_total:2, demo_pick_min_r180:2, demo_picks_per_model:3, demo_vins_per_combo:2 }; }
/* ---- outbound dealer trade log ---- */
const COMBO_MAP = {};
function comboLabel(c){ return c.model+" "+(c.trim||"")+" "+c.ext+"/"+c.int+" ("+c.code+")"; }
function buildComboList(){
  let dl=document.getElementById("combolist"); dl.innerHTML="";
  ROSTER.forEach(c=>{ let label=comboLabel(c); COMBO_MAP[label]={model:c.model,code:c.code,ext:c.ext,int:c.int};
    let o=document.createElement("option"); o.value=label; dl.appendChild(o); });
}
function addTradeRow(t){ t=t||{};
  let row=document.createElement("div"); row.className="traderow";
  row.innerHTML =
    "<input type='date' class='t-date' value='"+(t.date||"")+"'>"+
    "<input class='t-combo' list='combolist' placeholder='pick a combo…' value=\""+(t.label||"")+"\">"+
    "<input type='number' class='t-days' min='0' placeholder='days' value='"+(t.days!=null?t.days:"")+"'>"+
    "<button class='del' title='remove'>✕</button>";
  row.querySelector(".del").addEventListener("click",function(){ row.remove(); liveRecompute(); persistTrades(); });
  row.querySelectorAll("input").forEach(inp=>inp.addEventListener("change",function(){ liveRecompute(); persistTrades(); }));
  document.getElementById("tradeRows").appendChild(row);
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
  document.getElementById("addTrade").addEventListener("click",function(){ addTradeRow(); persistTrades(); });
  restoreTrades();
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
