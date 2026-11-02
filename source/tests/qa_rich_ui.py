"""End-to-end UI QA against a disposable local database. Requires Playwright/Pillow."""
from pathlib import Path
import json
import os
import sys
import tempfile
from unittest.mock import patch

from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from desktop import DesktopServer


def main():
    output = ROOT.parent / 'build' / 'qa-rich-markdown'
    output.mkdir(parents=True, exist_ok=True)
    checks, errors = [], []
    with tempfile.TemporaryDirectory(prefix='rich-ui-', dir=output) as directory, patch.dict(os.environ, {'LLM_MODEL': '', 'LLM_BASE_URL': '', 'LLM_API_KEY': ''}):
        fixture = Path(directory) / 'learning-map.png'
        picture = Image.new('RGB', (720, 240), '#eef3e8')
        draw = ImageDraw.Draw(picture)
        for index, label in enumerate(['QUESTION', 'PRACTICE', 'REFLECTION']):
            x = 22 + index * 236
            draw.rounded_rectangle((x, 60, x + 202, 178), radius=20, fill='#ffffff', outline='#b1c69f', width=2)
            draw.text((x + 35, 112), label, fill='#466136')
            if index < 2:
                draw.line((x + 204, 119, x + 233, 119), fill='#769567', width=3)
        picture.save(fixture)
        backend = DesktopServer(Path(directory) / 'data', token='ui-test-only-token', preferred_port=0).start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                context = browser.new_context(viewport={'width': 1320, 'height': 900}, accept_downloads=True)
                context.add_init_script("sessionStorage.setItem('shiguang.agent.access-token', 'ui-test-only-token')")
                page = context.new_page()
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(backend.url, wait_until='networkidle')
                page.locator('[data-view="logs"]').click()
                page.locator('#add-entry').click()
                page.locator('[name="title"]').fill('把知识连成一张图')
                page.locator('[name="subject"]').fill('学习方法')
                page.locator('#entry-content').fill('## 主动回忆的三个步骤\n\n把**问题、练习、复盘**连起来，理解会更牢固。\n\n- 先提出问题\n- 用例子检验理解\n- 记录收获和困惑\n')
                page.locator('[data-add-image="entry"]').click()
                page.locator('#editor-image-file').set_input_files(fixture)
                expect(page.locator('#entry-image-status')).to_contain_text('已插入 1 张')
                page.locator('#entry-preview-tab').click()
                expect(page.locator('#entry-preview h2')).to_have_text('主动回忆的三个步骤')
                expect(page.locator('#entry-preview img')).to_have_js_property('naturalWidth', 720)
                page.screenshot(path=str(output / 'entry-preview.png'))
                saved_content = page.locator('#entry-content').input_value()
                image_line = next(line for line in saved_content.splitlines() if line.startswith('!['))
                page.locator('#entry-preview img').click()
                expect(page.locator('#image-viewer')).to_be_visible()
                expect(page.locator('#image-viewer-image')).to_have_js_property('naturalWidth', 720)
                before_zoom = page.locator('#image-viewer-scale').inner_text()
                page.locator('#image-viewer-zoom-in').click()
                assert page.locator('#image-viewer-scale').inner_text() != before_zoom
                page.keyboard.press('Escape')
                expect(page.locator('#image-viewer')).not_to_be_visible()
                expect(page.locator('#entry-dialog')).to_be_visible()
                expect(page.locator('#entry-content')).to_have_value(saved_content)
                checks.append('image_zoom_preserves_open_entry_and_unsaved_content')
                page.locator('#save-entry').click()
                expect(page.locator('#entry-dialog')).not_to_be_visible()
                expect(page.locator('.entry-card')).to_have_count(1)
                expect(page.locator('.entry-prose img')).to_have_js_property('naturalWidth', 720)
                page.locator('.entry-prose img').click()
                expect(page.locator('#image-viewer')).to_be_visible()
                page.locator('#image-viewer-close').click()
                expect(page.locator('#image-viewer')).not_to_be_visible()
                checks.append('entry_image_upload_preview_and_saved_render')
                page.locator('[data-view="documents"]').click()
                md = '# Python 学习笔记\n\n> 把例子保留下来，复习时更容易想起。\n\n## 常用数据结构\n\n| 类型 | 特点 |\n| --- | --- |\n| 列表 | 有序，可修改 |\n| 元组 | 有序，不可修改 |\n\n```python\nitems = [1, 2, 3]\nprint([x * x for x in items])\n```\n\n- [x] 完成例题\n- [ ] 整理错题\n'
                md += '\n' + image_line + '\n'
                page.locator('#document-files').set_input_files({'name': 'Python学习笔记.md', 'mimeType': 'text/markdown', 'buffer': md.encode('utf-8')})
                expect(page.locator('#document-title')).to_have_text('Python学习笔记.md')
                expect(page.locator('#document-preview table')).to_have_count(1)
                expect(page.locator('#document-preview pre code')).to_contain_text('items =')
                page.screenshot(path=str(output / 'markdown-library.png'))
                expect(page.locator('#document-preview img')).to_have_js_property('naturalWidth', 720)
                page.locator('#document-preview img').click()
                expect(page.locator('#image-viewer')).to_be_visible()
                page.locator('#image-viewer-actual').click()
                expect(page.locator('#image-viewer-scale')).to_have_text('100%')
                page.locator('#image-viewer-zoom-in').click()
                page.screenshot(path=str(output / 'image-viewer.png'))
                page.locator('#image-viewer-fit').click()
                page.keyboard.press('Escape')
                expect(page.locator('#image-viewer')).not_to_be_visible()
                checks.append('markdown_library_click_zoom_actual_size_and_fit')
                checks.append('utf8_md_import_table_code_and_reading')
                page.locator('#document-edit-tab').click()
                page.locator('#document-content').fill(md + '\n## 今日收获\n已经理解列表推导式。\n')
                page.locator('#save-document').click()
                expect(page.locator('#document-save-status')).to_have_text('已保存到本地')
                with page.expect_download() as downloaded:
                    page.locator('#download-document').click()
                download = downloaded.value
                assert download.suggested_filename == 'Python学习笔记.md'
                assert '今日收获' in Path(download.path()).read_text(encoding='utf-8')
                checks.append('md_edit_save_and_utf8_download')
                page.locator('#document-query').fill('列表推导式')
                expect(page.locator('.document-item')).to_have_count(1)
                page.locator('#document-query').fill('没有这个词')
                expect(page.locator('.document-item')).to_have_count(0)
                page.locator('#document-query').fill('')
                expect(page.locator('.document-item')).to_have_count(1)
                page.locator('#document-content').fill(md + '未保存的内容')
                page.once('dialog', lambda dialog: dialog.dismiss())
                page.locator('[data-view="logs"]').click()
                expect(page.locator('#view-documents')).to_be_visible()
                expect(page.locator('#document-content')).to_have_value(md + '未保存的内容')
                checks.append('search_and_unsaved_edit_protection')
                page.locator('#document-content').fill(md + '\n## 今日收获\n已经理解列表推导式。\n')
                page.locator('#document-read-tab').click()
                page.set_viewport_size({'width': 960, 'height': 680})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(output / 'markdown-library-960.png'))
                checks.append('desktop_minimum_width_layout')
                browser.close()
        finally:
            backend.close()
    report = {'ok': not errors, 'checks': checks, 'javascript_errors': errors}
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    assert not errors, errors


if __name__ == '__main__':
    main()
