/* ===================== reports + rendering ===================== */
function esc(v){ return String(v==null?"":v).replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c])); }
function fdts(d){ return d===null||d===undefined||d===""?"—":String(Math.round(d)); }
function momPill(m){ let cls="m-"+(m==="on cadence"?"oncadence":m.replace(/\s/g,"")); return "<span class='pill "+cls+"'>"+esc(m)+"</span>"; }
function dtsCell(d){ if(d===null||d===undefined) return "<span class='dtsband' style='background:rgba(132,146,166,.14);color:#8492a6'>—</span>";
  d=Math.round(d); let bg,fg;
  if(d<=20){bg="rgba(52,211,153,.22)";fg="#4ade80";} else if(d<=40){bg="rgba(132,204,22,.18)";fg="#a3e635";}
  else if(d<=70){bg="rgba(251,191,36,.18)";fg="#fcd34d";} else if(d<=100){bg="rgba(251,146,60,.18)";fg="#fdba74";}
  else {bg="rgba(248,113,113,.2)";fg="#fb8888";}
  return "<span class='dtsband' style='background:"+bg+";color:"+fg+"'>"+d+"</span>"; }
function lerp(a,b,t){ return a+(b-a)*t; }
function heatColor(t){ t=Math.max(0,Math.min(1,t));
  let a=[22,32,46], b=[34,211,238];
  return "rgb("+Math.round(lerp(a[0],b[0],t))+","+Math.round(lerp(a[1],b[1],t))+","+Math.round(lerp(a[2],b[2],t))+")"; }
function heatText(t){ return t>0.55?"#06212a":"#dceefc"; }
// inventory-age chip: fresh -> aged color ramp (green / neutral / amber / red)
function ageCell(d){ d=Math.round(d||0);
  let c=d<=30?"var(--good)":(d<=60?"var(--ink2)":(d<=90?"var(--warn)":"var(--bad)"));
  return "<span style='color:"+c+";font-weight:700;font-variant-numeric:tabular-nums'>"+d+"<span style='font-size:.82em;opacity:.7'>d</span></span>"; }

function orderPriority(res){ let s=res.settings,out={};
  MODELS.forEach(model=>{ let ranked=res.lines.filter(l=>l.model===model&&l.priority>-1).sort((a,b)=>b.priority-a.priority);
    let alloc=s.allocations[model]||0, cum=0, rows=[];
    ranked.forEach((l,i)=>{ cum+=l.need; let tier=l.need===0?"option":(cum<=alloc?"build":"alt");
      rows.push({rank:i+1,line:l,cum:cum,tier:tier}); });
    out[model]={alloc:alloc,rows:rows,totalNeed:res.lines.filter(l=>l.model===model).reduce((a,l)=>a+l.need,0),
      buildUnits:rows.filter(r=>r.tier==="build").reduce((a,r)=>a+r.line.need,0)}; });
  return out; }
function overstock(res){ let rows=[];
  res.lines.forEach(l=>{ let over=l.onlot-l.overstockTarget; if(over<1) return;
    rows.push({model:l.model,trim:l.trim,ext:l.ext,int:l.int,onhand:l.onlot,target:l.overstockTarget,over:over,wholeNow:l.wholeNow,inbound:l.inbound,dts:l.dts,aged:l.pos.aged.length}); });
  rows.sort((a,b)=>(MODELS.indexOf(a.model)-MODELS.indexOf(b.model))||(b.over-a.over)||(b.wholeNow-a.wholeNow)); return rows; }
function wholesaleVins(res){ let rows=[];
  res.lines.forEach(l=>{ if(l.wholeNow<=0) return; let units=l.pos.whole.slice().sort((a,b)=>b.dis-a.dis).slice(0,l.wholeNow);
    units.forEach(u=>{ let vin=u.serial||u.stock; rows.push({stock:u.stock||"—",vin:vin||"—",vin6:vin?vin.slice(-6):"—",year:u.myear||u.my||"",model:u.model,trim:l.trim||u.desc,ei:u.ext+"/"+u.int,dis:Math.round(u.dis)}); }); });
  rows.sort((a,b)=>b.dis-a.dis); rows.forEach((r,i)=>r.num=i+1); return rows; }
function demoDashboard(res){ let s=res.settings, rows=[];
  res.demoUnits.forEach(u=>{ let dis=Math.round(u.dis), asDemo=dis;
    for(let pref in s.demo_starts){ if(pref&&u.stock.indexOf(pref)===0){ let d0=new Date(s.demo_starts[pref]); if(!isNaN(d0.getTime())) asDemo=Math.round((res.tb.today-d0)/86400000); break; } }
    let retIn=Math.max(0,s.swap_threshold-asDemo), note="";
    for(let pref in (s.demo_notes||{})){ if(pref&&u.stock.indexOf(pref)===0){ note=String(s.demo_notes[pref]||"").trim(); break; } }
    rows.push({stock:u.stock,vehicle:u.desc,dis:dis,asDemo:asDemo,swap:asDemo>s.swap_threshold,retIn:retIn,ei:u.ext+"/"+u.int,note:note}); });
  rows.sort((a,b)=>b.asDemo-a.asDemo); return rows; }
function previousLoaners(res){ let rows=[], byStock={};
  (res.settings.prev_loaners||[]).forEach(e=>{ let st=String(e.stock||"").trim(); if(st) byStock[st]=e; });
  (res.inv||[]).forEach(u=>{ if(u.isDlr&&u.prevLoaner){
    let met=res.metrics[u.key], dts=met&&met.dts!==null?met.dts:null, retail=effDis(u), entry=null;
    for(let k in byStock){ if(u.stock.indexOf(k)===0){ entry=byStock[k]; break; } }
    let read=(dts!==null&&retail>Math.max(60,dts))?"aging — watch":"on the market";
    rows.push({stock:u.stock,ei:u.ext+"/"+u.int,dms:Math.round(u.dis),retail:retail,
      daysOut:Math.round(u.dis-retail),note:entry?String(entry.note||"").trim():"",read:read}); } });
  rows.sort((a,b)=>b.retail-a.retail); return rows; }
function paceCheck(res){ let tb=res.tb, rows=[];
  MODELS.forEach(model=>{ let ms=res.sales.filter(s=>s.firstVin&&s.model===model);
    let a90=ms.filter(s=>s.midx>tb.latest-3).length, a60=xround(a90/tb.el90*2,1);
    let p60=xround(Object.values(res.metrics).filter(m=>m.model===model).reduce((a,m)=>a+m.hist60,0),1);
    let vr=xround(a60-p60,1), band=Math.max(2,0.25*p60), read=vr>band?"AHEAD":(vr<-band?"BEHIND":"ON");
    let total=ms.length, mapped=ms.filter(s=>res.metrics[s.key]).length, cov=total?mapped/total:1;
    rows.push({model:model,a90:a90,a60:a60,p60:p60,vr:vr,read:read,cov:cov}); });
  return rows; }
function demoScore(m){ return Math.max(0,(50-m.dts)/50)*40 + Math.min(m.prate,5)*8 + Math.min(m.total,12)*2 + m.r90*4 + ({ACCEL:10,steady:6,"on cadence":3}[m.momentum]||0); }
function demoReason(m){ let b=[Math.round(m.dts)+"-day resale", m.total+" sold lifetime"];
  if(m.r90) b.push(m.r90+" in 90d"); else if(m.r180) b.push(m.r180+" in 180d");
  if(m.momentum==="ACCEL"||m.momentum==="cooling") b.push(m.momentum); return b.join(" · "); }
