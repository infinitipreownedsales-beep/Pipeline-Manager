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
  let ci={ stock:pick(cm,"Stock#","Stock"),serial:pick(cm,"Serial"),status:pick(cm,"Status"),my:pick(cm,"MY"),
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
      msrp:coerceNum(cell(row,ci.msrp)),loc:loc,dis:coerceNum(cell(row,ci.dis)),key:buildKey(model,code,ext,intr),
      arr:parseArrivalMonth(loc,eta),myear:modelYear(code),prod:String(cell(row,ci.prod)||"").trim(),
      eta:eta==null?"":String(eta).trim(),
      isDlr:loc.toUpperCase()==="DLR-INV",isInbound:loc.toUpperCase()!=="DLR-INV"}); }
  return units; }
function loadSales(text){
  let rows=parseTable(text), h=findHeader(rows,["Sales Month","VIN","MODEL CODE"]), cm=colmap(rows[h]);
  let ci={ smonth:pick(cm,"Sales Month"),stock:pick(cm,"Stock#","Stock"),model:pick(cm,"Model"),vin:pick(cm,"VIN"),
    dts:pick(cm,"DAYS TO SELL","Days to Sell"),code:pick(cm,"MODEL CODE","Model Code"),ext:pick(cm,"EXT CODE","Ext Code"),int:pick(cm,"INT CODE","Int Code") };
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
function computeMetrics(sales, tb, roster){
  let M={};
  sales.forEach(s=>{ if(!s.firstVin||!s.key||!s.model) return;
    let m=M[s.key]; if(!m){ m={key:s.key,model:s.model,code:s.code.slice(0,4),ext:s.ext,int:s.int,total:0,dtsSum:0,dtsCnt:0,r90:0,r180:0,dts:null,hist60:0,prate:0,momentum:"dormant",floor:0,base:0}; M[s.key]=m; }
    m.total++; if(s.dts!==null){ m.dtsSum+=s.dts; m.dtsCnt++; }
    if(s.midx>tb.latest-3) m.r90++; if(s.midx>tb.latest-6) m.r180++; });
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
    if(m.prate>=0.5 && m.dts!==null && m.dts<=90) m.floor=Math.max(1,xround(m.prate,0));
    else if(m.dts!==null && m.dts<=60 && m.r180>0) m.floor=1; else m.floor=0;
    let adj=m.momentum==="ACCEL"?1:(m.momentum==="cooling"?-1:0);
    m.base=m.floor===0?0:Math.max(1,m.floor+adj); });
  return M; }
function computeSeasonality(sales, tb){
  let latestCalm=tb.latest?((tb.latest-1)%12)+1:0, out={};
  MODELS.forEach(model=>{ let byMonth=new Array(12).fill(0);
    sales.forEach(s=>{ if(s.firstVin&&s.model===model&&s.midx>0) byMonth[(s.midx-1)%12]++; });
    let rates=[];
    for(let m=1;m<=12;m++){ let occ=Math.max(1,Math.floor((tb.latest-m)/12)-Math.ceil((tb.earliest-m)/12)+1);
      occ=Math.max(0.1, occ-(latestCalm===m?(1-tb.part):0)); rates.push(byMonth[m-1]/occ); }
    let avg=rates.reduce((a,b)=>a+b,0)/12; out[model]={index:rates.map(r=>avg===0?1:r/avg),rate:rates}; });
  return out; }
function isDemo(stock, prefixes){ return prefixes.some(p=>p&&stock.indexOf(p)===0); }
function computePositions(inv, metrics, s){
  let P={};
  inv.forEach(u=>{ if(!u.key) return; let p=P[u.key]; if(!p){ p={onlot:0,inbound:0,arrivals:{},stalled:0,aged:[],whole:[]}; P[u.key]=p; }
    let demo=isDemo(u.stock,s.demo_stocks);
    if(u.isDlr){ if(demo) return; p.onlot++;
      if(u.dis>=s.stall_days) p.stalled++; if(u.dis>s.aged_days) p.aged.push(u);
      let met=metrics[u.key], dts=(met&&met.dts!==null)?met.dts:9999;
      if(u.dis>Math.max(s.wholesale_min_age,dts)) p.whole.push(u);
    } else { p.inbound++; if(u.arr) p.arrivals[u.arr]=(p.arrivals[u.arr]||0)+1; } });
  return P; }
function projRate(m,dts,s){ let ph=m?m.prate/2:0, dr=(m&&m.r90>0&&dts&&dts>0)?30.4/dts:0; return Math.min(s.rate_cap,Math.max(ph,dr)); }
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
function projChain(model,pos,metric,seas,s,n){
  let om=s.order_month, rate=projRate(metric,metric?metric.dts:null,s);
  function arr(off){ return pos.arrivals[((om-1+off)%12)+1]||0; }
  let later=0; for(let k=1;k<=n;k++) later+=arr(k);
  let proj=[pos.onlot+Math.max(0,pos.inbound-later)];
  for(let k=1;k<=n;k++){ let sm=seas[model].index[((om-1+(k-1))%12)]; proj.push(Math.max(pos.stalled,proj[k-1]-rate*sm)+arr(k)); }
  return proj; }
function projAt(chain, off){ let lo=Math.floor(off); if(lo>=chain.length-1) return chain[chain.length-1]; let fr=off-lo; return chain[lo]+(chain[lo+1]-chain[lo])*fr; }
function projectAtArrival(model,pos,metric,seas,s,window){
  let chain=projChain(model,pos,metric,seas,s,Math.max(8,Math.ceil(window)+1));
  if(s.mode!=="CPO"){ let pr=pos.onlot+pos.inbound; return [xround(pr,1),chain]; }
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
  return s.suppress.some(e=> String(e.code||"").trim().slice(0,4)===code && String(e.ext||"").trim()===ext && String(e.int||"").trim()===intr); }
