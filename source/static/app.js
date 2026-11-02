'use strict';

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const state = { health: null, config: null, entries: [], summary: null, sending: false, saving: false, sessionId: '', failedRequest: null, editingId: null, filterSequence: 0, view: 'chat' };
const library = { documents: [], selected: null, baseline: '', editing: false, saving: false, importing: false, sequence: 0, opening: 0 };
let entryBaseline = '', entryPreview = false, imageTarget = 'entry', assetUploads = 0;
const SESSION_KEY = 'shiguang.agent.session';
const TOKEN_KEY = 'shiguang.agent.access-token';
const MOOD_LABELS = { great: '充实', good: '专注', okay: '平稳', tired: '疲惫' };
let token = readStorage(sessionStorage, TOKEN_KEY);
state.sessionId = readStorage(localStorage, SESSION_KEY);

function readStorage(storage, key) { try { return storage.getItem(key) || ''; } catch { return ''; } }
function writeStorage(storage, key, value) { try { value ? storage.setItem(key, value) : storage.removeItem(key); } catch { /* The app also works without persistent browser storage. */ } }
function node(tag, className = '', content) { const result = document.createElement(tag); if (className) result.className = className; if (content !== undefined) result.textContent = String(content); return result; }
function icon(name) { const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); const use = document.createElementNS('http://www.w3.org/2000/svg', 'use'); use.setAttribute('href', '#i-' + name); svg.setAttribute('aria-hidden', 'true'); svg.append(use); return svg; }
function today() { return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date()); }
function number(value) { return Number(value || 0).toLocaleString('zh-CN'); }
function notify(message, error = false) { const item = node('div', 'toast' + (error ? ' error' : '')); item.append(icon(error ? 'close' : 'check'), node('span', '', message)); $('#toast-region').append(item); while ($('#toast-region').children.length>3) $('#toast-region').firstElementChild.remove(); setTimeout(() => item.remove(), error ? 6500 : 3800); }

class APIError extends Error { constructor(message, status = 0) { super(message); this.status = status; } }
async function api(path, options = {}) {
  if (!path.startsWith('/api/')) throw new Error('API 路径无效');
  const headers = { Accept: 'application/json', ...options.headers };
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';
  if (token) headers.Authorization = 'Bearer ' + token;
  let response;
  try { response = await fetch(path, { ...options, headers, credentials: 'same-origin', body: options.body === undefined ? undefined : JSON.stringify(options.body) }); }
  catch { throw new APIError('暂时无法连接本地服务器。请确认服务器仍在运行，然后重试。'); }
  let data;
  try { data = await response.json(); }
  catch { throw new APIError('服务器未返回有效数据，请检查服务日志后重试。', response.status); }
  if (!response.ok) {
    if (response.status === 401) showBanner('需要 Agent 访问令牌，请在连接设置中填写或更新。');
    throw new APIError(typeof data.error === 'string' ? data.error : ('请求失败（' + response.status + '）'), response.status);
  }
  return data;
}

function showBanner(text) { $('#connection-banner-text').textContent = text; $('#connection-banner').hidden = false; }
function setView(view, setHash = true) {
  if (!['chat', 'logs', 'documents', 'future', 'overview', 'settings', 'search', 'recovery'].includes(view)) view = 'chat';
  if (state.view === 'documents' && view !== 'documents' && !canLeaveDocument()) { history.replaceState(null, '', '#documents'); return; }
  state.view = view;
  $$('.view').forEach(item => { const active = item.id === 'view-' + view; item.hidden = !active; item.classList.toggle('active', active); });
  $$('.nav-item').forEach(item => { const active = item.dataset.view === view; item.classList.toggle('active', active); if (active) item.setAttribute('aria-current', 'page'); else item.removeAttribute('aria-current'); });
  const label = { chat: '学习助手', logs: '学习日志', documents: '文档', future: '未来学习知识', overview: '学习概览', settings: '连接设置', search: '统一搜索', recovery: '草稿与回收站' }[view];
  $('#breadcrumb').replaceChildren(document.createTextNode('工作台 '), node('span', '', '/'), document.createTextNode(' ' + label));
  if (setHash && location.hash !== '#' + view) history.replaceState(null, '', '#' + view);
  if (view === 'logs') loadEntries();
  if (view === 'overview') loadSummary();
  if (view === 'documents') loadDocuments();
  if (view === 'future') loadFuture();
  if (view === 'search') searchWorkspace();
  if (view === 'recovery') loadRecovery();
  if (view === 'settings') loadBackups();
}

function updateConnectionUI() {
  const configured = Boolean(state.health?.model_configured);
  const needsAuth = Boolean(state.health?.auth_required && !token);
  const status = !state.health ? '服务器未连接' : needsAuth ? '需要访问令牌' : configured ? (state.health.model || '模型已连接') : '等待连接模型';
  $('#chat-model-status').textContent = status;
  $('#chat-model-status').title = status;
  $('#settings-status').textContent = configured && !needsAuth ? '已保存模型配置' : status;
  $('#settings-status').classList.toggle('connected', configured && !needsAuth);
  $('#connection-dot').classList.toggle('connected', configured && !needsAuth);
  $('#chat-setup-notice').hidden = configured && !needsAuth;
  $('#chat-setup-notice > span').textContent = needsAuth ? '填写 Agent 访问令牌，开启对话。' : '连接模型 API，开启对话式记录。';
  $('#send-message').disabled = state.sending || !configured || needsAuth || !$('#chat-input').value.trim();
  $('#new-chat').disabled = state.sending;
  $('#token-state').textContent = token ? '已为当前浏览器会话保存令牌，关闭会话后失效。' : '令牌仅保存在当前浏览器会话中。';
  if (state.health?.desktop) {
    $('.local-badge').replaceChildren(icon('shield'), document.createTextNode('桌面应用 · 本地保存'));
    if (!$('#desktop-api-info')) {
      const info = node('div', 'desktop-api-info'); info.id = 'desktop-api-info';
      info.append(node('p', '', '当前 Agent 接口地址'), node('code', '', state.health.api_url || location.origin), node('p', '', '应用打开时可调用，关闭窗口后服务退出。'));
      $('.api-card').append(info);
    }
  }
}

