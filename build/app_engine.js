/* ===================== engine (ported 1:1 from the Python package) ===================== */
function coerceNum(v, def){ def = def===undefined?0:def;
  if(v===null||v===undefined) return def;
  if(typeof v==="number") return v;
  let s=String(v).trim().replace(/,/g,""); if(s==="") return def;
  let n=parseFloat(s); return isNaN(n)?def:n; }
function digitsOnly(v){ if(v===null||v===undefined) return ""; return String(v).replace(/[^0-9]/g,""); }
function xround(v,d){ d=d||0; if(v===null||v===undefined) return null;
  let f=Math.pow(10,d), s=v*f; let r = s>=0 ? Math.floor(s+0.5) : Math.ceil(s-0.5); return r/f; }
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

/* ---- parsing (paste = tab-separated, file = csv) ---- */
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
  return lines.map(l=> hasTab ? l.split("\t") : parseCsvLine(l)); }
function findHeader(rows, must){ let want=must.map(x=>x.toLowerCase());
  for(let i=0;i<rows.length;i++){ let cells=rows[i].map(c=>String(c==null?"":c).trim().toLowerCase());
    if(want.every(w=>cells.indexOf(w)>=0)) return i; }
  throw new Error("Couldn't find a header row with: "+must.join(", ")+". Make sure you copied the header row too."); }
function colmap(header){ let m={}; header.forEach((c,i)=>{ let k=String(c==null?"":c).trim().toLowerCase(); if(k) m[k]=i; }); return m; }
function pick(cm){ for(let i=1;i<arguments.length;i++){ let n=arguments[i].toLowerCase(); if(n in cm) return cm[n]; } return null; }
function cell(row,idx){ return (idx!==null&&idx<row.length)?row[idx]:null; }

const MONTHNAMES=["january","february","march","april","may","june","july","august","september","october","november","december"];
function parseArrivalMonth(location, eta){
  if(String(location).trim().toUpperCase()==="DLR-INV") return 0;
  if(eta===null||eta===undefined||String(eta).trim()==="") return 0;
  let s=String(eta).trim(), m=s.match(/month of\s+([a-z]+)/i);
  if(m && MONTHNAMES.indexOf(m[1].toLowerCase())>=0) return MONTHNAMES.indexOf(m[1].toLowerCase())+1;
  let s2=s.replace(/week of/i,"").trim(), d=new Date(s2);
  if(!isNaN(d.getTime()) && /\d/.test(s2)) return d.getMonth()+1;
  if(MONTHNAMES.indexOf(s.toLowerCase())>=0) return MONTHNAMES.indexOf(s.toLowerCase())+1;
  return 0; }
function loadInventory(text){
  let rows=parseTable(text), h=findHeader(rows,["Stock#","Model Code","Location"]), cm=colmap(rows[h]);
  let ci={ stock:pick(cm,"Stock#","Stock"),serial:pick(cm,"Serial","VIN","Vin","VIN#","Vin#","Serial#","Serial Number"),status:pick(cm,"Status"),my:pick(cm,"MY"),
    modelLine:pick(cm,"Model Line"),code:pick(cm,"Model Code"),desc:pick(cm,"Description"),trans:pick(cm,"Trans"),
    ext:pick(cm,"Ext"),int:pick(cm,"Int"),msrp:pick(cm,"MSRP"),inv:pick(cm,"Inv"),loc:pick(cm,"Location"),
    dis:pick(cm,"DIS"),eta:pick(cm,"ETA"),prod:pick(cm,"Production Month") };
  let units=[];
  for(let r=h+1;r<rows.length;r++){ let row=rows[r], code=cell(row,ci.code), ml=cell(row,ci.modelLine);
    if((code==null||code==="")&&(ml==null||ml==="")) continue;
    let model=modelFromCode(code)||(ml?String(ml).trim():"");
    let ext=String(cell(row,ci.ext)||"").trim(), intr=String(cell(row,ci.int)||"").trim(), loc=String(cell(row,ci.loc)||"").trim(), eta=cell(row,ci.eta);
    units.push({stock:String(cell(row,ci.stock)||"").trim(),serial:String(cell(row,ci.serial)||"").trim(),
      status:String(cell(row,ci.status)||"").trim(),my:String(cell(row,ci.my)||"").trim(),model:model,
      code:digitsOnly(code),desc:String(cell(row,ci.desc)||"").trim(),ext:ext,int:intr,
      msrp:coerceNum(cell(row,ci.msrp)),cost:coerceNum(cell(row,ci.inv)),loc:loc,dis:coerceNum(cell(row,ci.dis)),key:buildKey(model,code,ext,intr),
      arr:parseArrivalMonth(loc,eta),myear:modelYear(code),prod:String(cell(row,ci.prod)||"").trim(),
      eta:eta==null?"":String(eta).trim(),
      isDlr:loc.toUpperCase()==="DLR-INV",isInbound:loc.toUpperCase()!=="DLR-INV"}); }
  return units; }
function loadSales(text){
  let rows=parseTable(text), h=findHeader(rows,["Sales Month","VIN","MODEL CODE"]), cm=colmap(rows[h]);
  let ci={ smonth:pick(cm,"Sales Month","Sales Mo"),stock:pick(cm,"Stock#","Stock","Stock Number","Stock #","Stock No"),model:pick(cm,"Model"),vin:pick(cm,"VIN"),
    dts:pick(cm,"DAYS TO SELL","Days to Sell","DTS"),code:pick(cm,"MODEL CODE","Model Code"),
    // real exports label these EXTERIOR/INTERIOR CODE, not EXT/INT CODE
    ext:pick(cm,"EXT CODE","Ext Code","EXTERIOR CODE","Exterior Code"),int:pick(cm,"INT CODE","Int Code","INTERIOR CODE","Interior Code") };
  let seen={}, sales=[];
  for(let r=h+1;r<rows.length;r++){ let row=rows[r], raw=cell(row,ci.smonth);
    if(raw==null||raw==="") continue;
    let sm=Math.round(coerceNum(raw,-1)); if(sm<100000) continue;
    let year=Math.floor(sm/100), month=sm%100; if(month<1||month>12) continue;
    let code=cell(row,ci.code), ext=String(cell(row,ci.ext)||"").trim(), intr=String(cell(row,ci.int)||"").trim(), vin=String(cell(row,ci.vin)||"").trim();
    let dtsRaw=cell(row,ci.dts), dts=(dtsRaw==null||dtsRaw==="")?null:coerceNum(dtsRaw,null);
    let firstVin=true; if(vin){ firstVin=!seen[vin]; seen[vin]=true; }
    sales.push({sm:sm,model:modelFromCode(code),code:digitsOnly(code),ext:ext,int:intr,vin:vin,dts:dts,
      key:buildKey(modelFromCode(code),code,ext,intr),midx:year*12+month,firstVin:firstVin,
      stock:String(cell(row,ci.stock)||"").trim(),desc:String(cell(row,ci.model)||"").trim()}); }
  return sales; }

