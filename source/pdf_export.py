"""Print sanitized Markdown to a managed PDF using the installed Edge engine."""
import base64
import json
import html as html_escape
import os
from pathlib import Path
import re
import subprocess
import tempfile


def generate_pdf(files, identity, static_root):
    candidates=[Path(os.environ.get('PROGRAMFILES(X86)',r'C:\Program Files (x86)'))/'Microsoft/Edge/Application/msedge.exe',Path(os.environ.get('PROGRAMFILES',r'C:\Program Files'))/'Microsoft/Edge/Application/msedge.exe']
    edge=next((p for p in candidates if p.is_file()),None)
    if not edge: raise ValueError('生成 PDF 需要 Microsoft Edge 浏览器，请安装后重试。')
    info=files.prepare(identity); document=files.store.get_document(identity); content=document['content']
    for asset in set(re.findall(r'/api/assets/([a-f0-9]{64})',content)):
        try:
            data=files.store.get_asset(asset)
            content=content.replace('/api/assets/'+asset,'data:'+data['mime']+';base64,'+base64.b64encode(data['data']).decode())
        except KeyError: pass
    # Archived relative images are restricted to the same document directory.
    for name in set(re.findall(r'!\[[^\]]*\]\((assets/[^)\s]+)\)',content)):
        path=Path(info['directory'])/name
        if path.resolve().is_relative_to(Path(info['directory'])) and path.is_file() and path.suffix.lower() in ('.png','.jpg','.jpeg','.webp','.gif') and path.stat().st_size<=8*1024*1024:
            mime={'.jpg':'jpeg','.jpeg':'jpeg'}.get(path.suffix.lower(),path.suffix.lower()[1:])
            content=content.replace('('+name+')','(data:image/'+mime+';base64,'+base64.b64encode(path.read_bytes()).decode()+')')
    scripts='\n'.join((Path(static_root)/'vendor'/name).read_text(encoding='utf-8') for name in ('marked.min.js','purify.min.js'))
    payload=json.dumps(content,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e')
    html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:">
<style>@page{size:A4;margin:18mm 16mm}body{font:11pt/1.75 'Microsoft YaHei','Noto Sans CJK SC',sans-serif;color:#24312b}h1{font-size:23pt;color:#325944}h2{font-size:17pt;border-bottom:1px solid #d9e4dc;padding-bottom:5pt}h3{font-size:13pt}h1,h2,h3,h4{break-after:avoid}p,li{orphans:3;widows:3}img{max-width:100%;max-height:235mm;object-fit:contain}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f2f5f2;padding:10pt;font-size:9pt}code{font-family:Consolas,monospace}table{border-collapse:collapse;width:100%;font-size:9pt;table-layout:fixed}th,td{border:1px solid #ced8d1;padding:5pt;overflow-wrap:anywhere}tr{break-inside:avoid}thead{display:table-header-group}blockquote{border-left:3pt solid #94b49d;margin-left:0;padding-left:12pt;color:#51675a}a{color:#34634a;text-decoration:none}</style><body><main id="content"></main><script>'''+scripts+'''\nconst parser=new marked.Marked({gfm:true,renderer:{html(t){return t.text.replace(/&/g,'&amp;').replace(/</g,'&lt;')}}});
const root=document.getElementById('content');root.innerHTML=DOMPurify.sanitize(parser.parse('''+payload+'''),{FORBID_TAGS:['style','script','iframe','object','embed','form']});
root.querySelectorAll('img').forEach(i=>{if(!/^data:image\\/(png|jpeg|gif|webp);base64,/.test(i.getAttribute('src')||'')){i.replaceWith(document.createTextNode('〔图片未嵌入：'+(i.alt||'外部图片')+'〕'))}});
</script></body></html>'''
    html=html.replace('<meta charset="utf-8">','<meta charset="utf-8"><title>'+html_escape.escape(document['name'])+'</title>',1)
    with tempfile.TemporaryDirectory(prefix='shiguang-pdf-') as tmp:
        folder=Path(tmp); page=folder/'print.html'; pdf=folder/'print.pdf'; page.write_text(html,encoding='utf-8')
        try:
            subprocess.run([str(edge),'--headless','--disable-gpu','--no-first-run','--disable-background-networking','--no-pdf-header-footer','--user-data-dir='+str(folder/'profile'),'--print-to-pdf='+str(pdf),page.as_uri()],timeout=55,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),check=True)
        except (subprocess.SubprocessError,OSError): raise ValueError('PDF 生成未完成，请确认 Edge 可运行后重试。') from None
        if not pdf.is_file(): raise ValueError('浏览器没有生成 PDF。')
        return files.save_pdf(identity,{'source_sha256':info['source_sha256'],'data_base64':base64.b64encode(pdf.read_bytes()).decode()})
