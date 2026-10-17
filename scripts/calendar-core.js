(function(root){
 'use strict';
 const pad=n=>String(n).padStart(2,'0');
 function day(raw){const m=String(raw||'').match(/^(\d{4})-(\d{2})-(\d{2})(?:T(?:(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?|24:00(?::00)?))?$/);if(!m)return null;const s=m[1]+'-'+m[2]+'-'+m[3],d=new Date(s+'T00:00:00Z');return Number.isFinite(d.getTime())&&d.toISOString().slice(0,10)===s?s:null}
 function shift(date,amount){const d=new Date(date+'T00:00:00Z');d.setUTCDate(d.getUTCDate()+amount);return d.toISOString().slice(0,10)}
 function moveMonth(month,amount){const [y,m]=month.split('-').map(Number);const d=new Date(Date.UTC(y,m-1+amount,1));return d.toISOString().slice(0,7)}
 function cells(month){const first=month+'-01',d=new Date(first+'T00:00:00Z'),offset=(d.getUTCDay()+6)%7;return Array.from({length:42},(_,i)=>shift(first,i-offset))}
 function build(entries){const result=[];for(const entry of entries)for(const v of entry.versions){if(v.conflict)continue;const meta={entryId:entry.id,title:entry.title,category:v.source_fields?.category||entry.category,categoryLabel:v.source_fields?.category_label||entry.category_label,colleges:v.colleges||[],featured:entry.featured!==false,version:v};
   const deadline=day(v.deadline);if(deadline)result.push({...meta,id:v.source_url+'|deadline',kind:'deadline',label:v.deadline_kind==='submission'?'作品提交截止':v.deadline_kind==='combined'?'报名及作品截止':v.deadline_kind==='notice'?'截止':'报名截止',start:deadline,end:deadline,raw:v.deadline});
   const start=day(v.stage_start),end=day(v.stage_end);if(start||end){if(start&&end&&end<start)continue;const from=start||end,to=end||from;result.push({...meta,id:v.source_url+'|event',kind:'event',label:start?'活动阶段':'活动阶段结束',start:from,end:to,raw:v.stage_start||v.stage_end})}
  }return result}
 function matches(event,filters={}){return (!filters.kind||filters.kind==='all'||event.kind===filters.kind)&&(!filters.category||event.category===filters.category)&&(!filters.college||event.colleges.includes(filters.college))&&(!filters.featured||event.featured)}
 function inMonth(event,month){const next=moveMonth(month,1)+'-01';return event.start<next&&event.end>=month+'-01'}
 function onDay(event,date){return event.start<=date&&event.end>=date}
 function monthEvents(events,month,filters={}){return events.filter(e=>matches(e,filters)&&inMonth(e,month)).sort((a,b)=>a.start.localeCompare(b.start)||a.title.localeCompare(b.title,'zh-CN')||a.kind.localeCompare(b.kind))}
 function mentionedMonths(text){const months=new Set([...String(text||'').matchAll(/(?:^|[^\d])(1[0-2]|0?[1-9])月/g)].map(m=>Number(m[1])));for(const m of String(text||'').matchAll(/(1[0-2]|0?[1-9])月[^月]{0,25}?(?:至|到|—|–|~|～)[^月]{0,12}?(1[0-2]|0?[1-9])月/g)){let n=Number(m[1]);for(let i=0;i<12;i++){months.add(n);if(n===Number(m[2]))break;n=n%12+1}}return months}
 function monthRanges(text){const value=String(text||'').replace(/20\d{2}[./-](\d{1,2})[./-]\d{1,2}/g,'$1月');return [...value.matchAll(/(1[0-2]|0?[1-9])月[^月]{0,25}?(?:至|到|—|–|~|～|－|-)[^月]{0,12}?(1[0-2]|0?[1-9])月/g)].map(m=>({start:Number(m[1]),end:Number(m[2]),text:m[0]}))}
 function seasonalMonths(text){let remainder=String(text||'').replace(/20\d{2}[./-](\d{1,2})[./-]\d{1,2}/g,'$1月');const ranges=monthRanges(remainder),months=new Set(ranges.map(r=>r.start));for(const r of ranges)remainder=remainder.replace(r.text,'');for(const month of mentionedMonths(remainder))months.add(month);return months}
 function seasonal(entries,month,filters={}){const result=[];for(const entry of entries){const versions=[];for(const version of entry.versions){const meta={category:version.source_fields?.category||entry.category,colleges:version.colleges||[],featured:entry.featured!==false};if(!matches({...meta,kind:filters.kind||'all'},filters))continue;const signals=[];
    const dated=build([{...entry,versions:[version]}]),facts=version.participation_facts||[];
    const timingClues=[...facts,...(version.content_profile?.sections||[]).filter(s=>['schedule','registration'].includes(s.kind)).flatMap(s=>(s.items||[]).map(i=>({kind:s.kind,value:i.text})))];
    const registrationWindows=timingClues.filter(f=>['schedule','registration'].includes(f.kind)&&/报名|征集|征稿|投稿|申报|招募|作品提交/.test(f.value)).flatMap(f=>{const ranges=monthRanges(f.value).map(r=>({...r,text:f.value}));const published=day(version.published);if(published&&/即日起|自(?:本)?通知发布之日起|自发布之日起/.test(f.value)){const start=Number(published.slice(5,7));for(const end of mentionedMonths(f.value))if(start!==end)ranges.push({start,end,text:f.value})}return ranges}).filter(r=>r.start!==r.end);
    const stageWindows=dated.filter(e=>e.kind==='event'&&e.start.slice(0,7)!==e.end.slice(0,7)).map(e=>({start:Number(e.start.slice(5,7))}));
    const windows=filters.kind==='event'?stageWindows:registrationWindows.length?registrationWindows:stageWindows;
    if(windows.length&&!windows.some(w=>w.start===Number(month)))continue;
    for(const event of dated){if(filters.kind&&filters.kind!=='all'&&event.kind!==filters.kind)continue;if(Number(event.start.slice(5,7))===Number(month)){signals.push({kind:event.kind,text:event.label,raw:event.raw,start:event.start,end:event.end})}}
    for(const fact of facts){if(!['schedule','registration'].includes(fact.kind))continue;if(/奖项评审|结果公示|获奖名单/.test(fact.value)&&!/报名|申请|提交|报送/.test(fact.value))continue;const kind=fact.kind==='registration'||/截止|提交|报送|报名|申请/.test(fact.value)?'deadline':'event';if(filters.kind&&filters.kind!=='all'&&kind!==filters.kind)continue;if(seasonalMonths(fact.value).has(Number(month)))signals.push({kind,text:fact.value,raw:null})}
    if(!signals.length&&windows.some(w=>w.start===Number(month)&&w.text))signals.push({kind:'deadline',text:windows.find(w=>w.start===Number(month)&&w.text).text,raw:null});
    if(signals.length)versions.push({version,signals})}
   if(versions.length){versions.sort((a,b)=>(b.version.published||'').localeCompare(a.version.published||''));result.push({entry,versions})}}
  return result.sort((a,b)=>Number(b.entry.spotlight===true)-Number(a.entry.spotlight===true)||b.versions.length-a.versions.length||a.entry.title.localeCompare(b.entry.title,'zh-CN'))}
 const api={day,shift,moveMonth,cells,build,matches,inMonth,onDay,monthEvents,mentionedMonths,monthRanges,seasonalMonths,seasonal};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.ActivityCalendarCore=api;
})(typeof globalThis!=='undefined'?globalThis:this);
