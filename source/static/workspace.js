'use strict';
const work = { querySeq:0, searchOffset:0, searchTotal:0, linkOrigin:null, linkSeq:0, noteOrigin:null, drafts:new Map(), timers:new Map(), queues:new Map(), positionTimer:null, readingId:null, restorePreview:null };
const KIND_LABELS = {entry:'学习日志',document:'文档',future:'知识收藏',chat:'对话'};
function workButton(text, action, cls='button button-secondary') { const b=node('button',cls,text); b.type='button'; b.addEventListener('click',action); return b; }
function sourceLink(item) { const a=node('a','source-link',item.title || item.name || '查看来源'); a.href=item.url || '#resource/'+item.kind+'/'+encodeURIComponent(item.id); return a; }
function workError(error) { notify(error.message || String(error),true); }
function resourcePath(kind,id) { return '/api/'+({entry:'entries',document:'documents',future:'future-learning'}[kind])+'/'+encodeURIComponent(id); }
async function routeHash() {
  const match=location.hash.match(/^#resource\/(entry|document|future)\/([^/?#]+)$/);
  if (!match) { setView(location.hash.slice(1)||'chat',false); return; }
  try {
    const [,kind,raw]=match, id=decodeURIComponent(raw);
    if ($('#entry-dialog').open) { closeEntry(); if ($('#entry-dialog').open) return; }
    if ($('#future-dialog').open) { closeFuture(); if ($('#future-dialog').open) return; }
    const target={entry:'logs',document:'documents',future:'future'}[kind]; setView(target,false);
    if (state.view!==target) return;
    if (kind==='document') { await openDocument(id); if (library.selected?.id===id) $('#document-title').scrollIntoView({block:'start'}); }
    else { const item=await api(resourcePath(kind,id)); kind==='entry'?openEntry(item):openFuture(item); }
  } catch(error) { workError(error); }
}
function openResource(kind,id) { const hash='#resource/'+kind+'/'+encodeURIComponent(id); if(location.hash===hash) routeHash(); else location.hash=hash; }
function highlightSnippet(text,query) {
  const el=node('p','search-snippet'); const terms=query.trim().split(/\s+/).filter(Boolean);
  if(!terms.length){el.textContent=text;return el;}
  const pattern=new RegExp('('+terms.map(t=>t.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('|')+')','ig');
  let start=0; for(const match of text.matchAll(pattern)){el.append(document.createTextNode(text.slice(start,match.index)),node('mark','',match[0]));start=match.index+match[0].length;} el.append(document.createTextNode(text.slice(start))); return el;
}
async function searchWorkspace(reset=true) {
  if(reset) work.searchOffset=0;
  const seq=++work.querySeq,query=$('#global-query').value.trim(),kind=$('#global-kind').value;
  const params=new URLSearchParams({query,limit:20,offset:work.searchOffset}); if(kind)params.set('kind',kind);
  $('#search-status').textContent='正在搜索…';
  try{
    const result=await api('/api/search?'+params);if(seq!==work.querySeq)return;
    work.searchTotal=result.total; const list=$('#global-results'); list.replaceChildren();
    $('#search-status').textContent='共 '+result.total+' 条 · 日志 / 文档 / 收藏';
    result.items.forEach(item=>{const card=node('article','search-result');card.append(node('small','',KIND_LABELS[item.kind]+(item.subject?' · '+item.subject:'')),sourceLink(item),highlightSnippet(item.snippet,query));list.append(card);});
    if(!result.items.length) list.append(emptyState('没有找到匹配内容','试试更短的关键词，或切换内容类型。'));
    $('#search-prev').disabled=!work.searchOffset; $('#search-next').disabled=!result.has_more;
    $('#search-page').textContent=(result.total?Math.floor(work.searchOffset/20)+1:0)+' / '+Math.ceil(result.total/20);
  }catch(error){if(seq===work.querySeq)$('#search-status').textContent=error.message;}
}
async function showRelations(kind,id,container) {
  container.replaceChildren(); container.dataset.resource=kind+':'+id;
  if(!id){container.hidden=true;return;} container.hidden=false;
  container.append(node('strong','','相关资料与学习成果'));
  const actions=node('div','work-actions'); actions.append(workButton('关联已有内容',()=>openLinkChooser(kind,id)),workButton('写学习日志',()=>startLinkedNote(kind,id,'entry')),workButton('写文档',()=>startLinkedNote(kind,id,'document')));container.append(actions);
  try{const result=await api('/api/links?'+new URLSearchParams({kind,id}));if(container.dataset.resource!==kind+':'+id)return;
    if(!result.items.length)container.append(node('p','muted','还没有关联。可以连接收藏、学习经过和总结。'));
    result.items.forEach(item=>{const row=node('div','related-row');row.append(node('small','',KIND_LABELS[item.kind]),sourceLink(item),workButton('解除关联',async()=>{try{await api('/api/links/'+item.link_id,{method:'DELETE'});showRelations(kind,id,container);}catch(e){workError(e);}},'text-button'));container.append(row);});
  }catch(error){container.append(node('p','',error.message));}
}
function refreshRelations(){if($('#entry-dialog').open)showRelations('entry',state.editingId,$('#entry-relations'));if($('#future-dialog').open)showRelations('future',futureState.id,$('#future-relations'));if(library.selected)showRelations('document',library.selected.id,$('#document-relations'));}
function openLinkChooser(kind,id){work.linkOrigin={kind,id};$('#link-query').value='';$('#link-results').replaceChildren();$('#link-dialog').showModal();findLinks();}
async function findLinks(){const seq=++work.linkSeq,origin=work.linkOrigin;if(!origin)return;
  try{const result=await api('/api/search?'+new URLSearchParams({query:$('#link-query').value,limit:30}));if(seq!==work.linkSeq)return;const list=$('#link-results');list.replaceChildren();
    result.items.filter(x=>x.kind!==origin.kind||x.id!==origin.id).forEach(item=>{const row=node('div','related-row');row.append(node('span','',KIND_LABELS[item.kind]+' · '+item.title),workButton('关联',async event=>{const button=event.currentTarget;button.disabled=true;try{await api('/api/links',{method:'POST',body:{a_kind:origin.kind,a_id:origin.id,b_kind:item.kind,b_id:item.id}});button.textContent='已关联';refreshRelations();}catch(e){button.disabled=false;workError(e);}}));list.append(row);});
    if(result.has_more)list.append(node('p','muted','请输入更具体的关键词缩小结果。'));
    if(!list.children.length)list.append(node('p','muted','暂无可关联内容。'));
  }catch(e){workError(e);}}
async function startLinkedNote(kind,id,noteKind){
  try{
    if($('#future-dialog').open){closeFuture();if($('#future-dialog').open)return;}
    if($('#entry-dialog').open){closeEntry();if($('#entry-dialog').open)return;}
    if(!canLeaveDocument())return;
    const original=await api(resourcePath(kind,id));
    if(kind==='future'&&original.status==='pending')await api(resourcePath(kind,id),{method:'PATCH',body:{status:'learning'}});
    const title=original.title||original.name;
    if(noteKind==='entry'){openEntry();$('#entry-form').elements.title.value=title+' · 学习笔记';$('#entry-form').elements.subject.value=original.subject||'学习笔记';}
    else {setView('documents');newDocument();$('#document-name').value=title.replace(/\.(md|markdown)$/i,'')+' · 学习笔记.md';updateDocumentStatus();}
    work.noteOrigin={kind,id}; draftChanged(noteKind); notify('保存后会自动关联原内容。');
  }catch(e){workError(e);}
}
function draftKey(kind){return kind==='entry'?state.draftKey:kind==='document'?library.draftKey:kind==='future'?futureState.draftKey:'chat:current';}
function draftPayload(kind){
  if(kind==='entry')return {kind,id:state.editingId,data:JSON.parse(entrySnapshot()),origin:work.noteOrigin,base_updated_at:state.entryUpdated||''};
  if(kind==='document')return {kind,id:library.selected?.id,data:JSON.parse(documentSnapshot()),origin:work.noteOrigin,base_updated_at:library.selected?.updated_at||''};
  if(kind==='future')return {kind,id:futureState.id,data:JSON.parse(futureSnapshot()),base_updated_at:futureState.updated||''};
  return {kind,id:null,data:{message:$('#chat-input').value}};
}
function draftQueue(key,action){const next=(work.queues.get(key)||Promise.resolve()).catch(()=>{}).then(action);work.queues.set(key,next);return next;}
function draftChanged(kind){
  const key=draftKey(kind);if(!key)return;
  if(kind==='document'&&!library.selected)return;
  const dirty=kind==='entry'?entrySnapshot()!==entryBaseline:kind==='document'?documentDirty():kind==='future'?futureDirty():Boolean($('#chat-input').value.trim());
  if(!dirty)return;
  const payload=draftPayload(kind);work.drafts.set(key,{key,payload,updated_at:new Date().toISOString()});
  writeStorage(localStorage,'shiguang.draft.'+key,JSON.stringify({payload,updated_at:work.drafts.get(key).updated_at}));
  clearTimeout(work.timers.get(key));work.timers.set(key,setTimeout(()=>draftQueue(key,()=>api('/api/drafts/'+encodeURIComponent(key),{method:'POST',body:payload})).then(()=>{$('#draft-status').textContent='草稿已自动保存';}).catch(()=>{$('#draft-status').textContent='草稿已暂存到此设备，连接后重试';}),600));
  $('#draft-status').textContent='正在保存草稿…';updateDraftBadge();
}
function clearDraft(kind,key=draftKey(kind)){
  if(!key)return Promise.resolve();clearTimeout(work.timers.get(key));work.timers.delete(key);work.drafts.delete(key);writeStorage(localStorage,'shiguang.draft.'+key,'');updateDraftBadge();
  return draftQueue(key,()=>api('/api/drafts/'+encodeURIComponent(key),{method:'DELETE'})).catch(e=>{notify('正文已保存；草稿清理未完成，可稍后移除。',true);});
}
function updateDraftBadge(){if($('#draft-count'))$('#draft-count').textContent=work.drafts.size?'草稿 '+work.drafts.size:'草稿与回收站';}
async function loadRecovery(){
  try{const [drafts,trash]=await Promise.all([api('/api/drafts'),api('/api/trash')]);
    drafts.items.forEach(item=>{const local=work.drafts.get(item.key);if(!local||local.updated_at<item.updated_at)work.drafts.set(item.key,item);});
    updateDraftBadge();const list=$('#draft-list');list.replaceChildren();
    [...work.drafts.values()].forEach(item=>{const card=node('article','search-result');const data=item.payload.data||{};card.append(node('strong','',(KIND_LABELS[item.payload.kind]||'草稿')+' · '+(data.title||data.name||'未发送的对话')),node('small','',documentDate(item.updated_at)),node('p','',String(data.content||data.message||'').slice(0,160)),workButton('恢复编辑',()=>restoreDraft(item)),workButton('丢弃草稿',async()=>{if(!confirm('丢弃这份草稿？已保存的正文不受影响。'))return;await clearDraft(item.payload.kind,item.key);loadRecovery();},'text-button'));list.append(card);});
    if(!list.children.length)list.append(node('p','muted','暂时没有未完成的草稿。'));
    const bin=$('#trash-list');bin.replaceChildren();trash.items.forEach(item=>{const row=node('article','search-result');row.append(node('strong','',KIND_LABELS[item.kind]+' · '+item.title),node('small','',documentDate(item.deleted_at)),workButton('恢复',async event=>{event.currentTarget.disabled=true;try{await api('/api/trash/'+item.id+'/restore',{method:'POST',body:{}});notify('已恢复，原关联和文件仍保留。');await loadRecovery();}catch(e){workError(e);event.currentTarget.disabled=false;}}));bin.append(row);});if(!bin.children.length)bin.append(node('p','muted','回收站为空。'));
  }catch(e){workError(e);}
}
async function restoreDraft(item){
  const p=item.payload,kind=p.kind;
  if(!canLeaveDocument())return;
  if($('#entry-dialog').open||$('#future-dialog').open){notify('请先关闭当前编辑窗口。');return;}
  let current=null;
  try{if(p.id)current=await api(resourcePath(kind,p.id));}catch(e){if(e.status===404){notify('原内容已移入回收站，请先恢复原内容。',true);return;}workError(e);return;}
  if(current&&p.base_updated_at&&current.updated_at!==p.base_updated_at&&!confirm('原内容在草稿保存后已有更新。仍要恢复这份草稿进行编辑吗？'))return;
  if(kind==='entry'){setView('logs');openEntry(current);state.draftKey=item.key;Object.entries(p.data).forEach(([k,v])=>{if($('#entry-form').elements[k])$('#entry-form').elements[k].value=v;});}
  if(kind==='document'){setView('documents');displayDocument(current||{id:null,name:'未命名笔记.md',content:''},true);library.draftKey=item.key;$('#document-name').value=p.data.name;$('#document-content').value=p.data.content;updateDocumentStatus();}
  if(kind==='future'){setView('future');openFuture(current);futureState.draftKey=item.key;Object.entries(p.data).forEach(([k,v])=>{if($('#future-form').elements[k])$('#future-form').elements[k].value=v;});}
  if(kind==='chat'){setView('chat');$('#chat-input').value=p.data.message;resizeComposer();updateConnectionUI();}
  work.noteOrigin=p.origin||null;notify('草稿已恢复，保存后才会更新正文。');
}
function decorateDocument(){
  const preview=$('#document-preview'),toc=$('#document-toc');if(!preview||!toc)return;
  toc.replaceChildren(); if(library.editing){toc.hidden=true;return;}
  const headings=$$('h1,h2,h3',preview);toc.hidden=!headings.length;
  if(headings.length){toc.append(node('summary','','章节目录 · '+headings.length));headings.forEach((h,index)=>{h.id='document-heading-'+index;const a=node('a','toc-level-'+h.tagName.slice(1),h.textContent);a.href='#'+h.id;a.addEventListener('click',event=>{event.preventDefault();h.scrollIntoView({behavior:'smooth',block:'start'});});toc.append(a);});}
}
async function loadReadingPosition(id){work.readingId=id;if(!id)return;try{const position=await api('/api/documents/'+id+'/position');if(library.selected?.id!==id||library.editing)return;
  const old=$('#resume-reading');old.hidden=!(position.ratio>0.01||position.heading);old.onclick=()=>{const h=$$('#document-preview h1,#document-preview h2,#document-preview h3').find(x=>x.textContent===position.heading);if(h)h.scrollIntoView();else {const el=$('#document-preview');window.scrollTo(0,window.scrollY+el.getBoundingClientRect().top+position.ratio*el.scrollHeight);}old.hidden=true;};
}catch(e){/* Reading remains available if the position cannot be fetched. */}}
function saveReadingPosition(){const id=library.selected?.id;if(!id||library.editing||state.view!=='documents')return;const el=$('#document-preview');const ratio=Math.min(1,Math.max(0,-el.getBoundingClientRect().top/Math.max(1,el.scrollHeight)));const headings=$$('h1,h2,h3',el).filter(h=>h.getBoundingClientRect().top<=120);const position={ratio,heading:headings.at(-1)?.textContent.slice(0,200)||''};clearTimeout(work.positionTimer);work.positionTimer=setTimeout(()=>api('/api/documents/'+id+'/position',{method:'POST',body:position}).catch(()=>{}),500);}
async function generateDocumentPDF(event){const id=library.selected?.id;if(!id||documentDirty()){notify('请先保存文档。',true);return;}const button=event.currentTarget;button.disabled=true;button.textContent='正在生成 PDF…';try{await api('/api/documents/'+id+'/generate-pdf',{method:'POST',body:{}});await loadDocumentFiles(id);notify('PDF 已生成并归档为当前版本。');}catch(e){workError(e);}finally{button.disabled=false;button.textContent='重新生成 PDF';}}
async function showDocumentHistory(){const id=library.selected?.id;if(!id){notify('请先选择已保存的文档。');return;}$('#history-dialog').showModal();const list=$('#history-list');list.replaceChildren(node('p','','加载中…'));try{const result=await api('/api/documents/'+id+'/history');list.replaceChildren();result.items.forEach(item=>{const row=node('div','related-row');row.append(node('span','',documentDate(item.modified)+' · '+item.type.toUpperCase()+' · '+humanSize(item.size)),workButton('查看',async()=>{try{const response=await fetch('/api/documents/'+id+'/history/'+item.id,{headers:token?{Authorization:'Bearer '+token}:{}});if(!response.ok)throw new Error('历史版本读取失败');if(item.type==='md'){renderMarkdown($('#history-preview'),await response.text());}else{const url=URL.createObjectURL(await response.blob());const a=node('a');a.href=url;a.download=item.name;a.click();setTimeout(()=>URL.revokeObjectURL(url),60000);}}catch(e){workError(e);}}));list.append(row);});if(!result.items.length)list.append(node('p','muted','还没有历史版本。修改已保存的文档或重新生成 PDF 后会保留旧文件。'));}catch(e){list.replaceChildren(node('p','',e.message));}}
async function loadBackups(){try{const data=await api('/api/backups');const list=$('#backup-list');list.replaceChildren();$('#backup-last').textContent=data.items.length?'最近备份：'+documentDate(data.items[0].created_at):'尚未制作完整资料备份';data.items.slice(0,10).forEach(item=>{const row=node('div','related-row');row.append(node('span','',documentDate(item.created_at)+' · '+humanSize(item.size)+(item.includes_config?' · 含模型配置':'')),workButton('下载',()=>downloadFullBackup(item.id)));list.append(row);});}catch(e){$('#backup-last').textContent=e.message;}}
async function downloadFullBackup(id){try{const response=await fetch('/api/backups/'+id+'/download',{headers:token?{Authorization:'Bearer '+token}:{}});if(!response.ok)throw new Error('下载失败');const url=URL.createObjectURL(await response.blob());const a=node('a');a.href=url;a.download='拾光完整资料-'+id.slice(0,8)+'.zip';a.click();setTimeout(()=>URL.revokeObjectURL(url),60000);}catch(e){workError(e);}}
async function createFullBackup(event){const button=event.currentTarget;button.disabled=true;button.textContent='正在备份…';try{const result=await api('/api/backups',{method:'POST',body:{include_config:$('#backup-config').checked}});await loadBackups();notify('完整资料备份已保存在本地，可点击下载另存。');await downloadFullBackup(result.id);}catch(e){workError(e);}finally{button.disabled=false;button.textContent='一键完整备份';}}
async function previewBackup(event){const file=event.target.files[0];event.target.value='';if(!file)return;if(file.size>512*1024*1024){notify('备份超过 512 MiB。',true);return;}
  $('#restore-dialog').showModal();$('#restore-details').textContent='正在校验备份…';$('#restore-confirm').disabled=true;work.restorePreview=null;
  try{const response=await fetch('/api/backups/preview',{method:'POST',headers:{'Content-Type':'application/zip',...(token?{Authorization:'Bearer '+token}:{})},body:file});const result=await response.json();if(!response.ok)throw new Error(result.error||'预览失败');work.restorePreview=result;$('#restore-details').textContent='备份时间：'+documentDate(result.created_at)+'\n日志 '+result.counts.entries+' · 文档 '+result.counts.documents+' · 收藏 '+result.counts.future_learning+'\nPDF '+result.pdfs+' · 文件 '+result.files+'\n'+result.effect;$('#restore-config-label').hidden=!result.includes_config;$('#restore-config').checked=false;$('#restore-confirm').disabled=false;}catch(e){$('#restore-details').textContent=e.message;}}
async function restoreBackup(){const p=work.restorePreview;if(!p)return;const b=$('#restore-confirm');b.disabled=true;try{for(const timer of work.timers.values())clearTimeout(timer);clearTimeout(work.positionTimer);await Promise.allSettled([...work.queues.values()]);await api('/api/backups/restore',{method:'POST',body:{token:p.token,restore_config:$('#restore-config').checked}});for(const key of [...work.drafts.keys()])writeStorage(localStorage,'shiguang.draft.'+key,'');writeStorage(localStorage,SESSION_KEY,'');work.restoring=true;location.reload();}catch(e){workError(e);b.disabled=false;}}
function setupWorkspace(){
  const nav=$('.navigation');for(const [view,label] of [['search','统一搜索'],['recovery','草稿与回收站']]){const b=workButton(label,()=>setView(view),'nav-item');b.dataset.view=view;nav.append(b);}
  const top=node('form','global-search-form');top.id='global-search-form';const input=node('input');input.id='top-search';input.placeholder='搜索日志、文档、收藏  Ctrl+K';input.setAttribute('aria-label','统一搜索');top.append(input);$('.topbar-right').prepend(top);top.addEventListener('submit',e=>{e.preventDefault();$('#global-query').value=input.value;setView('search');});
  $('#global-query').addEventListener('input',()=>{clearTimeout(work.searchTimer);work.searchTimer=setTimeout(()=>searchWorkspace(),250);});$('#global-kind').addEventListener('change',()=>searchWorkspace());$('#search-prev').onclick=()=>{work.searchOffset=Math.max(0,work.searchOffset-20);searchWorkspace(false);};$('#search-next').onclick=()=>{work.searchOffset+=20;searchWorkspace(false);};
  $('#draft-count').onclick=()=>setView('recovery');$('#recovery-refresh').onclick=loadRecovery;
  $('#link-query').addEventListener('input',()=>{clearTimeout(work.linkTimer);work.linkTimer=setTimeout(findLinks,250);});
  $$('[data-close-dialog]').forEach(b=>b.onclick=()=>$('#'+b.dataset.closeDialog).close());
  $('#entry-form').addEventListener('input',()=>draftChanged('entry'));$('#future-form').addEventListener('input',()=>draftChanged('future'));$('#future-form').addEventListener('change',()=>draftChanged('future'));['#document-name','#document-content'].forEach(s=>$(s).addEventListener('input',()=>draftChanged('document')));$('#chat-input').addEventListener('input',()=>draftChanged('chat'));
  $('#generate-pdf').onclick=generateDocumentPDF;$('#document-history').onclick=showDocumentHistory;$('#create-full-backup').onclick=createFullBackup;$('#upload-full-backup').onclick=()=>$('#full-backup-file').click();$('#full-backup-file').onchange=previewBackup;$('#restore-confirm').onclick=restoreBackup;
  window.addEventListener('scroll',saveReadingPosition,{passive:true});
  window.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();$('#top-search').focus();}});
  try{for(let i=0;i<localStorage.length;i++){const key=localStorage.key(i);if(key.startsWith('shiguang.draft.')){try{const saved=JSON.parse(localStorage.getItem(key));const payload=saved.payload||saved;work.drafts.set(key.slice(15),{key:key.slice(15),payload,updated_at:saved.updated_at||''});}catch{}}}}catch{}
  updateDraftBadge(); api('/api/drafts').then(r=>{r.items.forEach(d=>{if(!work.drafts.has(d.key)||work.drafts.get(d.key).updated_at<d.updated_at)work.drafts.set(d.key,d);});updateDraftBadge();}).catch(()=>{});
}
