"""Temporary-database coverage for images, Markdown and atomic portable backups."""
import base64
import copy
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import struct
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from library import MAX_DOCUMENT_BYTES, MAX_IMAGE_BYTES
from server import Application, make_server
from store import Store


def png():
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(b"\0\xff\0\0")) + chunk(b"IEND", b"")


IMAGE = {"name": "红色.png", "data_base64": base64.b64encode(png()).decode("ascii")}
ENTRY = {"date": "2026-10-27", "title": "图文笔记", "subject": "测试", "content": "# 内容"}


class LibraryStoreChecks(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="library-check-", dir=Path(__file__).resolve().parent)
        self.path = Path(self.directory.name) / "journal.sqlite3"
        self.store = Store(self.path)

    def tearDown(self):
        self.store.close()
        self.directory.cleanup()

    def test_assets_are_immutable_deduplicated_and_persistent(self):
        first = self.store.create_asset(IMAGE)
        repeated = self.store.create_asset({**IMAGE, "name": "另一个名称.png"})
        self.assertEqual(first, repeated)
        self.assertEqual(first["mime"], "image/png")
        self.assertEqual(first["size"], len(png()))
        self.store.close()
        self.store = Store(self.path)
        self.assertEqual(self.store.get_asset(first["id"])["data"], png())
        self.assertEqual(len(self.store.export()["assets"]), 1)

    def test_images_validate_bytes_not_extension(self):
        for data in (b"<svg><script>alert(1)</script></svg>", b"<html>x</html>", png()[:25], png() + b"<script>x</script>", b"x" * (MAX_IMAGE_BYTES + 1)):
            with self.assertRaises(ValueError):
                self.store.create_asset({"name": "fake.png", "data_base64": base64.b64encode(data).decode("ascii")})
        with self.assertRaises(ValueError):
            self.store.create_asset({"name": "fake.png", "data_base64": "!!"})
        with self.assertRaises(ValueError):
            self.store.create_asset({**IMAGE, "name": "../escape.png"})
        with self.assertRaises(ValueError):
            self.store.get_asset("../study.sqlite3")

    def test_documents_create_search_update_restart_and_delete(self):
        document = self.store.create_document({"name": "中文笔记.md", "content": "# 标题\n\n公式与图表 ✓"})
        self.assertEqual(document["size"], len(document["content"].encode("utf-8")))
        self.assertEqual(self.store.list_documents("公式")[0]["id"], document["id"])
        self.assertEqual(self.store.list_documents("%"), [])
        changed = self.store.update_document(document["id"], {"name": "重命名.markdown"})
        self.assertEqual(changed["content"], document["content"])
        self.assertEqual(changed["created_at"], document["created_at"])
        self.store.close()
        self.store = Store(self.path)
        self.assertEqual(self.store.get_document(document["id"]), changed)
        self.assertTrue(self.store.delete_document(document["id"]))
        self.assertFalse(self.store.delete_document(document["id"]))
        with self.assertRaises(KeyError):
            self.store.get_document(document["id"])

    def test_document_validation_does_not_write(self):
        for name, content in (("bad.html", "hi"), ("../bad.md", "hi"), ("bad\n.md", "hi"), ("a.md", "\0"), ("a.md", "x" * (MAX_DOCUMENT_BYTES + 1)), ("a.md", 42)):
            with self.assertRaises(ValueError):
                self.store.create_document({"name": name, "content": content})
        self.assertEqual(self.store.list_documents(), [])
        empty = self.store.create_document({"name": "空白.md", "content": ""})
        self.assertEqual(empty["size"], 0)

    def test_full_backup_round_trip_and_legacy_merge(self):
        asset = self.store.create_asset(IMAGE)
        document = self.store.create_document({"name": "笔记.md", "content": "![图](" + asset["url"] + ")"})
        entry = self.store.create_entry({**ENTRY, "content": document["content"]})
        backup = self.store.export()
        self.assertEqual(backup["version"], 2)
        other = Store(":memory:")
        try:
            result = other.import_entries(backup)
            self.assertEqual(result["documents"], 1)
            self.assertEqual(result["assets"], 1)
            self.assertEqual(other.export(), backup)
            other.import_entries({"version": 1, "entries": [{**entry, "title": "旧版导入"}]})
            self.assertEqual(other.get_asset(asset["id"])["data"], png())
            self.assertEqual(other.get_document(document["id"]), document)
            self.assertEqual(other.get_entry(entry["id"])["title"], "旧版导入")
        finally:
            other.close()

    def test_bad_resource_backup_never_partially_overwrites_journals(self):
        entry = self.store.create_entry(ENTRY)
        self.store.create_asset(IMAGE)
        self.store.create_document({"name": "笔记.md", "content": "原始内容"})
        original = self.store.export()
        for section, field, value in (("assets", "data_base64", "broken"), ("assets", "id", "0" * 64), ("documents", "name", "../bad.md"), ("documents", "size", 999), ("documents", "updated_at", "1900-01-01T00:00:00Z")):
            changed = copy.deepcopy(original)
            changed["entries"][0]["title"] = "不应写入"
            changed[section][0][field] = value
            with self.assertRaises(ValueError):
                self.store.import_entries(changed)
            self.assertEqual(self.store.export(), original)
            self.assertEqual(self.store.get_entry(entry["id"])["title"], ENTRY["title"])

    def test_old_database_gains_tables_without_changing_entries(self):
        entry = self.store.create_entry(ENTRY)
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("DROP TABLE assets")
            connection.execute("DROP TABLE documents")
            connection.commit()
        self.store.close()
        self.store = Store(self.path)
        self.assertEqual(self.store.get_entry(entry["id"]), entry)
        self.assertEqual(self.store.export(), {"version": 1, "entries": [entry]})


