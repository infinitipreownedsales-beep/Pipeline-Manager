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

function orderPriority(res){ let s=res.settings,out={};
  MODELS.forEach(model=>{ let ranked=res.lines.filter(l=>l.model===model&&l.priority>-1).sort((a,b)=>b.priority-a.priority);
    let alloc=s.allocations[model]||0, cum=0, rows=[];
    ranked.forEach((l,i)=>{ cum+=l.need; let tier=l.need===0?"option":(cum<=alloc?"build":"alt");
      rows.push({rank:i+1,line:l,cum:cum,tier:tier}); });
    out[model]={alloc:alloc,rows:rows,totalNeed:res.lines.filter(l=>l.model===model).reduce((a,l)=>a+l.need,0),
      buildUnits:rows.filter(r=>r.tier==="build").reduce((a,r)=>a+r.line.need,0)}; });
  return out; }
function overstock(res){ let rows=[];
  res.lines.forEach(l=>{ let over=l.onlot-l.overstockTarget; if(l.suppressed||over<1) return;
    rows.push({model:l.model,trim:l.trim,ext:l.ext,int:l.int,onhand:l.onlot,target:l.overstockTarget,over:over,wholeNow:l.wholeNow,inbound:l.inbound,dts:l.dts,aged:l.pos.aged.length}); });
  rows.sort((a,b)=>(MODELS.indexOf(a.model)-MODELS.indexOf(b.model))||(b.over-a.over)||(b.wholeNow-a.wholeNow)); return rows; }
function wholesaleVins(res){ let rows=[];
  res.lines.forEach(l=>{ if(l.wholeNow<=0) return; let units=l.pos.whole.slice().sort((a,b)=>b.dis-a.dis).slice(0,l.wholeNow);
    units.forEach(u=>{ let vin=u.serial||u.stock; rows.push({stock:u.stock||"—",vin6:vin?vin.slice(-6):"—",year:u.myear||u.my||"",model:u.model,trim:l.trim||u.desc,ei:u.ext+"/"+u.int,dis:Math.round(u.dis)}); }); });
  rows.sort((a,b)=>b.dis-a.dis); rows.forEach((r,i)=>r.num=i+1); return rows; }
function demoDashboard(res){ let s=res.settings, rows=[];
  res.demoUnits.forEach(u=>{ let dis=Math.round(u.dis), asDemo=dis;
    for(let pref in s.demo_starts){ if(pref&&u.stock.indexOf(pref)===0){ let d0=new Date(s.demo_starts[pref]); if(!isNaN(d0.getTime())) asDemo=Math.round((res.tb.today-d0)/86400000); break; } }
    let retIn=Math.max(0,s.swap_threshold-asDemo);
    rows.push({stock:u.stock,vehicle:u.desc,dis:dis,asDemo:asDemo,swap:asDemo>s.swap_threshold,retIn:retIn,ei:u.ext+"/"+u.int}); });
  rows.sort((a,b)=>b.asDemo-a.asDemo); return rows; }
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

function tbl(head,cls,rows){
  let h="<div class='tblwrap'><table><thead><tr>"+head.map((x,i)=>"<th class='"+(cls[i]||"")+"'>"+x+"</th>").join("")+"</tr></thead><tbody>";
  h+=rows.map(r=>"<tr>"+r.map((c,i)=>"<td class='"+(cls[i]||"")+"'>"+(c&&c.html!==undefined?c.html:esc(c))+"</td>").join("")+"</tr>").join("");
  return h+"</tbody></table></div>"; }
function sec(n,title,meta){ return "<div class='sec'><span class='n'>"+n+"</span><h2>"+esc(title)+"</h2><span class='meta'>"+esc(meta||"")+"</span></div>"; }

function sparkline(vals){ // 12 monthly seasonality index values, baseline 1.0
  let w=210,h=46,pad=4, mn=Math.min.apply(null,vals.concat([1])), mx=Math.max.apply(null,vals.concat([1]));
  let rng=(mx-mn)||1, X=i=>pad+i*(w-2*pad)/11, Y=v=>h-pad-((v-mn)/rng)*(h-2*pad);
  let pts=vals.map((v,i)=>X(i)+","+Y(v).toFixed(1));
  let area="M"+X(0)+","+ (h-pad)+" L"+pts.join(" L ")+" L"+X(11)+","+(h-pad)+" Z";
  let line="M"+pts.join(" L ");
  let base=Y(1);
  return "<svg class='spark' width='"+w+"' height='"+h+"' viewBox='0 0 "+w+" "+h+"'>"+
    "<path d='"+area+"' fill='rgba(94,234,212,.13)'/>"+
    "<line x1='"+pad+"' y1='"+base.toFixed(1)+"' x2='"+(w-pad)+"' y2='"+base.toFixed(1)+"' stroke='#3a4a63' stroke-dasharray='3 3' stroke-width='1'/>"+
    "<path d='"+line+"' fill='none' stroke='#5eead4' stroke-width='2' stroke-linejoin='round' stroke-linecap='round'/>"+
    "</svg>"; }