async function loadHealth() {
  try { state.health = await api('/api/health'); $('#connection-banner').hidden = true; if (state.health.auth_required && !token) showBanner('服务器已启用访问认证，请先在连接设置中填写 Agent 访问令牌。'); }
  catch (error) { state.health = null; showBanner(error.message); }
  updateConnectionUI();
}
async function loadConfig() {
  try {
    const config = await api('/api/config'); state.config = config;
    $('#config-base-url').value = config.base_url || 'https://api.openai.com/v1';
    $('#config-model').value = config.model || '';
    $('#config-api-key').value = '';
    $('#config-api-key').placeholder = config.api_key_set ? '已保存，留空保留现有密钥' : '输入模型 API Key';
    $('#key-state').textContent = config.api_key_set ? '密钥已保存' : '尚未设置';
    const overrides = config.environment_overrides || [];
    const overrideLabels = { LLM_BASE_URL: '接口地址', LLM_MODEL: '模型', LLM_API_KEY: '密钥' };
    [['LLM_BASE_URL', '#config-base-url'], ['LLM_MODEL', '#config-model'], ['LLM_API_KEY', '#config-api-key']].forEach(([key, selector]) => { $(selector).readOnly = overrides.includes(key); $(selector).title = overrides.includes(key) ? '由服务器环境变量指定，请修改服务器启动环境。' : ''; });
    $('#config-save-status').textContent = overrides.length ? overrides.map(key => overrideLabels[key] || key).join('、') + '由服务器环境变量指定；请修改启动环境后重启服务。' : '';
  } catch (error) { if (error.status !== 401) $('#config-save-status').textContent = error.message; }
}

function appendMessage(role, content, options = {}) {
  $('#chat-welcome').hidden = true;
  const wrapper = node('div', 'message ' + role + (options.error ? ' error' : ''));
  const avatar = node('div', 'message-avatar'); avatar.append(role === 'user' ? document.createTextNode('我') : icon('spark'));
  const main = node('div', 'message-main');
  main.append(node('div', 'message-name', role === 'user' ? '你' : '拾光助手'));
  if (options.thinking) { const dots = node('div', 'thinking-dots'); dots.setAttribute('aria-label', '拾光正在整理思路'); dots.append(node('i'), node('i'), node('i')); main.append(dots); }
  else { const text = node('div', 'message-content'); if (role === 'assistant') { text.classList.add('markdown-body'); renderMarkdown(text, content); } else text.textContent = content; main.append(text); }
  if (options.actions?.length) {
    const actions = node('div', 'message-actions');
    options.actions.forEach(action => {
      const tool = String(action.tool || '');
      let label = '已完成操作';
      if (action.ok === false) label = '操作未完成';
      else if (/create|add|save|record/i.test(tool)) label = '学习日志已保存';
      else if (/update|edit|patch/i.test(tool)) label = '日志已更新';
      else if (/delete|remove/i.test(tool)) label = '日志已删除';
      else if (/summary|stats/i.test(tool)) label = '已读取学习统计';
      else if (/search|list|get|read/i.test(tool)) label = '已检索学习记录';
      const badge = node('span', 'action-badge', label); badge.title = tool; actions.append(badge);
    });
    main.append(actions);
    const sources = new Map(); (options.actions || []).filter(a => a.ok && ['search_knowledge','read_knowledge'].includes(a.tool)).forEach(a => { (a.result.items || [a.result]).forEach(r => { if (r.url && r.title) sources.set(r.url,r); }); });
    if (sources.size) { const refs = node('div','source-list'); refs.append(node('small','','参考资料')); [...sources.values()].slice(0,10).forEach(r => refs.append(sourceLink(r))); main.append(refs); }
  }
  (options.warnings || []).forEach(warning => main.append(node('div', 'message-warning', typeof warning === 'string' ? warning : JSON.stringify(warning))));
  wrapper.append(avatar, main); $('#messages').append(wrapper); scrollChat(); return wrapper;
}
function scrollChat() { requestAnimationFrame(() => { const scroll = $('#conversation-scroll'); scroll.scrollTop = scroll.scrollHeight; }); }
async function loadSession() {
  if (!state.sessionId) return;
  try {
    const result = await api('/api/sessions/' + encodeURIComponent(state.sessionId));
    $('#messages').replaceChildren();
    const messages = (result.messages || []).filter(message => ['user', 'assistant'].includes(message.role) && message.content);
    messages.forEach(message => appendMessage(message.role, String(message.content)));
    $('#chat-welcome').hidden = messages.length > 0;
  } catch (error) {
    if (error.status === 404) { state.sessionId = ''; writeStorage(localStorage, SESSION_KEY, ''); }
    else if (error.status !== 401) notify('上次对话暂时未能恢复。' + error.message, true);
  }
}
function fillPrompt(text) { setView('chat'); $('#chat-input').value = text; resizeComposer(); updateConnectionUI(); $('#chat-input').focus(); }
function resizeComposer() { const input = $('#chat-input'); input.style.height = 'auto'; input.style.height = Math.min(170, input.scrollHeight) + 'px'; }
async function sendMessage(event) {
  event.preventDefault();
  const message = $('#chat-input').value.trim();
  if (!message || state.sending) return;
  if (!state.health?.model_configured || (state.health.auth_required && !token)) { setView('settings'); notify('先完成连接设置，就可以和拾光对话了。'); return; }
  const retry = state.failedRequest && state.failedRequest.message === message && state.failedRequest.session_id === (state.sessionId || undefined);
  const payload = retry ? state.failedRequest : { message, request_id: crypto.randomUUID(), ...(state.sessionId ? { session_id: state.sessionId } : {}) };
  state.failedRequest = null;
  if (!retry) appendMessage('user', message);
  $('#chat-input').value = ''; resizeComposer();
  state.sending = true; updateConnectionUI();
  const thinking = appendMessage('assistant', '', { thinking: true });
  try {
    const result = await api('/api/chat', { method: 'POST', body: payload });
    thinking.remove(); clearDraft('chat');
    if (result.session_id) { state.sessionId = String(result.session_id); writeStorage(localStorage, SESSION_KEY, state.sessionId); }
    appendMessage('assistant', result.reply || '已完成。', { actions: result.actions, warnings: result.warnings });
    await Promise.allSettled([loadSummary(), state.view === 'logs' ? loadEntries() : Promise.resolve()]);
  } catch (error) {
    thinking.remove(); state.failedRequest = payload;
    appendMessage('assistant', error.message + '\n原消息已放回输入框，点击发送可重试。', { error: true });
    $('#chat-input').value = message; resizeComposer();
    if (error.status === 401) setView('settings');
  } finally { state.sending = false; updateConnectionUI(); }
}

