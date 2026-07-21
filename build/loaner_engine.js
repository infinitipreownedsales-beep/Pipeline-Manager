/* Loaner Intelligence engine — 1:1 mirror of pipeline_manager/loaner_intel.py.
   Pure computation; the dashboard renders whatever analyze() returns. */
"use strict";
const HALF_LIFE_DEFAULT = 24;
const MY_ANCHOR = 9;
const MIN_CELL_N = 5;
const AGE_BUCKETS = [0,6,12,18,24,36,48,60,84];
const LOANER_PREFIXES = ["LP","LNP"];
const INF_ORDER = ["QX80","QX60","QX55","QX50","QX30","Q50","Q60","Q70","Q70L","QX70","G37","JX"];
const COLOR_ABBR = {WHT:"WHITE",BLK:"BLACK",GRY:"GRAY",GREY:"GRAY",SLV:"SILVER",SIL:"SILVER",
  BLU:"BLUE",GRN:"GREEN",GLD:"GOLD",BRN:"BROWN",CHR:"CHARCOAL",CHAR:"CHARCOAL",GRPH:"GRAPHITE",OBS:"OBSIDIAN"};

function money(x){ if(x==null) return null; let s=String(x).replace(/[,$]/g,"").trim();
  if(s===""||s==="-"||s==="--") return null; let v=parseFloat(s); return isNaN(v)?null:v; }
function toInt(x){ let v=parseInt(String(x).trim(),10); return isNaN(v)?null:v; }
function norm(s){ return String(s==null?"":s).trim().toUpperCase(); }
function canonColor(c){ let n=norm(c); return COLOR_ABBR[n]||n; }
function stripSuffix(stock){ let s=norm(stock), i=s.length;
  while(i>0 && /[A-Z]/.test(s[i-1])) i--;
  let head=s.slice(0,i); return /[0-9]/.test(head)?head:s; }
function isLoanerStock(stock){ let s=norm(stock), base=stripSuffix(s);
  return LOANER_PREFIXES.some(p=>s.startsWith(p)) || LOANER_PREFIXES.some(p=>base.startsWith(p)); }
function makeFamily(mk){ let m=norm(mk);
  for(let t of [" SAV"," SAC"," TRUCK"," VAN"]) if(m.endsWith(t)) m=m.slice(0,-t.length);
  return m.trim(); }
function modelNorm(model){ let m=norm(model); return m?m.split(/\s+/)[0]:m; }

/* CSV parse (handles quoted commas) */
function parseCSV(text){
  let rows=[], i=0, field="", row=[], inq=false, t=text.replace(/\r\n/g,"\n").replace(/\r/g,"\n");
  while(i<t.length){ let c=t[i];
    if(inq){ if(c==='"'){ if(t[i+1]==='"'){field+='"';i++;} else inq=false; } else field+=c; }
    else { if(c==='"') inq=true; else if(c===","){ row.push(field); field=""; }
      else if(c==="\n"){ row.push(field); rows.push(row); row=[]; field=""; }
      else field+=c; }
    i++; }
  if(field.length||row.length){ row.push(field); rows.push(row); }
  if(!rows.length) return [];
  let hdr=rows[0].map(h=>h.trim().replace(/^﻿/,""));
  return rows.slice(1).filter(r=>r.length>1).map(r=>{ let o={}; hdr.forEach((h,k)=>o[h]=r[k]); return o; });
}

function parseRows(rows){
  let out=[], loanerVins=new Set(), staged=[];
  rows.forEach(r=>{
    let raw=String(r["Sales Date"]||"").trim();
    if(raw.length<8 || !/^\d{8}/.test(raw)) return;
    let y=+raw.slice(0,4), mo=+raw.slice(4,6), d=+raw.slice(6,8);
    if(mo<1||mo>12) return;
    let date=new Date(y,mo-1,Math.max(1,d));
    let vin=norm(r["VIN"]), stock=norm(r["Stock Number"]), my=toInt(r["Year"]);
    let make=makeFamily(r["Make"]), model=modelNorm(r["Model"]);
    let age=my!=null?Math.max(0,(y-my)*12+(mo-MY_ANCHOR)):null;
    let loanerStock=isLoanerStock(stock);
    if(loanerStock&&vin) loanerVins.add(vin);
    staged.push({r,date,y,mo,vin,stock,my,make,model,age,loanerStock});
  });
  staged.forEach(x=>{
    let isLoaner=x.loanerStock||(x.vin&&loanerVins.has(x.vin));
    out.push({date:x.date,year:x.y,month:x.mo,quarter:Math.floor((x.mo-1)/3)+1,
      stock:x.stock,vin:x.vin,model_year:x.my,make:x.make,model:x.model,
      trim:norm(x.r["Trim"]),ext:canonColor(x.r["Exterior Color"]),
      cost:money(x.r["Vehicle Cost"]),price:money(x.r["Vehicle Price"]),
      gross:money(x.r["Gross Profit"]),dts:toInt(x.r["Days to Sell"]),
      age_months:x.age,is_infiniti:x.make.startsWith("INFINITI"),is_loaner:!!isLoaner,weight:1});
  });
  return out;
}
function loadCSV(text){ return parseRows(parseCSV(text)); }