function render(res){
  let rep={op:orderPriority(res),over:overstock(res),vins:wholesaleVins(res),demo:demoDashboard(res),pace:paceCheck(res),fleet:fleetTargets(res)};
  let s=res.settings,tb=res.tb, H=[], paceBy={}; rep.pace.forEach(p=>paceBy[p.model]=p);
  let latest=tb.latest?(Math.floor(tb.latest/12)+"-"+String(tb.latest%12).padStart(2,"0")):"—";

  // KPI tiles
  let readColor={AHEAD:"var(--good)",ON:"var(--option)",BEHIND:"var(--bad)"};
  let readLabel={AHEAD:"ahead of pace",ON:"on target",BEHIND:"behind pace"};
  H.push("<div class='kpis'>");
  MODELS.forEach(model=>{ let b=rep.op[model], p=paceBy[model];
    H.push("<div class='kpi model'><span class='edge' style='background:"+readColor[p.read]+"'></span>"+
      "<div class='lab'>"+model+" — order now</div><div class='big'>"+b.totalNeed+"</div>"+
      "<div class='sub'>"+b.buildUnits+" within allocation · <span style='color:"+readColor[p.read]+"'>"+readLabel[p.read]+"</span></div></div>"); });
  let totWhole=res.lines.reduce((a,l)=>a+l.wholeNow,0), totOver=rep.over.reduce((a,r)=>a+r.over,0);
  H.push("<div class='kpi'><span class='edge' style='background:var(--over)'></span><div class='lab'>Overstock</div>"+
    "<div class='big' style='color:var(--over)'>"+totOver+"</div><div class='sub'>"+totWhole+" ready to wholesale today</div></div>");
  H.push("<div class='kpi'><span class='edge' style='background:var(--teal)'></span><div class='lab'>Sales history</div>"+
    "<div class='big' style='color:var(--teal)'>"+tb.span.toFixed(1)+"<span style='font-size:15px;color:var(--muted)'> mo</span></div>"+
    "<div class='sub'>newest "+latest+(tb.open?" · open":"")+" · "+res.orphans.length+" off-roster</div></div>");
  H.push("</div>");

  let winTxt = s.mode==="CPO"
    ? " · arrival lead "+MODELS.map(m=>m+" "+(res.windows[m]).toFixed(1)+"mo").join(" / ")
    : "";
  H.push("<div class='foot noprint' style='margin:-6px 2px 6px'>Recomputed "+tb.today.toISOString().slice(0,10)+
    " · order month <b style='color:var(--ink2)'>"+MONTHS[s.order_month-1]+"</b> · mode <b style='color:var(--ink2)'>"+s.mode+
    "</b>"+winTxt+" · "+res.invCount+" inventory units · "+res.salesCount+" sales rows</div>");

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
      ["num","","","","","num","","","num","num","num teal","num","num need","num"], rows)); });

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
  MODELS.forEach(model=>{ let f=rep.fleet[model], mx=Math.max.apply(null,f.concat([1]));
    let cells="<td class='rl'>"+model+"</td>"+f.map((v,i)=>{ let t=v/mx; return "<td class='cell' style='background:"+heatColor(t)+";color:"+heatText(t)+"'>"+v+"</td>"; }).join("");
    let cur=res.tb.latest?((res.tb.latest-1)%12):0;
    H.push("<div style='display:flex;gap:20px;align-items:center;flex-wrap:wrap;margin:8px 0'>"+
      "<table class='heat'><thead><tr><th></th>"+MONTHS.map(m=>"<th style='font-size:9px;color:#6b7891;text-align:center'>"+m+"</th>").join("")+"</tr></thead><tbody><tr>"+cells+"</tr></tbody></table>"+
      "<div style='text-align:center'>"+sparkline(res.seas[model].index)+"<div class='foot' style='margin:0;text-align:center'>seasonality · avg = 1.0</div></div></div>"); });

  // 4. EXECUTIVE DEMO BOARD
  H.push(sec(4,"Executive Demo Board","best proven fast-movers to put your execs in — resells quickly even with miles"));
  H.push("<div class='foot' style='margin:-4px 2px 10px'>Only combos with a short days-to-sell and repeat demand (never one-offs) qualify, so a demo still turns fast once released. VIN listed where in stock; otherwise flagged to order.</div>");
  let ed=executiveDemos(res);
  H.push("<div class='demogrid'>");
  MODELS.forEach(model=>{ let picks=ed[model];
    H.push("<div class='democol'><div class='demohd'>"+model+"</div>");
    if(!picks.length){ H.push("<div class='empty'>No proven fast combo yet.</div>"); }
    picks.forEach((p,i)=>{
      let medal=["①","②","③","④","⑤"][i]||("#"+(i+1));
      H.push("<div class='democard"+(i===0?" top":"")+"'>"+
        "<div class='demorank'>"+medal+"</div>"+
        "<div class='demotrim'>"+esc(p.trim)+" <span class='demoei'>"+esc(p.ext)+"/"+esc(p.int)+"</span></div>"+
        "<div class='demowhy'>"+dtsCell(p.dts)+" <span class='pill "+("m-"+(p.momentum==="on cadence"?"oncadence":p.momentum.replace(/\s/g,"")))+"'>"+esc(p.momentum)+"</span> <span class='demometa'>"+p.total+" sold · "+(p.r90||p.r180)+" recent</span></div>");
      if(p.units.length){ p.units.forEach(u=>{
        H.push("<div class='demovin'><span class='vintag'>VIN …"+esc(u.vin6)+"</span>"+
          "<span class='demound'>"+esc(u.year)+" "+esc(u.ei)+" · "+u.dis+"d"+(u.msrp?" · $"+Math.round(u.msrp).toLocaleString():"")+"</span></div>"); });
        if(p.backup>0) H.push("<div class='demoback'>"+p.backup+" more in stock as backup</div>");
        else H.push("<div class='demoback warn'>last one on lot — reorder before pulling</div>");
      } else {
        H.push("<div class='demovin order'>none in stock — order / allocate one</div>");
      }
      H.push("</div>");
    });
    H.push("</div>");
  });
  H.push("</div>");

  // 5. OVERSTOCK
  H.push(sec(5,"Overstock / Wholesale","over-target metal — order slower; wholesale only what won't sell"));
  if(rep.over.length) H.push(tbl(["Model","Trim","Ext","Int","On hand","60-day tgt","Over","Wholesale now","Inbound","DTS","Aged"],
    ["","","","","num","num","num","num need","num","num","num"],
    rep.over.map(r=>[r.model,esc(r.trim),r.ext,r.int,r.onhand,r.target,{html:"<b>"+r.over+"</b>"},{html:r.wholeNow>0?r.wholeNow:"<span class='dim'>0</span>"},{html:"<span class='dim'>"+r.inbound+"</span>"},{html:dtsCell(r.dts)},r.aged])));
  else H.push("<div class='empty'>Nothing over target.</div>");

  // 5. WHOLESALE VIN SHEET
  H.push(sec(6,"Wholesale Now — VIN sheet","aged, over-target, non-demo · print & send to other dealers"));
  if(rep.vins.length){ H.push("<div id='print-vin'><h2>WHOLESALE VIN SHEET — "+tb.today.toISOString().slice(0,10)+"</h2></div>");
    H.push(tbl(["#","Stock #","VIN (last 6)","Year","Model","Trim","Ext/Int","Days in stock"],["num","","","","","","","num"],
      rep.vins.map(r=>[r.num,esc(r.stock),esc(r.vin6),r.year,r.model,esc(r.trim),esc(r.ei),r.dis])));
    H.push("<button class='ghost noprint' style='margin-top:8px' onclick='window.print()'>🖨 Print this VIN sheet</button>"); }
  else H.push("<div class='empty'>No units past their selling window.</div>");

  // 6. DEMO
  H.push(sec(7,"Demo Dashboard","units currently pulled from sellable inventory"));
  if(rep.demo.length){
    let anticipated = s.anticipate_demo_returns;
    H.push(tbl(["Stock","Vehicle","Days in stock","Days as demo","Returns in","Swap?"],["","","num","num","num",""],
      rep.demo.map(r=>[esc(r.stock),esc(r.vehicle),r.dis,r.asDemo,
        {html:r.retIn>0?("~"+r.retIn+"d"):"<span class='swap'>now</span>"},
        {html:r.swap?"<span class='swap'>⚠ SWAP</span>":"<span style='color:var(--good)'>OK</span>"}])));
    H.push("<div class='foot'>"+(anticipated
      ? "✓ Ordering anticipates each of these coming back: the unit is added to its config's arrival projection and held as slow-moving (used, higher-mileage) stock — so you don't order a replacement for a unit that's returning, and you don't assume it resells at full pace."
      : "Demo-return anticipation is off — these units are treated as gone.")+"</div>"); }
  else H.push("<div class='empty'>No demos listed.</div>");

  // 7. PACE
  H.push(sec(8,"Pace Check","actual vs predicted 60-day pace"));
  H.push(tbl(["Model","Actual 90d","Actual 60d pace","Predicted 60d pace","Variance","Read","Coverage"],
    ["","num","num","num","num","",""],
    rep.pace.map(r=>{ let rl={AHEAD:"AHEAD of forecast",ON:"ON TARGET",BEHIND:"BEHIND forecast"}[r.read], ic={AHEAD:"▲",ON:"●",BEHIND:"▼"}[r.read];
      return [r.model,r.a90,r.a60,r.p60,(r.vr>=0?"+":"")+r.vr,{html:"<span class='read "+r.read+"'>"+ic+" "+rl+"</span>"},Math.round(r.cov*100)+"%"]; })));

  if(res.orphans.length){ let top=res.orphans.slice(0,16).map(o=>o.key+" ("+o.sales+")").join(",  ");
    H.push("<details class='exp' style='margin-top:14px'><summary>Data health — "+res.orphans.length+" configs sold but not on the order roster (ordering can't see them; many are discontinued/legacy — expected)</summary><div class='foot'>"+esc(top)+(res.orphans.length>16?" …":"")+"</div></details>"); }

  document.getElementById("results").innerHTML=H.join("");
}