async function loadSummary() {
  try {
    state.summary = await api('/api/summary');
    const summary = state.summary;
    const current = (summary.days || []).find(day => day.date === today()) || {};
    $('#today-entries').textContent = number(current.entries);
    $('#total-entries').textContent = number(summary.total_entries) + ' 篇';
    $('#total-days').textContent = number(summary.study_days) + ' 天';
    $('#today-note').textContent = current.entries ? '你留下的每一笔，都在积累' : '今天的故事，等你来记录';
    $('#metric-subjects').textContent = number((summary.subjects || []).length);
    $('#metric-entries').textContent = number(summary.total_entries);
    $('#metric-days').textContent = number(summary.study_days);
    renderCharts(summary);
  } catch (error) { if (state.view === 'overview' && error.status !== 401) notify(error.message, true); }
}
function renderCharts(summary) {
  const chart = $('#week-chart'); chart.replaceChildren();
  const midnight = new Date(today() + 'T00:00:00+08:00');
  const days = Array.from({ length: 7 }, (_, index) => { const date = new Date(midnight.getTime() - (6 - index) * 86400000); const key = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(date); return { key, date, entries: Number((summary.days || []).find(day => day.date === key)?.entries || 0) }; });
  const maximum = Math.max(1, ...days.map(day => day.entries));
  days.forEach((day, index) => { const group = node('div', 'bar-group' + (index === 6 ? ' today' : '')); group.title = day.key + ' · ' + day.entries + ' 篇日志'; const bar = node('div', 'chart-bar'); bar.style.height = (day.entries ? Math.max(3, day.entries / maximum * 75) : 1.5) + '%'; group.append(node('span', 'bar-value', day.entries || '—'), bar, node('span', '', index === 6 ? '今天' : new Intl.DateTimeFormat('zh-CN', { weekday: 'short', timeZone: 'Asia/Shanghai' }).format(day.date))); chart.append(group); });
  const subjects = $('#subject-chart'); subjects.replaceChildren();
  if (!(summary.subjects || []).length) { subjects.append(node('p', 'subject-empty', '还没有学习记录\n记下一笔，让成长慢慢清晰。')); return; }
  const maxSubject = Math.max(1, ...(summary.subjects || []).map(subject => Number(subject.entries || 0)));
  [...summary.subjects].sort((a, b) => b.entries - a.entries).forEach(subject => { const row = node('div', 'subject-row'); const head = node('div', 'subject-row-head'); head.append(node('span', '', subject.subject || '未分类'), node('span', '', number(subject.entries) + ' 篇')); const track = node('div', 'subject-track'); const fill = node('div', 'subject-fill'); fill.style.width = Math.max(0, Number(subject.entries || 0)) / maxSubject * 100 + '%'; track.append(fill); row.append(head, track); subjects.append(row); });
}
async function loadEntries(reset = true) {
  if (reset !== false) state.entryOffset = 0;
  const sequence = ++state.filterSequence;
  const query = new URLSearchParams({limit:20,offset:state.entryOffset||0});
  [['query','#log-query'],['subject','#filter-subject'],['date_from','#filter-from'],['date_to','#filter-to']].forEach(([key,selector])=>{const value=$(selector).value.trim();if(value)query.set(key,value);});
  try {
    const result=await api('/api/entries-page?'+query); if(sequence!==state.filterSequence)return;
    state.entries=result.entries;state.entryTotal=result.total;state.entryMore=result.has_more;renderEntries(query.has('query')||query.has('subject')||query.has('date_from')||query.has('date_to'));
    const filters=$('#subject-shortcuts');filters.replaceChildren();result.subjects.slice(0,20).forEach(subject=>filters.append(workButton(subject,()=>{$('#filter-subject').value=subject;loadEntries();},'subject-chip'+($('#filter-subject').value===subject?' active':''))));
    $('#entries-prev').disabled=!state.entryOffset;$('#entries-next').disabled=!result.has_more;$('#entries-page').textContent=(result.total?Math.floor((state.entryOffset||0)/20)+1:0)+' / '+Math.ceil(result.total/20);
  } catch(error) { if(sequence===state.filterSequence){$('#entries-count').textContent=error.message;$('#entries-list').replaceChildren(emptyState('日志暂时无法加载',error.message,'重试',()=>loadEntries()));} }
}
function emptyState(title, description, buttonText, handler) { const empty = node('div', 'empty-state'); empty.append(icon('book'), node('h2', '', title), node('p', '', description)); if (buttonText) { const button = node('button', 'button button-secondary', buttonText); button.addEventListener('click', handler); empty.append(button); } return empty; }
function disposeEntryList() { $$('.entry-prose', $('#entries-list')).forEach(element => window.StudyMarkdown?.dispose(element)); }
function renderEntries(filtered) {
  $('#entries-count').textContent='共 '+number(state.entryTotal)+' 篇'+(filtered?'匹配记录':'学习记录');
  const list=$('#entries-list');disposeEntryList();list.replaceChildren();
  if(!state.entries.length){list.append(emptyState('还没有找到学习足迹','可以记录一条，或调整筛选条件。'));return;}
  state.entries.forEach(entry=>{
    const card=node('article','entry-card');const date=node('div','entry-date');date.append(node('strong','',entry.date.slice(8)),node('span','',entry.date.slice(0,7)));
    const content=node('div','entry-content');content.append(node('h2','',entry.title),node('span','subject-badge',entry.subject));
    const excerpt=node('p','entry-excerpt',entry.content.replace(/!\[[^\]]*\]\([^)]*\)/g,'[图片]').slice(0,180)+'…');content.append(excerpt);
    const full=node('div','markdown-body entry-prose');full.hidden=true;content.append(full);
    const actions=node('div','work-actions');const expand=workButton('展开全文',async()=>{if(!full.hidden){full.hidden=true;excerpt.hidden=false;expand.textContent='展开全文';return;}expand.disabled=true;try{const item=await api('/api/entries/'+encodeURIComponent(entry.id));renderMarkdown(full,item.content+(item.reflection?'\n\n### 收获与思考\n'+item.reflection:'')+(item.next?'\n\n### 下一步\n'+item.next:''));full.hidden=false;excerpt.hidden=true;expand.textContent='收起';}catch(e){workError(e);}finally{expand.disabled=false;}},'text-button');
    actions.append(expand,workButton('编辑与关联',()=>openResource('entry',entry.id),'text-button'));content.append(actions);card.append(date,content);list.append(card);
  });
}
function clearFilters() { ['#log-query', '#filter-subject', '#filter-from', '#filter-to'].forEach(selector => $(selector).value = ''); loadEntries(); }
function openEntry(entry = null) {
  const form = $('#entry-form'); form.reset(); state.editingId = entry?.id ?? null; state.draftKey = 'entry:'+(entry?.id || crypto.randomUUID()); state.entryUpdated=entry?.updated_at||''; work.noteOrigin=null;
  ['title', 'date', 'subject', 'content', 'reflection', 'next', 'mood'].forEach(key => { const field = form.elements.namedItem(key); const value = entry?.[key] ?? (key === 'date' ? today() : key === 'mood' ? 'okay' : ''); if (key === 'mood' && value && ![...field.options].some(option => option.value === value)) { const option = node('option', '', value); option.value = value; field.append(option); } field.value = value; });
  $('#entry-dialog-title').textContent = entry ? '编辑这段学习足迹' : '记下今天的学习'; $('#delete-entry').hidden = !entry; $('#entry-error').hidden = true;
  entryBaseline = entrySnapshot(); setEntryMode(false);
  $('#entry-dialog').showModal(); showRelations('entry',state.editingId,$('#entry-relations'));
}
function closeEntry() { if (state.saving || assetUploads) return; if (entrySnapshot() !== entryBaseline && !window.confirm('这条日志还有未保存的修改，关闭后可从草稿恢复。确定关闭吗？')) return; $('#entry-dialog').close(); window.StudyMarkdown?.dispose($('#entry-preview')); }
async function saveEntry(event) {
  event.preventDefault(); if (state.saving || assetUploads) return;
  setEntryMode(false);
  const form = $('#entry-form'); if (!form.reportValidity()) return;
  const values = Object.fromEntries(new FormData(form).entries());
  state.saving = true; form.inert = true; $('#save-entry').disabled = true; $('#delete-entry').disabled = true; $('#entry-error').hidden = true;
  try { await api(state.editingId === null && work.noteOrigin ? '/api/linked-notes' : state.editingId === null ? '/api/entries' : '/api/entries/' + encodeURIComponent(state.editingId), { method: state.editingId === null ? 'POST' : 'PATCH', body: state.editingId === null && work.noteOrigin ? {kind:'entry',origin_kind:work.noteOrigin.kind,origin_id:work.noteOrigin.id,data:values} : values }); clearDraft('entry'); work.noteOrigin=null; $('#entry-dialog').close(); window.StudyMarkdown?.dispose($('#entry-preview')); notify(state.editingId === null ? '这份学习收获，已经好好存下来了。' : '学习记录已更新。'); await Promise.allSettled([loadEntries(), loadSummary()]); }
  catch (error) { $('#entry-error').textContent = error.message; $('#entry-error').hidden = false; }
  finally { state.saving = false; form.inert = false; $('#save-entry').disabled = false; $('#delete-entry').disabled = false; }
}
async function deleteEntry() {
  if (state.editingId === null || state.saving || assetUploads) return;
  if (!window.confirm('确定删除这条学习记录吗？将移入回收站，可随时恢复。')) return;
  state.saving = true; $('#entry-form').inert = true; $('#delete-entry').disabled = true; $('#save-entry').disabled = true;
  try { await api('/api/entries/' + encodeURIComponent(state.editingId), { method: 'DELETE' }); $('#entry-dialog').close(); window.StudyMarkdown?.dispose($('#entry-preview')); clearDraft('entry'); notify('这条学习记录已移入回收站。'); await Promise.allSettled([loadEntries(), loadSummary()]); }
  catch (error) { $('#entry-error').textContent = error.message; $('#entry-error').hidden = false; }
  finally { state.saving = false; $('#entry-form').inert = false; $('#delete-entry').disabled = false; $('#save-entry').disabled = false; }
}