function assignWeights(sales,hl,asOf){
  if(!sales.length) return sales;
  asOf=asOf||new Date(Math.max.apply(null,sales.map(s=>s.date.getTime())));
  hl=Math.max(0.5,hl);
  sales.forEach(s=>{ let ma=Math.max(0,(asOf.getFullYear()-s.date.getFullYear())*12+(asOf.getMonth()-s.date.getMonth()));
    s.weight=Math.pow(0.5,ma/hl); });
  return sales;
}
function wmean(pairs){ let n=0,d=0; pairs.forEach(([v,w])=>{ if(v==null)return; n+=v*w; d+=w; }); return d?n/d:null; }
function wsorted(pairs){ return pairs.filter(([v,w])=>v!=null&&w>0).sort((a,b)=>a[0]-b[0]); }
function wquant(pairs,p){ let v=wsorted(pairs); if(!v.length) return null;
  let tot=v.reduce((a,x)=>a+x[1],0), th=tot*p, run=0;
  for(let x of v){ run+=x[1]; if(run>=th) return x[0]; } return v[v.length-1][0]; }
function wmedian(pairs){ return wquant(pairs,0.5); }
function rnd(x,nd){ if(x==null) return null; return nd?Math.round(x*Math.pow(10,nd))/Math.pow(10,nd):Math.round(x); }
function cell(rows,field){ let pairs=rows.filter(r=>r[field]!=null).map(r=>[r[field],r.weight]);
  return {median:rnd(wmedian(pairs)),mean:rnd(wmean(pairs)),p25:rnd(wquant(pairs,0.25)),
    p75:rnd(wquant(pairs,0.75)),n:pairs.length,wn:Math.round(pairs.reduce((a,x)=>a+x[1],0)*100)/100}; }
function confidence(n){ if(n<=0) return 0; return Math.round(Math.min(1,Math.log10(n+1)/Math.log10(MIN_CELL_N*6+1))*1000)/1000; }

function ageBucket(age){ if(age==null) return null; let b=AGE_BUCKETS[0];
  for(let e of AGE_BUCKETS){ if(age>=e) b=e; else break; } return b; }
function bucketLabel(e){ if(e===0) return "0–6mo"; if(e<24) return e+"–"+(e+6)+"mo";
  let yr=Math.floor(e/12); return e>=60?yr+"yr+":yr+"yr"; }

function groupBy(rows,fn){ let g={}; rows.forEach(r=>{ let k=fn(r); (g[k]=g[k]||[]).push(r); }); return g; }

function ageCurves(inf,byTrim){
  let groups={};
  inf.forEach(s=>{ if(s.price==null||s.age_months==null) return;
    let key=byTrim?(s.model+"|"+s.trim):s.model, b=ageBucket(s.age_months);
    (groups[key]=groups[key]||{}); (groups[key][b]=groups[key][b]||[]).push(s); });
  let out={};
  for(let key in groups){ let buckets=groups[key], points=[];
    AGE_BUCKETS.forEach(e=>{ let rows=buckets[e]; if(!rows) return;
      let pc=cell(rows,"price");
      points.push({age:e,label:bucketLabel(e),price:pc.median,gross:cell(rows,"gross").median,
        dts:cell(rows,"dts").median,n:pc.n}); });
    if(!points.length) continue;
    let base=null; for(let p of points){ if(p.price){ base=p.price; break; } }
    let run=null;
    points.forEach(p=>{ if(p.price!=null) run=run==null?p.price:Math.min(run,p.price);
      p.price_smooth=run;
      p.retention=(base&&p.price)?Math.round(p.price/base*1000)/1000:null;
      p.retention_smooth=(base&&run)?Math.round(run/base*1000)/1000:null; });
    let parts=key.split("|"), name=parts.length===1?parts[0]:parts[0]+" "+parts[1];
    out[key]={model:parts[0],label:name,points:points,base_price:base}; }
  return out;
}

