/* A small, local-only souvenir. No analytics, account, or network progress sync. */
(() => {
 'use strict';
 const KEY='cdu-headsup:souvenir:v1',asset=new URL('souvenir-art.png',document.currentScript.src);
 const required=[...new Set([...document.querySelectorAll('.global-nav a[data-page],#views a[data-view],.life-switch a[data-life-tab]')].map(a=>a.hash.slice(1)).filter(Boolean))];
 if(!required.length)return;
 const reduced=matchMedia('(prefers-reduced-motion:reduce)');
 const make=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text)n.textContent=text;return n};
 let storageOK=true,state={visited:[],claimed:null},visitTimer=null,printTimer=null,sequence=0,source=null,canvas=null,imageURL=null,loadingArt=null;
 function valid(raw){if(!raw||typeof raw!=='object')return {visited:[],claimed:null};return {visited:Array.isArray(raw.visited)?raw.visited.filter(v=>required.includes(v)):[],claimed:raw.claimed&&/^HX-[A-F0-9]{8}$/.test(raw.claimed.serial||'')?{serial:raw.claimed.serial}:null}}
 function read(){try{return valid(JSON.parse(localStorage.getItem(KEY)||'null'))}catch(_){storageOK=false;return {visited:[],claimed:null}}}
 state=read();
 function save(){const other=read();state.visited=[...new Set([...other.visited,...state.visited])];state.claimed=state.claimed||other.claimed;try{localStorage.setItem(KEY,JSON.stringify({schema:1,...state}))}catch(_){storageOK=false}}
 const unlocked=()=>required.every(key=>state.visited.includes(key));
 const entry=make('section','souvenir-invitation');entry.hidden=true;entry.setAttribute('aria-labelledby','souvenir-invitation-title');
 const intro=make('div'),heading=make('h2','','你把这里，逛了一圈。');heading.id='souvenir-invitation-title';intro.append(make('p','souvenir-eyebrow','A LITTLE SOMETHING FOR YOU'),heading,make('p','','有张纪念票，想留给这份好奇。'));
 const claim=make('button','souvenir-claim','领取这段好奇 ↗');claim.type='button';entry.append(intro,claim);
 const ending=document.querySelector('#landing .home-end');if(ending)ending.before(entry);else document.getElementById('landing').append(entry);
 const nav=document.querySelector('.global-nav'),navButton=make('button','souvenir-nav'),thumb=make('img');navButton.type='button';navButton.hidden=true;navButton.setAttribute('aria-label','查看已收藏的校园漫游纪念票');navButton.title='我的校园漫游纪念票';thumb.alt='校园漫游纪念票';thumb.width=90;thumb.height=30;navButton.append(thumb);nav.append(navButton);
 const toast=make('div','souvenir-toast');toast.hidden=true;toast.setAttribute('role','status');toast.append(make('span','','首页好像，多了一样东西。'));const look=make('a','','去看看 ↗');look.href='#home';look.onclick=()=>{toast.hidden=true};toast.append(look);document.body.append(toast);
 const dialog=make('dialog','souvenir-dialog');dialog.setAttribute('aria-labelledby','souvenir-dialog-title');
 const top=make('div','souvenir-dialog-nav'),home=make('button','','← 返回首页'),close=make('button','','关闭 ×');home.type=close.type='button';top.append(home,close);
 const body=make('div','souvenir-dialog-body'),title=make('h2','','给好奇的人，一张纪念票。');title.id='souvenir-dialog-title';
 const printer=make('div','souvenir-printer'),slot=make('div','souvenir-slot'),paper=make('div','souvenir-paper'),ticket=make('img');ticket.alt='成大早知道校园漫游纪念票';paper.append(ticket);printer.append(slot,paper);
 const status=make('p','souvenir-status');status.setAttribute('role','status');status.setAttribute('aria-live','polite');
 const actions=make('div','souvenir-actions'),print=make('button','souvenir-print','收好这张票 ↗'),download=make('button','souvenir-download','保存票面图片 ↓');print.type=download.type='button';download.hidden=true;actions.append(print,download);body.append(make('p','souvenir-eyebrow','CDU HEADSUP / CAMPUS PASS'),title,printer,status,actions);dialog.append(top,body);document.body.append(dialog);
 function serial(){const bytes=new Uint8Array(4);if(globalThis.crypto?.getRandomValues)crypto.getRandomValues(bytes);else for(let i=0;i<4;i++)bytes[i]=Math.floor(Math.random()*256);return 'HX-'+[...bytes].map(v=>v.toString(16).padStart(2,'0')).join('').toUpperCase()}
 function art(){if(!loadingArt)loadingArt=new Promise((resolve,reject)=>{const image=new Image();const timer=setTimeout(()=>reject(new Error('art timeout')),12000);image.onload=()=>{clearTimeout(timer);resolve(image)};image.onerror=()=>{clearTimeout(timer);reject(new Error('art unavailable'))};image.src=asset.href}).catch(e=>{loadingArt=null;throw e});return loadingArt}
 async function draw(record){
  const image=await art(),c=document.createElement('canvas');c.width=image.naturalWidth;c.height=image.naturalHeight;const ctx=c.getContext('2d');if(!ctx)throw new Error('canvas unavailable');ctx.drawImage(image,0,0);
  const scale=c.width/2172;ctx.scale(scale,scale);ctx.fillStyle='#6b1723';ctx.textBaseline='alphabetic';
  const sans='"CDU Sans","Manrope","PingFang SC","Microsoft YaHei",system-ui,sans-serif';
  function spaced(text,x,y,gap){for(const char of text){ctx.fillText(char,x,y);x+=ctx.measureText(char).width+gap}}
  ctx.font='600 24px '+sans;spaced('CAMPUS / COLLECTIBLE PASS',122,153,5);
  ctx.font='650 126px '+sans;ctx.fillText('漫游纪念票',112,344);
  ctx.font='400 34px '+sans;ctx.fillText('给每一个愿意多看一眼的人',122,439);
  ctx.globalAlpha=.35;ctx.fillRect(122,506,1085,1);ctx.globalAlpha=1;
  ctx.font='600 30px '+sans;ctx.fillText('成大早知道',122,575);
  ctx.font='400 19px '+sans;spaced('A LITTLE CURIOSITY / A LONG WAY',122,623,3);
  c.dataset.serial=record.serial;return c;
 }
 function useCanvas(c){canvas=c;imageURL=c.toDataURL('image/png');ticket.src=imageURL;if(state.claimed?.serial===c.dataset.serial){thumb.src=imageURL;thumb.dataset.serial=c.dataset.serial}}
 function render(){entry.hidden=!unlocked()||!!state.claimed;navButton.hidden=!state.claimed;if(state.claimed&&thumb.dataset.serial!==state.claimed.serial){const serial=state.claimed.serial;thumb.dataset.serial=serial;if(imageURL&&canvas?.dataset.serial===serial)thumb.src=imageURL;else{thumb.src=asset.href;draw(state.claimed).then(c=>{if(state.claimed?.serial===serial)thumb.src=c.toDataURL('image/png')}).catch(()=>{delete thumb.dataset.serial})}}}
 function dismiss(toHome=false){++sequence;clearTimeout(printTimer);printTimer=null;dialog.classList.remove('is-printing','is-collected');if(dialog.open)dialog.close();render();document.body.classList.remove('souvenir-open');if(toHome){location.hash='home';window.scrollTo({top:0,behavior:'instant'})}else{const focus=state.claimed?navButton:source;if(focus&&!focus.hidden)focus.focus({preventScroll:true})}}
 close.onclick=()=>dismiss();home.onclick=()=>dismiss(true);dialog.addEventListener('cancel',e=>{e.preventDefault();dismiss()});
 async function open(event){
  if(!unlocked()&&!state.claimed)return;source=event.currentTarget;const attempt=++sequence;clearTimeout(printTimer);dialog.classList.remove('is-printing','is-collected');toast.hidden=true;
  title.textContent=state.claimed?'这份好奇，已经收好了。':'给好奇的人，一张纪念票。';status.textContent='正在准备票面…';print.hidden=!!state.claimed;print.disabled=true;download.hidden=!state.claimed;download.disabled=true;
  document.body.classList.add('souvenir-open');dialog.showModal();close.focus({preventScroll:true});
  try{const c=await draw(state.claimed||{serial:serial()});if(attempt!==sequence||!dialog.open)return;useCanvas(c);print.disabled=false;download.disabled=false;status.textContent=state.claimed?'从顶部的票根，随时回来看看。':'你已经打开过这里的全部一、二级栏目。';if(!storageOK)status.textContent+=' 当前浏览器无法保存收藏，关闭后不会保留。';if(!state.claimed)print.click()}
  catch(_){if(attempt!==sequence||!dialog.open)return;status.textContent='票面暂时没有加载成功，请关闭后再试一次。';print.disabled=true;download.disabled=true}
 }
 claim.onclick=open;navButton.onclick=open;
 print.onclick=async()=>{
  if(print.disabled||state.claimed||!canvas)return;const attempt=++sequence,record={serial:serial()};print.disabled=true;status.textContent='正在出票…';
  try{const c=await draw(record);if(attempt!==sequence||!dialog.open)return;useCanvas(c);dialog.classList.add('is-printing');
   printTimer=setTimeout(()=>{if(attempt!==sequence||!dialog.open)return;state.claimed=record;save();render();dialog.classList.add('is-collected');print.hidden=true;download.hidden=false;download.disabled=false;title.textContent='这份好奇，收好了。';status.textContent=storageOK?'纪念票已放到顶部菜单栏。':'纪念票已收好；当前浏览器无法持久保存，可以下载留念。';download.focus({preventScroll:true})},reduced.matches?0:2100);
  }catch(_){if(attempt!==sequence)return;print.disabled=false;status.textContent='出票没有完成，请再试一次。'}
 };
 download.onclick=()=>{if(!canvas||download.disabled)return;canvas.toBlob(blob=>{if(!blob){status.textContent='保存失败，请稍后再试。';return}const url=URL.createObjectURL(blob),a=make('a');a.href=url;a.download='成大早知道-校园漫游纪念票.png';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),30000)},'image/png')};
 function key(){const hash=location.hash.slice(1).split('?')[0];return hash.startsWith('guide/')?'guides':required.includes(hash)?hash:(!hash?'home':null)}
 function schedule(){clearTimeout(visitTimer);if(document.visibilityState!=='visible')return;const current=key();if(!current)return;visitTimer=setTimeout(()=>{if(key()!==current||document.visibilityState!=='visible')return;const expected=['home','about','calendar'].includes(current)?current:['guides','services'].includes(current)?'guides':'query';if(document.body.dataset.page!==expected)return;const was=unlocked();state.visited=[...new Set([...state.visited,current])];save();render();if(!was&&unlocked()&&!state.claimed){toast.hidden=false;art().catch(()=>{})}},1400)}
 document.addEventListener('cdu:view',()=>queueMicrotask(schedule));addEventListener('hashchange',schedule);document.addEventListener('visibilitychange',schedule);addEventListener('storage',e=>{if(e.key!==KEY)return;const other=read();state={visited:[...new Set([...state.visited,...other.visited])],claimed:state.claimed||other.claimed};render()});
 addEventListener('pageshow',()=>{render();schedule()});Promise.resolve(window.CduInitialViewReady).then(()=>{render();schedule()});
})();
