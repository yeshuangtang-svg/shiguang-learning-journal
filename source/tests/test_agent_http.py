"""Integration checks: a real local API server and a real fake model HTTP endpoint.

Run: python tests/test_agent_http.py
No external model, real API key, or user records are used.
"""
from collections import deque
import gc
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("study_agent_server", ROOT / "server.py")
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)

ENTRY = {"date": "2026-10-25", "title": "学习 HTTP", "subject": "编程", "content": "完成请求与响应练习", "mood": "okay"}


def tool_call(name, args, id="call_1"):
    return {"id": id, "type": "function", "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}}


class FakeProvider(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.requests.append({"path": self.path, "payload": payload, "authorization": self.headers.get("Authorization")})
        if self.server.responses:
            status, body = self.server.responses.popleft()
        else:
            status, body = 500, {"error": "test response queue exhausted"}
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class AgentHTTPChecks(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {name: "" for name in ("LLM_MODEL", "LLM_BASE_URL", "LLM_API_KEY", "AGENT_ALLOWED_HOSTS")})
        self.env.start()
        self.directory = tempfile.TemporaryDirectory(prefix="agent-http-", dir=Path(__file__).resolve().parent)
        self.provider = ThreadingHTTPServer(("127.0.0.1", 0), FakeProvider)
        self.provider.requests, self.provider.responses = [], deque()
        self.provider_thread = threading.Thread(target=self.provider.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        self.provider_thread.start()
        self.app = agent.Application(self.directory.name, token="local-agent-test-token")
        self.app.config.update({"base_url": f"http://127.0.0.1:{self.provider.server_port}/v1", "model": "stub-model", "api_key": "test-provider-key-not-real"})
        self.server = agent.make_server("127.0.0.1", 0, self.app)
        self.server_thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        self.server_thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.opener = build_opener(ProxyHandler({}))

    def tearDown(self):
        for server, thread in ((self.server, self.server_thread), (self.provider, self.provider_thread)):
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        self.app.store.close()
        gc.collect()
        self.directory.cleanup()
        self.env.stop()

    def message(self, **message):
        self.provider.responses.append((200, {"choices": [{"message": {"role": "assistant", **message}}]}))

    def request(self, method, path, body=None, authenticated=True, headers=None):
        actual_headers = {"Content-Type": "application/json"}
        if authenticated:
            actual_headers["Authorization"] = "Bearer local-agent-test-token"
        actual_headers.update(headers or {})
        request = Request(self.base + path, data=None if body is None else json.dumps(body, ensure_ascii=False).encode(), headers=actual_headers, method=method)
        try:
            response = self.opener.open(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    def test_real_provider_protocol_session_and_idempotency(self):
        self.message(content=None, tool_calls=[tool_call("create_entry", ENTRY)])
        self.message(content="已保存 HTTP 学习日志。")
        body = {"message": "把今天的 HTTP 问题和收获记录下来", "request_id": "record-1"}
        status, result = self.request("POST", "/api/chat", body)
        self.assertEqual(status, 200, result)
        self.assertTrue(result["actions"][0]["ok"])
        self.assertEqual(len(self.provider.requests), 2)
        first, second = self.provider.requests
        self.assertEqual(first["path"], "/v1/chat/completions")
        self.assertEqual(first["authorization"], "Bearer test-provider-key-not-real")
        self.assertEqual(first["payload"]["model"], "stub-model")
        self.assertFalse(first["payload"]["stream"])
        self.assertEqual(first["payload"]["tool_choice"], "auto")
        self.assertIn("tools", first["payload"])
        create_tool = next(t["function"] for t in first["payload"]["tools"] if t["function"]["name"] == "create_entry")
        self.assertNotIn("minutes", create_tool["parameters"]["properties"])
        self.assertNotIn("minutes", create_tool["parameters"]["required"])
        self.assertIn("不询问、不估算、不记录学习时长", first["payload"]["messages"][0]["content"])
        self.assertIsNone(result["actions"][0]["result"]["minutes"])
        self.assertTrue(any(message["role"] == "tool" and json.loads(message["content"])["ok"] for message in second["payload"]["messages"]))
        self.assertEqual(self.request("POST", "/api/chat", body), (200, result))
        self.assertEqual(len(self.app.store.list_entries()), 1)
        self.assertEqual(len(self.provider.requests), 2)
        self.assertEqual(self.request("POST", "/api/chat", {**body, "message": "另一条消息"})[0], 409)

        # Reconstruct the app to verify durable sessions and request replay.
        self.server.app = agent.Application(self.directory.name, token="local-agent-test-token")
        self.app = self.server.app
        self.assertEqual(self.request("POST", "/api/chat", body), (200, result))
        status, session = self.request("GET", "/api/sessions/" + result["session_id"])
        self.assertEqual(status, 200)
        self.assertEqual([message["role"] for message in session["messages"]], ["user", "assistant"])
        self.message(content="可以继续复习请求头。")
        status, _ = self.request("POST", "/api/chat", {"message": "接下来复习什么", "session_id": result["session_id"], "request_id": "followup-1"})
        self.assertEqual(status, 200)
        history = self.provider.requests[-1]["payload"]["messages"]
        self.assertTrue(any(message.get("content") == body["message"] for message in history))

    def test_list_summary_tools(self):
        self.app.store.create_entry(ENTRY)
        self.app.store.create_entry({**ENTRY, "subject": "英语", "minutes": 25})
        self.message(content=None, tool_calls=[tool_call("list_entries", {"date_from": "2026-10-25", "date_to": "2026-10-25"}), tool_call("study_summary", {"date_from": "2026-10-25", "date_to": "2026-10-25"}, "call_2")])
        self.message(content="今天记录了 2 篇日志，涉及编程与英语。")
        status, result = self.request("POST", "/api/chat", {"message": "总结今天的学习", "request_id": "summary-1"})
        self.assertEqual(status, 200, result)
        self.assertEqual(len(result["actions"][0]["result"]["entries"]), 2)
        self.assertEqual(result["actions"][1]["result"]["total_entries"], 2)
        self.assertNotIn("total_minutes", result["actions"][1]["result"])
        self.assertEqual(result["actions"][1]["result"]["study_days"], 1)
        tool_messages = [m for m in self.provider.requests[-1]["payload"]["messages"] if m["role"] == "tool"]
        for message in tool_messages:
            self.assertNotIn('"minutes"', message["content"])
            self.assertNotIn('"total_minutes"', message["content"])

    def test_legacy_tool_history_does_not_restore_duration_metadata(self):
        legacy_turn = [
            {"role": "user", "content": "记录我的学习"},
            {"role": "assistant", "content": None, "tool_calls": [tool_call("create_entry", {**ENTRY, "minutes": 60})]},
            {"role": "tool", "tool_call_id": "call_1", "content": agent.encode({"tool": "study_summary", "ok": True, "result": {"total_minutes": 60, "total_entries": 1, "subjects": [{"subject": "编程", "minutes": 60, "entries": 1}]}})},
            {"role": "assistant", "content": "已记录学习内容。"},
        ]
        with self.app.connection() as connection:
            connection.execute("INSERT INTO agent_sessions VALUES (?, ?)", ("legacy-session", agent.encode([legacy_turn])))
        self.message(content="已根据之前的知识点整理。")
        status, result = self.request("POST", "/api/chat", {"message": "复盘知识点", "session_id": "legacy-session", "request_id": "legacy-followup"})
        self.assertEqual(status, 200, result)
        replayed = next(m for m in self.provider.requests[-1]["payload"]["messages"] if m["role"] == "tool")
        self.assertNotIn('"minutes"', replayed["content"])
        self.assertNotIn('"total_minutes"', replayed["content"])
        self.assertEqual(json.loads(replayed["content"])["result"]["total_entries"], 1)
        replayed_call = next(m for m in self.provider.requests[-1]["payload"]["messages"] if m.get("tool_calls"))
        self.assertNotIn("minutes", json.loads(replayed_call["tool_calls"][0]["function"]["arguments"]))
        # Filtering model context must not rewrite the user's stored history.
        self.assertEqual(self.app.session("legacy-session")[0], legacy_turn)

    def test_provider_failure_after_write_has_truthful_cached_result(self):
        self.message(tool_calls=[tool_call("create_entry", ENTRY)])
        self.provider.responses.append((503, {"error": "down"}))
        body = {"message": "记录编程学习的问题与收获", "request_id": "partial-success"}
        status, result = self.request("POST", "/api/chat", body)
        self.assertEqual(status, 200, result)
        self.assertIn("已成功保存", result["reply"])
        self.assertIn("无需重复提交", result["reply"])
        self.assertNotIn("分钟", result["reply"])
        self.assertTrue(result["warnings"])
        self.assertEqual(len(self.app.store.list_entries()), 1)
        self.assertEqual(self.request("POST", "/api/chat", body), (200, result))

    def test_malformed_tool_arguments_do_not_save(self):
        broken = tool_call("create_entry", ENTRY)
        broken["function"]["arguments"] = "{bad json"
        self.message(tool_calls=[broken, tool_call("create_entry", {**ENTRY, "minutes": "35"}, "bad_type")])
        self.message(content="日志尚未保存，请补充有效的信息。")
        status, result = self.request("POST", "/api/chat", {"message": "记录学习", "request_id": "bad-arguments"})
        self.assertEqual(status, 200, result)
        self.assertTrue(all(not action["ok"] for action in result["actions"]))
        self.assertEqual(self.app.store.list_entries(), [])

    def test_malformed_reply_after_write_keeps_truthful_cached_result(self):
        self.message(tool_calls=[tool_call("create_entry", ENTRY)])
        self.message(content={"text": "incompatible content shape"})
        body = {"message": "记录编程学习的问题与收获", "request_id": "bad-reply-after-write"}
        status, result = self.request("POST", "/api/chat", body)
        self.assertEqual(status, 200, result)
        self.assertIn("已成功保存", result["reply"])
        self.assertEqual(self.request("POST", "/api/chat", body), (200, result))
        self.assertEqual(len(self.app.store.list_entries()), 1)

    def test_malformed_call_after_write_keeps_truthful_cached_result(self):
        self.message(tool_calls=[tool_call("create_entry", ENTRY)])
        self.message(tool_calls=[None])
        body = {"message": "记录编程学习的问题与收获", "request_id": "bad-call-after-write"}
        status, result = self.request("POST", "/api/chat", body)
        self.assertEqual(status, 200, result)
        self.assertIn("已成功保存", result["reply"])
        self.assertEqual(self.request("POST", "/api/chat", body), (200, result))
        self.assertEqual(len(self.app.store.list_entries()), 1)

    def test_access_and_config_redaction(self):
        self.assertEqual(self.request("GET", "/api/health", authenticated=False)[0], 200)
        for path in ("/api/config", "/api/entries", "/api/export"):
            self.assertEqual(self.request("GET", path, authenticated=False)[0], 401)
        self.assertEqual(self.request("GET", "/api/entries", headers={"Origin": "https://untrusted.example"})[0], 403)
        self.assertEqual(self.request("GET", "/api/entries", headers={"Host": "untrusted.example"})[0], 403)
        self.assertEqual(self.request("GET", "/api/entries", headers={"Origin": self.base})[0], 200)
        status, config = self.request("GET", "/api/config")
        self.assertEqual(status, 200)
        self.assertTrue(config["api_key_set"])
        self.assertNotIn("api_key", config)
        self.assertNotIn("test-provider-key-not-real", json.dumps(config))
        status, config = self.request("POST", "/api/config", {"api_key": "", "model": "stub-model-2"})
        self.assertEqual(status, 200)
        self.assertTrue(config["api_key_set"], "Blank key must preserve existing key.")
        self.assertNotIn("api_key", config)

    def test_manual_rest_crud_export_import(self):
        status, entry = self.request("POST", "/api/entries", ENTRY)
        self.assertEqual(status, 201, entry)
        self.assertIsNone(entry["minutes"])
        path = "/api/entries/" + entry["id"]
        self.assertEqual(self.request("GET", path), (200, entry))
        status, changed = self.request("PATCH", path, {"reflection": "理解了状态码"})
        self.assertEqual(status, 200, changed)
        self.assertEqual(changed["content"], ENTRY["content"])
        self.assertEqual(self.request("GET", "/api/summary")[1]["total_entries"], 1)
        self.assertIsNone(changed["minutes"])
        status, backup = self.request("GET", "/api/export")
        self.assertEqual(status, 200)
        self.assertEqual(len(backup["entries"]), 1)
        invalid = {"version": 1, "entries": [{**changed, "id": "new-id"}, {**changed, "date": "2025-02-29"}]}
        self.assertEqual(self.request("POST", "/api/import", invalid)[0], 400)
        self.assertEqual(len(self.request("GET", "/api/entries")[1]["entries"]), 1)
        self.assertEqual(self.request("DELETE", path), (200, {"deleted": True}))
        self.assertEqual(self.request("GET", path)[0], 404)
        self.assertEqual(self.request("POST", "/api/import", backup), (200, {"added": 1, "updated": 0, "total": 1}))
        self.assertEqual(self.request("POST", "/api/import", backup), (200, {"added": 0, "updated": 1, "total": 1}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
