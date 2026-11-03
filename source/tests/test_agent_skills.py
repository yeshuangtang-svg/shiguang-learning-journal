"""Document agent checks use an isolated database and deterministic model responses."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import Application, ApiError
from agent_skills import skill_catalog, load_skill
from flow_diagram import diagram_html


def call(name, args):
    return {'tool_calls': [{'id': 'call_1', 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}]}


class Client:
    def __init__(self, messages): self.messages = iter(messages)
    def complete(self, messages, tools):
        value = next(self.messages)
        if isinstance(value, Exception): raise value
        return value


class AgentSkillChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Application(self.tmp.name)

    def tearDown(self):
        self.app.store.close()
        self.tmp.cleanup()

    def test_catalog_is_bundled_and_unknown_paths_rejected(self):
        self.assertEqual(len(skill_catalog()), 8)
        for skill in skill_catalog(): self.assertIn('instructions', load_skill(skill['name']))
        for name in ('../config', '', 'custom'):
            with self.assertRaises(ValueError): load_skill(name)

    def test_document_creates_real_utf8_file_and_revision_keeps_history(self):
        original = self.app.run_tool('create_document', {'name': '学习.md', 'content': '# 原始内容\n保留中文'})
        path = Path(original['md_path'])
        self.assertEqual(path.read_text(encoding='utf-8'), '# 原始内容\n保留中文')
        updated = self.app.run_tool('update_document', {'id': original['id'], 'content': '# 修订\n原文补充', 'expected_source_sha256': original['source_sha256']})
        self.assertEqual(updated['id'], original['id'])
        self.assertEqual(path.read_text(encoding='utf-8'), '# 修订\n原文补充')
        self.assertTrue(any('原始内容' in p.read_text(encoding='utf-8') for p in (path.parent/'历史版本').glob('*.md')))
        with self.assertRaisesRegex(ValueError, '已变动'):
            self.app.run_tool('update_document', {'id': original['id'], 'content': '# 过时覆盖', 'expected_source_sha256': original['source_sha256']})
        self.assertIn('修订', path.read_text(encoding='utf-8'))

    def test_retry_uses_same_document_id_and_no_duplicates(self):
        args = {'name': '重试.md', 'content': '# 只保存一次'}
        first = self.app.run_tool('create_document', args, stable_document_id='a'*32)
        second = self.app.run_tool('create_document', args, stable_document_id='a'*32)
        self.assertEqual(first, second)
        self.assertEqual(len(self.app.store.list_documents()), 1)

    def test_tool_roundtrip_and_failure_after_save_reports_real_document(self):
        self.app.client = Client([call('load_skill', {'name': 'learning-document'}), call('create_document', {'name': '失败恢复.md', 'content': '# 正文'}), ApiError('模拟模型断线')])
        result = self.app.chat({'message': '保存这段内容为 MD', 'request_id': 'test-doc'})
        self.assertIn('MD 已保存', result['reply'])
        self.assertIn('#resource/document/', result['reply'])
        self.assertEqual(result, self.app.chat({'message': '保存这段内容为 MD', 'request_id': 'test-doc'}))
        self.assertEqual(len(self.app.store.list_documents()), 1)

    def test_pdf_failure_keeps_markdown_and_returns_tool_error(self):
        doc = self.app.run_tool('create_document', {'name': '仅源文件.md', 'content': '# 保留'})
        self.app.client = Client([call('generate_document_pdf', {'id': doc['id']}), {'content': 'MD 已保存，PDF 生成失败。'}])
        with patch('server.generate_pdf', side_effect=ValueError('模拟 Edge 不可用')):
            result = self.app.chat({'message': '生成 PDF'})
        self.assertFalse(result['actions'][0]['ok'])
        self.assertTrue(Path(doc['md_path']).is_file())
        self.assertFalse(self.app.document_files.prepare(doc['id'])['pdf_current'])

    def test_file_sync_failure_does_not_claim_md_exists(self):
        with patch.object(self.app.document_files, 'prepare', side_effect=OSError('模拟磁盘故障')):
            doc = self.app.run_tool('create_document', {'name': '待同步.md', 'content': '# 仍在库内'})
        self.assertFalse(doc['md_exists'])
        self.assertIn('文件同步失败', doc['file_warning'])
        self.assertIn('仍在库内', self.app.store.get_document(doc['id'])['content'])

    def test_flow_text_is_escaped_and_input_bounded(self):
        html = diagram_html('<script>alert(1)</script>', [{'label': '<img src=x>', 'detail': '输入'}, {'label': '输出', 'detail': '结果'}])
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)
        with self.assertRaises(ValueError): diagram_html('无步骤', [])
        with self.assertRaises(ValueError): diagram_html('过长', [{'label':'x', 'detail':'y'*121}]*2)


if __name__ == '__main__': unittest.main()
