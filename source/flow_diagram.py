"""Render bounded, escaped flow labels to a local PNG; no model HTML or code."""
import base64
import math
from html import escape
import os
from pathlib import Path
import subprocess
import tempfile


def diagram_html(title, steps):
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 80:
        raise ValueError('图标题须为 1–80 字。')
    if not isinstance(steps, list) or not 2 <= len(steps) <= 8:
        raise ValueError('流程图须包含 2–8 个步骤。')
    cards = []
    for index, step in enumerate(steps, 1):
        if not isinstance(step, dict) or set(step) != {'label', 'detail'}:
            raise ValueError('每步须包含 label 和 detail。')
        for key, maximum in (('label', 32), ('detail', 120)):
            if not isinstance(step[key], str) or not 1 <= len(step[key].strip()) <= maximum:
                raise ValueError(f'{key} 须为 1–{maximum} 字。')
        label = ' '.join(step['label'].split()); detail = ' '.join(step['detail'].split())
        height = max(118, 75 + math.ceil(len(detail) / 42) * 28)
        cards.append(f'<section style="height:{height}px"><b>{index:02}</b><div><h2>{escape(label)}</h2><p>{escape(detail)}</p></div></section>')
    return '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><style>*{box-sizing:border-box}body{width:1000px;margin:0;padding:36px 50px;background:#f5f7f2;color:#203e33;font-family:'Microsoft YaHei',sans-serif}h1{font-size:28px;margin:0 0 28px;line-height:1.5}section{display:flex;align-items:center;gap:22px;background:white;border:1px solid #bbd2c3;border-radius:14px;padding:18px 24px;min-height:118px}section b{font-size:26px;color:#448466}h2{font-size:21px;margin:0 0 8px}p{font-size:17px;line-height:1.6;margin:0;overflow-wrap:anywhere}.arrow{text-align:center;height:30px;font-size:24px;color:#448466}</style><body><h1>'''+escape(title)+'</h1>'+'<div class="arrow">↓</div>'.join(cards)+'</body></html>'


def create_flow_diagram(store, title, steps):
    html = diagram_html(title, steps)
    height = 100 + math.ceil(len(title) / 30) * 42 + sum(max(118, 75 + math.ceil(len(' '.join(step['detail'].split())) / 42) * 28) for step in steps) + (len(steps) - 1) * 30
    return render_image(store, title, html, 1000, height)


def render_image(store, title, html, width, height):
    """Only callers constructing escaped templates may supply HTML."""
    candidates = [Path(os.environ.get(key, default)) / 'Microsoft/Edge/Application/msedge.exe' for key, default in (('PROGRAMFILES(X86)', r'C:\Program Files (x86)'), ('PROGRAMFILES', r'C:\Program Files'))]
    edge = next((path for path in candidates if path.is_file()), None)
    if not edge:
        raise ValueError('生成流程图需要 Microsoft Edge。')
    with tempfile.TemporaryDirectory(prefix='shiguang-flow-') as tmp:
        folder = Path(tmp); page = folder / 'flow.html'; png = folder / 'flow.png'
        page.write_text(html, encoding='utf-8')
        try:
            subprocess.run([str(edge), '--headless', '--disable-gpu', '--no-first-run', '--disable-background-networking', '--hide-scrollbars', '--force-device-scale-factor=1', '--user-data-dir='+str(folder/'profile'), f'--window-size={width},{height}', '--screenshot='+str(png), page.as_uri()], timeout=45, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), check=True)
        except (subprocess.SubprocessError, OSError):
            raise ValueError('流程图生成失败，请稍后重试。') from None
        if not png.is_file():
            raise ValueError('浏览器没有生成流程图。')
        asset = store.create_asset({'name': '技术示意图.png', 'data_base64': base64.b64encode(png.read_bytes()).decode()})
    alt = title.replace('\\', '').replace('[', '（').replace(']', '）').replace('\n', ' ').replace('\r', ' ')
    return {**asset, 'title': title, 'markdown': f'![{alt}]({asset["url"]})'}
