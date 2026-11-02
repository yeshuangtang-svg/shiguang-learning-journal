"""Portable Windows desktop shell for the study journal and its local Agent API."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time
import traceback
from urllib.request import ProxyHandler, Request, build_opener

from server import Application, ROOT, load_env, make_server

TITLE = "拾光 · 学习日志"


def application_directory():
    # PyInstaller's extraction directory is temporary: never put user data there.
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def message_box(message, error=True):
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(None, message, TITLE, 0x10 if error else 0x40)
    elif sys.stderr:
        print(message, file=sys.stderr)


def log_failure(data_dir, error):
    """Keep useful locations while excluding exceptions' text, secrets and locals."""
    try:
        frames = traceback.extract_tb(error.__traceback__)
        locations = " > ".join(f"{Path(frame.filename).name}:{frame.lineno} ({frame.name})" for frame in frames)
        with (Path(data_dir) / "desktop-error.log").open("a", encoding="utf-8") as stream:
            stream.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {type(error).__name__}: {locations}\n")
    except OSError:
        pass


class SingleInstance:
    """A nonblocking, per-data-directory Windows mutex; crashes release the handle."""

    def __init__(self, data_dir):
        self.data_dir = Path(data_dir).resolve()
        self.handle = None
        self.kernel = None

    def acquire(self):
        if sys.platform != "win32":
            return True
        from ctypes import wintypes
        identity = hashlib.sha256(os.path.normcase(str(self.data_dir)).encode("utf-8")).hexdigest()
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
        self.kernel.CreateMutexW.restype = wintypes.HANDLE
        self.kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        self.kernel.CloseHandle.restype = wintypes.BOOL
        self.handle = self.kernel.CreateMutexW(None, False, "Local\\ShiguangStudyLog_" + identity)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            self.close()
            return False
        return True

    def foreground(self):
        if sys.platform != "win32":
            return False
        from ctypes import wintypes
        user = ctypes.WinDLL("user32", use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user.EnumWindows.argtypes = (callback_type, wintypes.LPARAM)
        user.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
        user.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
        user.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
        user.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
        user.SetForegroundWindow.argtypes = (wintypes.HWND,)
        for _ in range(20):  # A second click can arrive before WebView2 has initialized.
            try:
                pid = json.loads((self.data_dir / "runtime.json").read_text(encoding="utf-8"))["pid"]
            except (OSError, ValueError, KeyError):
                pid = None
            found = []

            @callback_type
            def visit(hwnd, _):
                owner = wintypes.DWORD()
                user.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
                if pid and owner.value == pid:
                    title = ctypes.create_unicode_buffer(user.GetWindowTextLengthW(hwnd) + 1)
                    user.GetWindowTextW(hwnd, title, len(title))
                    if title.value == TITLE:
                        found.append(hwnd)
                        return False
                return True

            user.EnumWindows(visit, 0)
            if found:
                user.ShowWindow(found[0], 9)  # SW_RESTORE
                user.SetForegroundWindow(found[0])
                return True
            time.sleep(0.1)
        return False

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


class DesktopServer:
    """Owns a new loopback-only server; never trusts a service already on the port."""

    def __init__(self, data_dir, token="", preferred_port=8787):
        self.data_dir = Path(data_dir).resolve()
        self.app = Application(self.data_dir, token)
        self.app.desktop = True
        self.server = None
        self.thread = None
        self.closed = False
        ports = [preferred_port]
        try:
            previous = json.loads((self.data_dir / "runtime.json").read_text(encoding="utf-8")).get("port")
            if preferred_port and type(previous) is int and 1 <= previous <= 65535 and previous not in ports:
                ports.append(previous)
        except (OSError, ValueError):
            pass
        if 0 not in ports:
            ports.append(0)
        for port in ports:
            try:
                self.server = make_server("127.0.0.1", port, self.app)
                break
            except OSError as error:
                if port == 0 or (error.errno not in (48, 98, 10048, 10013, 13) and getattr(error, "winerror", None) not in (10048, 10013)):
                    self.app.store.close()
                    raise
        self.port = self.server.server_port
        self.url = f"http://127.0.0.1:{self.port}"
        self.app.api_url = self.url

    def start(self):
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.1}, name="study-agent-http", daemon=True)
        self.thread.start()
        try:
            self.write_runtime("running")
        except OSError:
            self.close()
            raise
        return self

    def write_runtime(self, status):
        write_json(self.data_dir / "runtime.json", {"pid": os.getpid(), "port": self.port, "api_url": self.url, "status": status})

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.thread:
            self.server.shutdown()
        self.server.server_close()
        if self.thread:
            self.thread.join(timeout=3)
        self.app.store.close()
        try:
            self.write_runtime("closed")
        except OSError as error:
            log_failure(self.data_dir, error)


