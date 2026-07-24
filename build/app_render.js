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
function fbRow(lab,val,o){ o=o||{}; let disp;
  if(o.neg) disp="<span class='neg'>−"+money(Math.abs(val)).slice(1)+"</span>";
  else if(o.pos) disp="<span class='pos'>+"+money(Math.abs(val)).slice(1)+"</span>";
  else if(o.total) disp="<span class='"+(val<0?"neg":"pos")+"'>"+money(val)+"</span>";
  else disp="<span>"+money(val)+"</span>";
  return "<div class='fbrow"+(o.sub?" sub":"")+(o.total?" total":"")+"'><span>"+lab+"</span>"+disp+"</div>"; }
// ONE clean cash statement — every dollar counted once, no stacked frameworks.
// `e` defaults to the baseline econ but callers pass the BEST-strategy econ so
// the breakdown matches the recommended outcome shown on the card.
function fbRows(p, e){ e=e||p.econ; let row=fbRow, H=[];
  H.push("<div class='fbdiv'>Money in</div>");
  H.push("<div class='fbrow'><span>Expected resale "+srcBadge(p)+"</span><span class='pos'>+"+money(e.usedPrice).slice(1)+"</span></div>");
  if(e.icvTotal) H.push(row("ICV allowance (one-time factory cash)", e.icvTotal, {pos:true}));
  if(e.bonus) H.push(row("Velocity bonus (earned)", e.bonus, {pos:true}));
  else if(e.velocityAvail) H.push("<div class='fbrow sub'><span>Velocity bonus (misses window)</span><span class='dim'>"+money(e.velocityAvail)+" forfeited</span></div>");
  if(e.dealerCash) H.push(row("Dealer cash", e.dealerCash, {pos:true}));
  H.push("<div class='fbdiv'>Money out</div>");
  H.push(row("Vehicle cost (invoice)", e.cost, {neg:true}));
  if(e.recon) H.push(row("Reconditioning", e.recon, {neg:true}));
  if(e.holding) H.push(row("Holding ("+e.serviceSpan+"mo + used turn)", e.holding, {neg:true}));
  H.push(row("= Owner net profit", e.ownerNet, {total:true}));
  // write-down shown as an accounting NOTE only — never added to owner net
  H.push("<div class='fbrow sub' style='margin-top:6px'><span>Note: manufacturer write-down over "+e.serviceSpan+"mo ≈ "+money(e.deprTotal)+"</span><span class='dim'>internal book move (new→used dept) — depreciation is already in the resale, so it is NOT added again</span></div>");
  return H.join(""); }