function buyGrade(mom,mf,need){ if(need<=0) return ""; if(mom==="ACCEL"||mf>=0.85) return "💚 STRONG"; if(mf>=0.35) return "🔵 STEADY"; return "🟡 SPECULATIVE"; }
function buildLines(s,metrics,seas,positions,agedBrakes,overrideMap,windows){
  let lines=[];
  ROSTER.forEach((c,i)=>{
    let model=c.model,code=c.code,ext=c.ext,intr=c.int,key=model+"|"+code+"|"+ext+"|"+intr;
    let metric=metrics[key]||null, pos=positions[key]||{onlot:0,inbound:0,arrivals:{},stalled:0,aged:[],whole:[]}, dts=metric?metric.dts:null;
    let bf=baseForOrder(key,metrics), base=bf[0], found=bf[1], mf=momFactor(metric,dts);
    let seasOrder=seas[model].index[(s.order_month-1)%12];
    let win=s.mode==="CPO"?windows[model]:0;
    let seasArr=interpSeas(seas[model].index, s.order_month, win);
    let pj=projectAtArrival(model,pos,metric,seas,s,win), proj=pj[0], chain=pj[1];
    let sup=suppressed(code,ext,intr,s), dem=s.demote.some(e=>matchesDemote(e,model,ext,intr,key));
    let r90=metric?metric.r90:0, effDem=dem&&r90<s.prove_bar, blocked=sup||effDem;
    let needFloor=base===0?0:1;
    let orderTarget=Math.max(needFloor,xround(base*(1+(seasArr-1)*mf),0)), overstockTarget=Math.max(needFloor,xround(base*seasOrder,0));
    let agedBrake=agedBrakes[key]||0, ov=overrideMap[key]||0;
    let need=blocked?0:Math.max(0,xround(orderTarget-proj-agedBrake,0))+ov;
    let rate=projRate(metric,dts,s), excess=Math.max(0,xround(pos.onlot+pos.inbound-3*rate-overstockTarget,0));
    let wholeNow=sup?0:Math.min(excess,pos.whole.length), mom=metric?metric.momentum:"dormant";
    let plan=[]; for(let k=0;k<6;k++){ let cal=(s.order_month-1+k)%12;
      let tgt=Math.max(needFloor,xround(base*seas[model].index[cal],0)), arr=pos.arrivals[cal+1]||0;
      let ordk=blocked?0:Math.max(0,xround(tgt-chain[k],0)); if(k===0&&!blocked) ordk+=ov;
      plan.push({month:cal+1,tgt:tgt,arr:arr,ord:ordk}); }
    let prio=priority(dts,mom,need,proj,orderTarget,seasArr,effDem,i);
    lines.push({model:model,code:code,ext:ext,int:intr,trim:c.trim,key:key,dts:dts,mom:mom,onlot:pos.onlot,inbound:pos.inbound,
      proj:proj,base:base,found:found,mf:mf,orderTarget:orderTarget,overstockTarget:overstockTarget,need:need,
      suppressed:sup,demoted:dem,effDem:effDem,priority:prio,wholeNow:wholeNow,buyGrade:buyGrade(mom,mf,need),plan:plan,pos:pos,seasArr:seasArr}); });
  return lines; }
function priority(dts,mom,need,proj,orderTgt,seasArr,effDem,idx){
  let momBand={ACCEL:4,steady:2,"on cadence":1}[mom]||0, db=dtsBand(dts), seasBand=seasArr>=1.3?2:(seasArr>=1?1:0), tb=idx/100000;
  if(need>0){ let pb=proj===0?4:(proj<orderTgt?2:0); return 1000+db+momBand+pb+seasBand-1000*effDem-tb; }
  if((mom==="ACCEL"||mom==="steady"||mom==="on cadence")&&dts!==null&&dts<=90) return db+momBand+seasBand-1000*effDem-tb;
  return -1; }
function findOrphans(sales,roster){ let rk={}; roster.forEach(c=>rk[c.model+"|"+c.code+"|"+c.ext+"|"+c.int]=1);
  let seen={}; sales.forEach(s=>{ if(s.firstVin&&s.key&&!rk[s.key]) seen[s.key]=(seen[s.key]||0)+1; });
  return Object.keys(seen).map(k=>({key:k,sales:seen[k]})).sort((a,b)=>b.sales-a.sales); }
function runEngine(inv,sales,s,today){
  let tb=timeBase(sales,today), metrics=computeMetrics(sales,tb,ROSTER), seas=computeSeasonality(sales,tb), positions=computePositions(inv,metrics,s);
  let agedBrakes={}; (s.aged_memory||[]).forEach(e=>{ if(e.active===undefined||e.active===1||e.active===true||e.active==="1") agedBrakes[e.key]=(agedBrakes[e.key]||0)+1; });
  let overrideMap={}; s.overrides.forEach(e=>{ overrideMap[e.key]=(overrideMap[e.key]||0)+parseInt(e.qty||0,10); });
  let windows=resolveWindows(inv,today,s);
  let lines=buildLines(s,metrics,seas,positions,agedBrakes,overrideMap,windows);
  let demoUnits=inv.filter(u=>u.isDlr&&isDemo(u.stock,s.demo_stocks)), orphans=findOrphans(sales,ROSTER);
  return {settings:s,tb:tb,metrics:metrics,seas:seas,positions:positions,lines:lines,demoUnits:demoUnits,sales:sales,orphans:orphans,invCount:inv.length,salesCount:sales.length,windows:windows}; }