function executiveDemos(res){ let s=res.settings, out={};
  MODELS.forEach(model=>{ let picks=[];
    res.lines.forEach(l=>{ if(l.model!==model||l.suppressed) return; let m=res.metrics[l.key];
      if(!m||m.dts===null) return;
      if(!(m.dts<=s.demo_pick_max_dts && m.total>=s.demo_pick_min_total && m.r180>=s.demo_pick_min_r180 && m.momentum!=="dormant")) return;
      let pos=res.positions[l.key], fresh=pos?pos.onlotUnits.slice().sort((a,b)=>a.dis-b.dis):[];
      let units=fresh.slice(0,s.demo_vins_per_combo).map(u=>{ let vin=u.serial||u.stock;
        return {stock:u.stock||"—",vin6:vin?vin.slice(-6):"—",dis:Math.round(u.dis),msrp:u.msrp,year:u.myear||u.my||"",ei:u.ext+"/"+u.int}; });
      let score=demoScore(m)+(units.length?6:0);
      picks.push({trim:l.trim,ext:l.ext,int:l.int,key:l.key,dts:m.dts,total:m.total,r90:m.r90,r180:m.r180,momentum:m.momentum,
        score:score,reason:demoReason(m),onlot:l.onlot,backup:Math.max(0,l.onlot-1),units:units,inStock:units.length>0}); });
    picks.sort((a,b)=>b.score-a.score); out[model]=picks.slice(0,s.demo_picks_per_model); });
  return out; }
function fleetTargets(res){ let out={}; MODELS.forEach(model=>{ let r=res.seas[model].rate;
    out[model]=[]; for(let m=0;m<12;m++) out[model].push(xround(r[m]+r[(m+1)%12],0)); }); return out; }
/* ---- inventory-driven retail forecast (mirror of reports.retail_forecast) ---- */
function retailForecast(res){
  let today=res.tb.today, s=res.settings;
  let daysLeft=new Date(today.getFullYear(),today.getMonth()+1,0).getDate()-today.getDate()+1;
  let horizons=[["This month",daysLeft],["Next 30 days",30],["Next 60 days",60]];
  // month-to-date retail already booked this calendar month, per model
  let curMidx=today.getFullYear()*12+(today.getMonth()+1), soldMtd={};
  MODELS.forEach(m=>soldMtd[m]=0);
  (res.sales||[]).forEach(sale=>{ if(sale.firstVin&&sale.midx===curMidx&&soldMtd[sale.model]!=null) soldMtd[sale.model]++; });
  function seasFactor(days,seas){ let t=0; for(let d=0;d<days;d++){ t+=seas[new Date(today.getTime()+d*86400000).getMonth()]; } return days?t/days:1; }
  function inboundIn(pos,days){ if(!pos) return 0; let end=new Date(today.getTime()+days*86400000), n=0;
    for(let cm in pos.arrivals){ let month=parseInt(cm,10), year=month>=today.getMonth()+1?today.getFullYear():today.getFullYear()+1;
      let arr=new Date(year,month-1,15); if(arr>=today&&arr<=end) n+=pos.arrivals[cm]; } return n; }
  function pace(l){ let m=res.metrics[l.key]; return Math.min(s.rate_cap, m?m.prate/2:0); }
  let out={horizons:horizons.map(h=>({label:h[0],days:h[1]})),per_model:{},total:{forecast:[0,0,0]}};
  MODELS.forEach(model=>{
    let lines=res.lines.filter(l=>l.model===model);
    let onlot=lines.reduce((a,l)=>a+l.onlot,0), inbound=lines.reduce((a,l)=>a+l.inbound,0);
    let monthlyDemand=lines.reduce((a,l)=>a+pace(l),0), forecasts=[], demands=[];
    horizons.forEach((h,hi)=>{ let days=h[1], months=days/DPM, sf=seasFactor(days,res.seas[model].index), proj=0;
      lines.forEach(l=>{ let pos=res.positions[l.key], avail=Math.max(0,l.onlot-l.wholeNow)+inboundIn(pos,days); proj+=Math.min(pace(l)*sf*months, avail); });
      if(hi===0) proj+=soldMtd[model];   // this month = already retailed + constrained remainder
      forecasts.push(Math.round(proj)); demands.push(Math.round(monthlyDemand*sf*months)); out.total.forecast[hi]+=proj; });
    let sf60=seasFactor(60,res.seas[model].index), demand60=monthlyDemand*sf60*(60/DPM);
    let avail60=lines.reduce((a,l)=>a+Math.max(0,l.onlot-l.wholeNow)+inboundIn(res.positions[l.key],60),0);
    let health; if(demand60<=0.01) health="cold — little live demand";
      else if(avail60<demand60*0.85) health="tight — demand outruns stock";
      else if(avail60>demand60*1.6) health="heavy — stock outruns demand"; else health="balanced";
    let dos=monthlyDemand>0?Math.round(onlot/monthlyDemand*DPM):null;
    out.per_model[model]={forecast:forecasts,demand:demands,onlot:onlot,inbound:inbound,monthly_demand:Math.round(monthlyDemand*10)/10,days_supply:dos,demand60:Math.round(demand60),avail60:avail60,health:health,sold_mtd:soldMtd[model]};
  });
  out.total.forecast=out.total.forecast.map(x=>Math.round(x));
  out.total.onlot=Object.values(out.per_model).reduce((a,d)=>a+d.onlot,0);
  out.total.inbound=Object.values(out.per_model).reduce((a,d)=>a+d.inbound,0);
  out.total.sold_mtd=Object.values(out.per_model).reduce((a,d)=>a+d.sold_mtd,0);
  return out;
}
function healthBadge(h){ let c=h.indexOf("tight")>=0?"var(--bad)":(h.indexOf("heavy")>=0?"var(--warn)":(h.indexOf("cold")>=0?"var(--muted)":"var(--good)"));
  let dot=h.indexOf("tight")>=0?"▲":(h.indexOf("heavy")>=0?"▼":(h.indexOf("cold")>=0?"—":"●"));
  return "<span style='color:"+c+";font-weight:700;white-space:nowrap'>"+dot+" "+esc(h)+"</span>"; }
function money(n){ n=Math.round(n||0); return (n<0?"-$":"$")+Math.abs(n).toLocaleString(); }

/* ---- power-ranked RETAIL build sequence (per model) ---- */
function buildSeqBlock(res, model){
  let bs=res.buildSeq, d=bs&&bs.perModel?bs.perModel[model]:null; if(!d) return "";
  let H=[], reservedNote=d.fleet_reserved>0?" · "+d.fleet_reserved+" reserved for loaner fleet (see Loaner section)":"";
  if(!d.groups.length){
    return "<div class='bseqwrap'><div class='bseqhd'>Build sequence <span class='bseqsub'>no retail order needed this month for "+esc(model)+" — on-hand + inbound already cover the seasonal target"+reservedNote+"</span></div></div>";
  }
  let n=0, shownAltNote=false;
  H.push("<div class='bseqwrap'><div class='bseqhd'>Build sequence <span class='bseqsub'>order in this order · "+
    d.retail_build+" of "+d.allocation+" allocation"+reservedNote+"</span></div><div class='bseq'>");
  d.groups.forEach(g=>{
    if(g.tier==="alt" && !shownAltNote){ H.push("<span class='bseqcut'>▸ beyond allocation</span>"); shownAltNote=true; }
    n++;
    let cls="bstep"+(g.tier==="alt"?" alt":"");
    let dts=(g.dts!=null)?" <span class='btag'>"+Math.round(g.dts)+"d</span>":"";
    H.push("<span class='"+cls+"'><span class='bnum'>"+n+".</span><span class='bqty'>"+g.qty+"×</span> "+
      esc(g.trim)+" <span class='demoei'>"+esc(g.ext)+"/"+esc(g.int)+"</span>"+dts+"</span>");
  });
  H.push("</div></div>");
  return H.join("");
}

