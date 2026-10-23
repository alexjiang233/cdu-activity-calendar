/* Capture only the visible public About surface, then fracture its real DOM. */
(() => {
 const make=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text)n.textContent=text;return n};
 const polygons=['0 0,36% 0,30% 28%,0 23%','36% 0,68% 0,73% 24%,30% 28%','68% 0,100% 0,100% 29%,73% 24%','0 23%,30% 28%,37% 53%,0 48%','30% 28%,73% 24%,66% 52%,37% 53%','73% 24%,100% 29%,100% 56%,66% 52%','0 48%,37% 53%,28% 79%,0 76%','37% 53%,66% 52%,73% 77%,28% 79%','66% 52%,100% 56%,100% 79%,73% 77%','0 76%,28% 79%,35% 100%,0 100%','28% 79%,73% 77%,67% 100%,35% 100%','73% 77%,100% 79%,100% 100%,67% 100%'];
 function snapshot(){
  const host=make('div','journey-snapshot');host.inert=true;host.setAttribute('aria-hidden','true');
  const props=['display','color','background','font','font-family','font-size','font-weight','line-height','letter-spacing','text-align','text-transform','padding','margin','border','border-radius','box-shadow','width','height','max-width','min-width','grid-template-columns','grid-template-rows','gap','align-items','justify-content','flex-direction','flex-wrap','opacity','transform','overflow','position','top','left','right','bottom'];
  function freeze(original){
   if(original.nodeType===Node.TEXT_NODE)return original.cloneNode();
   if(original.nodeType!==Node.ELEMENT_NODE)return null;
   const rect=original.getBoundingClientRect(),style=getComputedStyle(original);
   if(['SCRIPT','DIALOG','STYLE'].includes(original.tagName)||style.display==='none'||style.visibility==='hidden'||rect.bottom<0||rect.top>innerHeight)return null;
   const clone=original.cloneNode(false);clone.removeAttribute('id');clone.removeAttribute('autofocus');clone.removeAttribute('name');
   for(const p of props)clone.style.setProperty(p,style.getPropertyValue(p));
   clone.style.animation='none';clone.style.transition='none';clone.style.pointerEvents='none';
   if(clone.matches('button,a,input,select,textarea'))clone.tabIndex=-1;
   for(const child of original.childNodes){const frozen=freeze(child);if(frozen)clone.append(frozen)}
   return clone;
  }
  for(const original of document.querySelectorAll('body > header,#about,body > footer')){
   const rect=original.getBoundingClientRect();if(rect.bottom<0||rect.top>innerHeight)continue;
   const clone=freeze(original);if(!clone)continue;
   Object.assign(clone.style,{position:'absolute',left:rect.left+'px',top:rect.top+'px',width:rect.width+'px',height:rect.height+'px',margin:'0',transform:'none'});host.append(clone);
  }
  return host;
 }
 window.CduJourneyScene={play:async({signal,reduced,onHome})=>{
  let overlay=null,origin=null,wake=null,skipped=false;
  const abortError=()=>new DOMException('Scene cancelled','AbortError');
  function cleanup(){document.body.classList.remove('journey-distorting');overlay?.remove();if(origin?.open)origin.close();origin?.remove()}
  const wait=ms=>new Promise((resolve,reject)=>{
   if(signal.aborted)return reject(abortError());
   let timer;const finish=()=>{clearTimeout(timer);signal.removeEventListener('abort',cancel);wake=null;resolve()};
   const cancel=()=>{clearTimeout(timer);signal.removeEventListener('abort',cancel);wake=null;reject(abortError())};
   timer=setTimeout(finish,ms);wake=finish;signal.addEventListener('abort',cancel,{once:true});
  });
  try{
   if(!reduced){
    const captured=snapshot();overlay=make('div','journey-arcade');overlay.setAttribute('role','region');overlay.setAttribute('aria-label','回到原点的隐藏演出');
    const controls=make('div','journey-scene-controls'),home=make('button','','返回首页'),skip=make('button','','跳过演出');home.type=skip.type='button';home.onclick=onHome;skip.onclick=()=>{skipped=true;wake?.()};controls.append(home,skip);overlay.append(controls);
    const tunnel=make('div','journey-tunnel');tunnel.setAttribute('aria-hidden','true');for(let i=0;i<7;i++){const ring=make('i');ring.style.setProperty('--ring',i);tunnel.append(ring)}overlay.append(tunnel);const scan=make('div','journey-scan');scan.setAttribute('aria-hidden','true');overlay.append(scan);
    const rail=make('div','journey-rails');rail.setAttribute('aria-hidden','true');for(let i=0;i<9;i++){const line=make('i');line.style.setProperty('--i',i);rail.append(line)}overlay.append(rail);
    const caption=make('div','journey-arcade-caption');caption.setAttribute('role','status');caption.append(make('small','','SIGNAL / MEMORY'),make('strong','','这里，少了一段记录。'));overlay.append(caption);
    document.body.append(overlay);home.focus({preventScroll:true});document.body.classList.add('journey-distorting');
    await wait(1600);
    if(!skipped){
     overlay.classList.add('is-fracturing');
     polygons.forEach((polygon,i)=>{const shard=make('div','journey-real-shard');shard.style.clipPath='polygon('+polygon+')';shard.style.setProperty('--dx',((i%3-1)*74+(i%2?14:-14))+'vw');shard.style.setProperty('--dy',((Math.floor(i/3)-1.5)*58)+'vh');shard.style.setProperty('--turn',((i%2?1:-1)*(12+i))+'deg');shard.style.setProperty('--delay',(i%4*95)+'ms');shard.style.setProperty('--tilt',((i%3-1)*38)+'deg');shard.append(captured.cloneNode(true));overlay.insertBefore(shard,scan)});
     caption.lastChild.textContent='那段记录，还在。';await wait(4800);
    }
    if(!skipped){overlay.classList.add('is-memory');caption.lastChild.textContent='在最开始的地方。';await wait(2400)}
    overlay.remove();overlay=null;document.body.classList.remove('journey-distorting');
   }
   if(signal.aborted)throw abortError();
   origin=make('dialog','journey-origin');origin.setAttribute('aria-labelledby','journey-origin-title');
   const nav=make('nav','origin-nav'),home=make('button','','← 返回首页');home.type='button';home.onclick=onHome;nav.append(make('span','','ORIGIN / 最初的草稿'),home);
   const copy=make('div','origin-copy'),title=make('h2','','最初，只有四条记录。');title.id='journey-origin-title';copy.append(make('p','origin-kicker','BACK TO THE BEGINNING'),title,make('p','','还没有红色主题，没有后台，也没有一整份校园指南。只是想先试试。'));
   const cards=make('div','origin-cards');['鹤鸣杯演讲比赛','军训旅演讲比赛','演讲比赛策划材料','成都马拉松志愿者'].forEach((text,i)=>{const card=make('div','origin-card');card.append(make('span','',String(i+1).padStart(2,'0')),make('h3','',text));cards.append(card)});copy.append(cards);
   const enter=make('button','origin-enter','从这里，继续这段故事 ↗');enter.type='button';copy.append(enter);origin.append(nav,copy);document.body.append(origin);origin.showModal();enter.focus({preventScroll:true});
   await new Promise((resolve,reject)=>{
    const abort=()=>{detach();reject(abortError())};const proceed=()=>{detach();resolve()};const cancel=event=>{event.preventDefault();onHome()};
    function detach(){signal.removeEventListener('abort',abort);enter.removeEventListener('click',proceed);origin.removeEventListener('cancel',cancel)}
    enter.addEventListener('click',proceed);origin.addEventListener('cancel',cancel);signal.addEventListener('abort',abort,{once:true});if(signal.aborted)abort();
   });
  }finally{cleanup()}
 }};
})();
