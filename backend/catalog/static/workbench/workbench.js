(()=>{'use strict';
 const $=(s,root=document)=>root.querySelector(s), $$=(s,root=document)=>[...root.querySelectorAll(s)];
 const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
 $$('select').forEach(select=>{if(select.options.length<13)return;const input=document.createElement('input');input.type='search';input.className='select-search';input.placeholder='输入关键词筛选选项';input.setAttribute('aria-label','筛选'+(select.labels?.[0]?.textContent||'关联内容'));select.before(input);input.addEventListener('input',()=>{const term=input.value.trim().toLowerCase();[...select.options].forEach(o=>o.hidden=!!term&&!o.selected&&!o.textContent.toLowerCase().includes(term));});});
 $('[data-remove-record]')?.addEventListener('click',e=>{if(!confirm('移除这一条记录？修改记录中保留恢复入口。'))e.preventDefault();});
 const menu=$('.menu-toggle'),shade=$('.sidebar-shade');
 function closeMenu(){document.body.classList.remove('nav-open');if(menu)menu.setAttribute('aria-expanded','false');if(shade)shade.hidden=true;}
 menu?.addEventListener('click',()=>{const open=!document.body.classList.contains('nav-open');document.body.classList.toggle('nav-open',open);menu.setAttribute('aria-expanded',String(open));shade.hidden=!open;});shade?.addEventListener('click',closeMenu);
 document.addEventListener('keydown',e=>{if(e.key==='Escape')closeMenu();});
 const checks=$$('input[name=selected]'),all=$('[data-select-all]'),bulk=$('.bulk-actions');
 function selection(){const count=checks.filter(c=>c.checked).length;if(bulk)bulk.hidden=!count;const n=$('[data-selected-count]');if(n)n.textContent=count;if(all){all.checked=count===checks.length&&count>0;all.indeterminate=count>0&&count<checks.length;}}
 all?.addEventListener('change',()=>{checks.forEach(c=>c.checked=all.checked);selection();});checks.forEach(c=>c.addEventListener('change',selection));$('[data-clear-selection]')?.addEventListener('click',()=>{checks.forEach(c=>c.checked=false);selection();});
 $$('.bulk-form').forEach(form=>form.addEventListener('submit',e=>{const action=e.submitter?.dataset.bulkConfirm;if(action&&!confirm('将'+action+'所选的 '+checks.filter(c=>c.checked).length+' 条内容？内容与修改记录会保留。'))e.preventDefault();}));
 $('[data-restore]')?.addEventListener('click',e=>{if(!confirm('撤回这次修改，并保留一条恢复记录？'))e.preventDefault();});
 const form=$('#editor-form');if(!form)return;
 const initial=new FormData(form),published=JSON.parse($('#published-data').textContent);let dirty=false,leaving=false,approved=false;
 const saveState=$('[data-save-state]'),dialog=$('#publish-dialog'),publish=$('[data-publish]');
 $('#discard-draft-form')?.addEventListener('submit',e=>{if(!confirm('放弃未发布的草稿？公开内容保持不变。'))e.preventDefault();else leaving=true;});
 function value(name){return form.elements.namedItem(name)?.value||'';}
 function setText(selector,text){const n=$(selector);if(n)n.textContent=text;}
 function updatePreview(){
  const title=value('title')||value('name')||$('.editor-heading h1').textContent;
  setText('[data-preview-title]',title);setText('[data-preview-summary]',value('summary')||value('description')||value('audience')||'在这里补充一两句，帮助读者快速判断。');
  const category=form.elements.namedItem('category');if(category?.tagName==='SELECT')setText('[data-preview-category]',category.selectedOptions[0]?.textContent||'未分类');
  setText('[data-preview-extra]',value('editorial_note')||value('scope')||value('note')||value('caution')||'具体要求按条目和原始通知分别保留。');
  const date=value('deadline')||value('stage_start')||value('published');if(date)setText('[data-preview-date]',(value('deadline')?'报名／提交截止 · ':value('stage_start')?'活动开始 · ':'公告发布 · ')+date.replace('T',' '));
  const blocks=$('[data-preview-blocks]');blocks.replaceChildren();
  const curated=form.elements.namedItem('curated_enabled');
  const details=curated?.checked?$$('textarea[name^=curated_]',form):$$('textarea[name^=fact_],textarea[name^=block_]',form);
  if(details.length){const ul=document.createElement('ul');details.forEach(input=>{for(const text of input.value.split('\n').filter(t=>t.trim())){const li=document.createElement('li');li.textContent=text;ul.append(li);}});blocks.append(ul);}
  const phone=value('phone'),location=value('location'),hours=value('open_hours');if(phone||location||hours){[phone&&('电话：'+phone),location&&('地点：'+location),hours&&('时间：'+hours)].filter(Boolean).forEach(text=>{const p=document.createElement('p');p.textContent=text;blocks.append(p);});}
 }
 form.addEventListener('input',()=>{dirty=true;saveState.textContent='有修改尚未保存';saveState.classList.add('dirty');updatePreview();});form.addEventListener('change',updatePreview);updatePreview();
 $$('[data-panel]').forEach(button=>button.addEventListener('click',()=>{$$('[data-panel]').forEach(b=>b.setAttribute('aria-selected',String(b===button)));$$('[data-content]').forEach(panel=>panel.hidden=panel.dataset.content!==button.dataset.panel);const panel=$('[data-content="'+button.dataset.panel+'"]');if(!reduced)panel.animate([{opacity:.2,transform:'translateY(5px)'},{opacity:1,transform:'none'}],{duration:200,easing:'ease-out'});}));
 $$('[data-preview-mode]').forEach(button=>button.addEventListener('click',()=>{$$('[data-preview-mode]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));$('.preview-expanded').hidden=button.dataset.previewMode!=='detail';}));
 form.addEventListener('submit',e=>{
  if(e.submitter===publish&&!approved){e.preventDefault();const box=$('.publish-summary');box.replaceChildren();const ul=document.createElement('ul');const labels=new Set();
   $$('input[name],textarea[name],select[name]',form).forEach(input=>{if(['csrfmiddlewaretoken','baseline','action'].includes(input.name))return;const now=input.type==='checkbox'?input.checked:input.value;let old=published[input.name];if(input.name==='tags'&&Array.isArray(old))old=old.join('，');if(old===undefined)old=initial.get(input.name);if(String(now)!==String(old??'')){const label=input.closest('.field')?.querySelector('label')?.textContent.replace('·','').trim()||'内容条目';labels.add(label);}});
   (labels.size?[...labels]:['当前已保存的编辑内容']).forEach(label=>{const li=document.createElement('li');li.textContent=label;ul.append(li);});box.append(ul);dialog.showModal();return;
  }
  leaving=true;$$('button[type=submit]',form).forEach(b=>{if(b!==e.submitter)b.disabled=true;});
 });
 $('[data-close-dialog]')?.addEventListener('click',()=>dialog.close());$('[data-confirm-publish]')?.addEventListener('click',()=>{approved=true;dialog.close();form.requestSubmit(publish);});
 window.addEventListener('beforeunload',e=>{if(dirty&&!leaving){e.preventDefault();e.returnValue='';}});
 document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='s'){e.preventDefault();form.requestSubmit($('button[value=save]',form));}if((e.ctrlKey||e.metaKey)&&e.key==='Enter'){e.preventDefault();publish.click();}});
 const error=$('.errorlist',form);if(error){const panel=error.closest('[data-content]');if(panel)$('[data-panel="'+panel.dataset.content+'"]').click();error.scrollIntoView({block:'center'});}
})();