/* ---- loaner / ICV program dashboard ---- */
function financialBreakdown(p){ let e=p.econ;
  function row(lab,val,o){ o=o||{}; let disp;
    if(o.neg) disp="<span class='neg'>−"+money(Math.abs(val)).slice(1)+"</span>";
    else if(o.pos) disp="<span class='pos'>+"+money(Math.abs(val)).slice(1)+"</span>";
    else if(o.total) disp="<span class='"+(val<0?"neg":"pos")+"'>"+money(val)+"</span>";  // signed
    else disp="<span>"+money(val)+"</span>";
    return "<div class='fbrow"+(o.sub?" sub":"")+(o.total?" total":"")+"'><span>"+lab+"</span>"+disp+"</div>"; }
  let H=["<details class='fbreak'><summary>▸ Financial breakdown — why it ranks here</summary><div class='fbwrap'>"];
  H.push(row("Invoice / acquisition cost", e.cost));
  H.push(row("MSRP", e.msrp, {sub:true}));
  if(e.rebate) H.push(row("Customer rebate (new sells at invoice − this)", e.rebate, {sub:true}));
  H.push("<div class='fbdiv'>Cost basis while in service ("+e.serviceSpan+" mo)</div>");
  H.push(row("ICV allowance (one-time)", e.icvTotal, {neg:true}));
  H.push(row("Write-down / depreciation", e.deprTotal, {neg:true}));
  if(e.bonus) H.push(row("Velocity bonus (earned)", e.bonus, {neg:true}));
  else if(e.velocityAvail) H.push("<div class='fbrow sub'><span>Velocity bonus (misses window)</span><span class='dim'>"+money(e.velocityAvail)+" avail</span></div>");
  H.push(row("= Adjusted cost basis", e.adjustedCost, {total:true}));
  H.push("<div class='fbdiv'>Resale</div>");
  H.push("<div class='fbrow'><span>Expected used retail "+srcBadge(p)+"</span><span class='pos'>+"+money(e.usedPrice).slice(1)+"</span></div>");
  if(e.recon) H.push(row("Estimated reconditioning", e.recon, {neg:true}));
  H.push(row("= Front-end gross", e.usedGross, {total:true}));
  if(e.holding||e.mileageAdj){ H.push("<div class='fbdiv'>To projected net</div>");
    if(e.holding) H.push(row("Holding cost ("+e.serviceSpan+"mo + used turn)", e.holding, {neg:true}));
    H.push("<div class='fbrow sub'><span>Mileage adjustment</span><span class='dim'>n/a — no odometer feed</span></div>");
    H.push(row("= Projected net profit", e.net, {total:true})); }
  H.push("</div></details>");
  return H.join(""); }
function srcBadge(p){
  if(p.usedSrc==="history"){ return "<span class='lhistory' title='resale estimated from your own 10-year history — "+(p.histResale?p.histResale.n:0)+" comparable sales'>📊 history ("+(p.histResale?p.histResale.n:0)+")</span>"; }
  if(p.usedSrc==="measured"){ return "<span class='lmeasured' title='measured from your preowned/auction data'>measured</span>"; }
  return "<span class='lmodeled' title='modeled: 80% of cheapest-new (no history for this config)'>modeled</span>";
}
function loanerRender(res){
  let board=res.loanerBoard||{}, plan=res.loanerFleetPlan||{rows:[],in_service:0,target:0,releasing_now:0,to_add:0};
  let H=[];
  // fleet status KPIs
  H.push("<div class='lkpis'>");
  H.push("<div class='lkpi'><div class='lab'>In service</div><div class='big'>"+plan.in_service+" <span style='font-size:14px;color:var(--muted)'>/ "+plan.target+" target</span></div></div>");
  H.push("<div class='lkpi'><div class='lab'>Releasing now</div><div class='big' style='color:"+(plan.releasing_now?"var(--bad)":"var(--muted)")+"'>"+plan.releasing_now+"</div></div>");
  H.push("<div class='lkpi'><div class='lab'>Add this cascade</div><div class='big' style='color:"+(plan.to_add?"var(--orange)":"var(--good)")+"'>"+plan.to_add+"</div></div>");
  // best-value pick across models
  let best=null; MODELS.forEach(m=>(board[m]||[]).forEach(p=>{ if(!best||p.netValue>best.netValue) best=p; }));
  if(best) H.push("<div class='lkpi'><div class='lab'>Best used gross</div><div class='big' style='color:var(--teal)'>"+money(best.netValue)+"</div><div class='foot' style='margin:2px 0 0'>"+esc(best.trim)+" "+esc(best.ext)+"/"+esc(best.int)+"</div></div>");
  H.push("</div>");

  // Fleet order this cascade — which combos to bring in for the loaner fleet.
  // This is netted out of the retail allocation (noted in Order Priority), but is
  // shown HERE, not mixed into the retail order.
  let fu=(res.buildSeq&&res.buildSeq.fleetUnits)||[];
  if(fu.length){
    H.push("<div class='dc-sub' style='margin-top:4px'>Fleet order this cascade <span class='dc-note'>"+fu.length+" units (~"+res.buildSeq.intake+"/mo) — best preowned economics · netted out of retail allocation</span></div>");
    H.push("<div class='bseq' style='margin-bottom:14px'>");
    fu.forEach((u,i)=>{ let e=u.econ, loss=e&&e.upsideDown;
      H.push("<span class='bstep fleet'><span class='bnum'>"+(i+1)+".</span><span class='bqty'>1×</span> "+
        esc(u.model)+" "+esc(u.trim)+" <span class='demoei'>"+esc(u.ext)+"/"+esc(u.int)+"</span> <span class='btag'>"+money(u.netValue)+(loss?" <span class='bloss'>loss</span>":"")+"</span></span>"); });
    H.push("</div>");
  }

  // current in-service fleet + cascading release
  if(plan.rows.length){
    H.push("<div class='dc-sub'>In-service fleet <span class='dc-note'>cascading release — 🔴 pull now, 🟢 eligible, 🅗 hold for ICV</span></div>");
    H.push(tbl(["Stock","Model","Vehicle","Ext/Int","In svc","Miles","ICV (once)","Release by","Status","Note"],
      ["","","","","num","num","num","","",""],
      plan.rows.map(r=>[esc(r.stock),r.model,{html:"<span class='dim'>"+esc(r.vehicle)+"</span>"},esc(r.ext_int),
        r.months+"mo",r.miles.toLocaleString(),{html:r.icv_secured?("<span style='color:var(--teal)'>"+money(r.icv_secured)+"</span>"):("<span class='dim' title='booked but not secured until it clears the min-months floor'>"+money(r.icv)+" pending</span>")},
        {html:"<span class='dim'>"+esc(r.release_by)+"</span>"},
        {html:"<b>"+esc(r.status)+"</b>"},{html:r.note?esc(r.note):"<span class='dim'>—</span>"}])));
  } else {
    H.push("<div class='empty'>No loaners in service yet. Add your current fleet in ✎ Data → Loaner / ICV program, then this shows each unit's age, miles, ICV earned and when to release it.</div>");
  }

  // candidate board — best combos to put INTO the program
  let anyModeled=false; MODELS.forEach(m=>(board[m]||[]).forEach(p=>{ if(p.modeled) anyModeled=true; }));
  H.push("<div class='dc-sub' style='margin-top:16px'>Best units to put into the program <span class='dc-note'>ranked by preowned profit after ICV + write-down + bonus, and whether they clear the used window</span></div>");
  H.push("<div class='demogrid'>");
  MODELS.forEach(model=>{ let picks=board[model]||[];
    H.push("<div class='democol'><div class='demohd'>"+model+"</div>");
    if(!picks.length){ H.push("<div class='empty'>No candidate — need cost/MSRP on units in the pipeline.</div>"); }
    picks.forEach((p,i)=>{ let e=p.econ, medal=["①","②","③","④","⑤"][i]||("#"+(i+1));
      H.push("<div class='loancard democard"+(i===0?" top":"")+(e.upsideDown?" upside":"")+"'>"+
        "<div class='demorank'>"+medal+"</div>"+
        "<div class='demotrim'>"+esc(p.trim)+" <span class='demoei'>"+esc(p.ext)+"/"+esc(p.int)+"</span></div>"+
        "<div class='money'><span class='net' style='color:"+(p.netValue>=0?"var(--good)":"var(--bad)")+"'>"+money(p.netValue)+"</span><span class='netlab'>preowned "+(p.netValue>=0?"profit":"LOSS")+"</span>"+
          " "+srcBadge(p)+"</div>"+
        (e.upsideDown?"<div class='lwarn'>⚠ upside-down — written-down cost is above street value; you'd re-buy it cheaper at auction</div>":"")+
        "<div class='demowhy' style='margin:4px 0 6px'>"+dtsCell(p.usedDts)+" <span class='demometa'>used turn</span> "+
          (e.bonusOk?"<span class='lbonus-ok'>✓ $"+Math.round(e.bonus).toLocaleString()+" bonus</span>":"<span class='lbonus-no'>✗ misses bonus</span>")+"</div>"+
        "<div class='lchips'>"+
          "<span class='lchip'>invoice "+money(e.cost)+"</span>"+
          (e.rebate?"<span class='lchip'>rebate <b>-"+money(e.rebate).slice(1)+"</b></span><span class='lchip'>cheapest-new "+money(e.cheapestNew)+"</span>":"")+
          "<span class='lchip'>ICV <b>-"+money(e.icvTotal).slice(1)+"</b></span>"+
          "<span class='lchip'>write-down <b>-"+money(e.deprTotal).slice(1)+"</b></span>"+
          (e.bonus?"<span class='lchip'>bonus <b>-"+money(e.bonus).slice(1)+"</b></span>":"")+
          "<span class='lchip'>adj cost <b>"+money(e.adjustedCost)+"</b></span>"+
          "<span class='lchip'>resale @ "+money(e.usedPrice)+(p.histResale?" <span class='dim'>("+money(p.histResale.low).slice(1)+"–"+money(p.histResale.high).slice(1)+")</span>":"")+"</span>"+
        "</div>");
      H.push(financialBreakdown(p));
      if(p.units.length){ p.units.forEach(u=>{
        H.push("<div class='demovin'><span class='vintag'>VIN …"+esc(u.vin_last6)+"</span>"+
          "<span class='demound'>"+esc(u.year)+" "+esc(u.ext_int)+" · "+u.dis+"d"+(u.cost?" · cost "+money(u.cost):"")+"</span></div>"); });
      } else H.push("<div class='demovin order'>none in stock — earmark one on the next order</div>");
      H.push("</div>"); });
    H.push("</div>"); });
  H.push("</div>");
  let anyHistory=MODELS.some(m=>(board[m]||[]).some(p=>p.usedSrc==="history"));
  if(anyHistory) H.push("<div class='foot'><b>📊 history</b> picks price resale from your own 10-year used-car sales — the config's real median resale at ~"+(res.settings.loaner_service_months||3)+" months of age (see the <b>Loaner Depreciation</b> section below), with the comp count in parentheses. That's the street value you could re-buy the unit for, so it's what you should carry internally. The write-downs (ICV + monthly write-down + bonus) only help the cost <i>when the unit retires from the fleet</i>; preowned profit is what's left after that.</div>");
  if(anyModeled) H.push("<div class='foot'>“modeled” picks (no history match — e.g. a brand-new nameplate) fall back to "+Math.round((res.settings.preowned_price_pct||0.8)*100)+"% of your <b>cheapest new price</b> (invoice − rebate) and used turn ≈ new days-to-sell — a deliberately conservative floor until history exists for that model.</div>");
  return H.join("");
}

