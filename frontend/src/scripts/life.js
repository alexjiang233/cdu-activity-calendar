(()=>{
 'use strict';
 /* 指南与校园查询：数据来自 /api/v1/guides/ 与 /api/v1/services/，不再内嵌。 */
 const meta=window.CduData.meta||{};
 const make=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n};
 const external=(text,url,cls='life-link')=>{const a=make('a',text,cls);a.href=url;a.target='_blank';a.rel='noopener noreferrer';return a};
 const local=(text,url,cls='life-link')=>{const a=make('a',text,cls);a.href=url;return a};
 const reduced=matchMedia('(prefers-reduced-motion:reduce)');
 const icons={network:'M4 8a13 13 0 0 1 24 0M8 13a8 8 0 0 1 16 0M13 18a3 3 0 0 1 6 0M16 23h.01',running:'M18 4h.01M13 10l5-2 5 5 5 1M18 9l-4 9 5 3 1 7M14 18l-5 6H4',club:'M11 13a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM21 13a4 4 0 1 0 0-8M3 27v-4a8 8 0 0 1 16 0v4M23 17a7 7 0 0 1 6 6v4'};
 function icon(type){const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 32 32');svg.setAttribute('aria-hidden','true');const p=document.createElementNS(svg.namespaceURI,'path');p.setAttribute('d',icons[type]||icons.network);svg.append(p);return svg}
 let guideCategory='全部',serviceCategory='全部',lastGuide=null;
 let guideRows=[],serviceRows=[],guidesLoaded=false,servicesLoaded=false;
 function chips(id,values,selected,change){const host=document.getElementById(id);host.replaceChildren();for(const label of ['全部',...values]){const b=make('button',label);b.type='button';b.setAttribute('aria-pressed',String(label===selected));b.addEventListener('click',()=>change(label));host.append(b)}}
 const query=id=>document.getElementById(id).value.trim().toLowerCase();
 function empty(host,clear){const n=make('div',undefined,'life-empty');n.append(make('h2','换个关键词试试。'),make('p','也可以清除筛选，看看已有内容。'));const b=make('button','清除筛选','life-action');b.type='button';b.addEventListener('click',clear);n.append(b);host.append(n)}
 function failure(host,message,retry){const n=make('div',undefined,'life-empty');n.append(make('h2','内容没有加载成功。'),make('p',message||'网络或服务暂时不可用，这不等于没有内容。'));const b=make('button','重试','life-action');b.type='button';b.addEventListener('click',retry);n.append(b);host.append(n)}
 async function loadGuides(){
  if(guidesLoaded)return;
  const host=document.getElementById('guide-grid');
  try{const data=await window.CduApi.guides();guideRows=data.results||[];guidesLoaded=true}
  catch(error){failure(host,'指南数据没有取到：'+(error.message||'网络异常'),()=>{guidesLoaded=false;loadGuides().then(renderGuides)});throw error}
 }
 async function loadServices(){
  if(servicesLoaded)return;
  const host=document.getElementById('service-grid');
  try{const data=await window.CduApi.services();serviceRows=(data.results||[]).map(s=>({
    id:s.id,title:s.name,category:s.category,description:s.description,owner:s.owner,phone:s.phone,
    url:s.url,source:s.source_url,sourceLabel:s.source_label,sourceDate:s.source_date,
    checked:s.checked_on,note:s.note,guide:s.related_guide,location:s.location}));servicesLoaded=true}
  catch(error){failure(host,'校园查询没有取到：'+(error.message||'网络异常'),()=>{servicesLoaded=false;loadServices().then(renderServices)});throw error}
 }
 function renderGuides(){
  chips('guide-filters',[...new Set(guideRows.map(g=>g.category).filter(Boolean))],guideCategory,v=>{guideCategory=v;renderGuides()});
  const q=query('guide-search');const rows=guideRows.filter(g=>(guideCategory==='全部'||g.category===guideCategory)&&[g.title,g.subtitle,g.summary,...(g.tags||[])].join(' ').toLowerCase().includes(q));
  document.getElementById('guide-count').textContent=rows.length+' 篇实用指南';const host=document.getElementById('guide-grid');host.replaceChildren();
  rows.forEach((g,i)=>{const a=local(undefined,'#guide/'+g.id,'guide-card');a.style.setProperty('--i',i);const art=make('div',undefined,'guide-card-art');art.append(icon(g.icon),make('span',g.number,'guide-no'));const metaRow=make('div',undefined,'guide-card-meta');metaRow.append(make('span',g.category),make('span','阅读指南 ↗'));const body=make('div',undefined,'guide-card-body');body.append(metaRow,make('h2',g.title),make('p',g.summary));const tags=make('div',undefined,'guide-tags');(g.tags||[]).forEach(t=>tags.append(make('span',t)));body.append(tags);a.append(art,body);host.append(a)});
  if(!rows.length)empty(host,()=>{guideCategory='全部';document.getElementById('guide-search').value='';renderGuides()});
 }
 async function renderArticle(id){
  const article=document.getElementById('guide-article');article.replaceChildren();
  article.append(local('← 全部校园指南','#guides','life-back'));
  let g=null;
  try{g=await window.CduApi.guide(id)}catch(error){
    if(error.status===404){article.append(make('h1','这篇指南还不存在。'),make('p','返回指南列表，查看已经整理好的内容。'));return}
    failure(article,'这篇指南没有取到：'+(error.message||'网络异常'),()=>renderArticle(id));return;
  }
  const header=make('header',undefined,'guide-detail-header');header.append(make('p',g.category+' / 操作指南','life-kicker'),make('h1',g.title),make('p',g.scope,'life-lead'));article.append(header);
  const layout=make('div',undefined,'guide-detail-layout'),toc=make('aside',undefined,'guide-toc'),body=make('div',undefined,'guide-steps');toc.setAttribute('aria-label','本篇步骤');toc.append(make('h2','这篇怎么用'));
  const warning=make('div',undefined,'guide-context');warning.append(make('strong','使用前看一眼'),make('p',g.caution));body.append(warning);
  (g.sections||[]).forEach((s,i)=>{const sec=make('section',undefined,'guide-step');sec.id='life-step-'+i;const number=String(i+1).padStart(2,'0');sec.append(make('span',number,'step-no'),make('h2',s.title));const ul=make('ul');(s.items||[]).forEach(t=>ul.append(make('li',t)));sec.append(ul);body.append(sec);const b=make('button',number+'  '+s.title);b.type='button';b.addEventListener('click',()=>{sec.scrollIntoView({behavior:reduced.matches?'instant':'smooth',block:'start'});sec.tabIndex=-1;sec.focus({preventScroll:true})});toc.append(b)});
  const faq=make('section',undefined,'guide-faq');faq.append(make('h2','你可能还会问'));(g.faqs||[]).forEach(f=>{const d=make('details');d.append(make('summary',f.q),make('p',f.a));faq.append(d)});body.append(faq);
  const source=make('details',undefined,'guide-source');source.append(make('summary','资料依据与适用范围'),make('p',g.source_note||''),make('p','整理于 '+(meta.published_at||'').slice(0,10)+'。这是资料整理日期，不代表已核实当前系统或本学期规定。'));body.append(source);
  if(g.related_service)body.append(local('遇到问题，查校园查询 ↗','#services','life-action'));
  layout.append(toc,body);article.append(layout);requestAnimationFrame(()=>{document.title=g.title+' · 校园指南'});
 }
 async function copyPhone(b,value){let copied=false;try{await navigator.clipboard.writeText(value);copied=true}catch(_){const t=make('textarea',value);t.style.cssText='position:fixed;opacity:0';document.body.append(t);t.select();try{copied=document.execCommand('copy')}catch(_){}t.remove();b.focus()}
  b.textContent=copied?'已复制':'请手动复制';document.getElementById('life-copy-status').textContent=copied?'已复制号码 '+value:'无法自动复制，号码为 '+value;setTimeout(()=>{if(b.isConnected)b.textContent='复制号码'},1800)}
 function renderServices(){
  chips('service-filters',[...new Set(serviceRows.map(s=>s.category).filter(Boolean))],serviceCategory,v=>{serviceCategory=v;renderServices()});
  const q=query('service-search');const rows=serviceRows.filter(s=>(serviceCategory==='全部'||s.category===serviceCategory)&&[s.title,s.description,s.owner,s.phone||'',s.location||''].join(' ').toLowerCase().includes(q));
  document.getElementById('service-count').textContent=rows.length+' 项服务与入口';const host=document.getElementById('service-grid');host.replaceChildren();
  rows.forEach((s,i)=>{const a=make('article',undefined,'service-card');a.style.setProperty('--i',i);a.dataset.service=s.id;const top=make('div',undefined,'service-card-top');top.append(make('span',s.category),make('span',String(i+1).padStart(2,'0'),'service-no'));a.append(top,make('h2',s.title),make('p',s.description));
   if(s.phone){const phone=make('a',s.phone,'service-phone');phone.href='tel:'+s.phone.replaceAll('-','');phone.setAttribute('aria-label','拨打'+s.phone);a.append(phone)}
   const actions=make('div',undefined,'service-actions');if(s.url)actions.append(external(s.phone?'部门官网 ↗':'打开官方入口 ↗',s.url));if(s.phone){const b=make('button','复制号码');b.type='button';b.addEventListener('click',()=>copyPhone(b,s.phone));actions.append(b)}if(s.guide)actions.append(local('操作指南','#guide/'+s.guide));a.append(actions);
   const details=make('details',undefined,'service-source');details.append(make('summary','来源与使用说明'));const p=make('p');if(s.source)p.append(external(s.sourceLabel||'来源',s.source));else p.append(make('span','来源信息待补'));details.append(p);if(s.sourceDate)details.append(make('p','来源发布：'+s.sourceDate));if(s.checked)details.append(make('p','入口或来源核对：'+s.checked+'。未进行电话接通测试。'));if(s.note)details.append(make('p',s.note));a.append(details);host.append(a)});
  if(!rows.length)empty(host,()=>{serviceCategory='全部';document.getElementById('service-search').value='';renderServices()});
 }
 async function route(){
  const page=document.body.dataset.page;if(page!=='guides')return;
  const isServices=location.hash==='#services',id=location.hash.startsWith('#guide/')?location.hash.slice(7):null;
  document.getElementById('guide-index').hidden=!!id||isServices;document.getElementById('guide-article').hidden=!id;document.getElementById('services-page').hidden=!isServices;
  document.querySelectorAll('[data-life-tab]').forEach(a=>{if(a.getAttribute('href')===(isServices?'#services':'#guides'))a.setAttribute('aria-current','page');else a.removeAttribute('aria-current')});
  try{
   if(id){await renderArticle(id);if(lastGuide!==id)window.scrollTo({top:0,behavior:'instant'})}
   else if(isServices){await loadServices();renderServices()}
   else {await loadGuides();renderGuides()}
  }catch(_){/* 失败状态已由各加载函数渲染 */}
  lastGuide=id;
 }
 document.getElementById('guide-search').addEventListener('input',()=>{if(guidesLoaded)renderGuides()});
 document.getElementById('service-search').addEventListener('input',()=>{if(servicesLoaded)renderServices()});
 document.addEventListener('cdu:view',route);route();
})();
