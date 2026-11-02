import copy
from contextlib import closing
import sqlite3
import unittest
from urllib.parse import quote
import test_library as fixtures
from store import Store


class FutureStoreChecks(unittest.TestCase):
    setUp = fixtures.LibraryStoreChecks.setUp
    tearDown = fixtures.LibraryStoreChecks.tearDown

    def test_lifecycle_persistence_and_separate_statistics(self):
        item = self.store.create_future({'title': 'KV Cache', 'subject': '推理', 'url': 'https://example.com/learn', 'content': '以后理解缓存'})
        self.assertEqual(item['status'], 'pending')
        self.assertEqual(self.store.list_future('缓存', 'pending'), [item])
        self.assertEqual(self.store.list_future('%'), [])
        updated = self.store.update_future(item['id'], {'status': 'learning'})
        self.assertEqual(updated['content'], item['content'])
        self.assertEqual(self.store.list_future(status='pending'), [])
        self.assertEqual(self.store.summary()['total_entries'], 0)
        self.store.close()
        self.store = Store(self.path)
        self.assertEqual(self.store.get_future(item['id']), updated)
        self.store.update_future(item['id'], {'status': 'done'})
        self.assertTrue(self.store.delete_future(item['id']))
        with self.assertRaises(KeyError):
            self.store.get_future(item['id'])

    def test_validation_and_atomic_backup(self):
        for raw in ({'title': ' '}, {'title': 'a', 'url': 'javascript:alert(1)'}, {'title': 'a', 'status': 'invalid'}, {'title': 'a', 'status': []}, {'title': 'a', 'content': 'a' * 20001}, {'title': 'a', 'unknown': 1}):
            with self.assertRaises(ValueError):
                self.store.create_future(raw)
        entry = self.store.create_entry(fixtures.ENTRY)
        item = self.store.create_future({'title': '以后学', 'content': '原始备注'})
        self.store.create_document({'name': '原文.md', 'content': '# 原文'})
        backup = self.store.export()
        self.assertEqual(backup['version'], 3)
        target = Store(':memory:')
        try:
            target.import_entries(backup)
            self.assertEqual(target.export(), backup)
            invalid = copy.deepcopy(backup)
            invalid['entries'][0]['title'] = '不应写入'
            invalid['future_learning'][0]['url'] = 'file:///C:/private'
            with self.assertRaises(ValueError):
                target.import_entries(invalid)
            self.assertEqual(target.export(), backup)
            target.import_entries({'version': 1, 'entries': [entry]})
            target.import_entries({'version': 2, 'entries': [], 'documents': [], 'assets': []})
            self.assertEqual(target.get_future(item['id']), item)
        finally:
            target.close()

    def test_existing_database_upgrade_preserves_content(self):
        entry = self.store.create_entry(fixtures.ENTRY)
        document = self.store.create_document({'name': '旧文档.md', 'content': '旧内容'})
        self.store.close()
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute('DROP TABLE future_learning')
            connection.commit()
        self.store = Store(self.path)
        self.assertEqual(self.store.get_entry(entry['id']), entry)
        self.assertEqual(self.store.get_document(document['id']), document)
        self.assertEqual(self.store.list_future(), [])


class FutureHTTPChecks(unittest.TestCase):
    setUp = fixtures.LibraryHTTPChecks.setUp
    tearDown = fixtures.LibraryHTTPChecks.tearDown
    request = fixtures.LibraryHTTPChecks.request

    def test_http_lifecycle_auth_and_filters(self):
        self.assertEqual(self.request('/api/future-learning', authenticated=False)[0], 401)
        self.assertEqual(self.request('/api/future-learning', 'POST', {'title': 'bad', 'url': 'data:text/html,bad'})[0], 400)
        status, _, item = self.request('/api/future-learning', 'POST', {'title': '缓存机制', 'content': '待了解'})
        self.assertEqual(status, 201)
        path = '/api/future-learning/' + item['id']
        self.assertEqual(self.request(path)[2], item)
        self.assertEqual(self.request('/api/future-learning?query=' + quote('缓存') + '&status=pending')[2]['items'], [item])
        self.assertEqual(self.request(path, 'PATCH', {'status': 'done'})[2]['status'], 'done')
        self.assertEqual(self.request('/api/future-learning?status=pending')[2]['items'], [])
        self.assertEqual(self.request('/api/export')[2]['version'], 3)
        self.assertEqual(self.request(path, 'DELETE')[2], {'deleted': True})
        self.assertEqual(self.request(path)[0], 404)