function srcBadge(p){
  if(p.usedSrc==="history"){ return "<span class='lhistory' title='resale estimated from your own 10-year history — "+(p.histResale?p.histResale.n:0)+" comparable sales'>📊 history ("+(p.histResale?p.histResale.n:0)+")</span>"; }
  if(p.usedSrc==="measured"){ return "<span class='lmeasured' title='measured from your preowned/auction data'>measured</span>"; }
  return "<span class='lmodeled' title='modeled: 80% of cheapest-new (no history for this config)'>modeled</span>";
}
/* ---------- Executive printable loaner report (Add 5 + 6) ---------- */
function executiveReport(res){
  let s=res.settings, today=res.tb.today, H=[];
  let maxMo=parseFloat(s.loaner_max_months)||7, svc=parseInt(s.loaner_service_months,10)||3;
  function addMonths(m){ let x=new Date(today.getTime()); x.setMonth(x.getMonth()+Math.round(m)); return x.toISOString().slice(0,10); }
  let retireBy=addMonths(maxMo), retailWin=MONTHS[((today.getMonth()+svc)%12+12)%12];
  // Same measure and ranking as the on-screen Service Loaner Selection — one
  // source of truth, so the printed report always matches the screen.
  let sel=(res.selection&&res.selection.units)||[], p=(res.selection&&res.selection.policy)||{};
  let lines=sel.slice(0,15);
  let wd=(p.method==="flat")?("$"+Number(p.flat).toLocaleString()+" flat"):((p.rate||0).toFixed(2)+"%/mo of "+(p.base==="msrp"?"MSRP":"invoice"));

  H.push("<div id='print-exec'><h2>Service Loaner Selection — "+today.toISOString().slice(0,10)+"</h2></div>");
  H.push("<div class='foot' style='margin-bottom:8px'>Which unit to place, ranked by what the used department makes or loses. Store policy: write-down "+wd+", "+(p.months||3)+" months in service. Difference = expected retail − expected cost.</div>");
  if(!lines.length){ H.push("<div class='empty'>No in-stock candidates — paste inventory with unit cost and set incentives.</div>"); }
  else H.push(tbl(
    ["Rank","Unit","Expected cost","Expected retail","Difference"],
    ["num","","num","num","num"],
    lines.map(function(u){
      let veh=(u.year||"")+" "+u.model+" "+esc(u.trim)+" · "+esc(u.uid);
      return [ u.rank, {html:veh}, money0(u.expectedCost), money0(u.expectedRetail),
        {html:"<b style='color:"+(u.difference>=0?"var(--good)":"var(--bad)")+"'>"+moneySign(u.difference)+"</b>"} ]; })));

  // Section 2 — recommended acquisitions
  let recs=res.acquisitionRecs||[];
  H.push("<div id='print-acq' style='margin-top:20px'><h2>RECOMMENDED VEHICLES TO ACQUIRE</h2></div>");
  H.push("<div class='foot' style='margin-bottom:8px'>Configurations our own history says perform well as loaners but which we're thin on today — inventory gaps worth sourcing.</div>");
  if(!recs.length){ H.push("<div class='empty'>Load depreciation history (✎ Data) to surface acquisition recommendations.</div>"); }
  else H.push(tbl(["#","Model year","Model","Trim","Hist. gross","Turn","In stock","Why acquire"],
    ["num","num","","","num","num","num",""],
    recs.map(function(r,i){ return [ i+1, r.year, {html:"<b>"+esc(r.model)+"</b>"}, esc(r.trim),
      money(r.gross), Math.round(r.dts)+"d", {html:(r.in_stock?r.in_stock:"<span class='dim'>0</span>")},
      {html:"<span class='dim'>"+esc(r.why)+"</span>"} ]; })));
  return H.join("");
}
function timingLeftCell(r){
  let left=r.timing?r.timing.remaining:null;
  if(left==null) return "<span class='dim'>—</span>";
  let col=left<=1?"var(--bad)":(left<=2?"var(--warn)":"var(--muted)");
  return "<span style='color:"+col+"'>"+left+"mo</span>";
}
function timingCell(r){
  if(!r.timing){ return "<span class='dim' title='needs cost + matching history to project'>—</span>"; }
  let t=r.timing, b=t.best;
  let opts=t.options.map(o=>o.label+": "+money(o.net)+" net"+(o===b?"  ◀ best":"")+(o.bonusOk?"":" (no bonus)")).join("\n");
  let col=b.delta===0?"var(--good)":"var(--teal)";
  return "<span title=\""+esc(opts)+"\"><b style='color:"+col+"'>"+esc(b.label)+"</b> <span class='dim'>· "+money(b.net)+" net · "+esc(b.why)+"</span></span>";
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

  // current in-service fleet + cascading release + timing optimizer
  if(plan.rows.length){
    let anyTiming=plan.rows.some(r=>r.timing);
    H.push("<div class='dc-sub'>In-service fleet <span class='dc-note'>cascading release — 🔴 pull now, 🟢 eligible, 🅗 hold for ICV"+(anyTiming?" · <b style='color:var(--teal)'>Best window</b> = manufacturer clock + depreciation + used-car seasonality":"")+"</span></div>");
    H.push(tbl(["Stock","Model","Ext/Int","In svc","Left","Miles","ICV (once)","Release by","Status","Best retail window"],
      ["","","","num","num","num","num","","",""],
      plan.rows.map(r=>[esc(r.stock),r.model,esc(r.ext_int),
        r.months+"mo",{html:timingLeftCell(r)},r.miles.toLocaleString(),{html:r.icv_secured?("<span style='color:var(--teal)'>"+money(r.icv_secured)+"</span>"):("<span class='dim' title='booked but not secured until it clears the min-months floor'>"+money(r.icv)+" pending</span>")},
        {html:"<span class='dim'>"+esc(r.release_by)+"</span>"},
        {html:"<b>"+esc(r.status)+"</b>"},{html:timingCell(r)}])));
    if(anyTiming) H.push("<div class='foot'>Best retail window weighs the manufacturer's mandatory-retirement clock, your history's depreciation-by-age, monthly used-car seasonality, velocity-bonus eligibility and holding cost, then picks the window with the highest projected net. Hover a recommendation to see every window compared.</div>");
  } else {
    H.push("<div class='empty'>No loaners in service yet. Add your current fleet in ✎ Data → Loaner / ICV program, then this shows each unit's age, miles, ICV earned and when to release it.</div>");
  }

  // candidate board — best combos to put INTO the program
  H.push("<div class='foot' style='margin-top:14px'>Which unit to place is decided in the <b>Service Loaner Selection</b> section at the top — one ranked list, one number per unit. This section tracks units already in service and when to retire them.</div>");
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

function outMoney(n){ n=Math.round(n||0); return (n<0?"-$":"+$")+Math.abs(n).toLocaleString(); }
// ONE expandable panel: strategy, break-even, sensitivity, scenario search,
// write-down what-ifs, and the full financial math — kept off the clean face.
function detailPanel(it){
  let st=it.strategy, H=["<details class='fbreak'><summary>▸ Strategy, scenarios &amp; math</summary><div class='fbwrap'>"];
  if(st){ let bs=st.best, be=st.breakeven;
    H.push("<div class='fbdiv'>Strategy</div>");
    H.push("<div class='fbrow'><span>Best placement</span><span><b>"+bs.months+" mo</b>"+(bs.pd>0?", place "+MONTHS[bs.placeMonth-1]:", now")+" → retail "+MONTHS[bs.retailMonth-1]+(bs.bonusOk?" ✓bonus":"")+"</span></div>");
    H.push("<div class='fbrow'><span>Break-even</span><span>"+(be.profitable?"<span class='pos'>already profitable</span>":("+$"+be.gap.toLocaleString()+" to cover")) +"</span></div>");
    if(st.retailNew.better) H.push("<div class='fbrow'><span>Retail-new alternative</span><span class='pos'>+$"+st.retailNew.gain.toLocaleString()+" better</span></div>");
    H.push("<div class='fbdiv'>Owner net by service duration (best timing)</div>");
    let byMonth={}; st.grid.forEach(g=>{ if(!byMonth[g.months]||g.ownerNet>byMonth[g.months].ownerNet) byMonth[g.months]=g; });
    Object.keys(byMonth).map(Number).sort((a,b)=>a-b).forEach(m=>{ let g=byMonth[m];
      H.push("<div class='fbrow"+(g===st.best?" total":"")+"'><span>"+m+" mo → retail "+MONTHS[g.retailMonth-1]+(g.bonusOk?" ✓":"")+"</span><span class='"+(g.ownerNet>=0?"pos":"neg")+"'>"+outMoney(g.ownerNet)+"</span></div>"); });
    H.push("<div class='fbdiv'>Write-down what-if — used-dept booked gross <span class='dim'>(owner net above is unchanged — this only shifts loss new↔used dept)</span></div>");
    st.writedownScan.forEach(w=>H.push("<div class='fbrow"+(Math.abs(w.pct-st.baseDepr)<0.01?" total":"")+"'><span>"+w.pct.toFixed(2)+"%/mo"+(Math.abs(w.pct-st.baseDepr)<0.01?" (current)":"")+"</span><span class='"+(w.usedGross>=0?"pos":"neg")+"'>"+outMoney(w.usedGross)+"</span></div>"));
    H.push("<div class='fbdiv'>Sensitivity — what moves the outcome most</div>");
    st.sensitivity.forEach(x=>H.push("<div class='fbrow sub'><span>"+esc(x.name)+" <span class='dim'>("+esc(x.note)+")</span></span><span>±$"+x.impact.toLocaleString()+"</span></div>"));
  }
  H.push("<div class='fbdiv'>Full financial breakdown"+(st?" (best strategy)":"")+"</div>");
  H.push(fbRows(it.p, st?st.best.econ:null));
  H.push("</div></details>");
  return H.join("");
}
function heroRecommendation(res){
  let r=res.serviceRecs; if(!r||!r.items.length) return "<div class='empty'>No in-stock candidates — paste inventory with cost/MSRP, then set the Service loaner need.</div>";
  let H=[];
  H.push("<div class='hero-head'>Service needs <b>"+r.need+"</b> vehicle"+(r.need===1?"":"s")+" — "+
    (r.need>0?("here "+(r.need===1?"is the one":"are the "+r.need)+" to provide"):"set the need up top to get a recommendation")+"</div>");
  if(r.need>0 && r.profitable<r.need){
    H.push("<div class='hero-note'>"+(r.profitable>0?(r.profitable+" of "+r.need+" beat a new-retail sale"):("None currently beat a new-retail sale — opportunity cost "+money(r.newGross)+" each"))+
      " — the rest are ranked as the <b>lowest-cost units to sacrifice</b>. Enter this month's ICV / velocity programs in ✎ Data to unlock more profitable placements.</div>");
  } else {
    H.push("<div class='hero-sub'>Ranked by <b>opportunity advantage</b> — the financial gain of placing each unit into Service Loaner versus keeping it in new retail. Open a card for the full breakdown.</div>");
  }
  let show=r.items.slice(0, Math.max(Math.min(r.items.length,r.need+3), Math.min(r.items.length,6)));
  H.push("<div class='hero-grid'>");
  show.forEach(it=>{
    let edge=it.tier==="provide"?"var(--good)":(it.tier==="accept"?"var(--warn)":"var(--muted)");
    let confCol=it.conf==="High"?"var(--good)":(it.conf==="Medium"?"var(--warn)":"var(--muted)");
    H.push("<div class='hero-card tier-"+it.tier+"'><span class='hr-edge' style='background:"+edge+"'></span>");
    H.push("<div class='hr-top'><span class='hr-rank'>#"+it.rank+"</span><span class='hr-badge'>"+esc(it.rec)+"</span></div>");
    H.push("<div class='hr-veh'>"+esc((it.year||"")+" "+it.model+" "+it.trim)+" <span class='demoei'>"+esc(it.ext)+"/"+esc(it.int)+"</span></div>");
    H.push("<div class='hr-stock'>Stock "+esc(it.stock)+" · VIN …"+esc(it.vin6||"")+(it.dis!=null?" · "+it.dis+"d in stock":"")+"</div>");
    let outN=(it.effNet!=null?it.effNet:it.loanerNet), advN=(it.effAdv!=null?it.effAdv:it.advantage);
    let st=it.strategy, bs=st?st.best:null;
    H.push("<div class='hr-out'><span class='lab'>Best-case outcome</span><span class='amt' style='color:"+(outN>=0?"var(--good)":"var(--bad)")+"'>"+outMoney(outN)+"</span><span class='hr-conf'>Confidence: <b style='color:"+confCol+"'>"+it.conf+"</b></span></div>");
    if(bs) H.push("<div class='hr-plan'>📋 "+bs.months+" months, place "+(bs.pd>0?MONTHS[bs.placeMonth-1]:"now")+" → retail "+MONTHS[bs.retailMonth-1]+(bs.bonusOk?" <span class='pos'>✓ bonus</span>":"")+" · <span class='dim'>vs retail "+outMoney(advN)+"</span></div>");
    if(st&&st.solution) H.push("<div class='hr-fix'>💡 "+esc(st.solution.text)+"</div>");
    H.push("<div class='hr-reason'>"+esc(it.reason)+"</div>");
    H.push(detailPanel(it));
    H.push("</div>");
  });
  H.push("</div>");
  return H.join("");
}
/* ===================== SERVICE LOANER SELECTION (email/print-friendly) ===================== */
// expand/collapse a unit's cost-stack detail row (global — called from onclick)
function toggleSel(tr){ var d=tr.nextElementSibling; if(!d||!d.classList.contains("udetail")) return;
  var open=d.style.display!=="none"; d.style.display=open?"none":"table-row";
  tr.classList.toggle("open",!open); var c=tr.querySelector(".caret"); if(c) c.innerHTML=open?"&#9656;":"&#9662;"; }
// adjust a lever on the fly: write to the canonical Data-panel input and recompute
function setLever(id,val){ var el=document.getElementById(id); if(!el) return; el.value=val;
  el.dispatchEvent(new Event("change")); }
function money0(n){ n=Math.round(n||0); return "$"+Math.abs(n).toLocaleString(); }
function moneySign(n){ n=Math.round(n||0); return (n<0?"-$":"+$")+Math.abs(n).toLocaleString(); }
function diffCell(n){ let c=n>=0?"var(--good)":"var(--bad)"; return "<span style='color:"+c+";font-weight:700'>"+moneySign(n)+"</span>"; }
function stkRow(label,val,cls){
  let disp;
  if(cls==="tot"||cls==="") disp="$"+Math.abs(Math.round(val)).toLocaleString();
  else disp=(val<0?"− $":"+ $")+Math.abs(Math.round(val)).toLocaleString();
  return "<tr class='"+cls+"'><td>"+label+"</td><td class='r'>"+disp+"</td></tr>"; }
// The fleet-flow header: hold N at all times, and let the program move the flow.
// This is what the service-loaner page leads with — current fleet, what's aging
// out, how many to place now, and the month-by-month cadence.
function fleetFlowRender(res){
  let plan=res.loanerFleetPlan; if(!plan) return "";
  let H=["<div class='flowbox'>"];
  let manual=(res.settings.service_need!=null && res.settings.service_need!=="");
  H.push("<div class='flowkpis'>");
  H.push("<div class='fk'><div class='fkl'>In service now</div><div class='fkv'>"+plan.in_service+"</div><div class='fkn'>target "+plan.target+" held at all times</div></div>");
  H.push("<div class='fk'><div class='fkl'>Retire now</div><div class='fkv' style='color:"+(plan.releasing_now?"var(--bad)":"var(--muted)")+"'>"+plan.releasing_now+"</div><div class='fkn'>at their best profit point (or forced by 7 mo / 10k mi)</div></div>");
  let placeNote=manual?"manual override set":(plan.releasing_now?("to hold "+plan.target+" once "+plan.releasing_now+" retire"):(plan.shortfall?(plan.shortfall+" under target"):"at target — nothing to place"));
  H.push("<div class='fk'><div class='fkl'>Place now</div><div class='fkv' style='color:"+(plan.to_add?"var(--orange)":"var(--good)")+"'>"+plan.to_add+"</div><div class='fkn'>"+placeNote+"</div></div>");
  H.push("</div>");
  // color mix of the current fleet
  let mix=plan.color_mix||{}, mk=Object.keys(mix).sort((a,b)=>mix[b]-mix[a]);
  if(mk.length) H.push("<div class='basis' style='margin:2px 0 6px'>Current fleet colors: "+mk.map(k=>"<b>"+esc(String(k).toLowerCase())+"</b> "+mix[k]).join(" · ")+".</div>");
  // per-unit retirement schedule — the engine's best time to retire each vehicle
  let rows=plan.rows||[];
  if(rows.length){
    H.push("<details class='retsched' open><summary class='mixh'>When to retire each unit <span class='dim' style='font-weight:400'>— engine-timed for best profit, within the 7-month / 10k-mile window</span></summary>");
    H.push("<table class='mos'><thead><tr><th>Stock</th><th>Vehicle</th><th>Color</th><th class='r'>In svc</th><th class='r'>Miles</th><th>Best retire</th><th>Why</th></tr></thead><tbody>");
    rows.forEach(r=>{ let now=(r.status.indexOf("RETIRE NOW")>=0);
      H.push("<tr"+(now?" class='toprow'":"")+"><td>"+esc(r.stock)+"</td><td>"+esc(r.vehicle||r.model)+"</td><td>"+esc(String(r.color||"").toLowerCase())+"</td>"+
        "<td class='r'>"+r.months+"mo</td><td class='r'>"+r.miles.toLocaleString()+"</td>"+
        "<td>"+(now?"<b style='color:var(--bad)'>now</b>":("<b>"+esc(monLabel((r.release_by||"").slice(0,7)))+"</b>"))+"</td>"+
        "<td class='dim'>"+esc(r.release_why||"")+"</td></tr>"); });
    H.push("</tbody></table></details>");
  }
  // forward cadence
  let cad=(plan.cadence||[]).filter(c=>c.releasing>0 || c.place>0);
  if(cad.length){
    H.push("<div class='basis' style='margin:6px 0 4px'>The flow to hold "+plan.target+" at all times — place as units hit their best retire month:</div>");
    H.push("<table class='mos'><thead><tr><th>Month</th>"+cad.map(c=>"<th class='r'>"+monLabel(c.month)+"</th>").join("")+"</tr></thead><tbody>");
    H.push("<tr><td>Retiring</td>"+cad.map(c=>"<td class='r'>"+(c.releasing||0)+"</td>").join("")+"</tr>");
    H.push("<tr><td><b>Place</b></td>"+cad.map(c=>"<td class='r'><b>"+(c.place||0)+"</b></td>").join("")+"</tr></tbody></table>");
  }
  H.push(outcomesRender(res));
  H.push("</div>");
  return H.join("");
}
// Forecast scorecard — predicted vs. actual on loaners that have sold. Tells us
// whether the front-end call is running high or low so the model can be tuned.
function outcomesRender(res){
  let o=res.loanerOutcomes; if(!o||!o.rows||!o.rows.length) return "";
  let a=o.agg, anyBorrowed=o.rows.some(r=>!r.exact);
  let H=["<details class='retsched' open style='margin-top:8px'><summary class='mixh'>Forecast vs. actual <span class='dim' style='font-weight:400'>— "+o.matched+" sold loaner"+(o.matched===1?"":"s")+" scored"+(o.unmatched?(" · "+o.unmatched+" sold row"+(o.unmatched===1?"":"s")+" had no VIN match"):"")+"</span></summary>"];
  if(a){
    let rb=a.retailBias, gb=a.grossBias;
    let call=g=>g==null?"":(g>0?("actuals ran <b style='color:var(--good)'>$"+Math.abs(g).toLocaleString()+" above</b> forecast"):(g<0?("actuals ran <b style='color:var(--bad)'>$"+Math.abs(g).toLocaleString()+" below</b> forecast"):"actuals matched forecast"));
    H.push("<div class='warn' style='background:rgba(76,141,255,.08);border-color:rgba(76,141,255,.30)'>"+
      "On "+a.n+" sold loaner"+(a.n===1?"":"s")+", resale "+call(rb)+" (avg miss $"+(a.retailMAE!=null?a.retailMAE.toLocaleString():"—")+"). "+
      (rb!=null&&Math.abs(rb)>=750?("<b>The resale model is running "+(rb>0?"low — it under-values these; nudge expected retail up.":"high — it over-values these; trim expected retail down.")+"</b> "):"The resale model is tracking close — no change needed. ")+
      ((a.grossN)?("Front gross "+call(gb)+" (avg miss $"+(a.grossMAE!=null?a.grossMAE.toLocaleString():"—")+", on "+a.grossN+" with a real cost basis)."):"")+
      "</div>");
  }
  H.push("<table class='mos'><thead><tr><th>Sold</th><th>Vehicle</th><th class='r'>In svc</th><th class='r'>Miles</th><th class='r'>Predicted retail</th><th class='r'>Actual</th><th class='r'>Miss</th><th class='r'>Pred. gross</th><th class='r'>Actual gross</th></tr></thead><tbody>");
  o.rows.forEach(r=>{
    H.push("<tr><td>"+esc(r.sold||"—")+"</td><td>"+esc((r.model||"")+" "+String(r.ext||"").toLowerCase())+" · "+esc(String(r.stock||r.vin||"").slice(-6))+(r.exact?"":" <span class='dim' title='no exact cost basis in inventory — front gross not scored'>·est</span>")+"</td>"+
      "<td class='r'>"+r.months+"mo</td><td class='r'>"+(r.miles!=null?r.miles.toLocaleString():"—")+"</td>"+
      "<td class='r'>"+money0(r.predRetail)+"</td><td class='r'>"+(r.actualPrice!=null?money0(r.actualPrice):"—")+"</td>"+
      "<td class='r'>"+(r.retailErr!=null?diffCell(r.retailErr):"—")+"</td>"+
      "<td class='r'>"+(r.exact?diffCell(r.predDiff):"<span class='dim'>—</span>")+"</td><td class='r'>"+(r.actualGross!=null?diffCell(r.actualGross):"—")+"</td></tr>"); });
  H.push("</tbody></table>");
  H.push("<div class='basis' style='margin-top:4px'>Predicted resale is recomputed at the age and mileage each unit actually sold at, with its entry-month ICV — a clean read on the model, not on timing. “Miss” is actual minus predicted resale (green = we were conservative)."+
    (anyBorrowed?" Rows marked <b>·est</b> aren't stocked in current inventory, so there's no real cost basis — their front gross is left out of the scoring.":"")+"</div>");
  H.push("</details>");
  return H.join("");
}
function monLabel(ym){ let m=String(ym||"").split("-"); if(m.length<2) return esc(ym||"");
  let n=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][parseInt(m[1],10)-1]||m[1];
  return n+" "+m[0].slice(2); }
