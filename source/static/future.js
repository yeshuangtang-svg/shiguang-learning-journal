'use strict';
const futureState = { items: [], id: null, baseline: '', saving: false, sequence: 0 };
const FUTURE_LABELS = { pending: '待学习', learning: '学习中', done: '已学完' };
function futureSnapshot() { return JSON.stringify(Object.fromEntries(new FormData($('#future-form')))); }
function futureDirty() { return $('#future-dialog').open && futureSnapshot() !== futureState.baseline; }
async function loadFuture() {
  const sequence = ++futureState.sequence;
  const params = new URLSearchParams({ query: $('#future-query').value.trim(), status: $('#future-filter').value });
  $('#future-count').textContent = '加载中…';
  try {
    const result = await api('/api/future-learning?' + params);
    if (sequence !== futureState.sequence) return;
    futureState.items = result.items;
    const list = $('#future-list'); list.replaceChildren();
    $('#future-count').textContent = '共 ' + result.items.length + ' 条知识收藏';
    if (!result.items.length) {
      const filtered = params.get('query') || params.get('status');
      list.append(emptyState(filtered ? '还没有匹配的知识' : '先收藏，等有精力再学', filtered ? '换个关键词或学习状态看看。' : '看到感兴趣的文章、课程或知识点，先把它放在这里。', filtered ? '' : '收藏第一条知识', () => openFuture()));
    }
    result.items.forEach(item => {
      const card = node('article', 'future-card');
      const top = node('div', 'future-card-top');
      top.append(node('span', 'future-status status-' + item.status, FUTURE_LABELS[item.status]));
      if (item.subject) top.append(node('span', 'subject-badge', item.subject));
      const edit = node('button', 'entry-edit'); edit.type = 'button'; edit.setAttribute('aria-label', '编辑：' + item.title); edit.append(icon('edit')); edit.addEventListener('click', () => openFuture(item)); top.append(edit);
      card.append(top, node('h2', '', item.title));
      if (item.content) {
        const detail = node('details', 'future-notes'); detail.append(node('summary', '', '查看备注'), node('p', '', item.content)); card.append(detail);
      }
      if (item.url) { const link = node('a', 'future-link', '打开资料 ↗'); link.href = item.url; link.target = '_blank'; link.rel = 'noopener noreferrer'; link.title = item.url; card.append(link); }
      const footer = node('div', 'future-card-footer');
      footer.append(node('span', '', '收藏于 ' + new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai' }).format(new Date(item.created_at))));
      const action = node('button', 'text-button', item.status === 'pending' ? '开始学习 →' : item.status === 'learning' ? '标记学完 ✓' : '放回待学习');
      action.addEventListener('click', async () => {
        action.disabled = true;
        try { await api('/api/future-learning/' + item.id, { method: 'PATCH', body: { status: item.status === 'pending' ? 'learning' : item.status === 'learning' ? 'done' : 'pending' } }); await loadFuture(); if(item.status === 'learning')openLinkChooser('future',item.id); }
        catch (error) { notify(error.message, true); } finally { action.disabled = false; }
      });
      footer.append(action, workButton('记学习笔记',()=>startLinkedNote('future',item.id,'entry'),'text-button'),workButton('关联成果',()=>openLinkChooser('future',item.id),'text-button')); card.append(footer); list.append(card);
    });
  } catch (error) {
    if (sequence !== futureState.sequence) return;
    $('#future-count').textContent = '加载失败';
    $('#future-list').replaceChildren(emptyState('暂时无法读取收藏', error.message, '重试', loadFuture));
  }
}
function openFuture(item = null) {
  futureState.id = item?.id || null; futureState.draftKey='future:'+(item?.id||crypto.randomUUID());futureState.updated=item?.updated_at||'';work.noteOrigin=null;
  const form = $('#future-form'); form.reset();
  for (const key of ['title', 'subject', 'content', 'url', 'status']) form.elements[key].value = item?.[key] || (key === 'status' ? 'pending' : '');
  $('#future-dialog-title').textContent = item ? '编辑未来学习知识' : '收藏未来学习知识';
  $('#future-error').hidden = true; $('#delete-future').hidden = !item;
  futureState.baseline = futureSnapshot(); $('#future-dialog').showModal(); form.elements.title.focus(); showRelations('future',futureState.id,$('#future-relations'));
}
function closeFuture() {
  if (futureState.saving) return;
  if (futureDirty() && !window.confirm('还有未保存的收藏内容，关闭后可从草稿恢复。确定关闭吗？')) return;
  $('#future-dialog').close();
}
async function saveFuture(event) {
  event.preventDefault(); if (futureState.saving) return;
  const form = $('#future-form'); if (!form.reportValidity()) return;
  const body = Object.fromEntries(new FormData(form)); body.title = body.title.trim();
  if (!body.title) { form.elements.title.focus(); return; }
  futureState.saving = true; $('#future-form').inert=true; $('#save-future').disabled = true; $('#delete-future').disabled = true; $('#future-error').hidden = true;
  try {
    await api('/api/future-learning' + (futureState.id ? '/' + futureState.id : ''), { method: futureState.id ? 'PATCH' : 'POST', body });
    clearDraft('future'); $('#future-dialog').close(); notify('未来学习知识已保存。'); await loadFuture();
  } catch (error) { $('#future-error').textContent = error.message; $('#future-error').hidden = false; }
  finally { futureState.saving = false; $('#future-form').inert=false; $('#save-future').disabled = false; $('#delete-future').disabled = false; }
}
async function deleteFuture() {
  if (futureState.saving || !futureState.id || !window.confirm('将这条收藏移入回收站？可随时恢复。')) return;
  futureState.saving = true; $('#future-form').inert=true; $('#save-future').disabled = true; $('#delete-future').disabled = true;
  try { await api('/api/future-learning/' + futureState.id, { method: 'DELETE' }); $('#future-dialog').close(); clearDraft('future'); notify('知识收藏已移入回收站。'); await loadFuture(); }
  catch (error) { $('#future-error').textContent = error.message; $('#future-error').hidden = false; }
  finally { futureState.saving = false; $('#future-form').inert=false; $('#save-future').disabled = false; $('#delete-future').disabled = false; }
}
function setupFuture() {
  $('#add-future').addEventListener('click', () => openFuture());
  $('#future-form').addEventListener('submit', saveFuture);
  $('#close-future').addEventListener('click', closeFuture);
  $('#cancel-future').addEventListener('click', closeFuture);
  $('#delete-future').addEventListener('click', deleteFuture);
  $('#future-dialog').addEventListener('cancel', event => { event.preventDefault(); closeFuture(); });
  $('#future-filter').addEventListener('change', loadFuture);
  let timer;
  $('#future-query').addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(loadFuture, 250); });
  $('#future-reset').addEventListener('click', () => { $('#future-query').value = ''; $('#future-filter').value = ''; loadFuture(); });
  window.addEventListener('beforeunload', event => { if (work.restoring) return; if (futureDirty() || futureState.saving) { event.preventDefault(); event.returnValue = ''; } });
  window.addEventListener('keydown', event => { if ($('#future-dialog').open && (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { event.preventDefault(); $('#future-form').requestSubmit(); } });
}