function tbl(head,cls,rows){
  let h="<div class='tblwrap'><table><thead><tr>"+head.map((x,i)=>"<th class='"+(cls[i]||"")+"'>"+x+"</th>").join("")+"</tr></thead><tbody>";
  h+=rows.map(r=>"<tr>"+r.map((c,i)=>"<td class='"+(cls[i]||"")+"'>"+(c&&c.html!==undefined?c.html:esc(c))+"</td>").join("")+"</tr>").join("");
  return h+"</tbody></table></div>"; }
function sec(n,title,meta){ return "<div class='sec'><span class='caret'>▾</span><span class='n'>"+n+"</span><h2>"+esc(title)+"</h2><span class='meta'>"+esc(meta||"")+"</span><span class='sechint noprint'>click to collapse</span></div>"; }

function sparkline(vals, nowM){ // 12 monthly seasonality values; split past (dim) vs forward (bright)
  nowM = (nowM==null? new Date().getMonth() : ((nowM%12)+12)%12);
  let w=220,h=50,pad=6, mn=Math.min.apply(null,vals.concat([1])), mx=Math.max.apply(null,vals.concat([1]));
  let rng=(mx-mn)||1, X=i=>pad+i*(w-2*pad)/11, Y=v=>h-pad-((v-mn)/rng)*(h-2*pad);
  let pts=vals.map((v,i)=>X(i)+","+Y(v).toFixed(1));
  let area="M"+X(0)+","+(h-pad)+" L"+pts.join(" L ")+" L"+X(11)+","+(h-pad)+" Z";
  let past="M"+pts.slice(0,nowM+1).join(" L ");
  let future="M"+pts.slice(nowM).join(" L ");
  let base=Y(1), nx=X(nowM).toFixed(1), ny=Y(vals[nowM]).toFixed(1);
  return "<svg class='spark' width='"+w+"' height='"+h+"' viewBox='0 0 "+w+" "+h+"'>"+
    "<path d='"+area+"' fill='rgba(94,234,212,.10)'/>"+
    "<line x1='"+pad+"' y1='"+base.toFixed(1)+"' x2='"+(w-pad)+"' y2='"+base.toFixed(1)+"' stroke='#3a4a63' stroke-dasharray='3 3' stroke-width='1'/>"+
    "<line x1='"+nx+"' y1='"+pad+"' x2='"+nx+"' y2='"+(h-pad)+"' stroke='#4c8dff' stroke-width='1' stroke-dasharray='2 2' opacity='.6'/>"+
    "<path d='"+past+"' fill='none' stroke='#3f6f68' stroke-width='2' stroke-linejoin='round' stroke-linecap='round'/>"+
    "<path d='"+future+"' fill='none' stroke='#5eead4' stroke-width='2.6' stroke-linejoin='round' stroke-linecap='round'/>"+
    "<circle cx='"+nx+"' cy='"+ny+"' r='3.2' fill='#4c8dff'/>"+
    "</svg>"; }
function seasHeading(vals, nowM){ // where demand is trending over the next ~2 months
  nowM=((nowM%12)+12)%12; let fwd=(vals[(nowM+1)%12]+vals[(nowM+2)%12])/2 - vals[nowM];
  if(fwd>0.08) return "<span style='color:var(--good)'>▲ demand rising</span>";
  if(fwd<-0.08) return "<span style='color:var(--warn)'>▼ demand easing</span>";
  return "<span style='color:var(--muted)'>▬ steady</span>"; }