class LibraryHTTPChecks(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="library-http-", dir=Path(__file__).resolve().parent)
        self.app = Application(self.directory.name, token="local-resource-test")
        self.server = make_server("127.0.0.1", 0, self.app)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.opener = build_opener(ProxyHandler({}))

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.app.store.close()
        self.directory.cleanup()

    def request(self, path, method="GET", data=None, authenticated=True, headers=None):
        actual_headers = {"Content-Type": "application/json"}
        if authenticated:
            actual_headers["Authorization"] = "Bearer local-resource-test"
        actual_headers.update(headers or {})
        request = Request(self.base + path, method=method, headers=actual_headers,
                          data=None if data is None else json.dumps(data, ensure_ascii=False).encode("utf-8"))
        try:
            response = self.opener.open(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            body = response.read()
            return response.status, dict(response.headers), json.loads(body) if response.headers["Content-Type"].startswith("application/json") else body

    def test_images_auth_bytes_and_spoofed_requests(self):
        status, _, asset = self.request("/api/assets", "POST", IMAGE)
        self.assertEqual(status, 201)
        status, headers, data = self.request(asset["url"])
        self.assertEqual((status, data), (200, png()))
        self.assertEqual(headers["Content-Type"], "image/png")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(self.request(asset["url"], authenticated=False)[0], 401)
        self.assertEqual(self.request(asset["url"], headers={"Origin": "https://untrusted.invalid"})[0], 403)
        self.assertEqual(self.request("/api/assets", "POST", {"name": "bad.png", "data_base64": "bm90IGFuIGltYWdl"})[0], 400)
        self.assertEqual(self.request("/api/assets/" + "0" * 64)[0], 404)
        self.assertEqual(self.request("/api/assets/../../study.sqlite3")[0], 404)

    def test_documents_http_lifecycle_and_download(self):
        status, _, document = self.request("/api/documents", "POST", {"name": "中文.md", "content": "# 标题\n\n<script>no execution</script>"})
        self.assertEqual(status, 201)
        path = "/api/documents/" + document["id"]
        self.assertEqual(self.request(path)[2], document)
        self.assertEqual(self.request(path, authenticated=False)[0], 401)
        self.assertEqual(len(self.request("/api/documents?query=%E4%B8%AD%E6%96%87")[2]["documents"]), 1)
        status, headers, content = self.request(path + "/download")
        self.assertEqual(content.decode("utf-8"), document["content"])
        self.assertEqual(headers["Content-Type"], "text/markdown; charset=utf-8")
        self.assertIn("attachment;", headers["Content-Disposition"])
        self.assertIn("sandbox", headers["Content-Security-Policy"])
        self.assertEqual(self.request(path, "PATCH", {"content": "更新"})[2]["content"], "更新")
        self.assertEqual(self.request(path, "DELETE")[2], {"deleted": True})
        self.assertEqual(self.request(path)[0], 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
