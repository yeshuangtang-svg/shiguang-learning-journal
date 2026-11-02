from pathlib import Path
import base64,json,os,sys,tempfile
from unittest.mock import patch
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from desktop import DesktopServer
out=ROOT.parent/'build'/'qa-document-files';out.mkdir(parents=True,exist_ok=True)
errors=[]
with tempfile.TemporaryDirectory(dir=out) as tmp,patch.dict(os.environ,{'LLM_MODEL':'','LLM_API_KEY':'','LLM_BASE_URL':''}):
 backend=DesktopServer(Path(tmp)/'data',preferred_port=0).start()
 try:
  with patch('document_files.os.startfile',create=True) as opened,patch('document_files.subprocess.Popen') as revealed,sync_playwright() as pw:
   browser=pw.chromium.launch(channel='msedge',headless=True)
   page=browser.new_page(viewport={'width':1320,'height':900})
   page.on('pageerror',lambda e:errors.append(str(e)))
   page.goto(backend.url+'/#documents',wait_until='networkidle')
   expect(page.locator('#open-document-pdf')).to_be_disabled()
   expect(page.locator('#reveal-document-md')).to_be_disabled()
   page.locator('#new-document').click()
   page.locator('#document-name').fill('学习资料归档.md')
   page.locator('#document-content').fill('# 学习资料归档\n\nPDF 用于阅读，MD 保留可编辑的源文件。\n\n- 同名文件存放在一起\n- 随时打开 PDF\n- 一键定位 MD 源文件')
   page.locator('#save-document').click()
   expect(page.locator('#reveal-document-md')).to_be_enabled()
   expect(page.locator('#open-document-pdf')).to_be_disabled()
   page.locator('#reveal-document-md').click()
   expect(page.locator('#toast-region')).to_contain_text('资源管理器')
   assert revealed.called
   items=page.request.get(backend.url+'/api/documents').json()['documents'];identity=items[0]['id'];path=backend.url+'/api/documents/'+identity
   info=page.request.get(path+'/files').json()
   assert Path(info['md_path']).exists()
   pdf_page=browser.new_page();pdf_page.set_content('<h1>Document archive QA</h1><p>PDF and Markdown stored together.</p>');pdf=pdf_page.pdf();pdf_page.close()
   response=page.request.post(path+'/pdf',data={'data_base64':base64.b64encode(pdf).decode(),'source_sha256':info['source_sha256']});assert response.ok
   page.reload(wait_until='networkidle');page.locator('.document-item').first.click()
   expect(page.locator('#open-document-pdf')).to_be_enabled()
   expect(page.locator('#document-files-status')).to_have_text('PDF 与 MD 源文件已归档。')
   page.screenshot(path=str(out/'documents.png'))
   page.locator('#open-document-pdf').click()
   expect(page.locator('#toast-region')).to_contain_text('系统打开 PDF')
   opened.assert_called_once_with(info['pdf_path'])
   page.locator('#document-edit-tab').click();page.locator('#document-content').fill('# 新的修订')
   expect(page.locator('#open-document-pdf')).to_be_disabled()
   page.locator('#save-document').click()
   expect(page.locator('#document-files-status')).to_contain_text('可能尚未反映')
   page.once('dialog',lambda dialog:dialog.dismiss());page.locator('#open-document-pdf').click()
   assert opened.call_count==1
   page.set_viewport_size({'width':960,'height':680})
   page.screenshot(path=str(out/'compact.png'))
   assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
   assert not errors,errors
   browser.close()
 finally:backend.close()
(out/'result.json').write_text(json.dumps({'ok':True,'errors':errors}),encoding='utf-8')
print('Document file buttons and layout passed')
