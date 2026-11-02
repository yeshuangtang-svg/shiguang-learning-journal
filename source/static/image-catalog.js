'use strict';
(() => {
  const dialog = document.createElement('dialog');
  dialog.id = 'image-catalog'; dialog.setAttribute('aria-labelledby', 'image-catalog-title');
  dialog.innerHTML = `<div class="modal-heading"><div><span class="eyebrow">YOUR IMAGE LIBRARY</span><h2 id="image-catalog-title">图片清单</h2></div><button type="button" class="icon-button" id="close-image-catalog" aria-label="关闭图片清单">×</button></div><div class="modal-body"><p class="catalog-help">点击缩略图可放大查看，也可以打开图片或定位文件。清单收录应用内插图及文档资料中的 PNG、JPG、GIF、WebP 图片（单张不超过 8 MB）。</p><div class="catalog-toolbar"><input type="search" id="image-catalog-query" aria-label="搜索图片" placeholder="搜索图片名称或位置"><button type="button" class="button button-secondary" id="refresh-image-catalog">刷新清单</button></div><p id="image-catalog-status" role="status"></p><p id="image-catalog-path"></p><div id="image-catalog-list"></div></div>`;
  document.body.append(dialog);
  const list = dialog.querySelector('#image-catalog-list'), status = dialog.querySelector('#image-catalog-status'), query = dialog.querySelector('#image-catalog-query');
  let sequence = 0, urls = [], records = [];
  function release() { urls.forEach(url => URL.revokeObjectURL(url)); urls = []; }
  function filter() {
    const value = query.value.trim().toLowerCase(); let count = 0;
    records.forEach(({card,item}) => { card.hidden = ![item.name, ...item.paths].join(' ').toLowerCase().includes(value); if (!card.hidden) count++; });
    status.textContent = records.length ? `共 ${records.length} 张图片${value ? '，匹配 ' + count + ' 张' : ''}` : '还没有图片。在日志或文档中插入图片后，刷新即可查看。';
  }
  async function nativeAction(item, action, location, button) {
    button.disabled = true;
    try { await api('/api/images/' + item.id + '/' + action, {method:'POST',body:{location}}); notify(action === 'open' ? '已请求系统打开图片。' : '已在资源管理器中定位图片。'); }
    catch (error) { notify(error.message, true); }
    finally { button.disabled = false; }
  }
  async function refresh() {
    const current = ++sequence; release(); records = []; list.replaceChildren(); status.textContent = '正在整理图片与位置…';
    dialog.querySelector('#image-catalog-path').textContent = '';
    try {
      const result = await api('/api/images'); if (current !== sequence) return;
      dialog.querySelector('#image-catalog-path').textContent = '清单文件：' + result.index_path + (result.skipped ? `（有 ${result.skipped} 个文件无法读取或不符合图片要求）` : '');
      for (const item of result.images) {
        const card = node('article','catalog-card'), preview = node('div','catalog-preview markdown-body'), img = node('img');
        img.alt = item.name; img.tabIndex = 0; img.setAttribute('role','button'); img.setAttribute('aria-label','放大查看：' + item.name); img.title = '点击放大查看';
        preview.append(img);
        const details = node('div','catalog-details'); details.append(node('h3','',item.name),node('p','catalog-size',humanSize(item.size) + ' · ' + item.paths.length + ' 个位置'));
        item.paths.forEach((path, location) => {
          const row = node('div','catalog-location'), actions = node('div','catalog-actions');
          row.append(node('p','',path));
          for (const [action,label] of [['open','打开图片'],['reveal','文件原位置']]) {
            const button = node('button','button button-secondary',label); button.type = 'button';
            button.addEventListener('click',() => nativeAction(item,action,location,button)); actions.append(button);
          }
          row.append(actions); details.append(row);
        });
        card.append(preview,details); list.append(card); records.push({card,item,img});
      }
      filter();
      // Bound concurrent thumbnail requests and discard stale results after closing.
      const queue = [...records];
      await Promise.all(Array.from({length:Math.min(4,queue.length)},async () => {
        while(queue.length && current === sequence) {
          const {item,img} = queue.shift();
          try {
            const response = await fetch(item.url,{headers:token ? {Authorization:'Bearer ' + token} : {},credentials:'same-origin'});
            if (!response.ok) throw Error('图片加载失败');
            const blob = await response.blob(); if(current !== sequence) return;
            const url = URL.createObjectURL(blob); urls.push(url); img.src = url;
          } catch { if(current === sequence) { img.replaceWith(node('p','','缩略图加载失败，请刷新重试。')); } }
        }
      }));
    } catch(error) { if(current === sequence) status.textContent = '加载失败：' + error.message; }
  }
  document.querySelector('#show-image-catalog').addEventListener('click',() => { dialog.showModal(); query.value = ''; refresh(); });
  dialog.querySelector('#close-image-catalog').addEventListener('click',() => dialog.close());
  dialog.querySelector('#refresh-image-catalog').addEventListener('click',refresh);
  query.addEventListener('input',filter);
  dialog.addEventListener('close',() => {sequence++;release();list.replaceChildren();records=[];});
})();
