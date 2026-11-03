"""Connection setup workflows against an isolated local API and fake provider."""
from collections import deque
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop import DesktopServer
from test_agent_http import FakeProvider
from playwright.sync_api import sync_playwright, expect

OUT = Path(__file__).resolve().parents[2] / 'build' / 'qa-config'
OUT.mkdir(parents=True, exist_ok=True)

with tempfile.TemporaryDirectory(prefix='config-ui-') as tmp, patch.dict(os.environ, {key: '' for key in ('LLM_MODEL', 'LLM_BASE_URL', 'LLM_API_KEY', 'AGENT_ALLOWED_HOSTS')}):
    provider = ThreadingHTTPServer(('127.0.0.1', 0), FakeProvider)
    provider.requests, provider.responses = [], deque()
    thread = threading.Thread(target=provider.serve_forever, daemon=True)
    thread.start()
    backend = DesktopServer(Path(tmp) / 'data', preferred_port=0).start()
    app = backend.server.app
    base = f'http://127.0.0.1:{provider.server_port}/v1'
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel='msedge', headless=True)
            page = browser.new_page(viewport={'width': 1320, 'height': 1000})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(backend.url + '/#settings', wait_until='networkidle')
            expect(page.locator('#save-config')).to_be_disabled()
            page.locator('#config-base-url').fill(base)
            page.locator('#config-api-key').fill('ui-test-key-not-real')
            provider.responses.append((200, {'data': [{'id': 'chat-model'}, {'id': 'other-model'}]}))
            page.locator('#check-config').click()
            expect(page.locator('#config-model-select')).to_be_visible()
            expect(page.locator('#config-check-status')).to_contain_text('已获取 2 个模型')
            assert not app.config.path.exists(), 'Checking must not save configuration'
            expect(page.locator('#save-config')).to_be_disabled()
            page.locator('#config-model-select').select_option('chat-model')
            expect(page.locator('#save-config')).to_be_enabled()
            page.screenshot(path=str(OUT / 'models-desktop.png'), full_page=True)
            page.locator('#save-config').click()
            expect(page.locator('#config-save-status')).to_contain_text('已保存')
            assert app.config.read()['model'] == 'chat-model'
            expect(page.locator('#config-api-key')).to_have_value('')
            page.locator('#config-reasoning-effort').select_option('high')
            page.locator('#save-reasoning').click()
            expect(page.locator('#reasoning-save-status')).to_contain_text('已保存')
            assert app.config.read()['reasoning_effort'] == 'high'
            assert app.config.read()['model'] == 'chat-model'
            page.reload(wait_until='networkidle')
            expect(page.locator('#config-reasoning-effort')).to_have_value('high')
            page.screenshot(path=str(OUT / 'reasoning-desktop.png'), full_page=True)
            original = app.config.path.read_bytes()

            # Saved key is reused only for the same endpoint; drafts reset validation.
            provider.responses.append((200, {'data': [{'id': 'chat-model'}]}))
            page.locator('#check-config').click()
            expect(page.locator('#config-model-select')).to_have_value('chat-model')
            assert provider.requests[-1]['authorization'] == 'Bearer ui-test-key-not-real'
            page.locator('#config-api-key').fill('bad-key')
            expect(page.locator('#save-config')).to_be_disabled()
            expect(page.locator('#config-model-step')).not_to_be_visible()
            provider.responses.append((401, {'error': 'do not display this upstream body'}))
            page.locator('#check-config').click()
            expect(page.locator('#config-check-status')).to_contain_text('API Key 校验失败')
            expect(page.locator('#save-config')).to_be_disabled()
            assert app.config.path.read_bytes() == original

            # Unsupported /models remains explicitly unverified, with manual fallback.
            page.locator('#config-api-key').fill('ui-test-key-not-real')
            provider.responses.append((404, {}))
            page.locator('#check-config').click()
            expect(page.locator('#config-model')).to_be_visible()
            expect(page.locator('#config-check-status')).to_contain_text('连接尚未验证')
            page.locator('#config-model').fill('custom-chat-model')
            page.locator('#save-config').click()
            expect(page.locator('#config-save-status')).to_contain_text('已保存')
            assert app.config.read()['model'] == 'custom-chat-model'
            assert app.config.read()['reasoning_effort'] == 'default'
            expect(page.locator('#config-reasoning-effort')).to_have_value('default')

            # Discard an old asynchronous response after credentials change.
            def stale_response(route):
                page.locator('#config-api-key').fill('new-draft-key')
                route.fulfill(json={'models': ['stale-model'], 'verified': True, 'message': 'STALE'})
            page.route('**/api/config/models', stale_response)
            page.locator('#check-config').click()
            expect(page.locator('#config-model-step')).not_to_be_visible()
            expect(page.locator('#save-config')).to_be_disabled()
            expect(page.locator('#config-check-status')).not_to_contain_text('STALE')
            page.unroute('**/api/config/models', stale_response)

            # Empty model lists support manual entry and fit narrow viewports.
            provider.responses.append((200, {'data': []}))
            page.locator('#check-config').click()
            expect(page.locator('#config-check-status')).to_contain_text('模型列表为空')
            expect(page.locator('#config-model')).to_be_visible()
            page.set_viewport_size({'width': 960, 'height': 900})
            page.screenshot(path=str(OUT / 'manual-960.png'), full_page=True)
            page.set_viewport_size({'width': 390, 'height': 844})
            page.screenshot(path=str(OUT / 'manual-mobile.png'), full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Horizontal overflow'
            assert not errors, errors
            browser.close()
            print(json.dumps({'ok': True, 'checks': ['discover', 'select', 'save', 'preserve_config', 'saved_key', 'auth_failure', 'manual_fallback', 'stale_response', 'empty_models', 'responsive'], 'page_errors': errors}))
    finally:
        backend.close()
        provider.shutdown()
        provider.server_close()
        thread.join(timeout=2)
