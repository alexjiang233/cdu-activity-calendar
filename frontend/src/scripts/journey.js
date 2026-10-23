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
 let flight=null,animation=null,note=null,timer,fold=null,foldAnimations=[],run=0;
 function clean(){++run;clearTimeout(timer);animation?.cancel();animation=null;foldAnimations.forEach(a=>a.cancel());foldAnimations=[];fold?.remove();fold=null;flight?.remove();flight=null;note?.remove();note=null;button.disabled=false;button.classList.remove('plane-folding')}
 function end(){flight?.remove();flight=null;animation=null;button.classList.remove('plane-folding');button.disabled=false;if(document.body.dataset.page!=='about')return;note=document.createElement('div');note.className='paper-plane-note';note.setAttribute('role','status');note.textContent='愿每一点好奇，都有去处。';document.body.append(note);timer=setTimeout(clean,2400)}
 button.addEventListener('click',async()=>{
  if(button.disabled)return;clean();button.disabled=true;const attempt=run;
  if(reduced.matches){end();return}
  const r=button.getBoundingClientRect(),x=r.left+r.width/2,y=r.top+r.height/2;
  fold=document.createElement('div');fold.className='paper-plane-fold';fold.setAttribute('aria-hidden','true');Object.assign(fold.style,{left:r.left+'px',top:r.top+'px',width:r.width+'px',height:r.height+'px'});fold.innerHTML='<i class="fold-sheet"></i><i class="fold-wing fold-left"></i><i class="fold-wing fold-right"></i><i class="fold-keel"></i>';document.body.append(fold);button.classList.add('plane-folding');
  const animate=(sel,frames,options)=>{const a=fold.querySelector(sel).animate(frames,{duration:1800,fill:'forwards',easing:'cubic-bezier(.4,0,.2,1)',...options});foldAnimations.push(a);return a};
  animate('.fold-sheet',[{opacity:1},{opacity:0,offset:.45},{opacity:0}]);
  animate('.fold-left',[{transform:'rotateY(0deg)'},{transform:'rotateY(-148deg)',offset:.6},{transform:'rotateY(-168deg) rotateZ(-14deg)',opacity:0}]);
  animate('.fold-right',[{transform:'rotateY(0deg)'},{transform:'rotateY(0deg)',offset:.2},{transform:'rotateY(148deg)',offset:.8},{transform:'rotateY(168deg) rotateZ(14deg)',opacity:0}]);
  const crease=animate('.fold-keel',[{transform:'scaleY(.15) scaleX(.2)',opacity:0},{transform:'scaleY(1) scaleX(.35)',opacity:1,offset:.65},{transform:'scaleY(.28) scaleX(.5) rotate(38deg)',opacity:0}]);
  try{await crease.finished}catch(_){return}if(attempt!==run||document.body.dataset.page!=='about')return;fold.remove();fold=null;foldAnimations=[];
  flight=document.createElement('div');flight.className='paper-plane-flight';flight.setAttribute('aria-hidden','true');flight.innerHTML='<svg viewBox="0 0 80 64" fill="none"><path d="M3 32 76 5 50 59 34 39Z" fill="#f9e8c7" stroke="#9b5c55" stroke-width="1.5"/><path d="M34 39 76 5 23 33m11 6 1 15 9-11" stroke="#9b5c55" stroke-width="1.5"/></svg>';
  Object.assign(flight.style,{left:x+'px',top:y+'px'});document.body.append(flight);button.classList.add('plane-folding');
  const w=innerWidth,h=innerHeight,points=[[x,y],[w*.48,h*.24],[w*.18,h*.53],[w*.43,h*.73],[w*.76,h*.48],[w*.58,h*.22],[w+100,h*.12]],samples=[];
  for(let i=0;i<points.length-1;i++){const a=points[Math.max(0,i-1)],b=points[i],c=points[i+1],d=points[Math.min(points.length-1,i+2)];for(let k=0;k<24;k++){const t=k/24,t2=t*t,t3=t2*t;const p=[0,1].map(j=>.5*((2*b[j])+(-a[j]+c[j])*t+(2*a[j]-5*b[j]+4*c[j]-d[j])*t2+(-a[j]+3*b[j]-3*c[j]+d[j])*t3));samples.push(p)}}samples.push(points.at(-1));
  let distance=0,angle=null;const lengths=[0];for(let i=1;i<samples.length;i++){distance+=Math.hypot(samples[i][0]-samples[i-1][0],samples[i][1]-samples[i-1][1]);lengths.push(distance)}
  const frames=samples.map((p,i)=>{const q=samples[Math.min(i+1,samples.length-1)],prev=angle??0;let next=i===samples.length-1?prev:Math.atan2(q[1]-p[1],q[0]-p[0])*180/Math.PI+36;if(angle!==null){while(next-prev>180)next-=360;while(next-prev< -180)next+=360}angle=next;const offset=lengths[i]/distance;return{transform:`translate3d(${p[0]-x-40}px,${p[1]-y-32}px,0) rotate(${next}deg)`,opacity:offset<.03?offset/.03:offset>.94?(1-offset)/.06:1,offset}});
  animation=flight.animate(frames,{duration:10000,easing:'linear',fill:'forwards'});animation.onfinish=end;
 });
 addEventListener('hashchange',clean);addEventListener('pagehide',clean);addEventListener('resize',clean);document.addEventListener('visibilitychange',()=>{if(document.hidden)clean()});document.addEventListener('keydown',e=>{if(e.key==='Escape'&&(flight||note||fold))clean()});
})();