async function saveConfig(event) {
  event.preventDefault(); $('#save-config').disabled = true; $('#config-save-status').textContent = '正在保存…';
  const payload = { base_url: $('#config-base-url').value.trim(), model: $('#config-model').value.trim() };
  const key = $('#config-api-key').value.trim(); if (key) payload.api_key = key;
  try { await api('/api/config', { method: 'POST', body: payload }); $('#config-api-key').value = ''; await Promise.allSettled([loadConfig(), loadHealth()]); notify('连接设置已保存。发一条消息，开始记录吧。'); if (!state.config?.environment_overrides?.length) $('#config-save-status').textContent = '已保存；实际连接将在发送消息时验证。'; }
  catch (error) { $('#config-save-status').textContent = error.message; notify(error.message, true); }
  finally { $('#save-config').disabled = false; }
}
async function applyToken(event) {
  event.preventDefault(); const input = $('#access-token').value.trim();
  if (!input) { notify('请输入访问令牌；如需移除，请点击“清除浏览器令牌”。', true); return; }
  const previous = token; token = input;
  try { await api('/api/config'); writeStorage(sessionStorage, TOKEN_KEY, token); $('#access-token').value = ''; await refreshData(); notify('浏览器访问令牌已应用。'); }
  catch (error) { token = previous; updateConnectionUI(); notify(error.message, true); }
}
async function refreshData() { await loadHealth(); await Promise.allSettled([loadConfig(), loadSummary(), loadEntries(), loadSession(), loadDocuments(), loadFuture()]); if (library.selected) renderMarkdown($('#document-preview'), $('#document-content').value); updateConnectionUI(); }
async function exportBackup() {
  try { const data = await api('/api/export'); const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })); const anchor = node('a'); anchor.href = url; anchor.download = '拾光-学习日志-' + today() + '.json'; document.body.append(anchor); anchor.click(); anchor.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000); notify('学习日志备份已导出。'); }
  catch (error) { notify(error.message, true); if (error.status === 401) setView('settings'); }
}
async function importBackup(event) {
  const file = event.target.files?.[0]; if (!file) return;
  try {
    if (file.size > 256 * 1024 * 1024) throw new Error('备份文件超过 256 MB。请使用数据目录迁移大型资料库。');
    let data; try { data = JSON.parse(await file.text()); } catch { throw new Error('无法读取这个 JSON 文件，请选择拾光导出的备份。'); }
    if (![1, 2, 3].includes(data.version) || !Array.isArray(data.entries)) throw new Error('备份格式不正确，请选择拾光导出的 JSON 备份。');
    if (!window.confirm('将导入备份中的 ' + data.entries.length + ' 条学习记录' + (data.documents?.length ? '、' + data.documents.length + ' 份 Markdown 文件' : '') + (data.future_learning?.length ? '、' + data.future_learning.length + ' 条未来学习知识' : '') + '及附带图片。同编号的现有内容会被备份覆盖，其他内容保留。确定继续吗？')) return;
    $('#import-button').disabled = true;
    const result = await api('/api/import', { method: 'POST', body: data });
    notify(result.added !== undefined ? '备份已导入：新增 ' + result.added + ' 条，更新 ' + result.updated + ' 条。' : '备份导入完成。'); await Promise.allSettled([loadEntries(), loadSummary(), loadDocuments(), loadFuture()]);
  } catch (error) { notify(error.message, true); }
  finally { event.target.value = ''; $('#import-button').disabled = false; }
}