function serviceSelectionRender(res){
  let sel=res.selection, s=res.settings, H=[];
  H.push(fleetFlowRender(res));   // the fleet-flow header — this is the part that "talks"
  if(!sel||!sel.units.length) return H.join("")+"<div class='empty'>No orderable candidate units in stock — paste inventory with unit cost (and check that the config isn't suppressed), then set incentives in Data.</div>";
  let units=sel.units, p=sel.policy, need=Math.max(1,(typeof _placeNeed==="function"?_placeNeed(res):1));
  // On-the-fly levers — adjust and the whole list re-ranks. These proxy the
  // canonical Data-panel inputs so there is still one source of truth.
  let methodSel="<select onchange=\"setLever('lwdmethod',this.value)\">"+
    "<option value='pct'"+(p.method!=="flat"?" selected":"")+">Percent / month</option>"+
    "<option value='flat'"+(p.method==="flat"?" selected":"")+">Flat dollars</option></select>";
  let rateInput = p.method==="flat"
    ? ("$<input type='number' value='"+Math.round(p.flat)+"' step='250' style='width:90px' onchange=\"setLever('lwdflat',this.value)\"> flat")
    : ("<input type='number' value='"+p.rate.toFixed(2)+"' step='0.05' style='width:70px' onchange=\"setLever('ldepr',this.value)\">% per month of "+(p.base==="msrp"?"MSRP":"invoice"));
  let mosInput="<input type='number' value='"+p.months+"' min='1' max='7' style='width:56px' onchange=\"setLever('lsvc',this.value)\"> months in service";
  H.push("<div class='polhdr'><b>Store policy (adjust on the fly):</b> write-down "+methodSel+" "+rateInput+", "+mosInput+
    ". <span class='dim'>Applied to every unit; changing it re-ranks the list below.</span></div>");
  let top=units[0], second=units[1];
  let margin=second?(top.difference-second.difference):null;
  let lead="Place the <b>"+esc(top.year+" "+top.model+" "+top.trim)+"</b> ("+esc(top.uid)+"). Difference "+diffCell(top.difference);
  if(second) lead += margin>0 ? (", <span style='color:var(--good);font-weight:700'>$"+margin.toLocaleString()+"</span> better than the next unit.")
                              : ", tied with the next unit.";
  else lead += ".";
  if(need>1) lead+=" You need to place <b>"+need+"</b> to hold your fleet target — the diversified mix below is the pick.";
  else if(need===1) lead+=" That's the one to place to hold your fleet target.";
  H.push("<div class='lead'>"+lead+"</div>");
  if(need>1) H.push(placementMixRender(sel, need));
  H.push(idealOrderRender(res));
  H.push("<div class='foot' style='margin:8px 0 4px'>Every candidate, ranked by difference. Click any unit to see how its cost stacks.</div>");
  H.push("<table class='seltbl'><thead><tr><th></th><th>Rank</th><th>Unit</th><th class='r'>Expected cost</th><th class='r'>Expected retail</th><th class='r'>Difference</th></tr></thead><tbody>");
  units.forEach(u=>{
    H.push("<tr class='urow"+(u.rank<=need?" toprow":"")+"' onclick='toggleSel(this)'>"+
      "<td class='caret'>&#9656;</td><td>"+u.rank+"</td>"+
      "<td>"+esc(u.year+" "+u.model+" "+u.trim)+" · "+esc(u.uid)+"</td>"+
      "<td class='r'>"+money0(u.expectedCost)+"</td><td class='r'>"+money0(u.expectedRetail)+"</td>"+
      "<td class='r'>"+diffCell(u.difference)+"</td></tr>");
    H.push("<tr class='udetail' style='display:none'><td></td><td colspan='5'>"+unitStackInner(u,p)+"</td></tr>");
  });
  H.push("</tbody></table>");
  H.push(policyExplorerRender(res));
  return H.join("");
}
// Diversified placement mix — caps identical configs so we don't flood the used
// lot with five of the same car when they all come out of service together.
function placementMixRender(sel, need){
  let mix=sel.mix, con=sel.concentration; if(!mix||!mix.length) return "";
  let H=["<div class='mixbox'>"];
  H.push("<div class='mixh'>Recommended placement mix"+(need>1?" ("+need+" units)":"")+"</div>");
  if(con&&con.over){
    H.push("<div class='warn'>Heads up on diversification: your best-difference units are mostly <b>"+esc(con.config)+"</b> ("+con.count+" of the top "+con.need+"). "+
      "Our history retails only about "+(con.rate!=null?con.rate.toFixed(1):"?")+" of those a month, and every loaner placed now comes out of service together — five identical ones would flood the used lot and undercut each other. The mix below spreads the placements while keeping the strongest units per config.</div>");
  } else if(need>1){
    H.push("<div class='basis'>These are diversified so the units don't all land on the used lot as the same car at the same time.</div>");
  }
  H.push("<table class='seltbl'><thead><tr><th>Place</th><th>Unit</th><th class='r'>Difference</th><th class='r'>Sells ~/mo</th></tr></thead><tbody>");
  mix.forEach((m,i)=>H.push("<tr class='toprow'><td>"+(i+1)+"</td><td>"+esc(m.name+" · "+m.stock)+"</td>"+
    "<td class='r'>"+diffCell(m.difference)+"</td><td class='r'>"+(m.absorb!=null?m.absorb.toFixed(1):"—")+"</td></tr>"));
  H.push("</tbody></table></div>");
  return H.join("");
}
// The other half of the question: not just which unit we HAVE, but which config
// we should keep ORDERING for the loaner program. Built from the same per-unit
// economics as the ranking above, grouped by model+trim and ranked by the MEDIAN
// difference — robust to one-off units, so it answers "what should we routinely
// order," and it converges with the in-stock top pick by construction.
function idealOrderRender(res){
  let sel=res.selection; if(!sel||!sel.units||!sel.units.length) return "";
  let g={};
  sel.units.forEach(u=>{ let k=u.model+" "+u.trim; (g[k]=g[k]||{units:[],model:u.model,trim:u.trim}).units.push(u); });
  let med=arr=>{ let v=arr.slice().sort((a,b)=>a-b), n=v.length; return n? (n%2?v[(n-1)/2]:Math.round((v[n/2-1]+v[n/2])/2)) : null; };
  let rows=Object.keys(g).map(k=>{ let x=g[k], ds=x.units.map(u=>u.difference);
    let days=x.units.map(u=>u.avgDays).filter(d=>d!=null);
    return {config:k, model:x.model, trim:x.trim, n:x.units.length,
      medDiff:med(ds), medRetail:med(x.units.map(u=>u.expectedRetail)), days:(days.length?med(days):null)}; });
  rows.sort((a,b)=>b.medDiff-a.medDiff);
  let top=rows.slice(0,3); if(!top.length) return "";
  let haveTop=(sel.units[0])?(sel.units[0].model+" "+sel.units[0].trim):null;
  let H=["<details class='mixbox' open><summary class='mixh'>Ideal unit to order &amp; keep in</summary>"];
  H.push("<div class='basis'>The config with the best <b>typical</b> difference across every unit of it we've got — what to keep ordering for the loaner program, rather than a one-off unit that happened to price well. Over time this and the in-stock top pick should converge.</div>");
  H.push("<table class='seltbl'><thead><tr><th>Order</th><th>Config</th><th class='r'>Units on lot</th><th class='r'>Typical difference</th><th class='r'>Days to sell</th></tr></thead><tbody>");
  top.forEach((r,i)=>{ let match=(haveTop&&r.config.toUpperCase()===haveTop.toUpperCase());
    H.push("<tr class='"+(match?"toprow":"")+"'><td>"+(i+1)+"</td><td>"+esc(r.config)+(match?" <span class='flag'>matches top in-stock pick</span>":"")+"</td>"+
      "<td class='r'>"+r.n+"</td><td class='r'>"+diffCell(r.medDiff)+"</td><td class='r'>"+(r.days!=null?r.days+"d":"—")+"</td></tr>"); });
  H.push("</tbody></table></details>");
  return H.join("");
}
function unitStackInner(u,p){
  let H=["<table class='stk'><tbody>"];
  H.push(stkRow("Invoice", u.invoice, ""));
  H.push(stkRow("ICV allowance", -u.icv, "sub"));
  H.push(stkRow("Velocity bonus"+(u.eligible?"":" (not earned)"), -(u.eligible?u.velocity:0), "sub"));
  H.push(stkRow("Write-down"+(p.method==="flat"?" (flat)":" ("+p.rate.toFixed(2)+"% of "+(u.wdBase||"invoice")+" × "+p.months+" mo)"), -u.writedown, "sub"));
  H.push(stkRow("Reconditioning", u.recon, "sub"));
  H.push(stkRow("Expected cost", u.expectedCost, "tot"));
  H.push("</tbody></table>");
  // the two prices the owner asked for
  H.push("<div class='prices'>"+
    "<div class='pr1'><div class='prl'>Lowest retail to break even</div><div class='prv'>"+money0(u.expectedCost)+"</div><div class='prn'>sell below this and it loses money</div></div>"+
    "<div class='pr1'><div class='prl'>Expected selling price</div><div class='prv' style='color:var(--teal)'>"+money0(u.expectedRetail)+"</div><div class='prn'>"+
      (u.retailLow!=null&&u.retailHigh!=null?("typical range "+money0(u.retailLow)+"&ndash;"+money0(u.retailHigh)):"modeled")+"</div></div>"+
    "<div class='pr1'><div class='prl'>Cushion (difference)</div><div class='prv' style='color:"+(u.difference>=0?"var(--good)":"var(--bad)")+"'>"+moneySign(u.difference)+"</div><div class='prn'>expected price &minus; break-even</div></div>"+
    "</div>");
  // basis + color, both drawn from the comps shown below
  let colorTxt = (u.color && u.colorN>=2 && u.colorPrem!=null && Math.abs(u.colorPrem)>0) ? (" Within these sales, the <b>"+esc(u.color.toLowerCase())+"</b> ones sold "+(u.colorPrem>=0?"+$":"−$")+Math.abs(u.colorPrem||0).toLocaleString()+" vs the set"+
      (u.colorDtsDelta!=null?" and "+(u.colorDtsDelta<=0?Math.abs(u.colorDtsDelta)+" days faster":u.colorDtsDelta+" days slower"):"")+", so that adjustment is applied.")
    : (u.color ? (" This unit is <b>"+esc(u.color.toLowerCase())+"</b>; the history here doesn't show a distinct color effect, so no color premium is applied.") : "");
  var ageTxt=(u.ageFactor!=null&&u.ageFactor<0.999)?(", then walked down this model's age curve to ~"+(u.ageAtSale!=null?u.ageAtSale:(p.months+1.5))+" months old at sale (×"+u.ageFactor.toFixed(3)+")"):"";
  H.push("<div class='basis'>Expected price is the recency-weighted median of "+
    (u.compN>0?("every recent "+esc(u.model+" "+u.trim)+" sale below ("+u.compN+" of them, each adjusted to a near-new baseline)"+ageTxt):"a modeled fallback (no matching history yet)")+
    ". Projected at today's market — no seasonal guessing."+colorTxt+"</div>");
  // the actual comps behind the number — full trim history, age-normalized to near-new
  var A=(typeof window!=="undefined"&&window.DEPR&&window.DEPR.a)?window.DEPR.a:null;
  var comps=A?(A.compsRange?A.compsRange(u.model,u.trim,36):(A.getComps?A.getComps(u.model,u.trim,u.refAge||3):[])):[];
  var curve=(A&&A.age_curves&&A.age_curves[u.model])?A.age_curves[u.model].points:null;
  if(comps.length){
    H.push("<details class='fbreak'><summary>Show the "+comps.length+" sale"+(comps.length>1?"s":"")+" this price is based on</summary><div class='fbwrap'>");
    H.push("<div class='basis' style='margin:0 0 6px'>Older sales are adjusted up this model's depreciation curve so a 2-year-old sale is comparable to a near-new one. The median of the <b>adjusted</b> column is the near-new baseline.</div>");
    H.push("<table class='mos'><thead><tr><th>Sold</th><th>Vehicle</th><th>Color</th><th class='r'>Sold for</th><th class='r'>Adjusted</th><th class='r'>Days to sell</th><th class='r'>Age</th></tr></thead><tbody>");
    comps.slice(0,40).forEach(function(c){
      var r=(typeof _interpRet==="function"&&curve)?_interpRet(curve,c.age):null, adj=c.price;
      if(r!=null&&r>0&&curve){ var rRef=_interpRet(curve,3); if(rRef!=null) adj=Math.round(c.price*(rRef/r)); }
      H.push("<tr><td>"+c.date.toISOString().slice(0,7)+"</td>"+
        "<td>"+esc((c.year||"")+" "+(c.trim||""))+"</td><td>"+esc((c.color||"").toLowerCase())+"</td>"+
        "<td class='r'>"+money0(c.price)+"</td><td class='r'>"+(adj!==c.price?money0(adj):"—")+"</td><td class='r'>"+(c.dts!=null?c.dts+"d":"—")+"</td><td class='r'>"+(c.age!=null?Math.round(c.age)+"mo":"—")+"</td></tr>"); });
    H.push("</tbody></table>");
    if(comps.length>40) H.push("<div class='basis'>Showing the 40 most recent of "+comps.length+".</div>");
    H.push("</div></details>");
  }
  H.push("<div class='basis' style='margin-top:8px'>Cushion at each service length. Month to month only two things move, and both are real: the <b>write-down grows</b> one more month (helps the cushion), while the car is <b>one month older</b> at sale so it resells for slightly less (hurts it). The bigger step happens when the sale age pushes past the 7-month velocity window and the bonus is lost:</div>");
  H.push("<table class='mos'><thead><tr><th>Months in service</th>"+u.byMonth.map(bm=>"<th class='r'>"+bm.months+"</th>").join("")+"</tr></thead><tbody><tr><td>Cushion</td>"+
    u.byMonth.map(bm=>"<td class='r"+(bm.months===p.months?" cur":"")+"'>"+diffCell(bm.difference)+"</td>").join("")+"</tr></tbody></table>");
  return H.join("");
}
function policyExplorerRender(res){
  let pe=res.policyExplorer; if(!pe||!pe.scenarios.length) return "";
  let H=["<details class='explorer'><summary>Policy explorer &mdash; what a write-down change would do</summary>"];
  H.push("<div class='basis'>Each scenario re-ranks every unit under a store-wide write-down change ("+pe.months+" months in service). Scenarios that change which unit ranks first are flagged.</div>");
  pe.scenarios.forEach(sc=>{
    H.push("<div class='scen'><div class='scenh'>"+esc(sc.label)+(sc.changesTop?" <span class='flag'>changes top pick</span>":"")+"</div>");
    H.push("<table class='seltbl'><thead><tr><th>Rank</th><th>Unit</th><th class='r'>Difference</th></tr></thead><tbody>");
    sc.order.slice(0,8).forEach(o=>H.push("<tr class='"+(o.rank===1?"toprow":"")+"'><td>"+o.rank+"</td><td>"+esc(o.name+" · "+o.stock)+"</td><td class='r'>"+diffCell(o.difference)+"</td></tr>"));
    H.push("</tbody></table></div>");
  });
  H.push("</details>");
  return H.join("");
}
function render(res){
  let rep={op:orderPriority(res),over:overstock(res),vins:wholesaleVins(res),demo:demoDashboard(res),fleet:fleetTargets(res)};
  let s=res.settings,tb=res.tb, H=[];
  let fc=retailForecast(res);   // computed once; reused in the Retail Forecast section
  let latest=tb.latest?(Math.floor(tb.latest/12)+"-"+String(tb.latest%12).padStart(2,"0")):"—";

  // SERVICE LOANER SELECTION — which unit to place into the mandatory program
  H.push(sec("1","Service Loaner Selection","which unit to place, ranked by what the used department makes or loses"));
  H.push(serviceSelectionRender(res));

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

  H.push(sec(4,"Executive Demo Program","owner / manager / employee demos — a SEPARATE program from Service Loaners"));
  H.push("<div class='democenter'><div class='dc-left'>"+board.join("")+"</div>"+
    "<div class='dc-right'>"+dash.join("")+"<div style='height:12px'></div>"+loaners.join("")+"</div></div>");

  // 5. LOANER / ICV PROGRAM
  H.push(sec(5,"Service Loaner Program","which units to sacrifice to the Service Loaner fleet for the best preowned profit"));
  H.push(loanerRender(res));

  // 5b. LOANER DEPRECIATION INTELLIGENCE — the engine behind the resale prices above
  if(res.deprActive&&res.depr){ H.push(sec(9,"Service Loaner Depreciation","what a Service Loaner really resells for — from your own 10-year history · powers the resale prices above")); H.push(depreciationRender(res)); }

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

  // 10. EXECUTIVE LOANER REPORT — printable worksheet for ownership
  H.push(sec(10,"Executive Report — Service Loaners","printer-friendly ranked worksheet — recommended units + acquisition targets · print this alone for the meeting"));
  H.push(executiveReport(res));

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
  const titleKey={"Service Loaner Selection":"selection",
    "Order Priority":"order","6-Month Rolling Order Plan":"plan",
    "Fleet Stock Target & Seasonality":"fleet","Executive Demo Program":"democenter",
    "Service Loaner Program":"loaner","Service Loaner Depreciation":"depr",
    "Overstock / Wholesale":"overstock","Wholesale Now — VIN sheet":"vins",
    "Retail Forecast":"forecast","Executive Report — Service Loaners":"execreport"};
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
