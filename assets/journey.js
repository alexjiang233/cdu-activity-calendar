/* A fictional visual interlude, never an OS or security warning. */
(() => {
 'use strict';
 const heading=document.getElementById('about-title'),deck=document.querySelector('#about .about-heading .editorial-deck');
 if(!heading||!deck||document.querySelector('[data-journey-trigger]'))return;
 const storyURL=new URL('journey.html',document.currentScript.src);storyURL.search=new URL(document.currentScript.src).search;storyURL.searchParams.set('via','about');
 const reduced=matchMedia('(prefers-reduced-motion:reduce)');
 let sceneController=null;let ready=null,sequence=0,leaving=false,source=null,fracture=null,scrollBefore=0;
 const inertBefore=new Map();
 const make=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text)n.textContent=text;return n};
 const dialog=make('dialog','journey-door');dialog.setAttribute('aria-labelledby','journey-door-title');dialog.setAttribute('aria-describedby','journey-door-description');
 const close=make('button','journey-door-close','返回 ×');close.type='button';close.setAttribute('aria-label','关闭彩蛋，返回关于');
 const panel=make('div','journey-door-panel');panel.append(make('p','journey-door-code','OUTSIDE THE INDEX'));
 const seal=make('div','journey-door-seal','');seal.setAttribute('aria-hidden','true');panel.append(seal);
 const title=make('h2','','这里，好像多了一页。');title.id='journey-door-title';
 const description=make('p','journey-door-description','不是新的功能。是我们走来时，留下的一点痕迹。');description.id='journey-door-description';
 const proceed=make('button','journey-door-proceed','再往里走一步 ↗');proceed.type='button';
 const status=make('p','journey-door-status');status.setAttribute('role','status');status.setAttribute('aria-live','polite');
 panel.append(title,description,proceed,status);dialog.append(close,panel,make('p','journey-door-foot','目录之外 / 来时的方向'));document.body.append(dialog);
 function trigger(id,text,kind){const n=make('button','journey-trigger journey-'+kind,text);n.id=id;n.type='button';n.dataset.journeyTrigger=kind;n.setAttribute('aria-label','打开来时路的隐藏入口');n.addEventListener('click',open);return n}
 const walker=document.createTreeWalker(heading,NodeFilter.SHOW_TEXT);let leaf,last;
 while((leaf=walker.nextNode()))if(leaf.textContent.trim())last=leaf;
 if(last&&/。\s*$/.test(last.textContent)){const index=last.textContent.lastIndexOf('。');last.replaceWith(document.createTextNode(last.textContent.slice(0,index)),trigger('journey-period','。','period'),document.createTextNode(last.textContent.slice(index+1)))}
 deck.replaceChildren(trigger('journey-subtitle',deck.textContent,'subtitle'));
 function prime(){
  if(ready)return ready;
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000);
  const request=fetch(storyURL,{signal:controller.signal,credentials:'same-origin'}).then(r=>{if(!r.ok)throw new Error('Journey unavailable');return r.text()}).finally(()=>clearTimeout(timer));
  ready=request;request.catch(()=>{if(ready===request)ready=null});return request;
 }
 function restore(){document.body.classList.remove('journey-distorting','journey-leaving','journey-door-open');fracture?.remove();fracture=null;for(const[n,value]of inertBefore)n.inert=value;inertBefore.clear();leaving=false;proceed.disabled=false}
 function reset(focus=true){++sequence;sceneController?.abort();sceneController=null;if(dialog.open)dialog.close();restore();status.textContent='';if(document.body.dataset.page==='about'){window.scrollTo({top:scrollBefore,behavior:'instant'});if(focus)source?.focus({preventScroll:true})}}
 function open(event){if(leaving||document.body.dataset.page!=='about')return;source=event.currentTarget;scrollBefore=window.scrollY;status.textContent='';document.body.classList.add('journey-door-open');dialog.showModal();proceed.focus({preventScroll:true});prime().catch(()=>{})}
 const doorHome=make('button','journey-door-home','← 返回首页');doorHome.type='button';doorHome.onclick=()=>{reset(false);location.hash='home';window.scrollTo({top:0,behavior:'instant'})};dialog.prepend(doorHome);
 close.addEventListener('click',()=>reset());dialog.addEventListener('cancel',event=>{event.preventDefault();reset()});
 const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
 proceed.addEventListener('click',async()=>{
  if(leaving||!dialog.open)return;const attempt=++sequence;leaving=true;proceed.disabled=true;status.textContent='正在打开那一页…';
  try{
   await prime();if(attempt!==sequence||document.body.dataset.page!=='about')return;
   dialog.close();document.body.classList.remove('journey-door-open');document.body.classList.add('journey-leaving');
   for(const n of document.querySelectorAll('body > header,body > main,body > footer')){inertBefore.set(n,n.inert);n.inert=true}
   sceneController=new AbortController();await window.CduJourneyScene.play({signal:sceneController.signal,reduced:reduced.matches,onHome:()=>{reset(false);location.hash='home';window.scrollTo({top:0,behavior:'instant'})}});
   if(attempt!==sequence)return;try{sessionStorage.setItem('cdu-journey-focus',source.id)}catch(_){}location.assign(storyURL.href);
  }catch(_){if(attempt!==sequence)return;restore();document.body.classList.add('journey-door-open');if(!dialog.open)dialog.showModal();status.textContent='那一页暂时没有打开，再试一次？';proceed.focus({preventScroll:true})}
 });
 document.addEventListener('keydown',event=>{if(event.key==='Escape'&&(dialog.open||leaving)){event.preventDefault();event.stopImmediatePropagation();reset()}},true);
 document.addEventListener('cdu:view',()=>{if(document.body.dataset.page!=='about'&&(dialog.open||leaving))reset(false)});
 function restoreFocus(){let id;try{id=sessionStorage.getItem('cdu-journey-focus');sessionStorage.removeItem('cdu-journey-focus')}catch(_){}if(id&&document.body.dataset.page==='about')document.getElementById(id)?.focus({preventScroll:true})}
 addEventListener('pageshow',event=>{if(event.persisted){reset(false);restoreFocus()}});Promise.resolve(window.CduInitialViewReady).then(()=>requestAnimationFrame(restoreFocus));
})();