/* ---- computation ---- */
function daysInMonth(d){ return new Date(d.getFullYear(), d.getMonth()+1, 0).getDate(); }
function timeBase(sales, today){
  let midxs=sales.filter(s=>s.midx>0).map(s=>s.midx), cur=today.getFullYear()*12+(today.getMonth()+1);
  if(!midxs.length) return {latest:0,earliest:0,cur:cur,part:1,span:1,el90:3,el180:6,open:false,today:today};
  let latest=Math.max.apply(null,midxs), earliest=Math.min.apply(null,midxs), open=latest===cur;
  let part=open?Math.max(0.05,today.getDate()/daysInMonth(today)):1, span=Math.max(0.25,(latest-earliest+1)-(1-part));
  return {latest:latest,earliest:earliest,cur:cur,part:part,span:span,el90:2+part,el180:5+part,open:open,today:today}; }
function tradeMidx(v){ if(!v) return null; let m=String(v).match(/^(\d{4})[-/]?(\d{2})/); return m?parseInt(m[1],10)*12+parseInt(m[2],10):null; }
function tradeRecords(trades){ let out=[]; (trades||[]).forEach(t=>{
  let code=digitsOnly(t.code), model=t.model||modelFromCode(code), ext=String(t.ext||"").trim(), intr=String(t.int||t.interior||"").trim();
  let key=buildKey(model,code,ext,intr); if(!key||!model) return;
  let days=(t.days===null||t.days===undefined||t.days==="")?null:coerceNum(t.days,null);
  out.push({key:key,model:model,midx:tradeMidx(t.date),days:days}); }); return out; }
function computeMetrics(sales, tb, roster, s){
  let M={}, trades=s.trades, smooth=s.smooth_base!==false;
  sales.forEach(s=>{ if(!s.firstVin||!s.key||!s.model) return;
    let m=M[s.key]; if(!m){ m={key:s.key,model:s.model,code:s.code.slice(0,4),ext:s.ext,int:s.int,total:0,dtsSum:0,dtsCnt:0,r90:0,r180:0,dts:null,hist60:0,prate:0,momentum:"dormant",floor:0,base:0}; M[s.key]=m; }
    m.total++; if(s.dts!==null){ m.dtsSum+=s.dts; m.dtsCnt++; }
    if(s.midx>tb.latest-3) m.r90++; if(s.midx>tb.latest-6) m.r180++; });
  tradeRecords(trades).forEach(tr=>{ let m=M[tr.key];
    if(!m){ let p=tr.key.split("|"); m={key:tr.key,model:tr.model,code:p[1],ext:p[2],int:p[3],total:0,dtsSum:0,dtsCnt:0,r90:0,r180:0,dts:null,hist60:0,prate:0,momentum:"dormant",floor:0,base:0}; M[tr.key]=m; }
    m.total++; if(tr.days!==null){ m.dtsSum+=tr.days; m.dtsCnt++; }
    if(tr.midx&&tb.latest){ if(tr.midx>tb.latest-3) m.r90++; if(tr.midx>tb.latest-6) m.r180++; } });
  roster.forEach(c=>{ let k=c.model+"|"+c.code+"|"+c.ext+"|"+c.int;
    if(!M[k]) M[k]={key:k,model:c.model,code:c.code,ext:c.ext,int:c.int,total:0,dtsSum:0,dtsCnt:0,r90:0,r180:0,dts:null,hist60:0,prate:0,momentum:"dormant",floor:0,base:0}; });
  Object.values(M).forEach(m=>{
    m.dts=m.dtsCnt?xround(m.dtsSum/m.dtsCnt,0):null;
    m.hist60=xround(m.total/tb.span*2,2);
    m.prate=m.r90/tb.el90 + m.r180/tb.el180;
    let recent60=m.r90/tb.el90*2, dtsOk60=(m.dts!==null&&m.dts<=60);
    if(m.r90>=2 && recent60>m.hist60*1.15 && dtsOk60) m.momentum="ACCEL";
    else if(m.r90===0 && m.r180>0) m.momentum="on cadence";
    else if(m.r90>0 && recent60<m.hist60*0.6) m.momentum="cooling";
    else if(m.r90>0) m.momentum="steady"; else m.momentum="dormant";
    if(m.prate>=0.5 && m.dts!==null && m.dts<=90) m.floor = smooth?Math.max(1,m.prate):Math.max(1,xround(m.prate,0));
    else if(m.dts!==null && m.dts<=60 && m.r180>0) m.floor=1; else m.floor=0;
    let adj=m.momentum==="ACCEL"?1:(m.momentum==="cooling"?-1:0);
    let base=m.floor===0?0:Math.max(1,m.floor+adj);
    m.base = smooth?base:Math.round(base); });
  return M; }
function computeSeasonality(sales, tb, shrinkK){
  shrinkK=shrinkK||0;
  let latestCalm=tb.latest?((tb.latest-1)%12)+1:0, out={};
  MODELS.forEach(model=>{ let byMonth=new Array(12).fill(0);
    sales.forEach(s=>{ if(s.firstVin&&s.model===model&&s.midx>0) byMonth[(s.midx-1)%12]++; });
    let rates=[];
    for(let m=1;m<=12;m++){ let occ=Math.max(1,Math.floor((tb.latest-m)/12)-Math.ceil((tb.earliest-m)/12)+1);
      occ=Math.max(0.1, occ-(latestCalm===m?(1-tb.part):0)); rates.push(byMonth[m-1]/occ); }
    let avg=rates.reduce((a,b)=>a+b,0)/12;
    let raw=rates.map(r=>avg===0?1:r/avg), index=raw;
    if(shrinkK>0){ // pull sparse months toward neutral 1.0, then renormalize
      let damped=raw.map((v,m)=>1.0+(v-1.0)*(byMonth[m]/(byMonth[m]+shrinkK)));
      let da=damped.reduce((a,b)=>a+b,0)/12; index=da>0?damped.map(d=>d/da):damped; }
    out[model]={index:index,rate:rates}; });
  return out; }
function isDemo(stock, prefixes){ return prefixes.some(p=>p&&stock.indexOf(p)===0); }
function matchPrevLoaner(u, list){
  for(let i=0;i<(list||[]).length;i++){ let st=String(list[i].stock||"").trim();
    if(st && u.stock.indexOf(st)===0) return list[i]; }
  return null; }
function loanerDaysOut(e){ let t=new Date(e.taken), r=new Date(e.returned);
  if(isNaN(t.getTime())||isNaN(r.getTime())) return null; return Math.max(0,Math.round((r-t)/86400000)); }