def run_smoke_test(data_dir, report_path):
    """Exercise the packaged assets and API using a new, explicitly supplied directory."""
    data_dir = Path(data_dir).resolve()
    if (data_dir / "study.sqlite3").exists():
        raise ValueError("Smoke tests require a fresh data directory; existing logs are never modified.")
    checks = []
    report = {"ok": False, "checks": checks, "data_dir": str(data_dir), "frozen": bool(getattr(sys, "frozen", False))}
    backend = None
    opener = build_opener(ProxyHandler({}))
    token = "smoke-test-local-token"

    def request(path, method="GET", payload=None, raw=False):
        headers = {"Authorization": "Bearer " + token}
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        with opener.open(Request(backend.url + path, data=body, headers=headers, method=method), timeout=10) as response:
            result = response.read()
            return result if raw else json.loads(result)

    try:
        backend = DesktopServer(data_dir, token, preferred_port=0).start()
        report["api_url"] = backend.url
        assert request("/api/health")["ok"]
        checks.append("health")
        assert "拾光" in request("/", raw=True).decode("utf-8")
        assert request("/api/openapi.json")["openapi"]
        assert request("/api/docs", raw=True)
        assert b'StudyMarkdown' in request("/markdown.js", raw=True)
        assert b'image-viewer' in request("/image-viewer.js", raw=True)
        assert b'image-viewer' in request("/image-viewer.css", raw=True)
        assert request("/vendor/marked.min.js", raw=True)
        assert request("/vendor/purify.min.js", raw=True)
        checks.append("bundled_static_and_api_docs")
        entry = request("/api/entries", "POST", {"date": "2026-10-26", "title": "桌面版自检", "subject": "测试", "content": "测试日志持久化，不调用模型 API。"})
        assert request("/api/entries/" + entry["id"])["title"] == "桌面版自检"
        assert entry["minutes"] is None
        checks.append("create_and_read")
        assert request("/api/entries/" + entry["id"], "PATCH", {"reflection": "无需时长即可记录学习内容"})["reflection"] == "无需时长即可记录学习内容"
        checks.append("update")
        assert request("/api/summary")["total_entries"] == 1
        assert "total_minutes" not in request("/api/summary")
        checks.append("summary")
        image = request("/api/assets", "POST", {
            "name": "smoke.png",
            "data_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC",
        })
        assert request(image["url"], raw=True).startswith(b"\x89PNG\r\n\x1a\n")
        document = request("/api/documents", "POST", {"name": "桌面自检.md", "content": "# 图文笔记\n\n![图片](" + image["url"] + ")\n"})
        assert request("/api/documents/" + document["id"])["content"].startswith("# 图文笔记")
        assert request("/api/documents/" + document["id"] + "/download", raw=True).decode("utf-8").startswith("# 图文笔记")
        checks.append("image_and_markdown_library")
        backend.close()
        backend = DesktopServer(data_dir, token, preferred_port=0).start()
        assert request("/api/entries/" + entry["id"])["minutes"] is None
        assert request("/api/entries/" + entry["id"])["reflection"] == "无需时长即可记录学习内容"
        checks.append("restart_persistence")
        assert request(image["url"], raw=True).startswith(b"\x89PNG")
        assert request("/api/documents/" + document["id"])["name"] == "桌面自检.md"
        exported = request("/api/export")
        assert exported["version"] == 2 and exported["entries"][0]["id"] == entry["id"]
        assert exported["assets"] and exported["documents"]
        checks.append("export")
        report["ok"] = True
    except Exception as error:
        report["error_type"] = type(error).__name__
        raise
    finally:
        if backend:
            backend.close()
        write_json(report_path, report)
    return report


def main(argv=None):
    base = application_directory()
    load_env(base / ".env")
    parser = argparse.ArgumentParser(description="拾光学习日志桌面版")
    parser.add_argument("--data-dir", help="数据目录；默认位于 EXE 旁的 data 文件夹")
    parser.add_argument("--smoke-test", metavar="REPORT_PATH", help="在新数据目录运行打包自检；不打开窗口")
    parser.add_argument("--quit-after", type=float, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    data_dir = Path(args.data_dir).expanduser().resolve() if args.data_dir else base / "data"
    instance, backend = None, None
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        if args.smoke_test:
            if not args.data_dir:
                raise ValueError("Smoke test requires an explicit new --data-dir.")
            run_smoke_test(data_dir, args.smoke_test)
            return 0
        instance = SingleInstance(data_dir)
        if not instance.acquire():
            if not instance.foreground():
                message_box("拾光已经在运行或正在启动。请稍候，或从任务栏打开已有窗口。", error=False)
            return 0
        backend = DesktopServer(data_dir, os.getenv("AGENT_API_TOKEN", "")).start()
        import webview
        webview.settings["ALLOW_DOWNLOADS"] = True
        webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
        webview.settings["ALLOW_FILE_URLS"] = False
        if sys.platform == "win32":
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Shiguang.StudyJournal.Desktop")
        window = webview.create_window(TITLE, backend.url, width=1320, height=900, min_size=(960, 680), background_color="#f7f5f0", text_select=True)
        # A bounded QA switch also exercises the actual GUI startup and shutdown.
        def auto_close():
            if args.quit_after and args.quit_after > 0:
                time.sleep(args.quit_after)
                window.destroy()
        icon = ROOT / "app.ico"
        webview.start(auto_close, gui="edgechromium", private_mode=False, storage_path=str(data_dir / "webview"), icon=str(icon) if icon.exists() else None)
        return 0
    except Exception as error:
        log_failure(data_dir, error)
        if not args.smoke_test:
            if isinstance(error, PermissionError):
                message_box("无法写入学习日志数据。请将整个应用文件夹移到你有写入权限的位置，例如桌面或文档，再重新打开。")
            else:
                message_box("拾光暂时无法启动。\n\n请确认系统已安装 Microsoft Edge WebView2 Runtime，并将应用完整解压到有写入权限的文件夹。\n\n错误位置已记录到 data/desktop-error.log；其中不会记录 API Key 或学习内容。")
        return 1
    finally:
        try:
            if backend:
                backend.close()
        finally:
            if instance:
                instance.close()


if __name__ == "__main__":
    raise SystemExit(main())