function colorAnalytics(inf,minN){
  minN=minN==null?MIN_CELL_N:minN;
  let byModel=groupBy(inf.filter(s=>s.ext),s=>s.model), out={};
  for(let model in byModel){ let rows=byModel[model];
    let bp=wmean(rows.map(r=>[r.price,r.weight])), bg=wmean(rows.map(r=>[r.gross,r.weight])), bd=wmean(rows.map(r=>[r.dts,r.weight]));
    let colors=groupBy(rows,r=>r.ext), items=[];
    for(let color in colors){ let cr=colors[color], pc=cell(cr,"price"),gc=cell(cr,"gross"),dc=cell(cr,"dts");
      if(pc.n<minN) continue;
      items.push({color:color,n:pc.n,price:pc.median,gross:gc.median,dts:dc.median,
        price_prem:(pc.mean&&bp)?rnd(pc.mean-bp):null,gross_prem:(gc.mean&&bg)?rnd(gc.mean-bg):null,
        dts_delta:(dc.mean&&bd)?rnd(dc.mean-bd):null,conf:confidence(pc.n)}); }
    items.sort((a,b)=>(a.gross_prem==null)-(b.gross_prem==null)||(b.gross_prem||0)-(a.gross_prem||0));
    if(items.length) out[model]={baseline:{price:rnd(bp),gross:rnd(bg),dts:rnd(bd)},colors:items}; }
  return out;
}

function trimAnalytics(inf,minN){
  minN=minN==null?MIN_CELL_N:minN;
  let byModel=groupBy(inf.filter(s=>s.trim),s=>s.model), out={};
  for(let model in byModel){ let trims=groupBy(byModel[model],r=>r.trim), items=[];
    for(let trim in trims){ let rows=trims[trim], pc=cell(rows,"price"),gc=cell(rows,"gross"),dc=cell(rows,"dts"),ac=cell(rows,"age_months");
      if(pc.n<minN) continue;
      items.push({trim:trim,n:pc.n,price:pc.median,gross:gc.median,dts:dc.median,avg_age_mo:ac.median,conf:confidence(pc.n)}); }
    items.sort((a,b)=>(a.gross==null)-(b.gross==null)||(b.gross||0)-(a.gross||0));
    if(items.length) out[model]=items; }
  return out;
}

function modelPerformance(inf,benchAll){
  let sg=wmean(benchAll.map(s=>[s.gross,s.weight])), sd=wmean(benchAll.map(s=>[s.dts,s.weight]));
  let byModel=groupBy(inf,s=>s.model), items=[];
  for(let model in byModel){ let rows=byModel[model], pc=cell(rows,"price"),gc=cell(rows,"gross"),dc=cell(rows,"dts");
    items.push({model:model,n:pc.n,loaner_n:rows.filter(r=>r.is_loaner).length,
      price:pc.median,gross:gc.median,dts:dc.median,
      gross_vs_store:(gc.mean&&sg)?rnd(gc.mean-sg):null,dts_vs_store:(dc.mean&&sd)?rnd(dc.mean-sd):null,conf:confidence(pc.n)}); }
  let order={}; INF_ORDER.forEach((m,i)=>order[m]=i);
  items.sort((a,b)=>(order[a.model]==null?99:order[a.model])-(order[b.model]==null?99:order[b.model]));
  return {store:{gross:rnd(sg),dts:rnd(sd)},models:items};
}

function seasonality(inf){
  let ap=wmean(inf.map(s=>[s.price,s.weight])), ag=wmean(inf.map(s=>[s.gross,s.weight]));
  let byM=groupBy(inf,s=>s.month), byQ=groupBy(inf,s=>s.quarter), months=[], quarters=[];
  for(let m=1;m<=12;m++){ let rows=byM[m]||[], pc=cell(rows,"price"),gc=cell(rows,"gross"),dc=cell(rows,"dts");
    let pm=wmean(rows.map(r=>[r.price,r.weight]));
    months.push({month:m,n:pc.n,gross:gc.median,dts:dc.median,
      price_index:(pm&&ap)?Math.round(pm/ap*1000)/1000:null,wn:pc.wn}); }
  for(let q=1;q<=4;q++){ let rows=byQ[q]||[], gc=cell(rows,"gross"), qm=wmean(rows.map(r=>[r.price,r.weight]));
    quarters.push({quarter:q,n:gc.n,gross:gc.median,price_index:(qm&&ap)?Math.round(qm/ap*1000)/1000:null}); }
  return {annual_price:rnd(ap),annual_gross:rnd(ag),months:months,quarters:quarters};
}

function loanerVsRetail(inf){
  function summ(rows){ let pc=cell(rows,"price"),gc=cell(rows,"gross"),dc=cell(rows,"dts"),ac=cell(rows,"age_months");
    return {n:pc.n,price:pc.median,gross:gc.median,dts:dc.median,avg_age_mo:ac.median}; }
  let loan=inf.filter(s=>s.is_loaner), ret=inf.filter(s=>!s.is_loaner), perModel={};
  let models=Array.from(new Set(loan.map(s=>s.model))).sort((a,b)=>loan.filter(s=>s.model===b).length-loan.filter(s=>s.model===a).length);
  models.forEach(m=>{ let lm=loan.filter(s=>s.model===m), rm=ret.filter(s=>s.model===m);
    if(lm.length<MIN_CELL_N) return; perModel[m]={loaner:summ(lm),retail:summ(rm)}; });
  return {overall:{loaner:summ(loan),retail:summ(ret)},per_model:perModel,loaner_total:loan.length};
}

