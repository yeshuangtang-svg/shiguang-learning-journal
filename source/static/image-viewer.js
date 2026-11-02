/* A local, keyboard-accessible viewer for rendered note images. */
'use strict';
(() => {
  if (document.getElementById('image-viewer')) return;

  const viewer = document.createElement('dialog');
  viewer.id = 'image-viewer';
  viewer.setAttribute('aria-labelledby', 'image-viewer-title');
  viewer.setAttribute('aria-describedby', 'image-viewer-help');
  viewer.innerHTML = `
    <header class="image-viewer-header">
      <div class="image-viewer-caption"><span>IMAGE PREVIEW</span><h2 id="image-viewer-title">图片预览</h2></div>
      <button type="button" id="image-viewer-close" aria-label="关闭图片预览" title="关闭 · Esc"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="m6 6 12 12M6 18 18 6"/></svg></button>
    </header>
    <div id="image-viewer-stage" tabindex="0" aria-label="图片查看区域，滚轮缩放，放大后可拖动或使用方向键移动">
      <img id="image-viewer-image" alt="" draggable="false">
    </div>
    <footer class="image-viewer-footer">
      <p id="image-viewer-help">滚轮缩放 · 放大后拖动 · Esc 关闭</p>
      <div class="image-viewer-controls" role="group" aria-label="图片缩放">
        <button type="button" id="image-viewer-zoom-out" aria-label="缩小图片" title="缩小 · −">−</button>
        <output id="image-viewer-scale" aria-live="polite" aria-label="当前缩放比例">100%</output>
        <button type="button" id="image-viewer-zoom-in" aria-label="放大图片" title="放大 · +">+</button>
        <span class="image-viewer-divider" aria-hidden="true"></span>
        <button type="button" id="image-viewer-actual" title="以原始尺寸显示 · 1">100%</button>
        <button type="button" id="image-viewer-fit" title="完整显示图片 · 0">适应窗口</button>
      </div>
    </footer>`;
  document.body.append(viewer);

  const stage = viewer.querySelector('#image-viewer-stage');
  const image = viewer.querySelector('#image-viewer-image');
  const scaleLabel = viewer.querySelector('#image-viewer-scale');
  const closeButton = viewer.querySelector('#image-viewer-close');
  const zoomIn = viewer.querySelector('#image-viewer-zoom-in');
  const zoomOut = viewer.querySelector('#image-viewer-zoom-out');
  const actualButton = viewer.querySelector('#image-viewer-actual');
  const fitButton = viewer.querySelector('#image-viewer-fit');
  const maximumScale = 8;
  let width = 0, height = 0, scale = 1, panX = 0, panY = 0;
  let fitted = true, origin = null, previousFocus = null, request = 0;
  let drag = null, moved = false, blankPointer = false;

  const clamp = (value, minimum, maximum) => Math.min(maximum, Math.max(minimum, value));
  function fittedScale() { return Math.max(Number.EPSILON, Math.min(1, Math.max(1, stage.clientWidth - 40) / width, Math.max(1, stage.clientHeight - 40) / height)); }
  function minimumScale() { return Math.min(0.1, fittedScale()); }
  function bounds() { return { x: Math.max(0, (width * scale - stage.clientWidth) / 2), y: Math.max(0, (height * scale - stage.clientHeight) / 2) }; }
  function paint() {
    if (!viewer.open || !width || !height) return;
    const limit = bounds(); panX = clamp(panX, -limit.x, limit.x); panY = clamp(panY, -limit.y, limit.y);
    image.style.width = width * scale + 'px'; image.style.height = height * scale + 'px';
    image.style.left = (stage.clientWidth - width * scale) / 2 + panX + 'px';
    image.style.top = (stage.clientHeight - height * scale) / 2 + panY + 'px';
    stage.classList.toggle('can-pan', limit.x > 0 || limit.y > 0);
    const percent = scale * 100; scaleLabel.value = (percent < 10 ? percent.toFixed(1) : Math.round(percent)) + '%';
    zoomIn.disabled = scale >= maximumScale - 0.00001;
    zoomOut.disabled = scale <= minimumScale() + 0.00001;
    actualButton.setAttribute('aria-pressed', String(Math.abs(scale - 1) < 0.00001));
    fitButton.setAttribute('aria-pressed', String(fitted));
  }
  function zoom(next, anchorX = 0, anchorY = 0) {
    if (!viewer.open) return;
    const value = clamp(next, minimumScale(), maximumScale);
    const ratio = value / scale;
    panX = anchorX - (anchorX - panX) * ratio; panY = anchorY - (anchorY - panY) * ratio;
    scale = value; fitted = false; paint();
  }
  function fit() { if (!viewer.open) return; fitted = true; scale = fittedScale(); panX = panY = 0; paint(); }
  function releaseDrag() {
    if (drag && stage.hasPointerCapture(drag.pointerId)) stage.releasePointerCapture(drag.pointerId);
    drag = null; stage.classList.remove('is-dragging');
  }
  function cleanup() {
    request++; releaseDrag(); image.onload = image.onerror = null; image.removeAttribute('src');
    image.removeAttribute('style'); image.alt = ''; width = height = 0;
    const focus = origin?.isConnected ? origin : previousFocus?.isConnected ? previousFocus : null;
    origin = previousFocus = null; moved = blankPointer = false;
    if (focus && typeof focus.focus === 'function') focus.focus({ preventScroll: true });
  }
  function close() { if (viewer.open) viewer.close(); else cleanup(); }
  function open(source) {
    // Reuse the displayed URL, including authenticated blob URLs, without a new API request.
    const url = source.currentSrc || source.getAttribute('src');
    if (!source.complete || !source.naturalWidth || !source.naturalHeight || !url || source.classList.contains('image-load-error')) return;
    const pending = ++request; origin = source; previousFocus = document.activeElement;
    width = source.naturalWidth; height = source.naturalHeight; scale = 1; panX = panY = 0;
    image.alt = source.alt || '学习笔记中的图片';
    viewer.querySelector('#image-viewer-title').textContent = source.alt || '图片预览';
    image.referrerPolicy = 'no-referrer'; image.decoding = 'async';
    let shown = false;
    const show = () => {
      if (pending !== request || shown) return;
      if (!source.isConnected || !image.naturalWidth) { cleanup(); return; }
      shown = true; width = image.naturalWidth; height = image.naturalHeight;
      // A separate top-layer dialog keeps an underlying entry editor open and intact.
      try { if (!viewer.open) viewer.showModal(); } catch { cleanup(); return; }
      fit(); closeButton.focus({ preventScroll: true });
    };
    image.onload = show;
    image.onerror = () => { if (pending === request) close(); };
    image.src = url;
    if (image.complete && image.naturalWidth) show();
  }

  // Capture before a wrapping Markdown hyperlink can navigate away from the note.
  document.addEventListener('click', event => {
    const source = event.target instanceof Element ? event.target.closest('.markdown-body img') : null;
    if (!source) return; event.preventDefault(); event.stopPropagation(); open(source);
  }, true);
  document.addEventListener('keydown', event => {
    if (viewer.open && (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
      // Saving belongs to the note editor, which is inert beneath this dialog.
      event.preventDefault(); event.stopImmediatePropagation(); return;
    }
    const source = event.target instanceof Element ? event.target.closest('.markdown-body img') : null;
    if (!source || !['Enter', ' '].includes(event.key)) return;
    event.preventDefault(); event.stopPropagation(); open(source);
  }, true);

  closeButton.addEventListener('click', close);
  zoomIn.addEventListener('click', () => zoom(scale * 1.25));
  zoomOut.addEventListener('click', () => zoom(scale / 1.25));
  actualButton.addEventListener('click', () => { zoom(1); panX = panY = 0; paint(); });
  fitButton.addEventListener('click', fit);
  viewer.addEventListener('cancel', event => { event.preventDefault(); event.stopPropagation(); close(); });
  viewer.addEventListener('close', cleanup);
  viewer.addEventListener('click', event => { if (event.target === viewer) close(); });
  viewer.addEventListener('keydown', event => {
    if (event.ctrlKey || event.metaKey || event.altKey) return;
    let handled = true;
    if (event.key === 'Escape') close();
    else if (event.key === '+' || event.key === '=') zoom(scale * 1.25);
    else if (event.key === '-') zoom(scale / 1.25);
    else if (event.key === '0' || event.key.toLowerCase() === 'f') fit();
    else if (event.key === '1') { zoom(1); panX = panY = 0; paint(); }
    else if (event.key === 'ArrowLeft') { panX += 50; paint(); }
    else if (event.key === 'ArrowRight') { panX -= 50; paint(); }
    else if (event.key === 'ArrowUp') { panY += 50; paint(); }
    else if (event.key === 'ArrowDown') { panY -= 50; paint(); }
    else handled = false;
    if (handled) { event.preventDefault(); event.stopPropagation(); }
  });
  stage.addEventListener('wheel', event => {
    event.preventDefault();
    const rect = stage.getBoundingClientRect(); const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? stage.clientHeight : 1;
    const delta = clamp(event.deltaY * unit, -180, 180);
    zoom(scale * Math.exp(-delta * 0.002), event.clientX - rect.left - rect.width / 2, event.clientY - rect.top - rect.height / 2);
  }, { passive: false });
  stage.addEventListener('pointerdown', event => {
    if (!event.isPrimary || event.button !== 0) return;
    moved = false; blankPointer = event.target === stage;
    if (event.target !== image || !stage.classList.contains('can-pan')) return;
    event.preventDefault(); stage.focus({ preventScroll: true });
    drag = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, panX, panY };
    stage.setPointerCapture(event.pointerId); stage.classList.add('is-dragging');
  });
  stage.addEventListener('pointermove', event => {
    if (!drag || drag.pointerId !== event.pointerId) return;
    const x = event.clientX - drag.x, y = event.clientY - drag.y;
    if (Math.abs(x) + Math.abs(y) > 4) moved = true;
    panX = drag.panX + x; panY = drag.panY + y; paint();
  });
  stage.addEventListener('pointerup', releaseDrag);
  stage.addEventListener('pointercancel', releaseDrag);
  stage.addEventListener('lostpointercapture', () => { drag = null; stage.classList.remove('is-dragging'); });
  stage.addEventListener('click', event => { if (event.target === stage && blankPointer && !moved) close(); });
  image.addEventListener('dragstart', event => event.preventDefault());
  new ResizeObserver(() => { if (viewer.open) { if (fitted) fit(); else paint(); } }).observe(stage);
})();