/* One little flight, on demand. No storage, tracking, assets or animation loop. */
(()=>{
 const art=document.querySelector('#about .art-about'),paper=art?.querySelector('.paper-two');
 if(!paper||art.querySelector('.paper-plane-trigger'))return;
 const reduced=matchMedia('(prefers-reduced-motion:reduce)'),button=document.createElement('button');
 button.type='button';button.className=paper.className+' paper-plane-trigger';button.innerHTML=paper.innerHTML;button.setAttribute('aria-label','让这一页折成纸飞机');button.title='好像，能飞起来';
 art.removeAttribute('aria-hidden');for(const n of art.children)n.setAttribute('aria-hidden','true');paper.replaceWith(button);
 let flight=null,animation=null,note=null,timer;
 function clean(){clearTimeout(timer);animation?.cancel();animation=null;flight?.remove();flight=null;note?.remove();note=null;button.disabled=false;button.classList.remove('plane-folding')}
 function end(){flight?.remove();flight=null;animation=null;button.classList.remove('plane-folding');button.disabled=false;if(document.body.dataset.page!=='about')return;note=document.createElement('div');note.className='paper-plane-note';note.setAttribute('role','status');note.textContent='愿每一点好奇，都有去处。';document.body.append(note);timer=setTimeout(clean,2400)}
 button.addEventListener('click',()=>{
  if(button.disabled)return;clean();button.disabled=true;
  if(reduced.matches){end();return}
  const r=button.getBoundingClientRect(),x=r.left+r.width/2,y=r.top+r.height/2;
  flight=document.createElement('div');flight.className='paper-plane-flight';flight.setAttribute('aria-hidden','true');flight.innerHTML='<svg viewBox="0 0 80 64" fill="none"><path d="M3 32 76 5 50 59 34 39Z" fill="#f9e8c7" stroke="#9b5c55" stroke-width="1.5"/><path d="M34 39 76 5 23 33m11 6 1 15 9-11" stroke="#9b5c55" stroke-width="1.5"/></svg>';
  Object.assign(flight.style,{left:x+'px',top:y+'px'});document.body.append(flight);button.classList.add('plane-folding');
  const dx=-x-130,dy=Math.max(-y+55,-230);
  animation=flight.animate([{transform:'translate(-50%,-50%) scale(.2) rotate(-12deg)',opacity:0},{transform:'translate(-50%,-50%) scale(1) rotate(-12deg)',opacity:1,offset:.15},{transform:`translate(${dx*.45}px,${dy-65}px) rotate(-28deg)`,opacity:1,offset:.58},{transform:`translate(${dx}px,${dy+30}px) rotate(-8deg)`,opacity:0}],{duration:2600,easing:'cubic-bezier(.3,.05,.4,1)',fill:'forwards'});animation.onfinish=end;
 });
 addEventListener('hashchange',clean);addEventListener('pagehide',clean);document.addEventListener('visibilitychange',()=>{if(document.hidden)clean()});document.addEventListener('keydown',e=>{if(e.key==='Escape'&&(flight||note))clean()});
})();