function factor(sub,base,lo,hi){ lo=lo==null?0.75:lo; hi=hi==null?1.35:hi;
  if(!sub||!base) return 1; return Math.max(lo,Math.min(hi,sub/base)); }

function buildPredictor(inf){
  let cm=ageCurves(inf,false), ct=ageCurves(inf,true), colors=colorAnalytics(inf,3), seas=seasonality(inf);
  function curveVal(key,age,field){
    let c=(key.indexOf("|")>=0 && key.split("|")[1])?ct[key]:cm[key];
    if(!c||!c.points.length) return [null,0];
    let bucket=ageBucket(age==null?6:age), fld=field==="price"?"price_smooth":field;
    let exact=c.points.find(p=>p.age===bucket);
    if(exact&&exact[fld]!=null) return [exact[fld],exact.n];
    let best=c.points.reduce((a,p)=>Math.abs(p.age-bucket)<Math.abs(a.age-bucket)?p:a);
    return [best[fld],best.n];
  }
  return function predict(model,trim,modelYear,color,month,ageMonths,asOfYear){
    model=modelNorm(model); trim=trim?norm(trim):""; color=color?canonColor(color):"";
    if(ageMonths==null&&modelYear&&asOfYear)
      ageMonths=Math.max(0,(asOfYear-modelYear)*12+((month||MY_ANCHOR)-MY_ANCHOR));
    let val=null,n=0;
    if(trim){ let r=curveVal(model+"|"+trim,ageMonths,"price"); val=r[0]; n=r[1]; }
    if(!val){ let r=curveVal(model,ageMonths,"price"); val=r[0]; n=r[1]; }
    if(!val) return {ok:false,reason:"no comparable history for this model"};
    let gkey=trim?(model+"|"+trim):model;
    let gross=curveVal(gkey,ageMonths,"gross")[0], dts=curveVal(gkey,ageMonths,"dts")[0];
    let cfac=1;
    if(color&&colors[model]){ let crow=colors[model].colors.find(c=>c.color===color), base=colors[model].baseline.price;
      if(crow&&crow.price&&base) cfac=factor(crow.price,base); }
    let sfac=1;
    if(month){ let mrow=seas.months[month-1]; if(mrow.price_index) sfac=Math.max(0.9,Math.min(1.1,mrow.price_index)); }
    let price=Math.round(val*cfac*sfac), conf=confidence(n||0), spread=0.06+0.14*(1-conf);
    return {ok:true,price:price,price_low:Math.round(price*(1-spread)),price_high:Math.round(price*(1+spread)),
      gross:rnd(gross),dts:rnd(dts),color_factor:Math.round(cfac*1000)/1000,season_factor:Math.round(sfac*1000)/1000,n:n,confidence:conf};
  };
}

function analyze(sales,halfLife,asOf){
  halfLife=halfLife==null?HALF_LIFE_DEFAULT:halfLife;
  assignWeights(sales,halfLife,asOf);
  let inf=sales.filter(s=>s.is_infiniti);
  asOf=asOf||new Date(Math.max.apply(null,sales.map(s=>s.date.getTime())));
  let predictor=buildPredictor(inf);
  let makes=groupBy(sales,s=>s.make);
  let bench=Object.keys(makes).map(mk=>{ let rows=makes[mk];
    return {make:mk,gross:cell(rows,"gross").median,dts:cell(rows,"dts").median,price:cell(rows,"price").median,n:rows.length}; })
    .sort((a,b)=>b.n-a.n).slice(0,10);
  let dmin=new Date(Math.min.apply(null,sales.map(s=>s.date.getTime())));
  return {
    meta:{rows:sales.length,infiniti_rows:inf.length,loaner_rows:inf.filter(s=>s.is_loaner).length,
      date_min:dmin,date_max:asOf,as_of:asOf,half_life_months:halfLife,age_axis:true,mileage_axis:false,
      note:"Retention is modeled on vehicle age (no odometer in source); age approximated from model year with a Sept anchor."},
    age_curves:ageCurves(inf,false),age_curves_trim:ageCurves(inf,true),
    color:colorAnalytics(inf),trim:trimAnalytics(inf),model_perf:modelPerformance(inf,sales),
    seasonality:seasonality(inf),loaner_vs_retail:loanerVsRetail(inf),benchmark:bench,
    predictor:predictor
  };
}
