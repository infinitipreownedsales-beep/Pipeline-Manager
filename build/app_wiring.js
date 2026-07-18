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
    demo_pick_max_dts:45, demo_pick_min_total:2, demo_pick_min_r180:2, demo_picks_per_model:3, demo_vins_per_combo:2 }; }
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
    document.getElementById("datacard").style.display="none";
    if(scroll) document.getElementById("results").scrollIntoView({behavior:"smooth",block:"start"});
  }catch(e){ st.className="foot err"; st.textContent="Problem: "+e.message; }
}
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
  document.getElementById("run").addEventListener("click",function(){ compute(true); });
  document.getElementById("editdata").addEventListener("click",function(){ let d=document.getElementById("datacard");
    d.style.display=d.style.display==="none"?"block":"none"; if(d.style.display!=="none") d.scrollIntoView({behavior:"smooth"}); });
  document.getElementById("loadsample").addEventListener("click",function(){
    document.getElementById("inv").value=SAMPLE.inv; document.getElementById("sales").value=SAMPLE.sales;
    document.getElementById("ordmonth").value=9; markFilled(); compute(true); });
  document.getElementById("clearall").addEventListener("click",function(){
    document.getElementById("inv").value=""; document.getElementById("sales").value=""; markFilled();
    document.getElementById("results").innerHTML=""; HAS_RUN=false;
    try{ localStorage.removeItem("pm_inv"); localStorage.removeItem("pm_sales"); }catch(e){} });
  document.getElementById("inv").addEventListener("input",markFilled);
  document.getElementById("sales").addEventListener("input",markFilled);
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
    if(i&&sa) compute(false);
  }catch(e){}
});
