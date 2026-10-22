(function(root){
 'use strict';
 function chinaNow(date=new Date()){return new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).format(date).replace(' ','T')}
 function endTime(raw){
  if(!raw)return null;let value=String(raw);
  if(value.includes('T24:')){const day=value.slice(0,10);value=new Date(Date.parse(day+'T00:00:00Z')+86400000).toISOString().slice(0,10)+'T00:'+value.split('T24:')[1]}
  /* 接口的截止时间是带时区的 UTC；先换算成北京时间墙钟，才能和 chinaNow() 按字符串比较。 */
  if(/(?:Z|[+-]\d{2}:?\d{2})$/.test(value)){const parsed=new Date(value);if(Number.isFinite(parsed.getTime()))return new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).format(parsed).replace(' ','T')}
  if(!value.includes('T'))value+='T23:59:59';return value.length===16?value+':00':value
 }
 function phase(version,kind,now=chinaNow()){
  if(kind==='reference')return {id:'reference',label:'参考资料',tone:'muted'};
  if(version.conflict)return {id:'unknown',label:'版本有差异',tone:'warning'};
  const day=now.slice(0,10),start=(version.stage_start||'').slice(0,10),end=version.stage_end;
  if(start&&end&&start<=day&&day<=end)return {id:'scheduled',label:'通知所列活动期',tone:'active'};
  const cutoff=endTime(version.deadline);
  if(cutoff){if(cutoff>=now)return {id:cutoff.slice(0,10)===day?'today':'before_deadline',label:cutoff.slice(0,10)===day?'今日截止':'所列截止前',tone:'active'};
   if((end&&end<day)||(!end&&start&&start<day))return {id:'past',label:'所列日期已过',tone:'muted'};
   return {id:'deadline_passed',label:version.deadline_kind==='submission'?'交作品已截止':version.deadline_kind==='combined'?'报名及作品已截止':version.deadline_kind==='notice'?'所列截止已过':'报名已截止',tone:'warning'};}
  if(start&&start>day)return {id:'upcoming',label:'活动日期未到',tone:'muted'};
  if(start&&start===day)return {id:'scheduled',label:'通知所列活动日',tone:'active'};
  if(start&&start<day)return {id:'past',label:'所列起始日已过',tone:'muted'};
  return {id:'unknown',label:version.year?version.year+' 年公告':'历史公告',tone:'muted'};
 }
 function timingRange(version,basis='event'){
  if(version.conflict)return null;
  const valid=raw=>{const m=String(raw||'').match(/^(\d{4})-(\d{2})-(\d{2})(?:$|T| )/);if(!m)return null;const day=m[1]+'-'+m[2]+'-'+m[3],d=new Date(day+'T00:00:00Z');return Number.isFinite(d.getTime())&&d.toISOString().slice(0,10)===day?day:null};
  if(basis==='deadline'){const day=valid(version.deadline);return day?[day,day]:null}
  const start=valid(version.stage_start),end=valid(version.stage_end);
  if(!start)return null;
  return [start,end&&end>=start?end:start];
 }
 function monthMatches(version,filters){
  if(!filters.month)return true;
  if(filters.month_basis==='seasonal'&&root.ActivityCalendarCore){
   if(version.conflict)return filters.month==='unknown';
   const entry={id:'month-probe',title:'',versions:[version]};
   if(filters.month==='unknown')return !Array.from({length:12},(_,i)=>i+1).some(m=>root.ActivityCalendarCore.seasonal([entry],m,{}).length);
   return root.ActivityCalendarCore.seasonal([entry],Number(filters.month),{}).length>0;
  }
  const range=timingRange(version,filters.month_basis);
  if(filters.month==='unknown')return !range;
  const month=Number(filters.month);if(!range||!Number.isInteger(month)||month<1||month>12)return false;
  for(let year=Number(range[0].slice(0,4));year<=Number(range[1].slice(0,4));year++){
   const first=String(year).padStart(4,'0')+'-'+String(month).padStart(2,'0')+'-01';
   const last=String(year).padStart(4,'0')+'-'+String(month).padStart(2,'0')+'-'+new Date(Date.UTC(year,month,0)).getUTCDate();
   if(first<=range[1]&&last>=range[0])return true;
  }
  return false;
 }
 function selectedVersion(entry,filters,now=chinaNow()){
  const candidates=entry.versions.filter(v=>relevant(v,filters.interest)&&(!filters.level||(v.levels||['unknown']).includes(filters.level))&&(!filters.college||v.colleges.includes(filters.college))&&(!filters.year||(filters.year==='unknown'?v.year===null:String(v.year)===filters.year))&&(!filters.phase||phase(v,entry.kind,now).id===filters.phase)&&(filters.view!=='registration'||registrationOpen(v,now))&&monthMatches(v,filters));
  return candidates.sort((a,b)=>(b.year||0)-(a.year||0))[0]||null;
 }
 function relevant(version,college){const s=version.audience_scope;return !college||college==='any'||Boolean(s&&(s.kind==='campus'||s.kind==='college'&&s.colleges.includes(college)))}
 function registrationOpen(version,now=chinaNow()){if(version.conflict)return false;const today=now.slice(0,10);const windows=version.registration_windows||[];if(windows.length)return windows.some(w=>w.start<=today&&today<=w.end)&&(!version.deadline||endTime(version.deadline)>=now);if(!version.deadline)return false;if(version.deadline_kind==='event')return false;return endTime(version.deadline)>=now}
 function matches(entry,filters,now=chinaNow()){
  if(filters.view==='discover'&&(entry.kind==='reference'||entry.featured===false||entry.spotlight===false||CduProjection.collegeOutOfFeatured(entry)))return false;
  if(filters.view==='compare'&&new Set(entry.versions.map(v=>v.year).filter(Boolean)).size<2)return false;
  if(filters.category&&!filters.category.split(',').includes(entry.category))return false;
  const q=(filters.q||'').trim().toLocaleLowerCase();
  if(q&&!([entry.title,entry.summary,...(entry.tags||[]),...entry.versions.flatMap(v=>[v.audience||'',...(v.participation_facts||[]).map(f=>f.value),...(v.content_profile?.sections||[]).flatMap(s=>[s.title,...(s.items||[]).map(i=>i.text)])])].join(' ').toLocaleLowerCase().includes(q)))return false;
  return Boolean(selectedVersion(entry,filters,now));
 }
 function nextFeaturedBatch(entries,currentIds,size=3,random=Math.random){
  const unique=[...new Map(entries.map(e=>[e.id,e])).values()];
  const fresh=unique.filter(e=>!currentIds.includes(e.id)),fallback=unique.filter(e=>currentIds.includes(e.id));
  for(let i=fresh.length-1;i>0;i--){const j=Math.floor(random()*(i+1));[fresh[i],fresh[j]]=[fresh[j],fresh[i]]}
  return [...fresh,...fallback].slice(0,size);
 }
 function monthDay(raw){if(!raw)return "日期待补";const match=String(raw).match(/^\d{4}-(\d{2})-(\d{2})(?:$|T| )/);return match?match[1]+"月"+match[2]+"日":"尚未提取"}
 const api={timingRange,monthMatches,monthDay,chinaNow,endTime,phase,selectedVersion,matches,nextFeaturedBatch,relevant,registrationOpen};
 if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.CatalogCore=api;
})(typeof globalThis!=='undefined'?globalThis:this);