function effDis(u){ return (u.retailDis!==undefined&&u.retailDis!==null)?u.retailDis:u.dis; }
function computePositions(inv, metrics, s, today, loanerPrefixes){
  let P={}; loanerPrefixes=loanerPrefixes||[];
  inv.forEach(u=>{ if(!u.key) return; let p=P[u.key]; if(!p){ p={onlot:0,inbound:0,arrivals:{},stalled:0,aged:[],whole:[],onlotUnits:[]}; P[u.key]=p; }
    let demo=isDemo(u.stock,s.demo_stocks), loaner=isDemo(u.stock,loanerPrefixes);
    if(u.isDlr){
      // a returned loaner is sellable again and takes precedence over a stale demo
      // row, so marking Returned always registers even if the demo row is left in place
      let entry=matchPrevLoaner(u,s.prev_loaners);
      if(!entry && (demo||loaner)) return;
      if(entry){ u.prevLoaner=true; let dout=loanerDaysOut(entry);
        if(dout!==null) u.retailDis=Math.max(0,u.dis-dout);
        else if(entry.since){ let d=new Date(entry.since); if(!isNaN(d.getTime())) u.retailDis=Math.max(0,Math.round((today-d)/86400000)); } }
      let eff=effDis(u);
      p.onlot++; p.onlotUnits.push(u);
      if(eff>=s.stall_days) p.stalled++; if(eff>s.aged_days) p.aged.push(u);
      let met=metrics[u.key], dts=(met&&met.dts!==null)?met.dts:9999;
      if(eff>Math.max(s.wholesale_min_age,dts) && !u.prevLoaner) p.whole.push(u);
    } else { p.inbound++; if(u.arr) p.arrivals[u.arr]=(p.arrivals[u.arr]||0)+1; } });
  return P; }
function projRate(m,dts,s){ let ph=m?m.prate/2:0, dr=(m&&m.r90>0&&dts&&dts>0)?30.4/dts:0; return Math.min(s.rate_cap,Math.max(ph,dr)); }
function computeDemoReturns(demoUnits, s, today){
  let R={}; if(!s.anticipate_demo_returns) return R;
  let oy = s.order_month>=today.getMonth()+1 ? today.getFullYear() : today.getFullYear()+1;
  let orderStart=new Date(oy, s.order_month-1, 1);
  demoUnits.forEach(u=>{ if(!u.key) return; let das=u.dis;
    for(let pref in s.demo_starts){ if(pref&&u.stock.indexOf(pref)===0){ let d0=new Date(s.demo_starts[pref]); if(!isNaN(d0.getTime())) das=Math.round((today-d0)/86400000); break; } }
    let retDate=new Date(today.getTime()+Math.max(0,s.swap_threshold-das)*86400000);
    let off=Math.max(0, Math.round((retDate-orderStart)/86400000/DPM));
    (R[u.key]=R[u.key]||[]).push(off); });
  return R; }
const DPM=30.44;
function productionDate(pm){ let p=String(pm).split("-"); if(p.length<2) return null;
  let y=parseInt(p[0],10),m=parseInt(p[1],10); return (isNaN(y)||isNaN(m))?null:new Date(y,m-1,15); }
function parseEtaFullDate(eta){ if(!eta) return null; let s=String(eta).replace(/week of/i,"").trim();
  if(!/\d/.test(s)) return null; let d=new Date(s); return isNaN(d.getTime())?null:d; }
function arrivalDate(u, today){
  if(u.isDlr) return new Date(today.getTime()-Math.round(u.dis)*86400000);
  let d=parseEtaFullDate(u.eta); if(d) return d;
  if(u.arr){ let year = u.arr>=today.getMonth()+1 ? today.getFullYear() : today.getFullYear()+1; return new Date(year,u.arr-1,15); }
  return null; }
function computeArrivalWindows(inv, today, s){
  // continuous, trend-weighted production->arrival lead per model, day-precise
  let fb={QX80:3,QX60:2,QX65:2}, out={};
  MODELS.forEach(model=>{ let wsum=0,lsum=0;
    inv.forEach(u=>{ if(u.model!==model) return;
      let prod=productionDate(u.prod), arr=arrivalDate(u,today); if(!prod||!arr) return;
      let lead=(arr-prod)/86400000/DPM; if(lead<0||lead>12) return;
      let monthsSince=Math.max(0,(today-prod)/86400000/DPM);
      let w=Math.pow(0.5, monthsSince/Math.max(0.5,s.lead_halflife)); wsum+=w; lsum+=w*lead; });
    out[model]= wsum===0 ? fb[model] : Math.max(s.min_cpo_window, lsum/wsum + s.order_lead_pad); });
  return out; }
function resolveWindows(inv, today, s){ let auto=computeArrivalWindows(inv,today,s), out={};
  MODELS.forEach(model=>{ let v=s.cpo_windows[model];
    out[model]= (typeof v==="string" && v.toLowerCase()==="auto") ? auto[model] : Math.max(s.min_cpo_window, parseFloat(v)); });
  return out; }
function interpSeas(idx, om, off){ let lo=Math.floor(off), fr=off-lo, a=idx[((om-1+lo)%12+12)%12], b=idx[((om-1+lo+1)%12+12)%12]; return a+(b-a)*fr; }
function projChain(model,pos,metric,seas,s,n,returns){
  returns=returns||[];
  let om=s.order_month, rate=projRate(metric,metric?metric.dts:null,s);
  function arr(off){ return pos.arrivals[((om-1+off)%12)+1]||0; }
  function demosAt(o){ let c=0; returns.forEach(r=>{ if(r===o) c++; }); return c; }
  function demosBy(o){ let c=0; returns.forEach(r=>{ if(r<=o) c++; }); return c; }
  let later=0; for(let k=1;k<=n;k++) later+=arr(k);
  let proj=[pos.onlot+Math.max(0,pos.inbound-later)+demosAt(0)];
  for(let k=1;k<=n;k++){ let held=pos.stalled+demosBy(k); let sm=seas[model].index[((om-1+(k-1))%12)];
    proj.push(Math.max(held,proj[k-1]-rate*sm)+arr(k)+demosAt(k)); }
  return proj; }
function projAt(chain, off){ let lo=Math.floor(off); if(lo>=chain.length-1) return chain[chain.length-1]; let fr=off-lo; return chain[lo]+(chain[lo+1]-chain[lo])*fr; }
function projectAtArrival(model,pos,metric,seas,s,window,returns){
  returns=returns||[];
  let chain=projChain(model,pos,metric,seas,s,Math.max(8,Math.ceil(window)+1),returns);
  if(s.mode==="MID-MONTH"){ let back=returns.filter(r=>r===0).length; let pr=pos.onlot+pos.inbound+back; return [xround(pr,1),chain]; }
  return [xround(projAt(chain,window),1),chain]; }
function baseForOrder(key, metrics){ let m=metrics[key]; return m?[m.base,true]:[1,false]; }
function momFactor(m,dts){ let r90=m?m.r90:0,r180=m?m.r180:0,accel=m?m.momentum==="ACCEL":false,base;
  if(r90>=2||accel) base=1.0; else if(r90===1) base=0.6; else if(r90===0&&r180>=2) base=0.35; else if(r90===0&&r180===1) base=0.25; else base=0.15;
  let pen=dts===null?1.0:(dts>90?0.6:(dts>60?0.85:1.0)); return Math.min(1.0,base*pen); }
