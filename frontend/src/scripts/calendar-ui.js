(()=>{
 'use strict';
 const core=ActivityCalendarCore,catalog=window.CduData.catalog;
 let events=[],annualCounts={},actualCounts={};
 const annualCache=new Map(),actualCache=new Map();let calendarSeq=0;
 const page=document.getElementById('calendar-page'),grid=document.getElementById('calendar-grid'),agenda=document.getElementById('calendar-agenda');
 const today=CatalogCore.chinaNow().slice(0,10),currentMonth=today.slice(0,7),reduced=matchMedia('(prefers-reduced-motion:reduce)');
 const make=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n};
 const categories=new Map(catalog.entries.map(e=>[e.category,e.category_label]));
 const years=events.flatMap(e=>[Number(e.start.slice(0,4)),Number(e.end.slice(0,4))]);
 /* 覆盖范围来自词表，不能等 events 加载后才决定可选年份，否则启动时只能选当前年和下一年。 */
 const coverageYears=((catalog.coverage||{}).range||[]).map(v=>Number(String(v||'').slice(0,4))).filter(y=>Number.isInteger(y)&&y>2000);
 const minYear=Math.min(Number(today.slice(0,4)),...years,...coverageYears),maxYear=Math.max(Number(today.slice(0,4))+1,...years,...coverageYears);
 let view='seasonal',agendaExpanded=false;
 let state={month:currentMonth,selected:'',kind:'all',category:'',college:'',featured:true},limit=view==='seasonal'?6:12;
 const monthLabel=m=>Number(m.slice(0,4))+'年 '+Number(m.slice(5))+'月';
 const monthShort=d=>Number(d.slice(5,7))+'月'+Number(d.slice(8,10))+'日';
 const time=raw=>raw?.includes('T')?' '+raw.split('T')[1]:'';
 const safe=url=>{try{const u=new URL(url);return ['http:','https:'].includes(u.protocol)&&(u.hostname==='cdu.edu.cn'||u.hostname.endsWith('.cdu.edu.cn'))}catch(_){return false}};
 for(const [id,label] of categories){if(id==='reference')continue;const o=make('option',label);o.value=id;document.getElementById('calendar-category').append(o)}
 for(const [id,label] of Object.entries(catalog.colleges)){if(id==='unknown')continue;const o=make('option',label);o.value=id;document.getElementById('calendar-college').append(o)}
 for(let y=maxYear;y>=minYear;y--){const o=make('option',y+'年');o.value=y;document.getElementById('calendar-year').append(o)}
 function read(){const p=new URL(location.href).searchParams,m=p.get('cal');view=p.get('cal_view')==='dates'?'dates':'seasonal';state.month=/^\d{4}-(0[1-9]|1[0-2])$/.test(m||'')&&Number(m.slice(0,4))>=minYear&&Number(m.slice(0,4))<=maxYear?m:currentMonth;const selected=core.day(p.get('cal_day'));state.selected=selected?.slice(0,7)===state.month?selected:'';state.kind=view==='dates'&&['deadline','event'].includes(p.get('cal_kind'))?p.get('cal_kind'):'all';state.category=categories.has(p.get('cal_type'))?p.get('cal_type'):'';state.college=catalog.colleges[p.get('cal_college')]?p.get('cal_college'):'';state.featured=p.get('cal_featured')!=='0';limit=view==='seasonal'?6:12}
 function save(){const u=new URL(location.href);for(const [k,v] of Object.entries({cal_view:view==='dates'?'dates':'',cal:state.month,cal_day:state.selected,cal_kind:state.kind==='all'?'':state.kind,cal_type:state.category,cal_college:state.college,cal_featured:state.featured?'':'0'})){if(v)u.searchParams.set(k,v);else u.searchParams.delete(k)}u.hash='calendar';history.replaceState(null,'',u)}
 function animate(node,direction=0){if(reduced.matches||document.documentElement.dataset.inputMethod==='keyboard'||!node.animate)return;node.animate([{opacity:.5,transform:direction?'translateX('+direction*12+'px)':'translateY(6px)'},{opacity:1,transform:'translate(0,0)'}],{duration:190,easing:'cubic-bezier(.16,1,.3,1)'})}
 function changeMonth(month,direction=0){const y=Number(month.slice(0,4));if(y<minYear||y>maxYear)return;state.month=month;state.selected='';agendaExpanded=false;limit=view==='seasonal'?6:12;save();render(direction)}
 function selectDay(day){const y=Number(day.slice(0,4));if(y<minYear||y>maxYear)return;if(day.slice(0,7)!==state.month)state.month=day.slice(0,7);state.selected=day;limit=view==='seasonal'?6:12;save();render();grid.querySelector('[data-day="'+day+'"]')?.focus();if(document.documentElement.dataset.inputMethod!=='keyboard')document.querySelector('.calendar-agenda').scrollIntoView({block:'start',behavior:reduced.matches?'instant':'smooth'})}
 function eventRow(event){const row=make('article',undefined,'calendar-agenda-item'),meta=make('div',undefined,'calendar-event-meta '+event.kind);const label=state.selected?(state.selected>event.start&&state.selected<event.end?'进行中':core.markLabel(event,state.selected)):event.label;meta.append(make('span',label),make('span',event.categoryLabel));row.append(meta,make('h3',event.title));const crossYear=event.start.slice(0,4)!==event.end.slice(0,4);const range=event.start===event.end?monthShort(event.start)+time(event.raw):(crossYear?event.start.slice(0,4)+'年':'')+monthShort(event.start)+time(event.version.stage_start)+' — '+(crossYear?event.end.slice(0,4)+'年':'')+monthShort(event.end)+time(event.version.stage_end);row.append(make('p',(crossYear?'':event.start.slice(0,4)+'年 · ')+range,'calendar-event-date'));
  const details=make('details');details.append(make('summary','参与条件与材料'));if(window.ActivityDetails)ActivityDetails.render(details,event.version);
  const links=make('div',undefined,'calendar-event-links'),q=new URLSearchParams({q:event.title,year:String(event.version.year||''),edition:event.version.source_url||''});const explore=make('a','完整活动');explore.href='?'+q+'#all';links.append(explore);if(safe(event.version.source_url)){const source=make('a','官方原文');source.href=event.version.source_url;source.target='_blank';source.rel='noopener noreferrer';links.append(source)}details.append(links);row.append(details);details.addEventListener('toggle',()=>{if(details.open)animate(details)});return row}
 function empty(rows){const box=make('div',undefined,'calendar-empty');box.append(make('h3',state.selected?'这一天，留点空白。':'这个月暂未收录安排。'),make('p',state.selected?'可以查看整月，或点选其他日期。':'换个月份，或放宽活动类型与精选筛选。'));
  const button=make('button',state.selected?'查看整月':'跳到有记录的月份');button.type='button';button.addEventListener('click',()=>{if(state.selected){state.selected='';save();render();return}const matching=events.filter(e=>core.matches(e,state));const months=[...new Set(matching.flatMap(e=>[e.start.slice(0,7),e.end.slice(0,7)]))].sort();const next=months.find(m=>m>state.month)||months.at(-1);if(next)changeMonth(next);else{state.category='';state.college='';state.featured=false;state.kind='all';save();render()}});if(!state.selected&&!events.some(e=>core.matches(e,state)))button.textContent='清除筛选';box.append(button);return box}
 function seasonalRows(month){return annualCache.get(Number(month))||[]}
 async function ensureAnnual(month){
  const key=Number(month);
  if(annualCache.has(key))return annualCache.get(key);
  const seq=++calendarSeq;
  try{
   const data=await window.CduApi.calendar({mode:'annual',month:key});
   if(seq!==calendarSeq)return annualCache.get(key)||[];
   const rows=(data.results||[]).map(r=>({entry:r.entry,versions:r.versions}));
   annualCache.set(key,rows);return rows;
  }catch(error){return null}
 }
 async function ensureAnnualCounts(){
  if(Object.keys(annualCounts).length)return;
  try{annualCounts=(await window.CduApi.calendar({mode:'annual',month:'all'})).counts||{}}catch(_){annualCounts={}}
 }
 async function ensureActualCounts(){
  const year=state.month.slice(0,4);
  if(actualCounts.year===year)return;
  try{const data=await window.CduApi.calendar({mode:'actual_counts',year:year});actualCounts=data.counts||{};actualCounts.year=year}catch(_){}
 }
 async function ensureMonth(){
  const key=state.month;
  if(actualCache.has(key)){events=actualCache.get(key);return true}
  const seq=++calendarSeq;
  try{
   const data=await window.CduApi.calendar({mode:'actual',year:Number(key.slice(0,4)),month:Number(key.slice(5))});
   if(seq!==calendarSeq)return true;
   events=(data.events||[]).map(e=>({
     entryId:e.entry_id,title:e.title,category:e.category,categoryLabel:e.category_label,
     colleges:[],featured:true,kind:e.kind,label:e.label,start:e.start,end:e.end,
     only:e.only||null,raw:e.raw,
     version:{source_url:e.source_url,year:Number(e.start.slice(0,4)),published:e.start,
              participation_facts:[],content_profile:{sections:[]}}
   }));
   actualCache.set(key,events);return true;
  }catch(error){events=[];return false}
 }
 const monthNames=['一月','二月','三月','四月','五月','六月','七月','八月','九月','十月','十一月','十二月'];
 function seasonalCard(record){
  const entry=record.entry,row=make('article',undefined,'calendar-seasonal-card'),latest=record.versions[0];
  row.append(make('span',entry.category_label,'seasonal-kind'),make('h2',entry.title));
  const clue=latest.signals.find(s=>!s.raw)||latest.signals[0];
  const text=clue.raw?(clue.end&&clue.start!==clue.end?monthShort(clue.start)+' — '+monthShort(clue.end):monthShort(clue.raw.slice(0,10))+time(clue.raw))+' · '+clue.text:clue.text.replace(/20\d{2}年/g,'');
  const method=(latest.version.participation_facts||[]).filter(f=>f.kind==='registration').map(f=>f.value).join(' ');const hint=/扫码|扫描.*二维码/.test(method)?'扫码参与':/组队|团队/.test(method)?'团队报名':/提交.*作品|投稿|投递作品/.test(method)?'提交作品':/报名表/.test(method)?'填写报名表':/申请/.test(method)?'提交申请':/报名/.test(method)?'报名参加':'';if(hint)row.append(make('p',hint,'seasonal-method'));
  const years=[...new Set(record.versions.map(r=>r.version.year).filter(Boolean))].sort((a,b)=>a-b);

  const details=make('details');details.append(make('summary','查看详情'),make('p','最近记录 · '+text,'seasonal-clue'),make('p',years.join(' / ')+' 年通知','seasonal-years'));
  const label=make('label','查看通知版本','seasonal-edition'),select=make('select');select.setAttribute('aria-label',entry.title+'的往届通知');
  for(const {version} of record.versions){const o=make('option',version.year+'年通知 · '+(version.published||'发布日期未明'));o.value=version.source_url;select.append(o)}label.append(select);details.append(label);
  const body=make('div',undefined,'seasonal-detail');
  function fill(){const v=record.versions.find(r=>r.version.source_url===select.value).version;body.replaceChildren();if(window.ActivityDetails)ActivityDetails.render(body,v);const a=make('a','官方原文');a.href=v.source_url;a.target='_blank';a.rel='noopener noreferrer';if(safe(v.source_url))body.append(a)}
  select.addEventListener('change',()=>{fill();animate(body)});details.addEventListener('toggle',()=>{if(details.open&&!body.childElementCount){fill();animate(body)}});details.append(body);row.append(details);return row;
 }
 async function renderSeasonal(){
  const month=Number(state.month.slice(5)),list=document.getElementById('calendar-seasonal-list');
  const rows=await ensureAnnual(month);
  if(rows===null){list.replaceChildren();const fail=make('div',undefined,'calendar-empty');fail.append(make('h2','这个月的内容没有加载成功。'),make('p','网络或服务暂时不可用，这不等于没有活动。'));const retry=make('button','重试');retry.type='button';retry.addEventListener('click',()=>renderSeasonal());fail.append(retry);list.append(fail);return}
  document.getElementById('calendar-title').textContent=monthNames[month-1]+'，可以做什么？';document.getElementById('calendar-month-count').textContent=(state.featured?'精选 · ':'')+rows.length+'项相关活动';
  list.replaceChildren(...rows.slice(0,limit).map(seasonalCard));
  if(!rows.length){const blank=make('div',undefined,'calendar-empty');blank.append(make('h2','这个月份还在慢慢补充。'),make('p','试试其他月份，或在筛选中查看全部活动。'));list.append(blank)}
  if(rows.length>limit){const more=make('button','再看 '+Math.min(6,rows.length-limit)+' 项','calendar-agenda-more');more.type='button';more.addEventListener('click',()=>{limit+=6;renderSeasonal()});list.append(more)}animate(list);
 }
 async function render(direction=0){
  let ok=true;
  if(view==='seasonal'){await ensureAnnualCounts()}else{ok=await ensureMonth();await ensureActualCounts()}
  page.dataset.calendarView=view;document.getElementById('calendar-mode').textContent=view==='seasonal'?'查看具体日期':'返回月份活动';document.getElementById('calendar-title').textContent='活动日历';document.getElementById('calendar-intro').textContent=view==='seasonal'?'从历年公告，找这个月份值得提前准备的事。':'选一天，查看安排。';document.querySelector('.calendar-footnote').textContent=view==='seasonal'?'跨月征集归入开始月份；历年记录不代表每年固定举办。':'只在报名截止、活动开始与结束日标注；进行中的周期点开当日可见。历史安排不代表今年安排。';const rows=events,date=state.selected;document.getElementById('calendar-month-title').textContent=monthLabel(state.month);document.getElementById('calendar-year').value=state.month.slice(0,4);document.getElementById('calendar-category').value=state.category;document.getElementById('calendar-college').value=state.college;document.getElementById('calendar-featured').checked=state.featured;
  document.querySelectorAll('[data-calendar-kind]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.calendarKind===state.kind)));
  const rail=document.getElementById('calendar-months');rail.replaceChildren();for(let i=1;i<=12;i++){const month=state.month.slice(0,4)+'-'+String(i).padStart(2,'0'),count=view==='seasonal'?(annualCounts[String(i).padStart(2,'0')]||0):(actualCounts[String(i).padStart(2,'0')]||0),b=make('button',undefined,count?'has-events':'');b.append(make('span',String(i)),make('span','月','calendar-month-unit'));b.type='button';b.setAttribute('aria-pressed',String(month===state.month));b.setAttribute('aria-label',i+'月，'+count+'项安排');b.addEventListener('click',()=>changeMonth(month,i-Number(state.month.slice(5))));rail.append(b)}
  if(view==='seasonal'){await renderSeasonal();return}
  if(!ok){const fail=make('div',undefined,'calendar-empty');fail.append(make('h2','这一天没有加载成功。'),make('p','网络或服务暂时不可用，可以重试。'));const retry=make('button','重试');retry.type='button';retry.addEventListener('click',()=>render());fail.append(retry);agenda.replaceChildren(fail);grid.replaceChildren();return}
  document.getElementById('calendar-prev').disabled=state.month===minYear+'-01';document.getElementById('calendar-next').disabled=state.month===maxYear+'-12';
  const unique=new Set(rows.map(e=>e.version.source_url)).size;document.getElementById('calendar-month-count').textContent=unique+' 个活动版本 · '+rows.filter(e=>e.kind==='deadline').length+' 项截止 · '+rows.filter(e=>e.kind==='event').length+' 项活动阶段';
  const filtered=events;grid.replaceChildren();grid.setAttribute('aria-label',monthLabel(state.month)+'日期，方向键可移动');core.cells(state.month).forEach((day,i)=>{const marks=core.dayMarks(filtered,day),outside=day.slice(0,7)!==state.month;const button=make('button',undefined,'calendar-day'+(outside?' outside':'')+(day===today?' today':'')+(i%7>4?' weekend':''));button.type='button';button.disabled=Number(day.slice(0,4))<minYear||Number(day.slice(0,4))>maxYear;button.dataset.day=day;button.setAttribute('aria-pressed',String(day===date));if(day===today)button.setAttribute('aria-current','date');button.setAttribute('aria-label',day+'，'+marks.length+'项'+(marks.length?'：'+marks.slice(0,2).map(e=>e.title+'，'+core.markLabel(e,day)).join('；'):''));button.append(make('span',Number(day.slice(8)),'calendar-day-number'));
   const dots=make('span',undefined,'calendar-dots');dots.setAttribute('aria-hidden','true');marks.slice(0,3).forEach(e=>dots.append(make('i',undefined,e.kind)));button.append(dots);for(const event of marks.slice(0,1)){const chip=make('span',event.title,'calendar-chip '+event.kind);chip.setAttribute('aria-hidden','true');button.append(chip)}if(marks.length)button.append(make('span',marks.length+' 项','calendar-day-count'));button.addEventListener('click',()=>selectDay(day));grid.append(button)});
  document.querySelector('.calendar-agenda').hidden=!state.selected&&!agendaExpanded;document.getElementById('calendar-show-list').setAttribute('aria-expanded',String(agendaExpanded||!!state.selected));document.getElementById('calendar-agenda-title').textContent=date?monthShort(date)+'的安排':'本月安排';document.getElementById('calendar-clear-day').hidden=!date;const selected=date?rows.filter(e=>core.onDay(e,date)):rows;agenda.replaceChildren(...selected.slice(0,limit).map(eventRow));if(!selected.length)agenda.append(empty(rows));if(selected.length>limit){const more=make('button','再看一些 · '+limit+' / '+selected.length,'calendar-agenda-more');more.type='button';more.addEventListener('click',()=>{limit+=12;render()});agenda.append(more)}
  animate(grid,direction?Math.sign(direction):0);animate(agenda);
 }
 document.getElementById('calendar-mode').addEventListener('click',()=>{view=view==='seasonal'?'dates':'seasonal';if(view==='seasonal')state.kind='all';state.selected='';agendaExpanded=false;limit=view==='seasonal'?6:12;save();render()});
 document.getElementById('calendar-show-list').addEventListener('click',()=>{agendaExpanded=true;state.selected='';save();render();document.querySelector('.calendar-agenda').scrollIntoView({block:'start',behavior:reduced.matches?'instant':'smooth'})});
 document.getElementById('calendar-hide-list').addEventListener('click',()=>{const day=state.selected;agendaExpanded=false;state.selected='';save();render();(grid.querySelector('[data-day="'+day+'"]')||grid).focus()});
 document.getElementById('calendar-prev').addEventListener('click',()=>changeMonth(core.moveMonth(state.month,-1),-1));document.getElementById('calendar-next').addEventListener('click',()=>changeMonth(core.moveMonth(state.month,1),1));
 document.getElementById('calendar-today').addEventListener('click',()=>changeMonth(currentMonth));document.getElementById('calendar-clear-day').addEventListener('click',()=>{state.selected='';agendaExpanded=true;save();render()});
 for(const [id,key] of [['calendar-category','category'],['calendar-college','college'],['calendar-featured','featured']])document.getElementById(id).addEventListener('change',e=>{state[key]=key==='featured'?e.target.checked:e.target.value;limit=view==='seasonal'?6:12;save();render()});
 document.getElementById('calendar-year').addEventListener('change',e=>changeMonth(e.target.value+state.month.slice(4)));
 document.querySelectorAll('[data-calendar-kind]').forEach(b=>b.addEventListener('click',()=>{state.kind=b.dataset.calendarKind;limit=view==='seasonal'?6:12;save();render()}));
 grid.addEventListener('keydown',event=>{const button=event.target.closest('[data-day]');if(!button)return;const offsets={ArrowLeft:-1,ArrowRight:1,ArrowUp:-7,ArrowDown:7},day=button.dataset.day;let next;if(event.key in offsets)next=core.shift(day,offsets[event.key]);else if(event.key==='Home'||event.key==='End'){const index=core.cells(state.month).indexOf(day)%7;next=core.shift(day,event.key==='Home'?-index:6-index)}else return;event.preventDefault();if(next.slice(0,7)!==state.month){const y=Number(next.slice(0,4));if(y<minYear||y>maxYear)return;state.month=next.slice(0,7);state.selected='';save();render()}grid.querySelector('[data-day="'+next+'"]')?.focus()});
 document.querySelector('.skip').addEventListener('click',e=>{if(page.hidden)return;e.preventDefault();e.stopImmediatePropagation();grid.tabIndex=-1;grid.focus();grid.scrollIntoView({block:'start',behavior:'instant'})},true);
 document.addEventListener('cdu:view',()=>{if(!page.hidden){read();render()}});
 /* 首次进入：脚本可能在 SitePages 分发之后才加载，这里补一次渲染 */
 let bootTries=0;
 function bootCalendar(){
  if(page.hidden&&location.hash!=='#calendar')return;
  try{read()}catch(error){console.error('calendar read',error)}
  render().then(()=>{
   const title=document.getElementById('calendar-month-title');
   if((!title||!title.textContent)&&bootTries++<6)setTimeout(bootCalendar,220);
  }).catch(error=>{
   if(bootTries++<6)setTimeout(bootCalendar,220);
  });
 }
 bootCalendar();
 addEventListener('hashchange',()=>{if(location.hash==='#calendar'&&!page.hidden)render()});
})();
