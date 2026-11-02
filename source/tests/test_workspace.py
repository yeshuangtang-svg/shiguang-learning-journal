"""Regression checks for cross-resource workflows and recoverable state."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server import Application
from store import Store
import test_library as http_fixtures

ENTRY={'date':'2026-11-02','title':'混合精度','subject':'训练','content':'FP32 主权重保存微小更新；BF16 用于计算。'}

class WorkspaceChecks(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.app=Application(self.temp.name);self.store=self.app.store
    def tearDown(self): self.store.close();self.temp.cleanup()
    def test_search_types_literal_terms_and_excerpt(self):
        e=self.store.create_entry(ENTRY)
        d=self.store.create_document({'name':'训练.md','content':'开头\n'+('无关内容 '*70)+'\n## 混合精度\n主权重使用 FP32。'})
        f=self.store.create_future({'title':'主权重后续学习','content':'补充混合精度'})
        result=self.store.search_all('主权重',limit=2)
        self.assertEqual(result['total'],3);self.assertTrue(result['has_more'])
        self.assertEqual(len(self.store.search_all('主权重',offset=2)['items']),1)
        found=self.store.search_all('主权重',kind='document')['items'][0]
        self.assertIn('主权重',found['snippet']);self.assertEqual(found['url'],'#resource/document/'+d['id'])
        self.assertEqual(self.store.search_all('%')['total'],0)
        read=self.app.run_tool('read_knowledge',{'kind':'document','id':d['id'],'query':'主权重','limit':10})
        self.assertIn('## 混合精度',read['content']);self.assertIsNotNone(read['next_offset'])
    def test_pagination_stable_and_summary_bounded(self):
        for n in range(45): self.store.create_entry({**ENTRY,'title':str(n),'content':'x'*10000})
        first=self.store.entries_page(limit=20);second=self.store.entries_page(limit=20,offset=20)
        self.assertEqual(first['total'],45);self.assertEqual(len(first['entries']),20)
        self.assertFalse(set(x['id'] for x in first['entries'])&set(x['id'] for x in second['entries']))
        self.assertLessEqual(len(first['entries'][0]['content']),360)
    def test_linked_creation_and_trash_roundtrip(self):
        f=self.store.create_future({'title':'混合精度'})
        e=self.store.create_linked_note('future',f['id'],'entry',ENTRY)
        self.assertEqual(self.store.links_for('entry',e['id'])[0]['id'],f['id'])
        link=self.store.add_link({'a_kind':'entry','a_id':e['id'],'b_kind':'future','b_id':f['id']})
        self.assertEqual(len(self.store.links_for('future',f['id'])),1)
        self.store.delete_entry(e['id']);self.assertEqual(self.store.search_all('主权重')['total'],0)
        self.assertEqual(self.store.links_for('future',f['id']),[])
        self.store.restore_trash(self.store.list_trash()[0]['id'])
        self.assertEqual(self.store.get_entry(e['id']),e);self.assertEqual(len(self.store.links_for('future',f['id'])),1)
        self.store.remove_link(link['id']);self.assertEqual(self.store.links_for('future',f['id']),[])
        before=self.store.summary()['total_entries']
        with self.assertRaises(KeyError):self.store.create_linked_note('future','f'*32,'entry',ENTRY)
        self.assertEqual(before,self.store.summary()['total_entries'])
    def test_restore_conflict_preserves_new_content(self):
        e=self.store.create_entry(ENTRY);self.store.delete_entry(e['id']);self.store.create_entry({**ENTRY,'id':e['id'],'content':'新的正文'})
        with self.assertRaises(ValueError):self.store.restore_trash(self.store.list_trash()[0]['id'])
        self.assertEqual(self.store.get_entry(e['id'])['content'],'新的正文');self.assertEqual(len(self.store.list_trash()),1)
    def test_drafts_positions_survive_restart(self):
        d=self.store.create_document({'name':'主题.md','content':'# 第一章'})
        self.store.save_draft('document:'+d['id'],{'kind':'document','data':{'content':'未保存修改'}})
        self.store.reading_position(d['id'],{'ratio':0.4,'heading':'第一章'})
        reopened=Store(self.app.db_path)
        self.assertEqual(reopened.list_drafts()[0]['payload']['data']['content'],'未保存修改')
        self.assertEqual(reopened.reading_position(d['id'])['ratio'],0.4);reopened.close()
    def test_full_backup_preview_restore_includes_pdf_history_links(self):
        f=self.store.create_future({'title':'混合精度'})
        d=self.store.create_linked_note('future',f['id'],'document',{'name':'主题.md','content':'初版'})
        self.app.document_files.prepare(d['id']);self.store.update_document(d['id'],{'content':'新版'});self.app.document_files.prepare(d['id'])
        folder=Path(self.temp.name)/'documents'/d['id'];(folder/'主题.pdf').write_bytes(b'%PDF-1.4\n%%EOF')
        self.store.save_draft('entry:new',{'data':{'content':'草稿'}})
        config=Path(self.temp.name)/'config.json';config.write_text('{"api_key":"test-only"}')
        saved=self.app.backups.create();raw=self.app.backups.archive_path(saved['id']).read_bytes()
        preview=self.app.backups.preview(raw);self.assertFalse(preview['includes_config']);self.assertEqual(preview['pdfs'],1)
        self.store.delete_document(d['id']);(folder/'主题.pdf').write_bytes(b'changed')
        result=self.app.backups.restore(preview['token']);self.assertTrue(result['restored'])
        self.assertEqual(self.store.get_document(d['id'])['content'],'新版');self.assertEqual((folder/'主题.pdf').read_bytes(),b'%PDF-1.4\n%%EOF')
        self.assertEqual(len(self.store.links_for('future',f['id'])),1);self.assertEqual(len(self.app.document_files.history(d['id'])),1)
        self.assertIn('test-only',config.read_text());self.assertTrue(self.app.backups.archive_path(result['safety_backup']['id']).is_file())
    def test_backup_rejects_corruption_and_path_traversal(self):
        self.store.create_entry(ENTRY);saved=self.app.backups.create();raw=self.app.backups.archive_path(saved['id']).read_bytes()
        for malicious in ('documents/../../outside.txt','../outside.txt','documents/x:stream'):
            buf=io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(raw)) as src,zipfile.ZipFile(buf,'w') as dst:
                manifest=json.loads(src.read('manifest.json'));manifest['files'][malicious]={'size':1,'sha256':'0'*64}
                for name in src.namelist():
                    if name!='manifest.json':dst.writestr(name,src.read(name))
                dst.writestr(malicious,b'x');dst.writestr('manifest.json',json.dumps(manifest))
            with self.assertRaises(ValueError):self.app.backups.preview(buf.getvalue())
        self.assertEqual(self.store.summary()['total_entries'],1)
    def test_history_opaque_identifier_and_durable_document_recovery(self):
        d=self.store.create_document({'name':'原文.md','content':'初版'});self.app.document_files.prepare(d['id'])
        self.store.update_document(d['id'],{'content':'新版'});self.app.document_files.prepare(d['id'])
        version=self.app.document_files.history(d['id'])[0]
        self.assertEqual(self.app.document_files.history_content(d['id'],version['id'])[0].decode(),'初版')
        with self.assertRaises(ValueError):self.app.document_files.history_content(d['id'],'../../config.json')
        self.store.delete_document(d['id']);self.store.restore_trash(self.store.list_trash()[0]['id'])
        self.assertEqual(len(self.app.document_files.history(d['id'])),1)

class WorkspaceHTTPChecks(unittest.TestCase):
    setUp=http_fixtures.LibraryHTTPChecks.setUp
    tearDown=http_fixtures.LibraryHTTPChecks.tearDown
    request=http_fixtures.LibraryHTTPChecks.request
    def test_new_routes_require_auth_and_return_sources(self):
        for path in ('/api/search','/api/trash','/api/drafts','/api/backups','/api/entries-page'):
            self.assertEqual(self.request(path,authenticated=False)[0],401)
        e=self.request('/api/entries','POST',ENTRY)[2]
        result=self.request('/api/search?query=FP32')[2]
        self.assertEqual(result['items'][0]['id'],e['id'])
        self.assertEqual(self.request('/api/entries-page?limit=0')[0],400)
        self.assertEqual(self.request('/api/drafts/entry%3Anew','POST',{'data':{'content':'恢复草稿'}})[0],200)
        self.assertEqual(len(self.request('/api/drafts')[2]['items']),1)
        self.request('/api/entries/'+e['id'],'DELETE')
        trash=self.request('/api/trash')[2]['items'][0]
        self.assertEqual(self.request('/api/trash/'+trash['id']+'/restore','POST',{})[0],200)