function dtsBand(dts){ if(dts===null) return 0; if(dts<=20)return 4; if(dts<=40)return 3; if(dts<=70)return 2; if(dts<=100)return 1; return 0; }
function matchesDemote(e,model,ext,intr,key){ function ok(fv,act){ fv=String(fv||"").trim(); return fv===""||fv===act; }
  let has=["model","code","ext","int"].some(f=>String(e[f]||"").trim()), code=key.indexOf("|")>=0?key.split("|")[1]:"";
  return has && ok(e.model,model)&&ok(e.code,code)&&ok(e.ext,ext)&&ok(e.int,intr); }
function suppressed(code,ext,intr,s){ if(code==="8461") return true;
  return (s.suppress||[]).some(function(e){ var ec=digitsOnly(e.code).slice(0,4);
    if(!ec||ec!==code) return false;
    var ee=String(e.ext||"").trim(), ei=String(e.int||"").trim();
    return (ee===""||ee===ext) && (ei===""||ei===intr); }); }
function effectiveRoster(s){ if(!s.roster_add||!s.roster_add.length) return ROSTER;
  var seen={}; ROSTER.forEach(function(c){ seen[c.model+"|"+c.code+"|"+c.ext+"|"+c.int]=1; });
  var out=ROSTER.slice();
  s.roster_add.forEach(function(c){ if(!c.model||!c.code) return;
    var code=digitsOnly(c.code).slice(0,4); if(!code) return;   // drop the year digit
    var k=c.model+"|"+code+"|"+(c.ext||"")+"|"+(c.int||"");
    if(!seen[k]){ seen[k]=1; out.push({model:c.model,code:code,ext:c.ext||"",int:c.int||"",trim:c.trim||""}); } });
  return out; }
function buyGrade(mom,mf,need){ if(need<=0) return ""; if(mom==="ACCEL"||mf>=0.85) return "💚 STRONG"; if(mf>=0.35) return "🔵 STEADY"; return "🟡 SPECULATIVE"; }
function buildLines(s,metrics,seas,positions,agedBrakes,overrideMap,windows,demoReturns){
  let lines=[];
  effectiveRoster(s).forEach((c,i)=>{
    let model=c.model,code=c.code,ext=c.ext,intr=c.int,key=model+"|"+code+"|"+ext+"|"+intr;
    let metric=metrics[key]||null, pos=positions[key]||{onlot:0,inbound:0,arrivals:{},stalled:0,aged:[],whole:[]}, dts=metric?metric.dts:null;
    let bf=baseForOrder(key,metrics), base=bf[0], found=bf[1], mf=momFactor(metric,dts);
    let seasOrder=seas[model].index[(s.order_month-1)%12];
    let win=(s.mode==="CPO"||s.mode==="PPO")?windows[model]:0;
    let seasArr=interpSeas(seas[model].index, s.order_month, win);
    let returns=demoReturns[key]||[];
    let pj=projectAtArrival(model,pos,metric,seas,s,win,returns), proj=pj[0], chain=pj[1];
    let sup=suppressed(code,ext,intr,s), dem=s.demote.some(e=>matchesDemote(e,model,ext,intr,key));
    let r90=metric?metric.r90:0, effDem=dem&&r90<s.prove_bar, blocked=sup||effDem;
    let needFloor=base===0?0:1;
    let orderTarget=Math.max(needFloor,xround(base*(1+(seasArr-1)*mf),0)), overstockTarget=Math.max(needFloor,xround(base*seasOrder,0));
    let agedBrake=agedBrakes[key]||0, ov=overrideMap[key]||0;
    let need=blocked?0:Math.max(0,xround(orderTarget-proj-agedBrake,0))+ov;
    let rate=projRate(metric,dts,s), excess=Math.max(0,xround(pos.onlot+pos.inbound-3*rate-overstockTarget,0));
    let wholeNow=Math.min(excess,pos.whole.length), mom=metric?metric.momentum:"dormant";
    // Six-month plan carries its own prior orders forward and sells down at the
    // config's DEMAND pace (prate/2 per month), not _proj_rate's 30.4/DTS retail
    // velocity — so it tops up to the seasonal target instead of re-ordering the
    // whole target every month. (Mirror of engine.py build_lines.)
    // center-weighted 3-month smoothing of the seasonal curve so the ORDER cadence
    // isn't spike-and-coast (mirror of engine.py). NEED still uses the sharp curve.
    let smi=seas[model].index, planSeas=[]; for(let c=0;c<12;c++) planSeas.push((smi[(c+11)%12]+2*smi[c]+smi[(c+1)%12])/4);
    let planRate=metric?Math.min(s.rate_cap,metric.prate/2):0, onhand=pos.onlot, held=pos.stalled||0;
    let plan=[]; for(let k=0;k<6;k++){ let cal=(s.order_month-1+k)%12, seasK=planSeas[cal];
      let arr=pos.arrivals[cal+1]||0;
      onhand=Math.max(held,onhand-planRate*seasK)+arr;
      let tgt=Math.max(needFloor,xround(base*seasK,0));
      let ordk=blocked?0:Math.max(0,xround(tgt-onhand,0)); if(k===0&&!blocked) ordk+=ov;
      onhand+=ordk;
      plan.push({month:cal+1,tgt:tgt,arr:arr,ord:ordk}); }
    let prio=sup?-1:priority(dts,mom,need,proj,orderTarget,seasArr,effDem,i);
    lines.push({model:model,code:code,ext:ext,int:intr,trim:c.trim,key:key,dts:dts,mom:mom,onlot:pos.onlot,inbound:pos.inbound,
      proj:proj,base:base,found:found,mf:mf,orderTarget:orderTarget,overstockTarget:overstockTarget,need:need,
      suppressed:sup,demoted:dem,effDem:effDem,priority:prio,wholeNow:wholeNow,buyGrade:buyGrade(mom,mf,need),plan:plan,pos:pos,seasArr:seasArr,
      demoReturning:returns.length}); });
  return lines; }
function priority(dts,mom,need,proj,orderTgt,seasArr,effDem,idx){
  let momBand={ACCEL:4,steady:2,"on cadence":1}[mom]||0, db=dtsBand(dts), seasBand=seasArr>=1.3?2:(seasArr>=1?1:0), tb=idx/100000;
  if(need>0){ let pb=proj===0?4:(proj<orderTgt?2:0); return 1000+db+momBand+pb+seasBand-1000*effDem-tb; }
  if((mom==="ACCEL"||mom==="steady"||mom==="on cadence")&&dts!==null&&dts<=90) return db+momBand+seasBand-1000*effDem-tb;
  return -1; }