function renderMarkdown(element, text) {
  window.StudyMarkdown?.dispose(element);
  if (window.StudyMarkdown) { element.innerHTML = window.StudyMarkdown.render(text); window.StudyMarkdown.hydrate(element, token).catch(() => {}); }
  else element.textContent = text;
}
function entrySnapshot() { return JSON.stringify(Object.fromEntries(new FormData($('#entry-form')).entries())); }
function setEntryMode(preview) {
  entryPreview = preview;
  $('#entry-content').hidden = preview; $('#entry-toolbar').hidden = preview; $('#entry-preview').hidden = !preview;
  [['#entry-edit-tab', !preview], ['#entry-preview-tab', preview]].forEach(([selector, active]) => { $(selector).classList.toggle('active', active); $(selector).setAttribute('aria-pressed', String(active)); });
  if (preview) { renderMarkdown($('#entry-preview'), $('#entry-content').value); if (!$('#entry-content').value.trim()) $('#entry-preview').append(node('p', 'preview-placeholder', '写下一点内容，预览会显示在这里。')); }
}
function editorInput(target) { return $(target === 'entry' ? '#entry-content' : '#document-content'); }
function insertText(target, before, after = '', placeholder = '') {
  const input = editorInput(target); const start = input.selectionStart, end = input.selectionEnd;
  const selected = input.value.slice(start, end) || placeholder; const value = before + selected + after;
  if (input.maxLength > 0 && input.value.length - (end - start) + value.length > input.maxLength) { notify('内容已达到字数上限，请精简后再插入。', true); return false; }
  input.setRangeText(value, start, end, 'end'); input.focus();
  if (placeholder && start === end) input.setSelectionRange(start + before.length, start + before.length + placeholder.length);
  input.dispatchEvent(new Event('input', { bubbles: true }));
  return true;
}
function applyFormat(target, format) {
  if (target === 'entry') setEntryMode(false); else setDocumentMode(true);
  const input = editorInput(target); const atStart = input.selectionStart === 0 || input.value[input.selectionStart - 1] === '\n';
  const prefix = atStart ? '' : '\n';
  const formats = { heading: [prefix + '## ', '', '小标题'], bold: ['**', '**', '重点内容'], list: [prefix + '- ', '', '列表内容'], quote: [prefix + '> ', '', '引用内容'], code: [prefix + '```\n', '\n```\n', '在这里写代码'] };
  if (formats[format]) insertText(target, ...formats[format]);
}
function readFileBase64(file) { return new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(',')[1]); reader.onerror = () => reject(new Error('无法读取图片，请重新选择。')); reader.readAsDataURL(file); }); }
function updateUploadControls() {
  $('#save-entry').disabled = state.saving || assetUploads > 0; $('#delete-entry').disabled = state.saving || assetUploads > 0;
  $('#save-document').disabled = library.saving || assetUploads > 0; $('#new-document').disabled = library.saving || assetUploads > 0;
  $$('[data-add-image]').forEach(button => button.disabled = assetUploads > 0);
}
async function uploadImages(target, files) {
  if (assetUploads || !files.length) return;
  if (target === 'entry') setEntryMode(false); else setDocumentMode(true);
  assetUploads++; updateUploadControls(); const status = $('#' + target + '-image-status');
  let success = 0;
  try {
    for (const file of files) {
      status.textContent = '正在保存图片…';
      if (!['image/png', 'image/jpeg', 'image/gif', 'image/webp'].includes(file.type)) throw new Error('请选择 PNG、JPG、GIF 或 WebP 图片。');
      if (file.size > 8 * 1024 * 1024) throw new Error('图片超过 8 MB，请压缩后再插入。');
      const asset = await api('/api/assets', { method: 'POST', body: { name: file.name || '粘贴的图片.png', data_base64: await readFileBase64(file) } });
      const alt = (file.name || '学习配图').replace(/[\[\]\\\r\n]/g, '').slice(0, 100);
      if (!insertText(target, '\n![' + alt + '](' + asset.url + ')\n')) throw new Error('图片已保存，但正文达到字数上限，请精简后重新插入。');
      success++;
    }
    status.textContent = '已插入 ' + success + ' 张图片';
  } catch (error) { status.textContent = success ? '已插入 ' + success + ' 张，部分失败' : '图片未能插入'; notify(error.message, true); }
  finally { assetUploads--; updateUploadControls(); }
}
function documentSnapshot() { return JSON.stringify({ name: $('#document-name').value, content: $('#document-content').value }); }
function documentDirty() { return library.selected !== null && documentSnapshot() !== library.baseline; }
function canLeaveDocument() {
  if (library.saving || assetUploads) { notify('正在保存，请稍候。'); return false; }
  if (!documentDirty()) return true;
  if (!window.confirm('这份 Markdown 文件还有未保存的修改，关闭后可从草稿恢复。确定关闭吗？')) return false;
  const previous = JSON.parse(library.baseline); $('#document-name').value = previous.name; $('#document-content').value = previous.content;
  updateDocumentStatus(); if (!library.editing) renderMarkdown($('#document-preview'), previous.content); return true;
}
function updateDocumentStatus() {
  $('#document-save-status').textContent = library.saving ? '正在保存…' : documentDirty() ? '有未保存的修改' : library.selected?.id ? '已保存到本地' : '新文件，尚未保存';
  $('#document-save-status').classList.toggle('unsaved', documentDirty());
  updateDocumentFileButtons();
}
function setDocumentMode(editing) {
  library.editing = editing; $('#document-edit-area').hidden = !editing; $('#document-preview').hidden = editing;
  $('#document-read-tab').classList.toggle('active', !editing); $('#document-edit-tab').classList.toggle('active', editing);
  $('#document-read-tab').setAttribute('aria-pressed', String(!editing)); $('#document-edit-tab').setAttribute('aria-pressed', String(editing));
  if (!editing) { renderMarkdown($('#document-preview'), $('#document-content').value); decorateDocument(); if (!$('#document-content').value.trim()) $('#document-preview').append(node('p', 'preview-placeholder', '这份笔记还是空白，点击“编辑”开始记录。')); }
}
function humanSize(size) { return size < 1024 ? size + ' B' : size < 1024 * 1024 ? (size / 1024).toFixed(1) + ' KB' : (size / 1024 / 1024).toFixed(1) + ' MB'; }
function documentDate(value) { const date = new Date(value); return Number.isNaN(date.getTime()) ? '' : new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(date); }
let documentFilesSequence = 0, currentDocumentFiles = null, documentFileOpening = false;
function updateDocumentFileButtons() {
  const ready = Boolean(library.selected?.id && currentDocumentFiles && !documentDirty() && !library.saving && !documentFileOpening);
  $('#open-document-pdf').disabled = !ready || !currentDocumentFiles?.pdf_exists;
  $('#reveal-document-md').disabled = !ready;
  $('#open-document-pdf').title = currentDocumentFiles?.pdf_exists ? currentDocumentFiles.pdf_path : '这份文档还没有 PDF';
  $('#reveal-document-md').title = currentDocumentFiles?.md_path || '先选择并保存文档';
}
async function loadDocumentFiles(id) {
  const sequence = ++documentFilesSequence; currentDocumentFiles = null; updateDocumentFileButtons();
  $('#document-files-status').textContent = id ? '正在读取源文件与 PDF…' : '保存文档后，会在本机资料文件夹中生成 MD 源文件。';
  if (!id) return;
  try {
    const info = await api('/api/documents/' + encodeURIComponent(id) + '/files');
    if (sequence !== documentFilesSequence || library.selected?.id !== id) return;
    currentDocumentFiles = info;
    $('#document-files-status').textContent = info.pdf_exists ? (info.pdf_current ? 'PDF 与 MD 源文件已归档。' : '已有 PDF；它可能尚未反映最新的 MD 修改。') : 'MD 源文件已归档；这份文档尚未制作 PDF。';
    $('#document-files-status').title = info.directory;
  } catch (error) { if (sequence === documentFilesSequence) $('#document-files-status').textContent = '源文件暂未同步：' + error.message; }
  finally { if (sequence === documentFilesSequence) updateDocumentFileButtons(); }
}
async function openDocumentFile(action) {
  const id = library.selected?.id;
  if (!id || documentFileOpening) return;
  if (documentDirty() || library.saving) { notify('请先保存文档修改。', true); return; }
  documentFileOpening = true; updateDocumentFileButtons();
  try {
    const info = await api('/api/documents/' + encodeURIComponent(id) + '/files');
    if (library.selected?.id !== id) return;
    if (action === 'open-pdf' && !info.pdf_exists) { await loadDocumentFiles(id); notify('这份文档还没有 PDF。', true); return; }
    if (action === 'open-pdf' && !info.pdf_current && !window.confirm('这份 PDF 可能还未包含最新的 MD 修改，仍要打开吗？')) return;
    await api('/api/documents/' + encodeURIComponent(id) + '/' + action, { method: 'POST', body: {} });
    notify(action === 'open-pdf' ? '已请求系统打开 PDF。' : '已在资源管理器中定位 MD 源文件。');
  } catch (error) { notify(error.message, true); }
  finally { documentFileOpening = false; updateDocumentFileButtons(); }
}
function displayDocument(doc, editing = false) {
  library.draftKey='document:'+(doc.id||crypto.randomUUID()); work.noteOrigin=null; library.selected = doc; $('#document-empty').hidden = true; $('#document-open').hidden = false;
  $('#document-name').value = doc.name || '未命名笔记.md'; $('#document-content').value = doc.content || '';
  $('#document-title').textContent = doc.name || '未命名笔记.md';
  $('#document-meta').textContent = doc.id ? humanSize(doc.size || 0) + ' · 更新于 ' + documentDate(doc.updated_at) : '本地笔记 · 支持图文排版';
  $('#download-document').disabled = !doc.id; $('#delete-document').hidden = !doc.id; $('#document-error').hidden = true;
  library.baseline = documentSnapshot(); updateDocumentStatus(); setDocumentMode(editing); renderDocumentList(); loadDocumentFiles(doc.id); showRelations('document',doc.id,$('#document-relations')); decorateDocument(); loadReadingPosition(doc.id);
}
async function loadDocuments() {
  const sequence = ++library.sequence; const query = $('#document-query').value.trim();
  try { const result = await api('/api/documents?' + new URLSearchParams(query ? { query } : {})); if (sequence !== library.sequence) return; library.documents = result.documents || []; renderDocumentList(); if (library.selected?.id) loadDocumentFiles(library.selected.id); }
  catch (error) { if (sequence !== library.sequence) return; $('#documents-count').textContent = '加载失败'; $('#documents-list').replaceChildren(emptyState('文件暂时无法加载', error.message, '重试', loadDocuments)); }
}
function renderDocumentList() {
  $('#documents-count').textContent = '共 ' + library.documents.length + ' 份' + ($('#document-query').value.trim() ? '匹配文件' : '文件'); const list = $('#documents-list'); list.replaceChildren();
  if (!library.documents.length) { list.append(node('p', 'document-list-empty', $('#document-query').value.trim() ? '没有找到匹配的文件，试试其他关键词。' : '这里还没有文件\n导入或新建你的第一份笔记。')); return; }
  library.documents.forEach(doc => { const button = node('button', 'document-item' + (library.selected?.id === doc.id ? ' active' : '')); button.type = 'button'; button.setAttribute('aria-pressed', String(library.selected?.id === doc.id)); const mark = node('span', 'document-file-mark', 'MD'); const text = node('span', 'document-item-text'); text.append(node('strong', '', doc.name), node('small', '', humanSize(doc.size || 0) + ' · ' + documentDate(doc.updated_at))); button.append(mark, text); button.addEventListener('click', () => openDocument(doc.id)); list.append(button); });
}
async function openDocument(id) {
  if (library.selected?.id === id) return;
  if (!canLeaveDocument()) return; const opening = ++library.opening; const snapshot = documentSnapshot();
  try { const doc = await api('/api/documents/' + encodeURIComponent(id)); if (opening === library.opening) { if (documentSnapshot() !== snapshot) { notify('当前笔记有新的修改，请保存后再切换。'); return; } displayDocument(doc); } }
  catch (error) { if (opening === library.opening) notify(error.message, true); }
}
function newDocument() {
  if (!canLeaveDocument()) return; library.opening++;
  displayDocument({ id: null, name: '未命名笔记.md', content: '' }, true); $('#document-name').focus(); $('#document-name').select();
}
async function saveDocument() {
  if (!library.selected || library.saving || assetUploads) return;
  let name = $('#document-name').value.trim(); const content = $('#document-content').value;
  if (!name) { setDocumentMode(true); $('#document-name').focus(); notify('请给文件起个名字。', true); return; }
  if (!/\.(md|markdown)$/i.test(name)) name += '.md';
  if (new TextEncoder().encode(content).length > 2 * 1024 * 1024) { notify('文件内容超过 2 MB，请精简后保存。', true); return; }
  library.saving = true; updateUploadControls(); updateDocumentStatus(); $('#document-error').hidden = true;
  const id = library.selected.id; const snapshot = documentSnapshot();
  try {
    const oldDraftKey=library.draftKey; const origin=work.noteOrigin; const doc = await api(!id && origin ? '/api/linked-notes' : id ? '/api/documents/' + encodeURIComponent(id) : '/api/documents', { method: id ? 'PATCH' : 'POST', body: !id && origin ? {kind:'document',origin_kind:origin.kind,origin_id:origin.id,data:{name,content}} : { name, content } });
    if (documentSnapshot() === snapshot) clearDraft('document',oldDraftKey); work.noteOrigin=null;
    if (documentSnapshot() === snapshot) displayDocument(doc, library.editing);
    else { library.selected = doc; library.baseline = JSON.stringify({ name, content }); library.draftKey='document:'+doc.id; clearDraft('document',oldDraftKey); draftChanged('document'); $('#document-title').textContent = doc.name; $('#download-document').disabled = false; $('#delete-document').hidden = false; loadDocumentFiles(doc.id); }
    await loadDocuments(); notify(doc.file_warning || 'Markdown 文件及源文件已保存。', Boolean(doc.file_warning));
  } catch (error) { $('#document-error').textContent = error.message; $('#document-error').hidden = false; }
  finally { library.saving = false; updateUploadControls(); updateDocumentStatus(); }
}
async function importDocuments(event) {
  const files = [...(event.target.files || [])]; event.target.value = ''; if (!files.length || library.importing) return;
  if (!canLeaveDocument()) return;
  library.importing = true; $('#import-documents').disabled = true; const failures = []; let last = null, imported = 0;
  try {
    for (const file of files) {
      try { if (!/\.(md|markdown)$/i.test(file.name)) throw new Error('仅支持 .md 或 .markdown 文件'); if (file.size > 2 * 1024 * 1024) throw new Error('超过 2 MB'); let content; try { content = new TextDecoder('utf-8', { fatal: true }).decode(await file.arrayBuffer()); } catch { throw new Error('请将文件另存为 UTF-8 编码后导入'); } last = await api('/api/documents', { method: 'POST', body: { name: file.name, content } }); imported++; }
      catch (error) { failures.push(file.name + '：' + error.message); }
    }
    if (last) { $('#document-query').value = ''; if (!documentDirty()) displayDocument(last); await loadDocuments(); notify('已导入 ' + imported + ' 份 Markdown 文件。'); }
    if (failures.length) notify(failures.join('\n'), true);
  } finally { library.importing = false; $('#import-documents').disabled = false; }
}
async function downloadDocument() {
  if (!library.selected?.id) return;
  if (documentDirty()) { notify('请先保存修改，再下载最新文件。', true); return; }
  try { const headers = token ? { Authorization: 'Bearer ' + token } : {}; const response = await fetch('/api/documents/' + encodeURIComponent(library.selected.id) + '/download', { headers, credentials: 'same-origin' }); if (!response.ok) throw new Error('下载失败，请重试。'); const url = URL.createObjectURL(await response.blob()); const link = node('a'); link.href = url; link.download = library.selected.name; document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
  catch (error) { notify(error.message, true); }
}
async function deleteDocument() {
  if (!library.selected?.id || library.saving || assetUploads) return;
  if (!window.confirm('确定删除“' + library.selected.name + '”吗？将移入回收站，可随时恢复。')) return;
  library.saving = true; updateUploadControls();
  try { await api('/api/documents/' + encodeURIComponent(library.selected.id), { method: 'DELETE' }); library.selected = null; library.baseline = ''; loadDocumentFiles(null); window.StudyMarkdown?.dispose($('#document-preview')); $('#document-empty').hidden = false; $('#document-open').hidden = true; await loadDocuments(); clearDraft('document'); notify('文档已移入回收站。'); }
  catch (error) { notify(error.message, true); }
  finally { library.saving = false; updateUploadControls(); }
}

$$('[data-view]').forEach(button => button.addEventListener('click', () => setView(button.dataset.view)));
$$('[data-open-settings]').forEach(button => button.addEventListener('click', () => setView('settings')));
$$('[data-prompt]').forEach(button => button.addEventListener('click', () => fillPrompt(button.dataset.prompt)));
$('#sidebar-add').addEventListener('click', () => openEntry());
$('#add-entry').addEventListener('click', () => openEntry());
$('#overview-review').addEventListener('click', () => fillPrompt('请根据我的学习记录，回顾最近一周的学习情况，总结进步、薄弱点和接下来的复习建议。'));
$('#chat-form').addEventListener('submit', sendMessage);
$('#chat-input').addEventListener('input', () => { resizeComposer(); updateConnectionUI(); });
$('#chat-input').addEventListener('keydown', event => { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); if (!$('#send-message').disabled) $('#chat-form').requestSubmit(); } });
$('#new-chat').addEventListener('click', () => { if (state.sending) return; state.sessionId = ''; state.failedRequest = null; writeStorage(localStorage, SESSION_KEY, ''); $('#messages').replaceChildren(); $('#chat-welcome').hidden = false; $('#chat-input').value = ''; resizeComposer(); updateConnectionUI(); notify('已开启新对话，学习日志仍会保留。'); });
$('#entry-form').addEventListener('submit', saveEntry);
$('#close-entry').addEventListener('click', closeEntry);
$('#cancel-entry').addEventListener('click', closeEntry);
$('#entry-dialog').addEventListener('cancel', event => { event.preventDefault(); closeEntry(); });
$('#delete-entry').addEventListener('click', deleteEntry);
$('#config-form').addEventListener('submit', saveConfig);
$('#token-form').addEventListener('submit', applyToken);
$('#clear-token').addEventListener('click', async () => { token = ''; writeStorage(sessionStorage, TOKEN_KEY, ''); $('#access-token').value = ''; await refreshData(); notify('浏览器访问令牌已清除。'); });
$('#clear-filters').addEventListener('click', clearFilters);
let filterTimer;
['#log-query', '#filter-subject'].forEach(selector => $(selector).addEventListener('input', () => { clearTimeout(filterTimer); filterTimer = setTimeout(loadEntries, 300); }));
['#filter-from', '#filter-to'].forEach(selector => $(selector).addEventListener('change', loadEntries));
$('#export-logs').addEventListener('click', exportBackup);
$('#settings-export').addEventListener('click', exportBackup);
$('#import-button').addEventListener('click', () => $('#import-file').click());
$('#import-file').addEventListener('change', importBackup);
$('#entry-edit-tab').addEventListener('click', () => setEntryMode(false));
$('#entry-preview-tab').addEventListener('click', () => setEntryMode(true));
$$('[data-format]').forEach(button => button.addEventListener('click', () => applyFormat(button.closest('[data-editor]').dataset.editor, button.dataset.format)));
$$('[data-add-image]').forEach(button => button.addEventListener('click', () => { imageTarget = button.dataset.addImage; $('#editor-image-file').click(); }));
$('#editor-image-file').addEventListener('change', event => { const files = [...event.target.files]; event.target.value = ''; uploadImages(imageTarget, files); });
['entry', 'document'].forEach(target => {
  const input = editorInput(target); const editor = input.closest('.markdown-editor');
  input.addEventListener('paste', event => { const files = [...(event.clipboardData?.items || [])].filter(item => item.kind === 'file' && item.type.startsWith('image/')).map(item => item.getAsFile()).filter(Boolean); if (files.length) { event.preventDefault(); uploadImages(target, files); } });
  editor.addEventListener('dragover', event => { if ([...(event.dataTransfer?.types || [])].includes('Files')) { event.preventDefault(); editor.classList.add('dragging'); } });
  editor.addEventListener('dragleave', event => { if (!editor.contains(event.relatedTarget)) editor.classList.remove('dragging'); });
  editor.addEventListener('drop', event => { editor.classList.remove('dragging'); if (event.dataTransfer?.files.length) { event.preventDefault(); uploadImages(target, [...event.dataTransfer.files]); } });
});
$('#document-read-tab').addEventListener('click', () => setDocumentMode(false));
$('#document-edit-tab').addEventListener('click', () => setDocumentMode(true));
$('#new-document').addEventListener('click', newDocument);
$('#save-document').addEventListener('click', saveDocument);
$('#download-document').addEventListener('click', downloadDocument);
$('#open-document-pdf').addEventListener('click', () => openDocumentFile('open-pdf'));
$('#reveal-document-md').addEventListener('click', () => openDocumentFile('reveal-md'));
$('#delete-document').addEventListener('click', deleteDocument);
$('#import-documents').addEventListener('click', () => $('#document-files').click());
$('#document-empty-import').addEventListener('click', () => $('#document-files').click());
$('#document-files').addEventListener('change', importDocuments);
$('#document-name').addEventListener('input', updateDocumentStatus);
$('#document-content').addEventListener('input', updateDocumentStatus);
let documentSearchTimer;
$('#document-query').addEventListener('input', () => { clearTimeout(documentSearchTimer); documentSearchTimer = setTimeout(loadDocuments, 250); });
window.addEventListener('beforeunload', event => { if (work.restoring) return; if (documentDirty() || ($('#entry-dialog').open && entrySnapshot() !== entryBaseline) || assetUploads) { event.preventDefault(); event.returnValue = ''; } });
window.addEventListener('keydown', event => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { if ($('#entry-dialog').open) { event.preventDefault(); $('#entry-form').requestSubmit(); } else if (state.view === 'documents' && library.selected) { event.preventDefault(); saveDocument(); } } });
window.addEventListener('focus', () => { if (state.view === 'documents' && library.selected?.id && !library.saving && !documentDirty()) loadDocumentFiles(library.selected.id); });
window.addEventListener('hashchange', routeHash);
$('#today-date').textContent = new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: 'long', day: 'numeric', weekday: 'long' }).format(new Date());
setupWorkspace();
setupFuture();
$('#entries-prev').onclick=()=>{state.entryOffset=Math.max(0,(state.entryOffset||0)-20);loadEntries(false);};
$('#entries-next').onclick=()=>{state.entryOffset=(state.entryOffset||0)+20;loadEntries(false);};
routeHash();
renderCharts({ days: [], subjects: [] });
updateConnectionUI();
refreshData();
