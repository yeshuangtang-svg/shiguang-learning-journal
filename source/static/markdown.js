/* Offline Markdown rendering. Never execute HTML embedded in a note. */
'use strict';
(() => {
  const localAsset = /^\/api\/assets\/[a-f0-9]{64}$/;
  const renderings = new WeakMap();
  const escapeHTML = text => String(text).replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]));
  const parser = new marked.Marked({ gfm: true, breaks: true, renderer: {
    html(token) { return escapeHTML(token.text); }
  }});

  function webURL(value) {
    try {
      const url = new URL(value);
      if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) return null;
      return url;
    } catch { return null; }
  }

  function render(text) {
    const source = String(text || '');
    const fragment = DOMPurify.sanitize(parser.parse(source), {
      RETURN_DOM_FRAGMENT: true,
      ALLOWED_TAGS: ['p', 'br', 'hr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong', 'em', 'del', 's', 'blockquote', 'ul', 'ol', 'li', 'pre', 'code', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'a', 'img', 'input'],
      ALLOWED_ATTR: ['href', 'src', 'alt', 'title', 'start', 'align', 'type', 'checked', 'disabled'],
      ALLOW_DATA_ATTR: false,
      ALLOW_ARIA_ATTR: false
    });
    fragment.querySelectorAll('a').forEach(link => {
      const href = link.getAttribute('href') || '';
      if (!webURL(href) && !/^mailto:[^\s<>]+$/i.test(href)) link.removeAttribute('href');
      else { link.target = '_blank'; link.rel = 'noopener noreferrer'; }
    });
    fragment.querySelectorAll('input').forEach(input => {
      if (input.type !== 'checkbox') input.remove();
      else { input.disabled = true; input.tabIndex = -1; }
    });
    fragment.querySelectorAll('img').forEach(img => {
      const src = img.getAttribute('src') || '';
      const url = webURL(src);
      img.removeAttribute('src');
      img.loading = 'lazy'; img.decoding = 'async'; img.referrerPolicy = 'no-referrer';
      if (localAsset.test(src)) img.dataset.asset = src;
      else if (url && url.origin !== location.origin && !['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)) img.src = url.href;
      else {
        const hint = document.createElement('span');
        hint.className = 'image-unavailable';
        hint.textContent = '〔' + (img.alt || '图片') + '：请通过“插入图片”保存到本地〕';
        img.replaceWith(hint);
        return;
      }
      img.tabIndex = 0; img.setAttribute('role', 'button');
      img.setAttribute('aria-label', '放大查看：' + (img.alt || '学习配图'));
      img.title = (img.title ? img.title + ' · ' : '') + '点击放大查看';
    });
    const wrapper = document.createElement('div');
    wrapper.append(fragment);
    return wrapper.innerHTML;
  }

  function dispose(element) {
    const previous = renderings.get(element);
    if (!previous) return;
    previous.controller.abort();
    previous.urls.forEach(url => URL.revokeObjectURL(url));
    renderings.delete(element);
  }

  async function hydrate(element, token = '') {
    dispose(element);
    const rendering = { controller: new AbortController(), urls: [] };
    renderings.set(element, rendering);
    await Promise.all([...element.querySelectorAll('img[data-asset]')].map(async img => {
      const path = img.dataset.asset;
      if (!localAsset.test(path || '')) return;
      try {
        const response = await fetch(path, { headers: token ? { Authorization: 'Bearer ' + token } : {}, credentials: 'same-origin', signal: rendering.controller.signal });
        if (!response.ok) throw new Error('图片读取失败');
        const blob = await response.blob();
        if (!['image/png', 'image/jpeg', 'image/gif', 'image/webp'].includes(blob.type.split(';')[0])) throw new Error('图片格式无效');
        if (rendering.controller.signal.aborted || renderings.get(element) !== rendering || !element.contains(img)) return;
        const url = URL.createObjectURL(blob);
        rendering.urls.push(url); img.src = url;
      } catch (error) {
        if (error.name === 'AbortError') return;
        img.alt = (img.alt || '图片') + '（加载失败，请重新打开预览或检查访问令牌）';
        img.classList.add('image-load-error');
      }
    }));
  }
  window.StudyMarkdown = Object.freeze({ render, hydrate, dispose });
})();
