"""Browser-to-agent-to-PNG/PDF smoke check, isolated from user data."""
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop import DesktopServer
from test_agent_skills import call
from playwright.sync_api import sync_playwright, expect

OUT = Path(__file__).resolve().parents[2] / 'build' / 'qa-skills'
OUT.mkdir(parents=True, exist_ok=True)


class DocumentClient:
    def __init__(self): self.round = 0
    def complete(self, messages, tools):
        self.round += 1
        if self.round == 1: return call('load_skill', {'name': 'learning-document'})
        if self.round == 2: return call('load_skill', {'name': 'visual-explanation'})
        if self.round == 3:
            return call('create_flow_diagram', {'title': '一次参数更新：从预测到新权重', 'steps': [{'label':'前向预测', 'detail':'输入 x = 2，权重 w = 3，得到预测值 y = wx = 6。'}, {'label':'计算误差与梯度', 'detail':'标签 t = 4；L = (y − t)² = 4；dL/dw = 2(y − t)x = 8。'}, {'label':'更新权重', 'detail':'学习率 η = 0.1，新权重 w = 3 − 0.1 × 8 = 2.2。'}]})
        if self.round == 4:
            diagram = json.loads(messages[-1]['content'])['result']['markdown']
            return call('create_document', {'name':'技能验收_训练数据流.md', 'content':'# 一次参数更新\n\n用一个简化数值例子理解预测、误差与更新之间的关系。\n\n'+diagram+'\n\n## 从预测到梯度\n\n输入 x = 2，权重 w = 3。预测值为 6，标签为 4。平方误差 L = (6 − 4)² = 4。\n\n梯度描述权重变化时误差如何变化：dL/dw = 2(wx − t)x = 8。\n\n## 更新后的结果\n\n学习率取 0.1，更新后 w = 2.2，新的预测为 4.4，误差降至 0.16。\n\n| 对象 | 更新前 | 更新后 |\n|---|---:|---:|\n| 权重 | 3 | 2.2 |\n| 预测 | 6 | 4.4 |\n| 平方误差 | 4 | 0.16 |\n'})
        if self.round == 5:
            self.identity = json.loads(messages[-1]['content'])['result']['id']
            return call('generate_document_pdf', {'id':self.identity})
        if self.round == 6: return call('document_files', {'id':self.identity})
        return {'content':f'MD 与 PDF 已保存：[一次参数更新](#resource/document/{self.identity})。文档中包含流程图和数值例子。'}


with tempfile.TemporaryDirectory(prefix='skills-ui-') as tmp, patch.dict(os.environ, {key:'' for key in ('LLM_MODEL','LLM_BASE_URL','LLM_API_KEY')}):
    backend = DesktopServer(Path(tmp)/'data', preferred_port=0).start()
    app = backend.server.app
    app.client = DocumentClient()
    app.config.update({'base_url':'http://127.0.0.1:1/v1','model':'isolated-test-model'})
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel='msedge', headless=True)
            page = browser.new_page(viewport={'width':1320,'height':1080})
            errors=[];page.on('pageerror',lambda error: errors.append(str(error)))
            page.goto(backend.url+'/#settings',wait_until='networkidle')
            expect(page.locator('#installed-skills .installed-skill')).to_have_count(8)
            page.locator('#installed-skills').scroll_into_view_if_needed()
            page.screenshot(path=str(OUT/'settings.png'),full_page=True)
            page.goto(backend.url+'/#chat',wait_until='networkidle')
            page.locator('#chat-input').fill('把一次训练更新做成图解文档，保存 MD 和 PDF。')
            page.locator('#send-message').click()
            expect(page.locator('.message.assistant').last).to_contain_text('MD 与 PDF 已保存',timeout=120000)
            expect(page.locator('.action-badge',has_text='MD 文件已保存')).to_have_count(1)
            expect(page.locator('.action-badge',has_text='PDF 已生成')).to_have_count(1)
            page.screenshot(path=str(OUT/'chat.png'),full_page=True)
            identity=app.client.identity; info=app.document_files.prepare(identity)
            assert info['pdf_current'] and info['pdf_exists']
            md=Path(info['md_path']).read_text(encoding='utf-8'); assert 'assets/' in md
            import shutil
            shutil.copytree(info['directory'],OUT/'document',dirs_exist_ok=True)
            page.locator(f'.message-content a[href="#resource/document/{identity}"]').click()
            expect(page.locator('#document-preview')).to_contain_text('一次参数更新')
            page.screenshot(path=str(OUT/'document.png'),full_page=True)
            assert not errors,errors
            browser.close()
            print(json.dumps({'ok':True,'pdf_current':True,'screenshots':str(OUT)},ensure_ascii=False))
    finally:
        backend.close()