function render(res){
  let rep={op:orderPriority(res),over:overstock(res),vins:wholesaleVins(res),demo:demoDashboard(res),fleet:fleetTargets(res)};
  let s=res.settings,tb=res.tb, H=[];
  let fc=retailForecast(res);   // computed once; reused in the Retail Forecast section
  let latest=tb.latest?(Math.floor(tb.latest/12)+"-"+String(tb.latest%12).padStart(2,"0")):"—";

  // KPI tiles — one per model: what to order now, colored by inventory health
  function hColor(h){ return h.indexOf("tight")>=0?"var(--bad)":(h.indexOf("heavy")>=0?"var(--warn)":(h.indexOf("cold")>=0?"var(--muted)":"var(--good)")); }
  function hShort(h){ return h.split("—")[0].trim(); }
  H.push("<div class='kpis'>");
  MODELS.forEach(model=>{ let b=rep.op[model], d=fc.per_model[model], col=hColor(d.health);
    H.push("<div class='kpi model'><span class='edge' style='background:"+col+"'></span>"+
      "<div class='lab'>"+model+" — order now</div><div class='big'>"+b.totalNeed+"</div>"+
      "<div class='sub'>"+b.buildUnits+" within allocation · <span style='color:"+col+"'>"+esc(hShort(d.health))+"</span> stock</div></div>"); });
  let totWhole=res.lines.reduce((a,l)=>a+l.wholeNow,0), totOver=rep.over.reduce((a,r)=>a+r.over,0);
  H.push("<div class='kpi'><span class='edge' style='background:var(--over)'></span><div class='lab'>Overstock</div>"+
    "<div class='big' style='color:var(--over)'>"+totOver+"</div><div class='sub'>"+totWhole+" ready to wholesale today</div></div>");
  H.push("<div class='kpi'><span class='edge' style='background:var(--teal)'></span><div class='lab'>Sales history</div>"+
    "<div class='big' style='color:var(--teal)'>"+tb.span.toFixed(1)+"<span style='font-size:15px;color:var(--muted)'> mo</span></div>"+
    "<div class='sub'>newest "+latest+(tb.open?" · open":"")+" · "+res.orphans.length+" off-roster</div></div>");
  H.push("</div>");

  let winTxt = (s.mode==="CPO"||s.mode==="PPO")
    ? " · arrival lead "+MODELS.map(m=>m+" "+(res.windows[m]).toFixed(1)+"mo").join(" / ")
    : "";
  let tradeTxt = (s.trades&&s.trades.length) ? " · <b style='color:var(--teal)'>"+s.trades.length+" dealer trade"+(s.trades.length>1?"s":"")+" graded</b>" : "";
  let modeName={"CPO":"CPO — factory order","PPO":"PPO — this order's arrival window","MID-MONTH":"Dealer trade — available today"}[s.mode]||s.mode;
  let modeWhy={"CPO":"measured against what you'll hold when the factory order lands",
    "PPO":"future inventory — measured against your projected on-hand at arrival",
    "MID-MONTH":"right-now — measured against what you could pull today via dealer trade"}[s.mode]||"";
  H.push("<div class='foot noprint' style='margin:-6px 2px 6px'>Recomputed "+tb.today.toISOString().slice(0,10)+
    " · order month <b style='color:var(--ink2)'>"+MONTHS[s.order_month-1]+"</b> · basis <b style='color:var(--accent)'>"+esc(modeName)+
    "</b> <span class='dim'>("+esc(modeWhy)+")</span>"+winTxt+" · "+res.invCount+" inventory units · "+res.salesCount+" sales rows"+tradeTxt+"</div>");

  // 1. ORDER PRIORITY
  H.push(sec(1,"Order Priority","teal = where you'll be at arrival · orange = whole trucks to order"));
  H.push("<div class='legend'><span><b>✓ BUILD</b> real need within allocation</span><span><b>↑ alt</b> need beyond allocation</span><span><b>○ option</b> fast combo to swap in</span><span><b>PROJ@ARR</b> your on-hand when the order lands</span></div>");
  MODELS.forEach(model=>{ let b=rep.op[model];
    let arrTag="";
    if(s.mode==="CPO"){ let w=res.windows[model], am=MONTHS[((s.order_month-1+Math.round(w))%12+12)%12];
      arrTag="<span class='tag' title='data-driven production→arrival lead'>lands ≈ "+am+" ("+w.toFixed(1)+"mo)</span>"; }
    H.push("<div class='modelband'><span class='mn'>"+model+"</span><span class='tag'>allocated "+b.alloc+"</span><span class='tag'>total NEED "+b.totalNeed+"</span><span class='tag'>build "+b.buildUnits+"</span>"+arrTag+"</div>");
    let rows=b.rows.map(r=>{ let l=r.line;
      let badge={build:"<span class='badge b-build'>✓ BUILD</span>",alt:"<span class='badge b-alt'>↑ alt</span>",option:"<span class='badge b-opt'>○ option</span>"}[r.tier];
      return [ r.rank, {html:badge}, esc(l.trim), esc(l.ext), esc(l.int), {html:dtsCell(l.dts)}, {html:momPill(l.mom)},
        {html:l.buyGrade?"<span class='grade'>"+l.buyGrade+"</span>":"<span class='dim'>—</span>"},
        l.onlot, {html:"<span class='dim'>"+l.inbound+"</span>"},
        {html:l.proj.toFixed(1)+(l.demoReturning?" <span title='includes "+l.demoReturning+" demo returning to inventory, held as slow stock' style='color:var(--warn)'>↩"+l.demoReturning+"</span>":"")},
        {html:"<b>"+l.orderTarget+"</b>"}, {html:l.need>0?l.need:"<span class='dim'>0</span>"}, r.cum ]; });
    H.push(tbl(["#","Build?","Trim","Ext","Int","DTS","Momentum","Grade","Lot","Inb","PROJ@ARR","Tgt","NEED","Cum"],
      ["num","","","","","num","","","num","num","num teal","num","num need","num"], rows));
    H.push(buildSeqBlock(res, model)); });

  // 2. SIX-MONTH ROLLING PLAN
  H.push(sec(2,"6-Month Rolling Order Plan","when to place each truck — orders by arrival month"));
  MODELS.forEach(model=>{
    let ml=res.lines.filter(l=>l.model===model), monthsTot=[0,0,0,0,0,0], labels=[];
    ml.forEach(l=> l.plan.forEach((p,k)=>{ monthsTot[k]+=p.ord; }));
    if(ml.length) labels=ml[0].plan.map(p=>MONTHS[p.month-1]);
    let mx=Math.max.apply(null,monthsTot.concat([1]));
    H.push("<div class='modelband'><span class='mn'>"+model+"</span><span class='tag'>"+monthsTot.reduce((a,b)=>a+b,0)+" units over 6 months</span></div>");
    H.push("<div class='plan'>"+monthsTot.map((t,k)=>"<div class='pcell"+(t>0&&t>=mx*0.66?" hot":"")+"'><div class='pm'>"+labels[k]+"</div>"+
      "<div class='po' style='color:"+(t>0?"var(--orange)":"var(--muted)")+"'>"+t+"</div><div class='pd'>order</div></div>").join("")+"</div>");
    // top configs contributing, expandable
    let contrib=ml.filter(l=>l.plan.some(p=>p.ord>0)).sort((a,b)=>b.plan.reduce((x,p)=>x+p.ord,0)-a.plan.reduce((x,p)=>x+p.ord,0));
    if(contrib.length){ let rows=contrib.map(l=>[esc(l.trim),esc(l.ext),esc(l.int)].concat(l.plan.map(p=>({html:p.ord>0?"<b style='color:var(--orange)'>"+p.ord+"</b>":"<span class='dim'>·</span>"}))));
      H.push("<details class='exp'><summary>per-combo detail ("+contrib.length+")</summary>"+
        tbl(["Trim","Ext","Int"].concat(labels),["","","","num","num","num","num","num","num"],rows)+"</details>"); }
  });

  // 3. FLEET TARGET + SEASONALITY
  H.push(sec(3,"Fleet Stock Target & Seasonality","live 60-day stock target by month, and each model's demand shape"));
  let nowM=res.tb.today.getMonth();
  MODELS.forEach(model=>{ let f=rep.fleet[model], mx=Math.max.apply(null,f.concat([1]));
    let cells="<td class='rl'>"+model+"</td>"+f.map((v,i)=>{ let t=v/mx; let now=i===nowM;
      return "<td class='cell'"+(now?" style='background:"+heatColor(t)+";color:"+heatText(t)+";box-shadow:0 0 0 2px var(--accent) inset'":" style='background:"+heatColor(t)+";color:"+heatText(t)+"'")+">"+v+"</td>"; }).join("");
    H.push("<div style='display:flex;gap:22px;align-items:center;flex-wrap:wrap;margin:10px 0'>"+
      "<table class='heat'><thead><tr><th></th>"+MONTHS.map((m,i)=>"<th style='font-size:9.5px;color:"+(i===nowM?"var(--accent)":"#6b7891")+";text-align:center;font-weight:"+(i===nowM?700:400)+"'>"+m+"</th>").join("")+"</tr></thead><tbody><tr>"+cells+"</tr></tbody></table>"+
      "<div style='text-align:center'>"+sparkline(res.seas[model].index, nowM)+"<div class='foot' style='margin:2px 0 0;text-align:center'>seasonality · "+seasHeading(res.seas[model].index, nowM)+"</div></div></div>"); });

  // 4. DEMO CENTER — board (left) + current demos & previous loaners (right)
  let ed=executiveDemos(res), board=[];
  board.push("<div class='dc-sub'>Best combos to demo <span class='dc-note'>proven fast-movers only — still turn fast with miles</span></div>");
  board.push("<div class='demogrid'>");
  MODELS.forEach(model=>{ let picks=ed[model];
    board.push("<div class='democol'><div class='demohd'>"+model+"</div>");
    if(!picks.length) board.push("<div class='empty'>No proven fast combo yet.</div>");
    picks.forEach((p,i)=>{ let medal=["①","②","③","④","⑤"][i]||("#"+(i+1));
      board.push("<div class='democard"+(i===0?" top":"")+"'>"+
        "<div class='demorank'>"+medal+"</div>"+
        "<div class='demotrim'>"+esc(p.trim)+" <span class='demoei'>"+esc(p.ext)+"/"+esc(p.int)+"</span></div>"+
        "<div class='demowhy'>"+dtsCell(p.dts)+" <span class='pill "+("m-"+(p.momentum==="on cadence"?"oncadence":p.momentum.replace(/\s/g,"")))+"'>"+esc(p.momentum)+"</span> <span class='demometa'>"+p.total+" sold · "+(p.r90||p.r180)+" recent</span></div>");
      if(p.units.length){ p.units.forEach(u=>{
        board.push("<div class='demovin'><span class='vintag'>VIN …"+esc(u.vin6)+"</span>"+
          "<span class='demound'>"+esc(u.year)+" "+esc(u.ei)+" · "+u.dis+"d"+(u.msrp?" · $"+Math.round(u.msrp).toLocaleString():"")+"</span></div>"); });
        board.push(p.backup>0?"<div class='demoback'>"+p.backup+" more in stock as backup</div>":"<div class='demoback warn'>last one on lot — reorder before pulling</div>");
      } else board.push("<div class='demovin order'>none in stock — order / allocate one</div>");
      board.push("</div>"); });
    board.push("</div>"); });
  board.push("</div>");

  let dash=["<div class='dc-sub'>Current demos <span class='dc-note'>age = days in inventory · demo = days out with a driver</span></div>"];
  if(rep.demo.length){
    // Compact: Stock (driver as subtitle) · Ext/Int · Inventory age · Days-as-demo
    // · Return ETA · Swap — no long vehicle column, so it fits without scrolling.
    dash.push(tbl(["Stock","E/I","Age","Demo","Ret","Swap"],["","","num","num","num","c"],
      rep.demo.map(r=>[
        {html:"<b>"+esc(r.stock)+"</b>"+(r.note?"<div class='dim' style='font-size:10.5px;font-weight:400;margin-top:1px;white-space:normal'>"+esc(r.note)+"</div>":"")},
        {html:"<span class='dim'>"+esc(r.ei)+"</span>"},
        {html:ageCell(r.dis)},
        {html:"<span style='font-variant-numeric:tabular-nums'>"+r.asDemo+"<span style='font-size:.82em;opacity:.6'>d</span></span>"},
        {html:r.retIn>0?("<span class='dim'>~"+r.retIn+"d</span>"):"<span class='swap'>now</span>"},
        {html:r.swap?"<span class='swap' title='past swap threshold'>⚠</span>":"<span style='color:var(--good)'>✓</span>"}])));
    if(s.anticipate_demo_returns) dash.push("<div class='foot'>✓ Ordering anticipates each of these coming back (held as slow, used stock), so you don't reorder a unit that's returning.</div>");
  } else dash.push("<div class='empty'>No demos listed. Add them in ✎ Data.</div>");

  let loaners=["<div class='dc-sub'>Previous loaners <span class='dc-note'>retail clock — hidden until they reappear</span></div>"];
  let pl=previousLoaners(res);
  if(pl.length){
    loaners.push(tbl(["Stock","Driver / reason","DMS","Demo out","On market"],["","","num","num","num"],
      pl.map(r=>[esc(r.stock),{html:r.note?esc(r.note):"<span class='dim'>—</span>"},
        {html:"<span class='dim'>"+r.dms+"d</span>"},
        {html:"<span class='dim'>−"+r.daysOut+"d</span>"},
        {html:"<b style='color:var(--teal)'>"+r.retail+"d</b>"}])));
    loaners.push("<div class='foot'>On market = days-in-stock minus the demo period. Never wholesale-listed (miles), and not aged on the inflated days-in-stock.</div>");
  } else loaners.push("<div class='empty'>None flagged. Add returned loaners in ✎ Data (taken + returned dates) so their real market time is right.</div>");

  H.push(sec(4,"Demo Center","execs' best picks · current demos · returned loaners — worked side by side"));
  H.push("<div class='democenter'><div class='dc-left'>"+board.join("")+"</div>"+
    "<div class='dc-right'>"+dash.join("")+"<div style='height:12px'></div>"+loaners.join("")+"</div></div>");

  // 5. LOANER / ICV PROGRAM
  H.push(sec(5,"Loaner / ICV Program","which units to cycle through the courtesy fleet for the best preowned profit"));
  H.push(loanerRender(res));

  // 5b. LOANER DEPRECIATION INTELLIGENCE — the engine behind the resale prices above
  if(res.deprActive&&res.depr){ H.push(sec(9,"Loaner Depreciation","what a loaner really resells for — from your own 10-year history · powers the resale prices above")); H.push(depreciationRender(res)); }

  // 6. OVERSTOCK
  H.push(sec(6,"Overstock / Wholesale","over-target metal — order slower; wholesale only what won't sell"));
  if(rep.over.length) H.push(tbl(["Model","Trim","Ext","Int","On hand","60-day tgt","Over","Wholesale now","Inbound","DTS","Aged"],
    ["","","","","num","num","num","num need","num","num","num"],
    rep.over.map(r=>[r.model,esc(r.trim),r.ext,r.int,r.onhand,r.target,{html:"<b>"+r.over+"</b>"},{html:r.wholeNow>0?r.wholeNow:"<span class='dim'>0</span>"},{html:"<span class='dim'>"+r.inbound+"</span>"},{html:dtsCell(r.dts)},r.aged])));
  else H.push("<div class='empty'>Nothing over target.</div>");

  // 7. WHOLESALE VIN SHEET
  H.push(sec(7,"Wholesale Now — VIN sheet","aged, over-target, non-demo · print & send to other dealers"));
  if(rep.vins.length){ H.push("<div id='print-vin'><h2>WHOLESALE VIN SHEET — "+tb.today.toISOString().slice(0,10)+"</h2></div>");
    H.push(tbl(["#","Stock #","VIN","Year","Model","Trim","Ext/Int","Days in stock"],["num","","vincol","","","","","num"],
      rep.vins.map(r=>[r.num,esc(r.stock),{html:"<span class='vintag'>"+esc(r.vin)+"</span>"},r.year,r.model,esc(r.trim),esc(r.ei),r.dis])));
    H.push("<div class='foot noprint'>Use 🖨 Print (top-right) to print this sheet on its own or with any other dashboards.</div>"); }
  else H.push("<div class='empty'>No units past their selling window.</div>");

  // 8. RETAIL FORECAST — what your current inventory can produce (fc from top)
  let fh=fc.horizons;
  H.push(sec(8,"Retail Forecast","what the inventory you own is projected to retail — not a pace extrapolation"));
  H.push("<div class='kpis' style='margin-bottom:14px'>");
  ["var(--teal)","var(--accent)","var(--orange)"].forEach(function(col,i){
    let sub="projected units retailed · all models";
    if(i===0){ let mtd=fc.total.sold_mtd, togo=Math.max(0,fc.total.forecast[0]-mtd);
      sub="<b style='color:var(--teal)'>"+mtd+" already retailed</b> + "+togo+" projected to month-end"; }
    H.push("<div class='kpi'><span class='edge' style='background:"+col+"'></span>"+
      "<div class='lab'>"+esc(fh[i].label)+(i===0?" <span class='dim' style='font-weight:400'>(full month)</span>":"")+"</div>"+
      "<div class='big' style='color:"+col+"'>"+fc.total.forecast[i]+"</div>"+
      "<div class='sub'>"+sub+"</div></div>");
  });
  H.push("<div class='kpi'><span class='edge' style='background:var(--muted)'></span><div class='lab'>In stock now</div>"+
    "<div class='big'>"+fc.total.onlot+"</div><div class='sub'>+ "+fc.total.inbound+" inbound in the pipeline</div></div>");
  H.push("</div>");
  H.push("<div class='legend'><span><b>Forecast</b> = min(demand, what you own + inbound) per config</span><span><b>Demand</b> = what the market wants regardless of stock</span><span>gap of the two = your mix / stock health</span></div>");
  H.push(tbl(["Model",fh[0].label,fh[1].label,fh[2].label,"60-day demand","In stock","Inbound","Days supply","Inventory health"],
    ["","num teal","num","num","num","num","num","num",""],
    MODELS.map(function(m){ let d=fc.per_model[m];
      let tmHint=d.sold_mtd>0?"<span class='dim' style='font-weight:400'> ("+d.sold_mtd+" out)</span>":"";
      return [ {html:"<b>"+m+"</b>"}, {html:"<b>"+d.forecast[0]+"</b>"+tmHint}, d.forecast[1],
        {html:"<b style='color:var(--orange)'>"+d.forecast[2]+"</b>"},
        {html:"<span class='dim'>"+d.demand[2]+"</span>"}, d.onlot, {html:"<span class='dim'>"+d.inbound+"</span>"},
        {html:d.days_supply==null?"<span class='dim'>—</span>":d.days_supply+"d"},
        {html:healthBadge(d.health)} ]; })));
  H.push("<div class='foot'><b>This month</b> is a full-month total: units already retailed this calendar month plus the inventory-constrained projection for the days still left. <b>Next 30 / 60 days</b> are purely forward-looking. Reads inventory intelligence — current stock, model/trim/color mix, per-config speed-to-sale, inbound pipeline, aging (wholesale-flagged units excluded), and seasonality. A model can hold heavy stock yet forecast below demand when the stock is in the wrong configs; that gap is the signal to re-mix or dealer-trade.</div>");

  if(res.orphans.length){ let top=res.orphans.slice(0,16).map(o=>o.key+" ("+o.sales+")").join(",  ");
    H.push("<details class='exp' style='margin-top:14px'><summary>Data health — "+res.orphans.length+" configs sold but not on the order roster (ordering can't see them; many are discontinued/legacy — expected)</summary><div class='foot'>"+esc(top)+(res.orphans.length>16?" …":"")+"</div></details>"); }

  let root=document.getElementById("results");
  root.innerHTML=H.join("");
  window.__dashes = groupSections(root);
  if(res.deprActive&&res.depr) wireDepr(res.depr, res.settings);
}
/* ---------- Loaner Depreciation dashboard (in-tool view of the history engine) ---------- */
function deprSvgLine(series, cats){
  let W=680,H=260,pl=50,pr=14,pt=14,pb=38, n=cats.length; if(!n) return "";
  let x=i=>pl+(n<=1?0:(W-pl-pr)*i/(n-1)), y=v=>pt+(H-pt-pb)*(1-v/1.05);
  let g=["<svg viewBox='0 0 "+W+" "+H+"' width='100%' style='max-width:"+W+"px'>"];
  for(let k=0;k<=4;k++){ let v=1.05*k/4, yy=y(v);
    g.push("<line x1='"+pl+"' y1='"+yy+"' x2='"+(W-pr)+"' y2='"+yy+"' stroke='#273448'/>");
    g.push("<text x='"+(pl-8)+"' y='"+(yy+4)+"' fill='#8492a6' font-size='11' text-anchor='end'>"+Math.round(v*100)+"%</text>"); }
  cats.forEach((c,i)=>g.push("<text x='"+x(i)+"' y='"+(H-pb+19)+"' fill='#9dabbf' font-size='10.5' text-anchor='middle'>"+esc(c)+"</text>"));
  series.forEach(s=>{ let pts=s.pts.map((v,i)=>v==null?null:[x(i),y(v)]).filter(Boolean);
    if(pts.length>1) g.push("<polyline fill='none' stroke='"+s.color+"' stroke-width='2.5' points='"+pts.map(p=>p[0].toFixed(1)+","+p[1].toFixed(1)).join(" ")+"'/>");
    s.pts.forEach((v,i)=>{ if(v!=null) g.push("<circle cx='"+x(i)+"' cy='"+y(v)+"' r='3.2' fill='"+s.color+"'/>"); }); });
  return g.join("")+"</svg>";
}
const DEPR_COLORS=["#5eead4","#fb923c","#4c8dff","#f472b6","#a3e635"];
function depreciationRender(res){
  let a=res.depr, s=res.settings, H=[];
  let lv=a.loaner_vs_retail.overall, gd=lv.loaner.gross-lv.retail.gross;
  // headline: does loaner service pay
  H.push("<div class='kpis' style='margin-bottom:12px'>");
  H.push("<div class='kpi'><span class='edge' style='background:var(--teal)'></span><div class='lab'>Loaner resale</div><div class='big' style='color:var(--teal)'>"+money(lv.loaner.price)+"</div><div class='sub'>median · sold at ~"+lv.loaner.avg_age_mo+"mo age</div></div>");
  H.push("<div class='kpi'><span class='edge' style='background:var(--muted)'></span><div class='lab'>Ordinary used resale</div><div class='big'>"+money(lv.retail.price)+"</div><div class='sub'>median · age ~"+lv.retail.avg_age_mo+"mo</div></div>");
  H.push("<div class='kpi'><span class='edge' style='background:"+(gd>=0?"var(--good)":"var(--bad)")+"'></span><div class='lab'>Loaner gross edge</div><div class='big' style='color:"+(gd>=0?"var(--good)":"var(--bad)")+"'>"+(gd>=0?"+":"−")+money(Math.abs(gd)).slice(1)+"</div><div class='sub'>vs ordinary used · "+lv.loaner.n+" past loaners</div></div>");
  H.push("<div class='kpi'><span class='edge' style='background:var(--accent)'></span><div class='lab'>History depth</div><div class='big'>"+a.meta.infiniti_rows.toLocaleString()+"</div><div class='sub'>Infiniti sales · half-life "+a.meta.half_life_months+"mo</div></div>");
  H.push("</div>");
  // retention curves
  let keys=Object.keys(a.age_curves).filter(k=>a.age_curves[k].points.reduce((x,p)=>x+p.n,0)>=40);
  let order={QX80:0,QX60:1,QX55:2,QX50:3,Q50:4}; keys.sort((x,y)=>(order[x]==null?9:order[x])-(order[y]==null?9:order[y]));
  keys=keys.slice(0,5);
  let cats=["0–6mo","6–12mo","1yr","1.5yr","2yr","3yr","4yr","5yr","7yr+"], edges=[0,6,12,18,24,36,48,60,84];
  let series=keys.map((k,i)=>({name:k,color:DEPR_COLORS[i%DEPR_COLORS.length],
    pts:edges.map(e=>{ let p=a.age_curves[k].points.find(pp=>pp.age===e); return p?p.retention_smooth:null; })}));
  H.push("<div class='legend'>"+series.map(sr=>"<span><i style='display:inline-block;width:13px;height:4px;border-radius:2px;background:"+sr.color+";margin-right:5px'></i>"+esc(sr.name)+"</span>").join("")+"</div>");
  H.push("<div class='tblwrap' style='background:var(--panel2);border:1px solid var(--line);border-radius:12px;padding:10px'>"+deprSvgLine(series,cats)+"</div>");
  H.push("<div class='foot' style='margin:6px 0 10px'>Value retention vs vehicle age — your own Infiniti depreciation curves (age axis; the source has no odometer). This is the data that prices each loaner candidate's resale in the Loaner section above.</div>");
  // interactive what-if predictor
  let models=Object.keys(a.age_curves).map(k=>a.age_curves[k].model).filter((v,i,ar)=>ar.indexOf(v)===i);
  let trimsByModel={}; for(let m in a.trim) trimsByModel[m]=a.trim[m].map(t=>t.trim);
  window.__DEPRPC={trimsByModel:trimsByModel};
  H.push("<div class='dc-sub' style='margin-top:6px'>Resale what-if <span class='dc-note'>put a spec into service and see what your history says it resells for at a given age</span></div>");
  H.push("<div class='calc' style='display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end;margin:8px 0 10px'>");
  H.push("<div class='fld'><label>Model</label><select id='dp_model'>"+models.map(m=>"<option>"+esc(m)+"</option>").join("")+"</select></div>");
  H.push("<div class='fld'><label>Trim</label><select id='dp_trim'></select></div>");
  H.push("<div class='fld'><label>Age in service</label><select id='dp_age'>"+
    [["0","new / just placed"],["3","3 months"],["6","6 months"],["12","1 year"],["18","1.5 years"],["24","2 years"],["36","3 years"]].map(o=>"<option value='"+o[0]+"'"+(o[0]=="6"?" selected":"")+">"+o[1]+"</option>").join("")+"</select></div>");
  H.push("</div><div id='dp_out'></div>");
  // per-model resale-by-age table (leading model)
  let lead=keys[0]; if(lead){ let pts=a.age_curves[lead].points;
    H.push("<div class='subttl' style='font-size:12.5px;font-weight:700;color:var(--ink2);text-transform:uppercase;letter-spacing:.5px;margin:14px 0 4px'>"+esc(lead)+" — median resale by age</div>");
    H.push(tbl(["Age"].concat(pts.map(p=>p.label)),[""].concat(pts.map(()=>"num")),
      [["Resale"].concat(pts.map(p=>({html:money(p.price_smooth)}))),
       ["Retention"].concat(pts.map(p=>({html:p.retention_smooth==null?"—":Math.round(p.retention_smooth*100)+"%"}))),
       [{html:"<span class='dim'>Comps</span>"}].concat(pts.map(p=>({html:"<span class='dim'>"+p.n+"</span>"})))])); }
  return H.join("");
}
function wireDepr(a, s){
  let pc=window.__DEPRPC||{trimsByModel:{}};
  function fillTrims(){ let m=document.getElementById("dp_model").value, ts=(pc.trimsByModel[m]||[]);
    let sel=document.getElementById("dp_trim"); sel.innerHTML="<option value=''>(any trim)</option>"+ts.map(t=>"<option value='"+esc(t)+"'>"+esc(t)+"</option>").join(""); }
  function run(){ let m=document.getElementById("dp_model").value, t=document.getElementById("dp_trim").value||null, age=+document.getElementById("dp_age").value;
    let r=window.LoanerIntel.predictResale(a,m,t,null,age), out=document.getElementById("dp_out");
    if(!r||!r.ok){ out.innerHTML="<div class='empty'>No comparable history for that spec.</div>"; return; }
    let dots=Math.round(r.confidence*5);
    out.innerHTML="<div class='lchips' style='gap:10px'>"+
      "<span class='lchip' style='font-size:14px'>Expected resale <b style='color:var(--teal)'>"+money(r.price)+"</b></span>"+
      "<span class='lchip'>range "+money(r.price_low)+"–"+money(r.price_high).slice(1)+"</span>"+
      "<span class='lchip'>gross <b>"+money(r.gross)+"</b></span>"+
      "<span class='lchip'>used turn "+(r.dts==null?"—":r.dts+"d")+"</span>"+
      "<span class='lchip'>confidence "+"●".repeat(dots)+"<span class='dim'>"+"○".repeat(5-dots)+"</span> · "+r.n+" comps</span></div>";
  }
  let dm=document.getElementById("dp_model"); if(!dm) return;
  dm.addEventListener("change",function(){ fillTrims(); run(); });
  document.getElementById("dp_trim").addEventListener("change",run);
  document.getElementById("dp_age").addEventListener("change",run);
  fillTrims(); run();
}
// Wrap the flat output into one <section class="dash"> per dashboard so print
// (and anything else) can show/hide them individually.
function groupSections(root){
  const titleKey={"Order Priority":"order","6-Month Rolling Order Plan":"plan",
    "Fleet Stock Target & Seasonality":"fleet","Demo Center":"democenter",
    "Loaner / ICV Program":"loaner","Loaner Depreciation":"depr",
    "Overstock / Wholesale":"overstock","Wholesale Now — VIN sheet":"vins",
    "Retail Forecast":"forecast"};
  let kids=[].slice.call(root.childNodes), groups=[], cur={key:"summary",title:"Summary",nodes:[]};
  kids.forEach(node=>{
    if(node.nodeType===1 && node.classList && node.classList.contains("sec")){
      if(cur.nodes.length) groups.push(cur);
      let h=node.querySelector("h2"), t=h?h.textContent.trim():"";
      cur={key:titleKey[t]||t, title:t, nodes:[node]};
    } else cur.nodes.push(node);
  });
  if(cur.nodes.length) groups.push(cur);
  let collapsed={}; try{ (JSON.parse(localStorage.getItem("pm_collapsed")||"[]")).forEach(k=>collapsed[k]=1); }catch(e){}
  root.innerHTML="";
  groups.forEach(g=>{ let sec=document.createElement("section"); sec.className="dash"+(collapsed[g.key]?" collapsed":"");
    sec.dataset.dash=g.key; sec.dataset.title=g.title;
    g.nodes.forEach(n=>sec.appendChild(n)); root.appendChild(sec); });
  return groups.map(g=>({key:g.key,title:g.title}));
}