function findOrphans(sales,roster){ let rk={}; roster.forEach(c=>rk[c.model+"|"+c.code+"|"+c.ext+"|"+c.int]=1);
  let seen={}; sales.forEach(s=>{ if(s.firstVin&&s.key&&!rk[s.key]) seen[s.key]=(seen[s.key]||0)+1; });
  return Object.keys(seen).map(k=>({key:k,sales:seen[k]})).sort((a,b)=>b.sales-a.sales); }
/* ---- loaner / ICV program (ported 1:1 from pipeline_manager/loaner.py) ---- */
function loanerNum(v){ if(v===null||v===undefined||v==="") return null;
  let n=parseFloat(String(v).replace(/[$,]/g,"").trim()); return isNaN(n)?null:n; }
function loanerStockPrefixes(s){ return (s.loaner_units||[]).map(e=>String(e.stock||"").trim()).filter(x=>x); }
function repMaps(inv){ let cs={},ms={},cn={},tcs={},tms={},tcn={};
  inv.forEach(u=>{ if(!u.key) return; let code=u.key.split("|")[1], tk=u.model+"|"+code;
    if(u.cost){ cs[u.key]=(cs[u.key]||0)+u.cost; cn[u.key]=(cn[u.key]||0)+1; tcs[tk]=(tcs[tk]||0)+u.cost; tcn[tk]=(tcn[tk]||0)+1; }
    if(u.msrp){ ms[u.key]=(ms[u.key]||0)+u.msrp; tms[tk]=(tms[tk]||0)+u.msrp; } });
  let costKey={},msrpKey={},costTrim={},msrpTrim={};
  Object.keys(cs).forEach(k=>{ if(cn[k]) costKey[k]=cs[k]/cn[k]; });
  Object.keys(ms).forEach(k=>{ if(cn[k]) msrpKey[k]=ms[k]/cn[k]; });
  Object.keys(tcs).forEach(k=>{ if(tcn[k]) costTrim[k]=tcs[k]/tcn[k]; });
  Object.keys(tms).forEach(k=>{ if(tcn[k]) msrpTrim[k]=tms[k]/tcn[k]; });
  return {costKey:costKey,msrpKey:msrpKey,costTrim:costTrim,msrpTrim:msrpTrim}; }
function repCostMsrp(key,model,code,rm){ let tk=model+"|"+code;
  return [rm.costKey[key]||rm.costTrim[tk]||0, rm.msrpKey[key]||rm.msrpTrim[tk]||0]; }
function trimNewDts(metrics,model,code){ let v=[]; Object.values(metrics).forEach(m=>{ if(m.model===model&&m.code===code&&m.dts!==null&&m.total>0) v.push(m.dts); });
  return v.length?v.reduce((a,b)=>a+b,0)/v.length:null; }
function modelAvgDts(metrics,model){ let v=[]; Object.values(metrics).forEach(m=>{ if(m.model===model&&m.dts!==null&&m.total>0) v.push(m.dts); });
  return v.length?v.reduce((a,b)=>a+b,0)/v.length:null; }
/* Centralized incentive lookup (Enh 1+2): programs vary by model, model YEAR,
   and calendar MONTH. Rows live in s.incentives = [{year,model,month,rebate,icv,
   dealer_cash,velocity_bonus}] where year 0 = any year and month 0 = any month.
   Most-specific row wins; when nothing matches we fall back to the legacy flat
   per-model fields, so an empty table reproduces today's behavior exactly. */
function incentive(s,model,year,month,field){
  let rows=s.incentives||[], best=null, bestScore=-1;
  year=parseInt(year,10)||0; month=parseInt(month,10)||0;
  for(let r of rows){ if(String(r.model||"").trim().toUpperCase()!==model) continue;
    let ry=parseInt(r.year,10)||0, rm=parseInt(r.month,10)||0;
    if(ry&&year&&ry!==year) continue; if(rm&&month&&rm!==month) continue;
    let score=(ry?2:0)+(rm?1:0);               // prefer year- and month-specific rows
    if(score>bestScore){ bestScore=score; best=r; } }
  if(best&&best[field]!==undefined&&best[field]!==""&&best[field]!==null) return parseFloat(best[field])||0;
  // legacy fallback
  if(field==="rebate") return parseFloat((s.rebates||{})[model]||0)||0;
  if(field==="icv") return parseFloat((s.loaner_icv||{})[model]||0)||0;
  if(field==="velocity_bonus") return parseFloat(s.loaner_velocity_bonus||0)||0;
  return 0;
}
function modelRebate(s,model,year,month){ return incentive(s,model,year,month,"rebate"); }
function computePreowned(s,metrics,inv){
  let rm=repMaps(inv), measured={};
  function modeledPrice(tk){ let model=tk.split("|")[0]; let cn=Math.max(0,(rm.costTrim[tk]||0)-modelRebate(s,model)); return cn*s.preowned_price_pct; }
  (s.preowned_sales||[]).forEach(r=>{ let code=digitsOnly(r.code).slice(0,4), model=String(r.model||"").trim().toUpperCase();
    if(!model||!code) return; let tk=model+"|"+code, days=loanerNum(r.days), price=loanerNum(r.price)||loanerNum(r.gross);
    let a=measured[tk]||(measured[tk]={d:0,dc:0,p:0,pc:0,n:0}); a.n++;
    if(days!==null){ a.d+=days; a.dc++; } if(price!==null){ a.p+=price; a.pc++; } });
  let out={};
  Object.keys(measured).forEach(tk=>{ let a=measured[tk], model=tk.split("|")[0];
    let dts=a.dc?a.d/a.dc:(modelAvgDts(metrics,model)||45);
    let price=a.pc?a.p/a.pc:modeledPrice(tk);
    out[tk]={usedDts:Math.round(dts*10)/10,usedPrice:Math.round(price),count:a.n,modeled:false}; });
  let trims={}; inv.forEach(u=>{ if(u.key) trims[u.model+"|"+u.key.split("|")[1]]=1; });
  Object.keys(trims).forEach(tk=>{ if(out[tk]) return; let p=tk.split("|"), model=p[0], code=p[1];
    let dts=trimNewDts(metrics,model,code)||modelAvgDts(metrics,model)||45;
    out[tk]={usedDts:Math.round(dts*10)/10,usedPrice:Math.round(modeledPrice(tk)),count:0,modeled:true}; });
  return out; }
