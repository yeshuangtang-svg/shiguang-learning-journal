import base64
from pathlib import Path
import unittest
from unittest.mock import patch

import test_library as fixtures
from document_files import DocumentFiles

PDF = b'%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF\n'


class DocumentFileChecks(unittest.TestCase):
    setUp = fixtures.LibraryHTTPChecks.setUp
    tearDown = fixtures.LibraryHTTPChecks.tearDown
    request = fixtures.LibraryHTTPChecks.request

    def create(self, name='学习资料.md', content='# 我的知识'):
        status, _, document = self.request('/api/documents', 'POST', {'name': name, 'content': content})
        self.assertEqual(status, 201)
        return '/api/documents/' + document['id']

    def publish(self, path, info):
        return self.request(path + '/pdf', 'POST', {'data_base64': base64.b64encode(PDF).decode(), 'source_sha256': info['source_sha256']})

    def test_sources_pdf_association_and_old_files_preserved(self):
        path = self.create()
        info = self.request(path + '/files')[2]
        self.assertEqual(Path(info['md_path']).read_text(encoding='utf-8'), '# 我的知识')
        self.assertFalse(info['pdf_exists'])
        self.assertEqual(self.publish(path, info)[0], 200)
        self.assertTrue(self.request(path + '/files')[2]['pdf_current'])
        self.request(path, 'PATCH', {'content': '# 最新知识'})
        current = self.request(path + '/files')[2]
        self.assertFalse(current['pdf_current'])
        self.assertEqual(Path(current['pdf_path']).read_bytes(), PDF)
        self.assertTrue(any(p.read_text(encoding='utf-8') == '# 我的知识' for p in (Path(info['directory'])/'历史版本').glob('*.md')))
        self.assertEqual(self.publish(path, info)[0], 400)
        self.assertEqual(self.publish(path, current)[0], 200)
        self.assertTrue(self.request(path + '/files')[2]['pdf_current'])
        renamed = self.request(path, 'PATCH', {'name': '新的名称.md'})
        self.assertEqual(renamed[0], 200)
        self.assertFalse(self.request(path + '/files')[2]['pdf_exists'])
        self.assertTrue(Path(info['md_path']).is_file())
        self.assertTrue(Path(info['pdf_path']).is_file())

    def test_images_are_portable_and_duplicate_names_isolated(self):
        asset = self.request('/api/assets', 'POST', fixtures.IMAGE)[2]
        path = self.create(content='![图片](' + asset['url'] + ')')
        info = self.request(path + '/files')[2]
        source = Path(info['md_path']).read_text(encoding='utf-8')
        self.assertIn('assets/' + asset['id'] + '.png', source)
        self.assertEqual((Path(info['directory'])/'assets'/(asset['id']+'.png')).read_bytes(), fixtures.png())
        other = self.request(self.create() + '/files')[2]
        self.assertNotEqual(info['md_path'], other['md_path'])
        reserved = self.request(self.create(name='CON.md') + '/files')[2]
        self.assertEqual(Path(reserved['md_path']).name, '_CON.md')

    def test_auth_restricted_native_actions_and_missing_files(self):
        path = self.create()
        self.assertEqual(self.request(path + '/files', authenticated=False)[0], 401)
        self.assertEqual(self.request(path + '/files', 'POST', {})[0], 405)
        self.assertEqual(self.request(path + '/open-pdf', 'POST', {})[0], 400)
        self.app.desktop = True
        self.assertEqual(self.request(path + '/open-pdf', 'POST', {})[0], 400)
        info = self.request(path + '/files')[2]
        self.publish(path, info)
        with patch('document_files.os.startfile', create=True) as open_pdf, patch('document_files.subprocess.Popen') as explorer:
            self.assertEqual(self.request(path + '/open-pdf', 'POST', {})[0], 200)
            open_pdf.assert_called_once_with(info['pdf_path'])
            self.assertEqual(self.request(path + '/reveal-md', 'POST', {})[0], 200)
            self.assertEqual(explorer.call_args[0][0][1:], ['/select,', info['md_path']])
            self.assertEqual(self.request(path + '/open-pdf', 'POST', {'path': 'C:/Windows/notepad.exe'})[0], 400)
            self.assertEqual(self.request(path + '/open-pdf', 'POST', {}, headers={'Origin': 'https://evil.invalid'})[0], 403)
        with self.assertRaises(ValueError):
            self.app.document_files.checked(Path(self.directory.name)/'elsewhere.pdf')

    def test_external_source_edits_are_preserved_and_failures_do_not_duplicate(self):
        path = self.create()
        info = self.request(path + '/files')[2]
        Path(info['md_path']).write_text('外部修改', encoding='utf-8')
        self.request(path + '/files')
        self.assertTrue(any(p.read_text(encoding='utf-8') == '外部修改' for p in (Path(info['directory'])/'历史版本').glob('*.md')))
        with patch.object(DocumentFiles, 'prepare', side_effect=OSError('disk unavailable')):
            status, _, doc = self.request('/api/documents', 'POST', {'name': '故障.md', 'content': '# 已保存到库'})
        self.assertEqual(status, 201)
        self.assertIn('file_warning', doc)
        self.assertEqual(self.request('/api/documents/' + doc['id'])[2]['content'], '# 已保存到库')
        self.assertEqual(self.request('/api/documents/' + doc['id'] + '/files')[0], 200)
