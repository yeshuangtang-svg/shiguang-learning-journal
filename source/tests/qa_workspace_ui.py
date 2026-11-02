"""Exercise user workflows using isolated data and the installed Edge browser."""
from pathlib import Path
import json, os, sys, tempfile
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from desktop import DesktopServer
from playwright.sync_api import sync_playwright,expect

OUT=Path(__file__).resolve().parents[2]/'build/qa-workspace';OUT.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='workspace-ui-') as tmp,patch.dict(os.environ,{'LLM_MODEL':'','LLM_BASE_URL':'','LLM_API_KEY':'','AGENT_ALLOWED_HOSTS':''}):
    backend=DesktopServer(Path(tmp)/'data',preferred_port=0).start()
    app=backend.app if hasattr(backend,'app') else backend.server.app
    store=app.store
    for i in range(26):store.create_entry({'date':'2026-11-02','title':'训练记录 '+str(i),'subject':'模型训练','content':'主权重用于保存微小更新。\n\n'+('补充解释。'*100)})
    doc=store.create_document({'name':'混合精度.md','content':'# 混合精度\n\n## 主权重\n\nFP32 主权重保留小更新。\n\n## 计算权重\n\nBF16 用于计算。'})
    app.document_files.prepare(doc['id']);store.update_document(doc['id'],{'content':doc['content']+'\n\n## 梯度\n\n反向传播计算梯度。'});app.document_files.prepare(doc['id'])
    future=store.create_future({'title':'主权重复习','subject':'模型训练','content':'以后复习精度差异。'})
    errors=[]
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True)
            context=browser.new_context(viewport={'width':1320,'height':950},accept_downloads=True)
            page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.on('dialog',lambda d:d.accept())
            page.goto(backend.url+'/#logs',wait_until='networkidle')
            expect(page.locator('.entry-card')).to_have_count(20);expect(page.locator('#entries-page')).to_have_text('1 / 2')
            page.locator('#entries-next').click();expect(page.locator('.entry-card')).to_have_count(6)
            page.locator('.entry-card').first.get_by_text('展开全文').click();expect(page.locator('.entry-prose').first).to_be_visible()
            page.locator('#top-search').fill('主权重');page.locator('#top-search').press('Enter');expect(page.locator('#view-search')).to_be_visible();expect(page.locator('#search-status')).to_contain_text('28')
            page.locator('#global-kind').select_option('document');expect(page.locator('#global-results .search-result')).to_have_count(1)
            page.screenshot(path=str(OUT/'search-1320.png'),full_page=True)
            page.locator('#global-results .source-link').click();expect(page.locator('#document-title')).to_have_text('混合精度.md');expect(page.locator('#document-toc a')).to_have_count(4)
            page.locator('#document-history').click();expect(page.locator('#history-list .related-row')).to_have_count(1);page.locator('#history-list button').click();expect(page.locator('#history-preview')).to_contain_text('主权重');page.locator('[data-close-dialog="history-dialog"]').click()
            page.locator('#sidebar-add').click();page.locator('#entry-form [name=title]').fill('需要恢复的草稿');page.locator('#entry-form [name=subject]').fill('草稿测试');page.locator('#entry-content').fill('异常关闭前的内容');expect(page.locator('#draft-status')).to_have_text('草稿已自动保存')
            page.close();page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.on('dialog',lambda d:d.accept());page.goto(backend.url+'/#recovery',wait_until='networkidle');expect(page.locator('#draft-list')).to_contain_text('需要恢复的草稿');page.locator('#draft-list').get_by_text('恢复编辑').first.click();expect(page.locator('#entry-content')).to_have_value('异常关闭前的内容');page.locator('#save-entry').click();expect(page.locator('#entry-dialog')).not_to_be_visible()
            page.goto(backend.url+'/#future',wait_until='networkidle');page.locator('#future-list').get_by_text('记学习笔记').click();page.locator('#entry-content').fill('通过实践理解了主权重。');page.locator('#save-entry').click();expect(page.locator('#entry-dialog')).not_to_be_visible()
            links=store.links_for('future',future['id']);assert len(links)==1;note=links[0]
            page.goto(backend.url+'/#resource/entry/'+note['id'],wait_until='networkidle');expect(page.locator('#entry-relations')).to_contain_text('主权重复习')
            page.locator('#entry-relations').get_by_text('关联已有内容').click();page.locator('#link-query').fill('混合精度.md');expect(page.locator('#link-results .related-row')).to_have_count(1);page.locator('#link-results button').click();expect(page.locator('#link-results button')).to_have_text('已关联');page.locator('[data-close-dialog="link-dialog"]').click()
            page.locator('#delete-entry').click();expect(page.locator('#entry-dialog')).not_to_be_visible();page.goto(backend.url+'/#recovery',wait_until='networkidle');expect(page.locator('#trash-list')).to_contain_text('学习笔记');page.locator('#trash-list button').click();expect(page.locator('#trash-list')).to_contain_text('回收站为空');assert len(store.links_for('entry',note['id']))==2
            class KnowledgeModel:
                def __init__(self):self.step=0
                def complete(self,messages,tools):
                    self.step+=1
                    if self.step==1:return {'role':'assistant','content':None,'tool_calls':[{'id':'search','type':'function','function':{'name':'search_knowledge','arguments':json.dumps({'query':'主权重','kind':'document'})}}]}
                    if self.step==2:return {'role':'assistant','content':None,'tool_calls':[{'id':'read','type':'function','function':{'name':'read_knowledge','arguments':json.dumps({'kind':'document','id':doc['id'],'query':'主权重'})}}]}
                    return {'role':'assistant','content':'FP32 主权重保留小更新。[查看笔记](#resource/document/'+doc['id']+')'}
            app.client=KnowledgeModel();app.config.update({'model':'test-workspace','base_url':'http://127.0.0.1:9/v1'})
            page.goto(backend.url+'/#chat',wait_until='networkidle');page.reload(wait_until='networkidle');page.locator('#chat-input').fill('我的文档如何解释主权重？');page.locator('#send-message').click();expect(page.locator('.message.assistant').last).to_contain_text('FP32 主权重保留小更新');page.locator('.message.assistant').last.locator('.message-content a').click();expect(page.locator('#document-title')).to_have_text('混合精度.md')
            longdoc=store.create_document({'name':'长文阅读.md','content':'# 阅读测试\n\n'+''.join('## 章节 '+str(n)+'\n\n'+('长文阅读位置恢复验证。'*40)+'\n\n' for n in range(20))})
            page.goto(backend.url+'/#resource/document/'+longdoc['id'],wait_until='networkidle');page.locator('#document-heading-10').scroll_into_view_if_needed();page.wait_for_timeout(800);assert store.reading_position(longdoc['id'])['ratio']>0
            page.reload(wait_until='networkidle');expect(page.locator('#resume-reading')).to_be_visible();page.locator('#resume-reading').click();expect(page.locator('#resume-reading')).not_to_be_visible()
            page.goto(backend.url+'/#settings',wait_until='networkidle')
            with page.expect_download() as download:page.locator('#create-full-backup').click()
            downloaded=OUT/'backup.zip';download.value.save_as(downloaded);assert downloaded.is_file()
            page.locator('#full-backup-file').set_input_files(str(downloaded));expect(page.locator('#restore-confirm')).to_be_enabled();expect(page.locator('#restore-details')).to_contain_text('日志 28');page.screenshot(path=str(OUT/'restore-preview.png'))
            page.locator('[data-close-dialog="restore-dialog"]').click();page.goto(backend.url+'/#resource/document/'+doc['id'],wait_until='networkidle');page.set_viewport_size({'width':960,'height':800});page.locator('#document-title').scroll_into_view_if_needed();page.wait_for_timeout(4000);page.screenshot(path=str(OUT/'document-960.png'))
            assert not errors,errors
            print(json.dumps({'ok':True,'page_errors':errors,'checks':['search','pagination','source_navigation','document_toc','history_preview','draft_reload','linked_notes','cross_links','trash_restore','full_backup_download','restore_preview','assistant_document_sources','reading_position']},ensure_ascii=False))
            context.close();browser.close()
    finally:backend.close()