// Estimated resale from our OWN 10-year history (Loaner Intelligence), used to
// price a loaner candidate BEFORE it goes into service. Age = the months it
// will have served when it comes out (new when placed, so age ≈ service months).
// Falls back silently to null when history isn't loaded or has no comparable.
function deprResale(model,trim,ext,ageMonths){
  var D=(typeof window!=="undefined")?window.DEPR:null;
  if(!D||!D.active||!D.a||!window.LoanerIntel) return null;
  var r=window.LoanerIntel.predictResale(D.a,model,trim,ext,ageMonths);
  return (r&&r.ok)?{price:r.price,low:r.price_low,high:r.price_high,dts:r.dts,n:r.n,conf:r.confidence}:null;
}
function loanerEconomics(cost,msrp,model,usedDts,usedPrice,s,rebate,ctx){
  ctx=ctx||{}; let year=ctx.year||0, month=ctx.month||0;
  // incentive-table driven (falls back to flat fields when the table is empty)
  rebate=(rebate!==undefined&&rebate!==null)?parseFloat(rebate||0)||0:incentive(s,model,year,month,"rebate");
  let icv=incentive(s,model,year,month,"icv");
  let svc=Math.max(0,parseInt(s.loaner_service_months,10)||0);
  let already=Math.max(0,parseFloat(ctx.monthsInService||0));       // for in-service units (Enh 3)
  let remainingSvc=(ctx.retailInMonths!=null)?Math.max(0,ctx.retailInMonths):svc;
  let serviceSpan=already+remainingSvc;                             // total months in fleet at sale
  let icvTotal=icv, baseVal=(String(s.loaner_depr_base).toLowerCase()==="msrp")?msrp:cost;  // ICV is one-time
  let deprTotal=baseVal*(s.loaner_depr_pct/100)*serviceSpan;
  let usedMonths=(usedDts||0)/DPM, saleMonth=serviceSpan+usedMonths, miles=s.loaner_miles_per_month*serviceSpan;
  // velocity bonus is a monthly program: use the projected RETAIL month if given
  let retailMonth=ctx.retailMonth||month, velo=incentive(s,model,year,retailMonth,"velocity_bonus");
  let bonusOk=(saleMonth<=s.loaner_max_months)&&(miles<s.loaner_mile_cap), bonus=bonusOk?velo:0;
  let recon=parseFloat(s.loaner_recon||0)||0;
  let daysHeld=serviceSpan*DPM+(usedDts||0), holdPerDay=parseFloat(s.loaner_hold_per_day||0)||0, holding=holdPerDay*daysHeld;
  let cheapestNew=Math.max(0,cost-rebate), adj=cost-icvTotal-deprTotal-bonus;
  let gross=(usedPrice||0)-adj-recon;                              // front-end gross
  let net=gross-holding;                                            // after holding cost
  return {cost:Math.round(cost),msrp:Math.round(msrp),rebate:Math.round(rebate),cheapestNew:Math.round(cheapestNew),
    icvTotal:Math.round(icvTotal),deprTotal:Math.round(deprTotal),bonus:Math.round(bonus),bonusOk:bonusOk,velocityAvail:Math.round(velo),
    recon:Math.round(recon),holding:Math.round(holding),mileageAdj:0,net:Math.round(net),
    adjustedCost:Math.round(adj),usedPrice:Math.round(usedPrice||0),usedGross:Math.round(gross),upsideDown:gross<0,
    saleMonth:Math.round(saleMonth*10)/10,milesAtSale:Math.round(miles),serviceMonths:svc,
    monthsInService:Math.round(already*10)/10,retailInMonths:Math.round(remainingSvc*10)/10,serviceSpan:Math.round(serviceSpan*10)/10}; }
function loanerScore(econ,pstat,metric){
  let gb=Math.max(-60,Math.min(40,econ.usedGross/500));
  let vel=Math.max(0,(60-(pstat.usedDts||60))/60)*20, bb=econ.bonusOk?10:0;
  let opp=(metric&&metric.dts!==null&&metric.r90>=2&&metric.dts<=30)?-8:0;
  // quality bump: measured street data best, 10-yr history next, blind model floor none
  let mb=(pstat.src==="measured")?3:((pstat.src==="history")?2:0);
  return gb+vel+bb+opp+mb; }
function loanerCandReason(econ,pstat,line){
  let src=pstat.src==="history"?(pstat.histN+" historical comps"):(pstat.modeled?"modeled":(pstat.count+" used sales"));
  let g=Math.round(econ.usedGross);
  let bits=[(g>=0?"$"+g.toLocaleString()+" preowned profit":"-$"+Math.abs(g).toLocaleString()+" preowned LOSS"),Math.round(pstat.usedDts)+"-day used turn ("+src+")"];
  if(econ.upsideDown) bits.push("⚠ upside-down vs. street");
  bits.push(econ.bonusOk?"✓ bonus":"✗ misses bonus window");
  if(line.dts!==null&&line.dts<=30&&(line.mom==="ACCEL"||line.mom==="steady")) bits.push("fast new-seller — weigh opportunity cost");
  return bits.join(" · "); }
function allCandidates(res){ let s=res.settings, rm=repMaps(res.inv), pre=res.preowned, out=[];
  res.lines.forEach(l=>{ let model=l.model;
    let pos=res.positions[l.key], inStock=!!(pos&&pos.onlotUnits&&pos.onlotUnits.length);
    // suppressed-but-in-stock is still a valid loaner (designate existing stock)
    if(l.suppressed&&!inStock) return;
    let code=l.key.split("|")[1], tk=model+"|"+code, pstat=pre[tk]; if(!pstat) return;
    let cm=repCostMsrp(l.key,model,code,rm), cost=cm[0], msrp=cm[1]; if(cost<=0&&msrp<=0) return;
    let metric=res.metrics[l.key]||null;
    // candidate model year (freshest in-stock unit, else current) + program month → incentive context
    let candYear=0; if(pos&&pos.onlotUnits){ let ys=pos.onlotUnits.map(u=>parseInt(u.myear||u.my||0,10)).filter(y=>y); if(ys.length) candYear=Math.max.apply(null,ys); }
    if(!candYear) candYear=res.tb.today.getFullYear();
    let svc=Math.max(1,parseInt(s.loaner_service_months,10)||3);
    let ordM=parseInt(s.order_month,10)||(res.tb.today.getMonth()+1);
    let retailMonth=((ordM-1+Math.round(svc))%12+12)%12+1;
    let ctx={year:candYear,month:ordM,retailMonth:retailMonth};
    let rebate=modelRebate(s,model,candYear,ordM);
    // resale-price precedence: explicit measured sales > 10-yr history curve > 80% modeled floor
    let hist=pstat.modeled?deprResale(model,l.trim,l.ext,svc):null;
    let usedPrice, usedSrc, usedDts=pstat.usedDts;
    if(!pstat.modeled){ usedPrice=pstat.usedPrice; usedSrc="measured"; }
    else if(hist){ usedPrice=hist.price; usedSrc="history"; if(hist.dts!=null) usedDts=hist.dts; }
    else { usedPrice=Math.max(0,cost-rebate)*s.preowned_price_pct; usedSrc="modeled"; }
    let econ=loanerEconomics(cost,msrp,model,usedDts,usedPrice,s,rebate,ctx);
    // synthetic pstat carrying the chosen source, so score/reason reflect history
    let ps={usedDts:usedDts,modeled:(usedSrc==="modeled"),count:pstat.count,src:usedSrc,histN:hist?hist.n:null,histConf:hist?hist.conf:null};
    let fresh=pos?pos.onlotUnits.slice().sort((a,b)=>a.dis-b.dis):[];
    let units=fresh.slice(0,s.demo_vins_per_combo).map(u=>({stock:u.stock||"—",vin:(u.serial||u.stock),
      vin_last6:(u.serial||u.stock)?(u.serial||u.stock).slice(-6):"—",dis:Math.round(u.dis),msrp:u.msrp,cost:u.cost,
      year:u.myear||u.my||"",ext_int:u.ext+"/"+u.int}));
    let score=loanerScore(econ,ps,metric)+(units.length?4:0);
    out.push({model:model,trim:l.trim,ext:l.ext,int:l.int,key:l.key,year:candYear,usedDts:usedDts,usedPrice:econ.usedPrice,
      modeled:ps.modeled,usedSrc:usedSrc,histResale:hist,score:Math.round(score*10)/10,netValue:econ.usedGross,econ:econ,newDts:l.dts,
      onlot:l.onlot,inStock:units.length>0,units:units,reason:loanerCandReason(econ,ps,l)}); });
  out.sort((a,b)=>b.score-a.score); return out; }
