(()=>{
 'use strict';
 const batch=JSON.parse(document.getElementById('batch').textContent);
 const catalog=JSON.parse(document.getElementById('catalog-data').textContent);
 const proof=JSON.parse(document.getElementById('verification-data').textContent);
 const core=CatalogCore;
 const display=catalog.display_options||{};
 const show=(key)=>display[key]!==false;
 const materialMap=new Map(batch.records.map(r=>[r.id,r]));
 const proofMap=new Map(proof.records.map(r=>[r.id,r]));
 const categories={sports:'运动健身',creative:'文化创作',technology:'科技竞赛',speech:'演讲表达',volunteering:'志愿服务',learning:'学习发展',lecture:'学术讲座',exchange:'国际交流',practice:'社会实践',recruitment:'组织招募',career:'生涯就业',reference:'参考资料'};
 let visibleLimit=12;
 let hasRendered=false;
 const state={view:'home',q:'',college:'',level:'',year:'',category:'',phase:'',month:'',month_basis:'seasonal',interest:'any'};
 const fieldNames={published:'原文日期',deadline:'截止时间',event_start:'活动阶段起始',audience:'参与对象片段',preparation:'准备条款',team_max:'人数条款',categories:'类别设置',song_authors:'歌曲类作者人数',digital_authors:'数智类作者人数',resolution:'分辨率要求',file_size:'文件大小',long_film:'长片时长',work_photos:'团队工作照',animation_ai:'动画 AI 比例',short_film:'超短片时长'};
 const statuses={agree:'日期及用途独立提取一致',image_agree:'图片转录一致，非自动正文核验',not_compared:'原文可定位，未做独立语义比较',missing:'独立提取待补',evidence_missing:'独立引文未定位',disagree:'提取有分歧',type_disagrees:'日期用途有分歧',value_without_support:'值与引文不符'};
 const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n};
 const link=(text,url)=>{const a=el('a',text,'source-link');a.href=url;a.target='_blank';a.rel='noopener noreferrer';return a};
 const date=v=>v?String(v).replace('T',' '):'日期待补';
 const profileCovers=(version,kind)=>Boolean(version.content_profile?.coverage?.[kind]);
 const profileHasDatedSchedule=version=>(version.content_profile?.sections||[]).some(s=>['schedule','registration'].includes(s.kind)&&(s.items||[]).some(i=>/(?:20\d{2}[年./-]\d{1,2}|\d{1,2}月\d{1,2}日|\d{1,2}日)/.test(i.text||'')));
 function safeCduUrl(value){try{const url=new URL(value);return (url.protocol==='http:'||url.protocol==='https:')&&(url.hostname==='cdu.edu.cn'||url.hostname.endsWith('.cdu.edu.cn'))}catch(_){return false}}
 const profileNames={audience:'参与对象',conditions:'参与条件',location:'地点',registration:'报名步骤',materials:'所需材料',schedule:'日程安排',content:'活动内容',benefits:'费用与奖励',duties:'职责要求',other:'其他说明'};
 const cleanListText=text=>String(text||'').replace(/^\s*(?:(?:[•·▪◦])\s*)?(?:(?:[（(]?\d{1,2}[）)]?[.、)）])\s*)+/,'');
 const displayText=text=>cleanListText(String(text||'').replace(/^\s*(?:[•·▪◦]\s*)?\d{1,2}[.、)）](?=[\u4e00-\u9fff《（])/,'').replace(/^\s*[•·▪◦]\s*/,''));
 function factList(parent,facts){
  facts=facts.filter(f=>show(f.kind));const kinds=[...new Set(facts.map(f=>f.kind))];
  for(const kind of kinds){const group=el('section',undefined,'profile-section');group.append(el('h5',profileNames[kind]||'参与要求'));const list=el('ul');
   for(const fact of facts.filter(f=>f.kind===kind)){const li=el('li',displayText(fact.value));li.title=fact.locator||'';list.append(li)}group.append(list);parent.append(group)}
 }
 function activityProfile(parent,version){
  const p=version.content_profile,facts=version.participation_facts||[];
  if(facts.length)factList(parent,facts);
  if(!p)return;
  if(show('full_text')){const source=el('details',undefined,'profile-original');source.append(el('summary','报名与参与详情'));
  for(const section of p.sections||[]){if(!show(section.kind))continue;const group=el('section',undefined,'profile-section');group.append(el('h5',section.title||profileNames[section.kind]||'原文条款'));const list=el('ul');
   for(const item of section.items||[])for(const text of (item.text||'').split(/(?<=[。；])\s*/).filter(Boolean)){const li=el('li',displayText(text));if(item.locator)li.title=item.locator;list.append(li)}group.append(list);source.append(group)}
  if(source.children.length>1)parent.append(source)}
  if(show('attachments')&&(p.attachments||[]).length){const attachments=el('details',undefined,'profile-attachments');attachments.append(el('summary','附件与相关链接 · '+p.attachments.length));const extracted=facts.filter(f=>f.basis==='attachment').length;attachments.append(el('p',extracted?'已提取 '+extracted+' 条附件信息；未覆盖的内容请查对应附件。':'以下附件尚未提取正文。','profile-status'));
   for(const att of p.attachments){const row=el('p',undefined,'profile-attachment');if(safeCduUrl(att.url))row.append(link(att.title||'官方附件',att.url));else row.append(el('span',att.title||'附件'));if(!att.url&&att.status)row.append(el('span',' · '+att.status,'profile-attachment-status'));attachments.append(row)}parent.append(attachments)}
 }
 const now=()=>core.chinaNow();
 const filters=document.getElementById('filters');
 filters.open=false;
 for(const [id,label] of Object.entries(catalog.colleges)){if(id!=='unknown'){const pref=el('option',label);pref.value=id;document.getElementById('my-college').append(pref)}const o=el('option',label);o.value=id;document.getElementById('college').append(o)}
 for(const [id,label] of Object.entries(catalog.levels)){const o=el('option',label);o.value=id;document.getElementById('level').append(o)}
 const yearControl=document.getElementById('year');yearControl.replaceChildren();for(const [value,label] of [['','全部年份'],...[...new Set(catalog.entries.flatMap(e=>e.versions.map(v=>v.year)).filter(Number.isInteger))].sort((a,b)=>b-a).map(y=>[String(y),y+' 年']),['unknown','年份未明确']]){const o=el('option',label);o.value=value;yearControl.append(o)}
 const filterKeys=['q','college','level','year','category','phase','month','month_basis','interest'];
 function choice(parent,text,key,value){const b=el('button',text);b.type='button';b.dataset[key]=value;b.setAttribute('aria-pressed','false');b.addEventListener('click',()=>{if(key==='category'&&value){const values=new Set(state.category.split(',').filter(Boolean));if(values.has(value))values.delete(value);else values.add(value);select(key,[...values].join(','))}else select(key,value)});parent.append(b)}
 const yearTabs=el('div',undefined,'year-shortcuts');yearTabs.setAttribute('role','group');yearTabs.setAttribute('aria-label','按公告年份筛选');choice(yearTabs,'全部年份','year','');for(const y of [...new Set(catalog.entries.flatMap(e=>e.versions.map(v=>v.year)).filter(Number.isInteger))].sort((a,b)=>b-a))choice(yearTabs,String(y),'year',String(y));document.querySelector('#filters .filter-body').append(yearTabs);
 const months=document.getElementById('month-tabs');choice(months,'全年','month','');for(let i=1;i<=12;i++)choice(months,i+'月','month',String(i));choice(months,'日期待补','month','unknown');
 const types=document.getElementById('category-tabs');choice(types,'全部类型','category','');for(const id of ['sports','creative','technology','speech','volunteering','practice','recruitment'])choice(types,categories[id],'category',id);const extra=el('details',undefined,'extra-types');extra.append(el('summary','更多类型'));const extraBody=el('div');for(const id of ['learning','lecture','exchange','career'])choice(extraBody,categories[id],'category',id);extra.append(extraBody);types.append(extra);

 document.getElementById('college-policy').textContent=catalog.college_policy;
 document.getElementById('year-policy').textContent=catalog.year_policy;
 if(catalog.coverage){const c=catalog.coverage;document.getElementById('coverage').textContent='资料覆盖 '+c.range[0]+' 至 '+c.range[1]+'；精选页展示竞赛、项目、实践与招募，其他通知保留在资料库。'}
 function storedCollege(){try{return localStorage.getItem('cdu-college-preference')||'any'}catch{return 'any'}}
 function readState(){const u=new URL(location.href);for(const k of filterKeys)state[k]=u.searchParams.get(k)||(k==='month_basis'?'seasonal':k==='interest'?storedCollege():'');const h=u.hash;state.view=h==='#registration'?'registration':['#compare','#year-comparison'].includes(h)?'compare':['#reference','#references'].includes(h)?'reference':h==='#calendar'?'calendar':h==='#about'?'about':h==='#home'?'home':h==='#discover'?'discover':h==='#all'||h==='#results'||['q','college','level','year','category','phase','month'].some(k=>state[k])?'all':'home';
  if(!catalog.colleges[state.interest])state.interest='any';if(state.college&&!catalog.colleges[state.college])state.college='';if(state.level&&!catalog.levels[state.level])state.level='';state.category=[...new Set(state.category.split(',').filter(k=>categories[k]))].join(',');if(!['seasonal','event','deadline'].includes(state.month_basis))state.month_basis='seasonal';if(state.month&&!['unknown',...Array.from({length:12},(_,i)=>String(i+1))].includes(state.month))state.month='';
  for(const key of ['year','phase'])if(![...document.getElementById(key).options].some(o=>o.value===state[key]))state[key]='';}
 function saveState(){try{const u=new URL(location.href);for(const key of filterKeys){if(state[key]&&!(key==='month_basis'&&state[key]==='seasonal'))u.searchParams.set(key,state[key]);else u.searchParams.delete(key)}u.hash=state.view==='home'?'home':state.view==='about'?'about':state.view==='compare'?'compare':state.view==='reference'?'reference':state.view==='all'?'all':state.view==='registration'?'registration':state.view==='calendar'?'calendar':'discover';history.replaceState(null,'',u)}catch(_){/* Local file previews can deny history writes; filtering still works. */}}
 function syncControls(){document.querySelectorAll('[data-year]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.year===state.year)));document.getElementById('my-college').value=state.interest;document.getElementById('college-hint').textContent=state.interest==='any'?'可跳过；选择后会在这台设备记住。':'按原文明示的参与对象匹配；年级、专业等条件仍请看详情。';document.getElementById('query').value=state.q;for(const k of ['college','level','year','phase','month_basis'])document.getElementById(k).value=state[k];document.querySelectorAll('[data-month]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.month===state.month)));document.querySelectorAll('[data-category]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.category?state.category.split(',').includes(b.dataset.category):!state.category)));document.getElementById('month-help').textContent=state.month_basis==='seasonal'?'按往年参与月份查找，跨月征集只列开始月份。':state.month_basis==='deadline'?'按通知所列报名、作品提交等截止日期归类，不表示整个报名期间。':'按通知所列活动阶段归类；历史月份不代表今年安排。';document.querySelectorAll('[data-view]').forEach(a=>{if(a.dataset.view===state.view)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current')});document.getElementById('clear-query').hidden=!state.q;requestAnimationFrame(()=>{moveNav();if(!document.getElementById('query-page').hidden){const active=months.querySelector('[aria-pressed=true]');if(active){const x=active.offsetLeft-months.offsetLeft;if(x<months.scrollLeft||x+active.offsetWidth>months.scrollLeft+months.clientWidth)months.scrollLeft=Math.max(0,x-months.clientWidth/2+active.offsetWidth/2)}}});const extraCount=state.category.split(',').filter(k=>['learning','lecture','exchange','career'].includes(k)).length;extra.querySelector('summary').textContent='更多类型'+(extraCount?' · '+extraCount:'');if(extraCount)extra.open=true;document.getElementById('time-help').textContent='按北京时间 '+now().slice(0,10)+' 计算，不代表实时开放情况。'}
 function select(key,value){visibleLimit=12;if(['home','about'].includes(state.view)&&value)state.view='discover';if(key==='category'&&value&&state.view==='reference')state.view='all';state[key]=value;saveState();syncControls();render()}
 function addTag(parent,text,key,value){const b=el('button',text,'meta-tag');b.type='button';b.setAttribute('aria-label','按'+text+'筛选');b.addEventListener('click',()=>select(key,value));parent.append(b)}
 function materials(parent,entry){for(const id of entry.material_ids){const r=materialMap.get(id);if(!r)continue;if(entry.material_ids.length>1)parent.append(el('h4',r.title));parent.append(el('p',r.summary));
   for(const [key,label] of [['audience','参与对象'],['preparation','准备要求'],['event_start','原文活动日期'],['registration_end','原文报名截止']]){if(r.facts[key])parent.append(el('p',label+'：'+r.facts[key]))}
   if(r.editorial.uncertainties.length){parent.append(el('h4','仍需核实'));const ul=el('ul');r.editorial.uncertainties.forEach(x=>ul.append(el('li',x)));parent.append(ul)}
   if(r.editorial.suggestions.length){parent.append(el('h4','准备建议（编辑归纳）'));const ul=el('ul');r.editorial.suggestions.forEach(x=>ul.append(el('li',x)));parent.append(ul)}
   parent.append(el('p','材料文件：'+r.source.path,'proof-note'));if(r.source.published_on)parent.append(el('p','原文发布日期：'+r.source.published_on,'proof-note'));if(r.source.url)parent.append(link('查看公开来源',r.source.url));else parent.append(el('p','目前仅有本地材料摘要，公开来源待补齐。','proof-note'));
  }}
 function evidence(parent,entry){
  const rows=entry.versions.slice().sort((a,b)=>b.year-a.year).map(v=>({record:proofMap.get(v.proof_id)})).filter(x=>x.record);
  if(!show('proofs')||!rows.length)return;
  const section=el('details',undefined,'entry-evidence');section.append(el('summary','查看原文核验依据'));
  section.append(el('p','以下摘录用于核对少数重点字段；状态说明本轮核验范围，不代表持续监测。','proof-note'));
  rows.forEach(({record:r})=>{const d=el('details',undefined,'proof-year');d.append(el('summary',r.year+' 年：'+r.fields.length+' 项依据'));
   r.fields.forEach(f=>{const row=el('div',undefined,'proof-field');row.append(el('strong',fieldNames[f.field]||f.field),el('div',f.withheld?'暂缓确定展示':date(f.value)),el('small',statuses[f.independent_status]||'待核实'),el('blockquote',f.quote),el('small',f.locator),link('查看原始公告',f.notice_url));if(f.source_url!==f.notice_url)row.append(link(f.method==='image_manual'?'查看赛程图':'查看原始附件',f.source_url));d.append(row)});section.append(d)});
  section.append(el('p','核验快照 '+proof.checked_on+'；后续更正检索范围有限，未覆盖群消息、公众号和全部赛事网站更新。','proof-note'));parent.append(section);
 }
 function annualCompare(parent,entry){const strip=el('div',undefined,'compare-strip');entry.versions.slice().sort((a,b)=>a.year-b.year).forEach(v=>{const box=el('div');const heading=el('strong',v.year+' 年');if(String(v.year)===state.year){const mark=el('mark',v.year+' 年');heading.replaceChildren(mark)}box.append(heading);box.append(el('p','发布 '+CatalogCore.monthDay(v.published)),el('p',(v.deadline_kind==='submission'?'作品截止 ':v.deadline_kind==='combined'?'报名及作品截止 ':'报名截止 ')+CatalogCore.monthDay(v.deadline)));if(v.stage_start)box.append(el('p',(entry.id==='microfilm'?'入围展播 ':entry.id==='digital'?'校内评审 ':'所列活动 ')+CatalogCore.monthDay(v.stage_start)));if(v.stage_end&&v.stage_end!==v.stage_start?.slice(0,10))box.append(el('p','该阶段至 '+CatalogCore.monthDay(v.stage_end)));strip.append(box)});parent.append(strip)}
 window.ActivityDetails={render:activityProfile};
 const editionSelection=new Map();const linkedEdition=new URL(location.href).searchParams.get('edition');if(linkedEdition)for(const entry of catalog.entries)if(entry.versions.some(v=>v.source_url===linkedEdition))editionSelection.set(entry.id,linkedEdition);
 function card(entry){
  const candidates=entry.versions.filter(v=>core.selectedVersion({...entry,versions:[v]},state,now())).sort((a,b)=>(b.published||'').localeCompare(a.published||''));
  const picked=editionSelection.get(entry.id);
  const version=candidates.find(v=>v.source_url===picked)||core.selectedVersion(entry,state,now());
  const status=core.phase(version,entry.kind,now()),a=el('article',undefined,'entry');a.dataset.id=entry.id;
  const top=el('div',undefined,'entry-top'),category=el('div',entry.category_label,'entry-category');
  for(const level of version.levels||[]){if(level==='unknown')continue;const b=el('button',catalog.levels[level],'scope-tag');b.type='button';b.addEventListener('click',()=>select('level',level));category.append(b)}
  top.append(category,el('span',status.label,'phase '+status.tone));const heading=el('h3'),titleButton=el('button',entry.title,'entry-title-button');titleButton.type='button';titleButton.setAttribute('aria-expanded','false');titleButton.setAttribute('aria-label',entry.title+'：展开详情');heading.append(titleButton);a.append(top,heading);
  const meta=el('div',undefined,'entry-meta');if(version.year)addTag(meta,version.year+' 年','year',String(version.year));
  const facts=version.participation_facts||[];
  const audience=version.audience||facts.find(f=>f.kind==='audience')?.value;
  if(show('card_audience')&&audience)a.append(el('p','适合谁 · '+audience,'entry-audience compact-clause'));
  const keyFact=facts.find(f=>show(f.kind)&&f.kind==='registration')||facts.find(f=>show(f.kind)&&f.kind==='materials')||facts.find(f=>show(f.kind)&&f.kind==='content');
  if(show('editorial_notes')&&entry.editorial_note)a.append(el('p',entry.editorial_note,'entry-takeaway compact-clause'));
  else if(keyFact)a.append(el('p',displayText(keyFact.value),'entry-takeaway compact-clause'));
  const keyDate=show('card_dates')&&(version.deadline||version.stage_start);
  if(keyDate)a.append(el('p',(version.deadline?'所列截止 · ':'活动日期 · ')+date(keyDate),'compact-date'));
  else if(show('card_dates')){const timing=facts.find(f=>show(f.kind)&&['schedule','registration'].includes(f.kind)&&/\d{1,2}月\d{1,2}日|20\d{2}-\d{2}-\d{2}/.test(f.value));if(timing&&timing!==keyFact)a.append(el('p','时间 · '+timing.value,'compact-date compact-clause'));else if(!timing)a.append(el('p',(version.year?version.year+' 年':'历史')+'公告','compact-date'))}
  if(state.view==='compare'&&show('past_versions'))annualCompare(a,entry);
  const d=el('details',undefined,'entry-details');d.append(el('summary','查看详情'+(entry.versions.length>1?' · '+entry.versions.length+' 个公告版本':'')));titleButton.addEventListener('click',()=>{d.open=!d.open});d.addEventListener('toggle',()=>{titleButton.setAttribute('aria-expanded',String(d.open));titleButton.setAttribute('aria-label',entry.title+(d.open?'：收起详情':'：展开详情'))});const body=el('div',undefined,'detail-content');
  const quickFacts=[];if(audience&&show('audience'))quickFacts.push(['参与对象',audience]);if(show('card_dates')&&version.deadline)quickFacts.push(['原文所列截止',date(version.deadline)]);const materials=facts.filter(f=>show('materials')&&f.kind==='materials').map(f=>displayText(f.value));if(materials.length)quickFacts.push(['需交材料',materials.join('；')]);
  if(quickFacts.length){const quick=el('dl',undefined,'detail-quickfacts');for(const [label,value] of quickFacts){quick.append(el('dt',label),el('dd',value))}body.append(quick)}
  body.append(meta);
  if(show('editorial_notes')&&entry.editorial_note)body.append(el('h4','补充说明'),el('p',entry.editorial_note));
  if(show('past_versions')&&entry.versions.length>1){const row=el('label',undefined,'edition-control');row.append(el('span','往届与通知版本'));const control=el('select');control.setAttribute('aria-label',entry.title+'的公告版本');for(const v of candidates){const option=el('option',(v.edition_label||v.year+'年')+' · '+(v.published||'日期未注明'));option.value=v.source_url;option.selected=v===version;control.append(option)}control.addEventListener('change',()=>{editionSelection.set(entry.id,control.value);const next=card(entry);next.querySelector('.entry-details').open=true;a.replaceWith(next);next.querySelector('select')?.focus()});row.append(control);body.append(row)}
  if(show('audience')&&audience&&!facts.some(f=>f.kind==='audience'&&f.value===audience))body.append(el('p','参与对象：'+audience));
  activityProfile(body,version);
  evidence(body,entry);
  const r=version.source_detail||entry.source_detail;
  if(show('full_text')&&!facts.length&&r?.requirements){const list=el('ul');for(const text of r.requirements.split(/\n|(?<=[。；])\s*/).filter(Boolean))list.append(el('li',text));body.append(list)}
  const source=el('div',undefined,'entry-source');if(show('published_dates')&&version.published)source.append(el('span','发布于 '+date(version.published)));if(show('source_links')&&safeCduUrl(version.source_url))source.append(link('官方原文',version.source_url));body.append(source);
  if(show('source_links')&&r?.related_sources?.length){const related=el('details');related.append(el('summary','补充通知'));for(const item of r.related_sources)if(safeCduUrl(item.source_url))related.append(link(item.title,item.source_url));body.append(related)}
  if(show('editorial_notes')&&r?.notes?.length){const notes=r.notes.filter(n=>!/(?:WorkBuddy|DeepSeek|首筛|人工审核|后续.*提取|原文未提供：)/i.test(n)).map(n=>n.replace(/(?:stage_start|stage_end|deadline_kind)[^；。]*/g,'').replace(/，结束日期不重复写年份，/g,'。').replace(/。；/g,'。'));if(notes.length){const ul=el('ul',undefined,'notice-notes');for(const n of notes)ul.append(el('li',n));body.append(ul)}}
  d.append(body);a.append(d);return a;
 }
 function render(){SitePages.show(state.view);if(['home','about','calendar'].includes(state.view))return;const list=document.getElementById('catalog-list');const previous=new Map([...list.querySelectorAll('article')].map(n=>[n.dataset.id,n.getBoundingClientRect()]));document.getElementById('view-description').classList.toggle('sr-only',state.view!=='registration');const rows=catalog.entries.filter(e=>core.matches(e,state,now())).sort((a,b)=>(core.selectedVersion(b,state,now()).published||'').localeCompare(core.selectedVersion(a,state,now()).published||''));document.getElementById('result-title').textContent=state.view==='compare'?'往届对比':state.view==='reference'?'资料库':state.view==='all'?'全部活动':state.view==='registration'?'当前报名':'精选活动';document.getElementById('count').textContent=rows.length+' 项结果';
  document.getElementById('view-description').textContent=state.view==='compare'?'同一系列按年份对照；筛选学院和年份时，以同一年度的组织信息匹配。':state.view==='registration'?'仅列出原文明示报名起止、且今天仍在报名期内的公告。没有明确报名期的记录可在全部活动查找。':state.view==='reference'?'普通讲座、数据库培训、考试提醒和办事参考放在这里，按需查找。': '优先看需要组队、准备作品或提出申请的竞赛、项目、实践与招募。时间和资格请回到原文确认。';
  list.replaceChildren(...rows.slice(0,visibleLimit).map(card));animateResults(list,previous);if(rows.length>visibleLimit){const more=el('button','再看 12 项 · '+visibleLimit+' / '+rows.length,'primary-button');more.type='button';more.addEventListener('click',()=>{visibleLimit+=12;render();const firstNew=list.querySelectorAll('article')[visibleLimit-12];if(firstNew){const heading=firstNew.querySelector('h3');heading.tabIndex=-1;heading.focus()}});list.append(more)}if(!rows.length){const e=el('div',undefined,'empty');e.append(el('h3','没有匹配的活动'),el('p',state.view==='registration'?'没有找到可确认仍在报名期内的匹配公告，可清除筛选或查看全部活动。':state.month==='unknown'?'当前类型没有日期待补的记录。':state.month?'这个月份暂未收录匹配记录，试试全年或其他类型。':'试试其他类型，或清除筛选。'));if(state.month){const all=el('button','查看全年','text-button');all.type='button';all.addEventListener('click',()=>select('month',''));e.append(all)}if(state.interest!=='any'){const any=el('button','不限学院查看','text-button');any.type='button';any.addEventListener('click',()=>{try{localStorage.removeItem('cdu-college-preference')}catch{}select('interest','any')});e.append(any)}const b=el('button','清除全部筛选','primary-button');b.type='button';b.addEventListener('click',reset);e.append(b);list.append(e)}
  const tags=document.getElementById('active-tags');tags.replaceChildren();if(state.interest!=='any'){const b=el('button','适合 '+catalog.colleges[state.interest]+' ×','filter-tag');b.addEventListener('click',()=>{try{localStorage.removeItem('cdu-college-preference')}catch{}select('interest','any')});tags.append(b)}
  for(const key of ['q','college','level','year','category','phase','month']){if(!state[key])continue;const values=key==='category'?state.category.split(','):[state[key]];for(const value of values){const text=key==='q'?'搜索：'+value:key==='category'?categories[value]:key==='month'?(value==='unknown'?'日期待补':value+'月')+' · '+(state.month_basis==='seasonal'?'往年参与':state.month_basis==='deadline'?'所列截止':'举办时间'):document.getElementById(key).selectedOptions[0]?.textContent||value;const b=el('button',text,'filter-tag');b.type='button';b.append(el('span','×'));b.setAttribute('aria-label','移除筛选：'+text);b.addEventListener('click',()=>select(key,key==='category'?state.category.split(',').filter(k=>k!==value).join(','):''));tags.append(b)}}
  const n=['college','level','year','phase'].filter(k=>state[k]).length;filters.querySelector('summary').textContent='更多筛选'+(n?' · '+n:'');

 }
 function reset(){try{localStorage.removeItem('cdu-college-preference')}catch{}visibleLimit=12;for(const k of filterKeys)state[k]=k==='month_basis'?'seasonal':k==='interest'?'any':'';saveState();syncControls();render()}
 document.getElementById('my-college').addEventListener('change',e=>{try{localStorage.setItem('cdu-college-preference',e.target.value)}catch{}select('interest',e.target.value)});
 document.getElementById('reset').addEventListener('click',reset);document.getElementById('clear-query').addEventListener('click',()=>select('q',''));
 document.querySelector('.skip').addEventListener('click',e=>{e.preventDefault();state.view='all';saveState();syncControls();render();const results=document.getElementById('results');results.tabIndex=-1;results.focus();results.scrollIntoView({block:'start',behavior:reduced.matches?'instant':'smooth'})});
 for(const key of ['college','level','year','phase','month_basis'])document.getElementById(key).addEventListener('change',e=>select(key,e.target.value));
 document.getElementById('query').addEventListener('input',e=>select('q',e.target.value));
 document.getElementById('views').addEventListener('click',e=>{const a=e.target.closest('[data-view]');if(!a||e.ctrlKey||e.metaKey||e.shiftKey||e.altKey||e.button!==0)return;e.preventDefault();visibleLimit=12;state.view=a.dataset.view;saveState();syncControls();render()});
 addEventListener('hashchange',()=>{readState();syncControls();render()});addEventListener('popstate',()=>{readState();syncControls();render()});

 const reduced=matchMedia('(prefers-reduced-motion:reduce)');
 function moveNav(){if(document.getElementById('query-page').hidden)return;const nav=document.getElementById('views'),active=nav.querySelector('[aria-current]');if(!active)return;let line=nav.querySelector('.nav-line');if(!line){line=el('span',undefined,'nav-line');line.setAttribute('aria-hidden','true');nav.append(line)}line.style.transform='translateX('+active.offsetLeft+'px) scaleX('+active.offsetWidth+')'}
 function animateResults(list,previous){if(document.documentElement.dataset.inputMethod==='keyboard'||document.activeElement?.id==='query'||reduced.matches)return;if(!hasRendered){hasRendered=true;return}if(!Element.prototype.animate)return;let i=0;for(const n of list.querySelectorAll('article')){const old=previous.get(n.dataset.id),rect=n.getBoundingClientRect();if(reduced.matches){n.animate([{opacity:.7},{opacity:1}],{duration:70});continue}if(old){const dy=old.top-rect.top;if(Math.abs(dy)>1&&Math.abs(dy)<innerHeight)n.animate([{transform:'translateY('+dy+'px)'},{transform:'translateY(0)'}],{duration:180,easing:'cubic-bezier(.23,1,.32,1)'})}else if(i<6){n.animate([{opacity:.65,transform:'translateY(5px)'},{opacity:1,transform:'translateY(0)'}],{duration:140,delay:0,easing:'cubic-bezier(.16,1,.3,1)',fill:'backwards'});i++}}}
 document.addEventListener('toggle',event=>{if(!event.target.open||!event.target.classList.contains('entry-details'))return;const body=event.target.querySelector('.detail-content');if(body?.animate&&document.documentElement.dataset.inputMethod!=='keyboard')body.animate(reduced.matches?[{opacity:.7},{opacity:1}]:[{opacity:.4,transform:'translateY(-5px)'},{opacity:1,transform:'translateY(0)'}],{duration:reduced.matches?70:220,easing:'cubic-bezier(.16,1,.3,1)'})},true);
 addEventListener('resize',moveNav);

 readState();syncControls();render();
})();
