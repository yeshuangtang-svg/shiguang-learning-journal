"""Desktop lifecycle checks without WebView2, a GUI, or real model API calls.

Run: python tests/test_desktop.py
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import gc
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from desktop import DesktopServer, SingleInstance, run_smoke_test
from server import Application

ENTRY = {"date": "2026-10-25", "title": "桌面应用测试", "subject": "编程", "content": "验证日志保存与重启。"}


class UnrelatedService(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.server.request_count += 1
        body = b'{"unrelated":true}'
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class DesktopLifecycleChecks(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="study-desktop-test-", dir=Path(__file__).resolve().parent)
        self.data_dir = Path(self.directory.name) / "data"
        self.env = patch.dict(os.environ, {name: "" for name in ("LLM_MODEL", "LLM_BASE_URL", "LLM_API_KEY", "AGENT_ALLOWED_HOSTS")})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self.cleanup_directory)
        self.opener = build_opener(ProxyHandler({}))

    def cleanup_directory(self):
        # SQLite context managers commit/rollback; CPython may finalize their
        # connection cycles later. Flush those handles before Windows cleanup.
        gc.collect()
        self.directory.cleanup()

    def request(self, url, payload=None):
        headers = {"Authorization": "Bearer launcher-test-token"}
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        with self.opener.open(Request(url, data=body, headers=headers), timeout=3) as response:
            return json.loads(response.read())

    def start(self, preferred_port=0):
        backend = DesktopServer(self.data_dir, "launcher-test-token", preferred_port).start()
        self.addCleanup(backend.close)
        return backend

    def test_occupied_port_is_not_reused_and_health_reports_actual_endpoint(self):
        unrelated = ThreadingHTTPServer(("127.0.0.1", 0), UnrelatedService)
        unrelated.request_count = 0
        thread = threading.Thread(target=unrelated.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()

        def close_unrelated():
            unrelated.shutdown()
            unrelated.server_close()
            thread.join(timeout=2)

        self.addCleanup(close_unrelated)
        backend = self.start(unrelated.server_port)
        self.assertNotEqual(backend.port, unrelated.server_port)
        health = self.request(backend.url + "/api/health")
        self.assertTrue(health["ok"])
        self.assertTrue(health["desktop"])
        self.assertEqual(health["api_url"], backend.url)
        self.assertTrue(health["auth_required"])
        self.assertEqual(unrelated.request_count, 0, "The launcher must not probe or adopt an unrelated service.")
        backend.close()
        self.assertEqual(self.request(f"http://127.0.0.1:{unrelated.server_port}/"), {"unrelated": True})

    def test_window_backend_closes_its_socket_and_reopens_saved_logs(self):
        backend = self.start()
        entry = self.request(backend.url + "/api/entries", ENTRY)
        port = backend.port
        backend.close()
        self.assertFalse(backend.thread.is_alive())
        with self.assertRaises(OSError):
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                pass
        state = json.loads((self.data_dir / "runtime.json").read_text(encoding="utf-8"))
        self.assertEqual(state["status"], "closed")
        self.assertEqual(state["api_url"], backend.url)
        reopened = self.start(port)
        saved = self.request(reopened.url + "/api/entries/" + entry["id"])
        self.assertEqual(saved["content"], ENTRY["content"])
        self.assertIsNone(saved["minutes"])

    @unittest.skipUnless(sys.platform == "win32", "Windows desktop mutex")
    def test_mutex_prevents_duplicate_directory_and_releases_on_close(self):
        first = SingleInstance(self.data_dir)
        duplicate = SingleInstance(self.data_dir / ".")
        independent = SingleInstance(self.data_dir.parent / "independent")
        for instance in (first, duplicate, independent):
            self.addCleanup(instance.close)
        self.assertTrue(first.acquire())
        self.assertFalse(duplicate.acquire())
        self.assertTrue(independent.acquire())
        first.close()
        self.assertTrue(duplicate.acquire())

    def test_smoke_test_refuses_existing_logs_without_changing_them(self):
        app = Application(self.data_dir)
        self.addCleanup(app.store.close)
        entry = app.store.create_entry(ENTRY)
        before = app.db_path.read_bytes()
        report_path = self.data_dir / "should-not-exist.json"
        with self.assertRaisesRegex(ValueError, "fresh data directory"):
            run_smoke_test(self.data_dir, report_path)
        self.assertEqual(app.db_path.read_bytes(), before)
        self.assertEqual(app.store.get_entry(entry["id"])["title"], ENTRY["title"])
        self.assertFalse(report_path.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