function loanerCandidates(res){ let s=res.settings, n=(s.loaner_picks_per_model!==undefined?s.loaner_picks_per_model:6), out={}; MODELS.forEach(m=>out[m]=[]);
  allCandidates(res).forEach(p=>out[p.model].push(p));
  MODELS.forEach(m=>{ out[m].sort((a,b)=>((a.inStock?0:1)-(b.inStock?0:1))||(b.score-a.score)); out[m]=out[m].slice(0,n); }); return out; }
function loanerProgramActive(s){
  // Fleet reservation must NOT contaminate the core order until the program is
  // actually set up (else every model's build sequence is seeded with loss picks).
  let icv=Object.values(s.loaner_icv||{}).some(v=>parseFloat(v||0)>0);
  let reb=Object.values(s.rebates||{}).some(v=>parseFloat(v||0)>0);
  return !!(icv||reb||(s.loaner_units&&s.loaner_units.length)||(s.preowned_sales&&s.preowned_sales.length)); }
function loanerOrderPlan(res){ let s=res.settings, svc=Math.max(1,parseInt(s.loaner_service_months,10)||1);
  let intake=loanerProgramActive(s)?Math.max(0,Math.round(s.loaner_fleet_target/svc)):0, ranked=allCandidates(res);
  let fleetUnits=[], perModel={}; MODELS.forEach(m=>perModel[m]=0);
  if(intake&&ranked.length){ let i=0, guard=0, counts={};
    while(fleetUnits.length<intake && guard<intake*ranked.length+ranked.length){
      let c=ranked[i%ranked.length]; counts[c.key]=(counts[c.key]||0)+1;
      fleetUnits.push({model:c.model,key:c.key,trim:c.trim,ext:c.ext,int:c.int,econ:c.econ,netValue:c.netValue,n:counts[c.key]});
      perModel[c.model]++; i++; guard++; } }
  return {intake:intake,serviceMonths:svc,fleetUnits:fleetUnits,perModel:perModel}; }
// RETAIL-only build sequence (mirror of reports.build_sequence). Loaner-fleet
// units are NEVER injected here — they live in the Loaner section. If the loaner
// program is active, fleet slots are reported as reserved out of allocation.
function buildSequence(res){ let s=res.settings, plan=loanerOrderPlan(res), out={};
  MODELS.forEach(model=>{ let alloc=s.allocations[model]||0, reserved=plan.perModel[model]||0, effAlloc=Math.max(0,alloc-reserved);
    // rank combos by priority; each shown ONCE with its full quantity
    let combos=res.lines.filter(l=>l.model===model&&!l.suppressed&&l.need>0&&l.priority>-1).sort((a,b)=>b.priority-a.priority);
    let groups=[], filled=0, totalUnits=0;
    combos.forEach(l=>{ totalUnits+=l.need;
      let takeBuild=Math.max(0,Math.min(l.need, effAlloc-filled)), takeAlt=l.need-takeBuild;
      if(takeBuild>0){ groups.push({key:l.key,trim:l.trim,ext:l.ext,int:l.int,stream:"retail",tier:"build",qty:takeBuild,dts:l.dts,momentum:l.mom}); filled+=takeBuild; }
      if(takeAlt>0) groups.push({key:l.key,trim:l.trim,ext:l.ext,int:l.int,stream:"retail",tier:"alt",qty:takeAlt,dts:l.dts,momentum:l.mom}); });
    let buildTotal=groups.filter(g=>g.tier==="build").reduce((a,g)=>a+g.qty,0);
    out[model]={allocation:alloc,fleet_reserved:reserved,eff_alloc:effAlloc,retail_build:buildTotal,groups:groups,total_units:totalUnits}; });
  return {intake:plan.intake,serviceMonths:plan.serviceMonths,fleetUnits:plan.fleetUnits,perModel:out}; }
function loanerMatchUnit(stock,inv){ for(let i=0;i<inv.length;i++){ if(stock&&inv[i].stock.indexOf(stock)===0) return inv[i]; } return null; }
// Timing optimizer (Enh 3): given a unit already N months in service, project
// the net at several retail windows (now / +30 / +60 / at mandatory retirement)
// combining manufacturer clock, depreciation (age curve), used-car seasonality,
// velocity eligibility and holding cost — and recommend the best window.
function loanerTiming(res, u, monthsInService, model, year){
  let s=res.settings, D=(typeof window!=="undefined")?window.DEPR:null;
  if(!D||!D.active||!D.a||!u||!(u.cost>0)) return null;
  let today=res.tb.today, maxMo=parseFloat(s.loaner_max_months)||7;
  let trim=u.trim||"", ext=u.ext||"", cost=u.cost, msrp=u.msrp||u.cost;
  let deltas=[0,1,2, Math.max(0, Math.round(maxMo-monthsInService))];
  let seen={}, opts=[];
  deltas.forEach(dm=>{ if(monthsInService+dm>maxMo+0.5) return; if(seen[dm]) return; seen[dm]=1;
    let retailAge=Math.max(0,Math.round(monthsInService+dm));
    let retailMonthIdx=((today.getMonth()+dm)%12+12)%12+1;
    let pr=D.a.predictor(model,trim||null,null,ext||null,retailMonthIdx,retailAge);   // resale w/ season + age
    if(!pr||!pr.ok) return;
    let ctx={year:year||0,month:today.getMonth()+1,retailMonth:retailMonthIdx,monthsInService:monthsInService,retailInMonths:dm};
    let econ=loanerEconomics(cost,msrp,model,pr.dts,pr.price,s,undefined,ctx);
    opts.push({delta:dm,label:dm===0?"Retail now":(dm===1?"Wait ~30 days":(dm===2?"Wait ~60 days":"Hold to retirement")),
      retailMonth:MONTHS[retailMonthIdx-1],age:retailAge,resale:pr.price,net:econ.net,gross:econ.usedGross,
      bonusOk:econ.bonusOk,conf:pr.confidence}); });
  if(!opts.length) return null;
  let best=opts.reduce((a,b)=>b.net>a.net?b:a,opts[0]), now=opts[0];
  let lift=best.net-now.net;
  best.why = best.delta===0 ? "best today — waiting loses value faster than demand improves"
    : "+$"+Math.round(lift).toLocaleString()+" vs. retailing now"+(best.bonusOk?"":" (past bonus window)");
  return {options:opts, best:best, monthsInService:Math.round(monthsInService*10)/10,
    remaining:Math.round((maxMo-monthsInService)*10)/10};
}
// Recommended acquisitions (Add 6): configs our own history says perform well
// as loaners but which we're thin on today. Pure data — no hardcoded picks.
function acquisitionRecs(res){
  if(!res.deprActive||!res.depr||!res.depr.trim) return [];
  let firstWord=t=>String(t||"").trim().toUpperCase().split(/\s+/)[0];
  // current coverage by model + trim head
  let cov={}; res.lines.forEach(l=>{ let k=l.model+"|"+firstWord(l.trim); cov[k]=(cov[k]||0)+(l.onlot||0); });
  let recs=[];
  Object.keys(res.depr.trim).forEach(model=>{ res.depr.trim[model].forEach(t=>{
    if(t.n<8||t.gross==null) return;                      // need real history + a gross read
    let head=firstWord(t.trim), onlot=cov[model+"|"+head]||0;
    let turn=t.dts||45, speed=Math.max(0,(60-turn)/60);   // 0..1 fast
    let score=t.gross*(0.6+0.4*speed)-onlot*250;          // reward gross+speed, penalize we already own it
    recs.push({model:model,trim:t.trim,gross:t.gross,dts:turn,n:t.n,price:t.price,in_stock:onlot,score:Math.round(score)}); }); });
  recs.sort((a,b)=>b.score-a.score);
  // one per model+trim-head, keep the strongest, cap at 5
  let seen={}, out=[];
  for(let r of recs){ let k=r.model+"|"+firstWord(r.trim); if(seen[k]) continue; seen[k]=1;
    let year=res.tb.today.getFullYear()+(res.tb.today.getMonth()>=8?1:0);
    // freshest model year we actually stock for this model, if any
    res.inv.forEach(u=>{ if(u.model===r.model){ let y=parseInt(u.myear||u.my||0,10); if(y&&y>year-2) year=Math.max(year,y); } });
    r.year=year;
    r.why=(r.in_stock?("thin in stock ("+r.in_stock+") — "):"not in stock — ")+"history: $"+Math.round(r.gross).toLocaleString()+" median gross on "+r.n+" sales, "+Math.round(r.dts)+"-day turn";
    out.push(r); if(out.length>=5) break; }
  return out;
}
function loanerFleet(res){ let s=res.settings, today=res.tb.today, rows=[], releasing=0;
  (s.loaner_units||[]).forEach(e=>{ let stock=String(e.stock||"").trim(); if(!stock) return;
    let start=new Date(e.start), hasStart=!isNaN(start.getTime());
    let months=hasStart?((today-start)/86400000/DPM):0, miles=loanerNum(e.miles);
    if(miles===null) miles=s.loaner_miles_per_month*months;
    let u=loanerMatchUnit(stock,res.inv), model=u?u.model:String(e.model||"").trim().toUpperCase();
    let uyear=u?parseInt(u.myear||u.my||0,10):0;
    let icv=incentive(s,model,uyear,today.getMonth()+1,"icv");
    let releaseAt=hasStart?new Date(start.getTime()+Math.round(s.loaner_max_months*DPM)*86400000):null;
    let eligible=months>=s.loaner_min_months, nearCap=miles>=s.loaner_mile_cap*0.9, nearTime=months>=s.loaner_max_months-1, status;
    if(!eligible) status="🅗 HOLD · "+Math.max(0,Math.ceil((s.loaner_min_months-months)*DPM))+"d to ICV";
    else if(nearCap||nearTime){ status="🔴 RELEASE NOW"; releasing++; }
    else status="🟢 READY";
    let timing=(u&&hasStart)?loanerTiming(res,u,months,model,uyear):null;
    rows.push({stock:stock,model:model,vehicle:u?u.desc:"",ext_int:u?(u.ext+"/"+u.int):"",
      months:Math.round(months*10)/10,miles:Math.round(miles),icv_secured:eligible?Math.round(icv):0,icv:Math.round(icv),
      eligible:eligible,status:status,release_by:releaseAt?releaseAt.toISOString().slice(0,10):"",note:String(e.note||"").trim(),
      timing:timing}); });
  rows.sort((a,b)=>b.months-a.months);
  let inService=rows.length, afterRelease=inService-releasing, toAdd=Math.max(0,s.loaner_fleet_target-afterRelease);
  return {target:s.loaner_fleet_target,in_service:inService,releasing_now:releasing,to_add:toAdd,rows:rows}; }

function runEngine(inv,sales,s,today){
  let tb=timeBase(sales,today), metrics=computeMetrics(sales,tb,effectiveRoster(s),s), seas=computeSeasonality(sales,tb,(s.seasonality_shrink_k!==undefined?s.seasonality_shrink_k:6));
  let loanerPrefixes=loanerStockPrefixes(s), positions=computePositions(inv,metrics,s,today,loanerPrefixes);
  let agedBrakes={}; (s.aged_memory||[]).forEach(e=>{ if(e.active===undefined||e.active===1||e.active===true||e.active==="1") agedBrakes[e.key]=(agedBrakes[e.key]||0)+1; });
  let overrideMap={}; s.overrides.forEach(e=>{ overrideMap[e.key]=(overrideMap[e.key]||0)+parseInt(e.qty||0,10); });
  let windows=resolveWindows(inv,today,s);
  let demoUnits=inv.filter(u=>u.isDlr&&isDemo(u.stock,s.demo_stocks)&&!matchPrevLoaner(u,s.prev_loaners));
  let demoReturns=computeDemoReturns(demoUnits,s,today);
  let lines=buildLines(s,metrics,seas,positions,agedBrakes,overrideMap,windows,demoReturns);
  let orphans=findOrphans(sales,effectiveRoster(s));
  let res={settings:s,tb:tb,metrics:metrics,seas:seas,positions:positions,lines:lines,demoUnits:demoUnits,sales:sales,orphans:orphans,inv:inv,invCount:inv.length,salesCount:sales.length,windows:windows};
  res.depr=(typeof window!=="undefined"&&window.DEPR)?window.DEPR.a:null;
  res.deprActive=!!(typeof window!=="undefined"&&window.DEPR&&window.DEPR.active);
  res.preowned=computePreowned(s,metrics,inv);
  res.loanerAll=allCandidates(res);           // flat, score-ranked (for the exec report)
  res.loanerBoard=loanerCandidates(res);
  res.acquisitionRecs=acquisitionRecs(res);
  res.loanerFleetPlan=loanerFleet(res);
  res.buildSeq=buildSequence(res);
  return res; }
