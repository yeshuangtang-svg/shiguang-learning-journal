"""Run: python tests/test_store_agent.py"""
import importlib.util
from pathlib import Path
import tempfile
import sqlite3
from unittest.mock import patch
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing

MODULE_PATH = Path(__file__).resolve().parents[1] / "store.py"
spec = importlib.util.spec_from_file_location("study_store", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
Store = module.Store


class StoreChecks(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="store-test-", dir=Path(__file__).resolve().parent)
        self.store = Store(Path(self.directory.name) / "nested" / "journal.sqlite3")

    def tearDown(self):
        self.store.close()
        self.directory.cleanup()

    def entry(self, **patch):
        return self.store.create_entry({"date": "2026-10-25", "title": "学习 SQLite", "subject": "编程", "minutes": 30, "content": "", **patch})

    def test_empty_create_and_patch(self):
        self.assertEqual(self.store.list_entries(), [])
        entry = self.entry()
        self.assertEqual(entry["mood"], "okay")
        updated = self.store.update_entry(entry["id"], {"minutes": 45, "reflection": "事务很重要"})
        self.assertEqual(updated["title"], entry["title"])
        self.assertEqual(updated["created_at"], entry["created_at"])
        self.assertEqual(updated["minutes"], 45)
        self.assertEqual(self.store.get_entry(entry["id"]), updated)
        self.assertEqual(self.store.update_entry(entry["id"], {}), updated)
        with self.assertRaises(KeyError):
            self.store.update_entry("missing", {"minutes": 30})
        with self.assertRaises(KeyError):
            self.store.get_entry("missing")

    def test_calendar_and_validation(self):
        valid = dict(date="2024-02-29", title="闰日学习", subject="数学", minutes=1, content="")
        self.store.create_entry(valid)
        for patch in ({"date": "2025-02-29"}, {"date": "2026-13-01"}, {"date": "20261025"}, {"date": "0000-01-01"}, {"minutes": True}, {"minutes": 1.0}, {"minutes": 0}, {"minutes": 1441}, {"title": " "}, {"content": None}, {"mood": []}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                self.store.create_entry({**valid, **patch})
        entry = self.entry()
        with self.assertRaises(ValueError):
            self.store.update_entry(entry["id"], {'title = NULL; DROP TABLE entries; --': 'x'})
        with self.assertRaises(ValueError):
            self.store.update_entry(entry["id"], {"id": "different"})
        self.assertEqual(len(self.store.list_entries()), 2)

    def test_query_dates_summary_and_literal_search(self):
        base = dict(date="2025-12-31", title="复习", subject="数学", minutes=40, content="完成 100% 和 a_b")
        self.store.create_entry(base)
        self.store.create_entry({**base, "date": "2026-01-01", "minutes": 20})
        self.store.create_entry({**base, "date": "2026-01-01", "subject": "英语", "minutes": 30, "content": "阅读", "reflection": "关键收获"})
        self.assertEqual(len(self.store.list_entries(query="100%")), 2)
        self.assertEqual(len(self.store.list_entries(query="a_b")), 2)
        self.assertEqual(len(self.store.list_entries(query="关键")), 1)
        self.assertEqual(len(self.store.list_entries(query="' OR 1=1 --")), 0)
        self.assertEqual(len(self.store.list_entries(date_from="2026-01-01", subject="数学")), 1)
        self.assertEqual(len(self.store.list_entries(limit=1)), 1)
        with self.assertRaises(ValueError):
            self.store.list_entries(date_from="2026-01-02", date_to="2026-01-01")
        result = self.store.summary()
        self.assertEqual((result["total_entries"], result["study_days"]), (3, 2))
        self.assertNotIn("total_minutes", result)
        self.assertEqual(result["subjects"][0], {"subject": "数学", "entries": 2})
        self.assertEqual(result["days"][-1], {"date": "2026-01-01", "entries": 2})
        self.assertEqual(self.store.summary(date_from="2026-01-01")["total_entries"], 2)

    def test_import_merge_is_atomic(self):
        saved = self.entry()
        backup = self.store.export()
        incoming = {**saved, "id": "new-id", "title": "新记录"}
        before = self.store.export()
        with self.assertRaises(ValueError):
            self.store.import_entries({"version": 1, "entries": [incoming, {**saved, "date": "2025-02-29"}]})
        self.assertEqual(self.store.export(), before)
        with self.assertRaises(ValueError):
            self.store.import_entries({"version": 1, "entries": [incoming, incoming]})
        self.assertEqual(self.store.export(), before)
        result = self.store.import_entries({"version": 1, "entries": [incoming, {**saved, "title": "更新"}]})
        self.assertEqual(result, {"added": 1, "updated": 1, "total": 2})
        self.assertEqual(self.store.get_entry(saved["id"])["title"], "更新")
        self.assertEqual(self.store.import_entries(backup), {"added": 0, "updated": 1, "total": 2})
        self.assertTrue(self.store.delete_entry(saved["id"]))
        self.assertFalse(self.store.delete_entry(saved["id"]))

    def test_parallel_partial_updates_preserve_fields(self):
        entry = self.entry()
        patches = [{"title": "并发标题"}, {"subject": "数据库"}, {"reflection": "收获"}, {"next": "继续练习"}]
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda patch: self.store.update_entry(entry["id"], patch), patches))
        actual = self.store.get_entry(entry["id"])
        for patch in patches:
            for key, value in patch.items():
                self.assertEqual(actual[key], value)

    def test_memory_store(self):
        memory = Store(":memory:")
        try:
            memory.create_entry(dict(date="2026-10-25", title="内存", subject="测试", minutes=1, content=""))
            self.assertEqual(len(memory.list_entries()), 1)
        finally:
            memory.close()

    def test_conversation_logs_need_no_duration(self):
        payload = dict(date="2026-10-26", title="理解 KV Cache", subject="模型推理", content="问题：为什么缓存 K/V？\n结论：避免重复计算历史 token。")
        saved = self.store.create_entry(payload)
        self.assertIsNone(saved["minutes"])
        updated = self.store.update_entry(saved["id"], {"reflection": "缓存改善自回归推理效率"})
        self.assertIsNone(updated["minutes"])
        self.assertEqual(self.store.get_entry(saved["id"])["content"], payload["content"])
        self.assertIsNone(self.store.create_entry({**payload, "minutes": None})["minutes"])
        backup = self.store.export()
        self.assertTrue(all(entry["minutes"] is None for entry in backup["entries"]))
        restored = Store(":memory:")
        try:
            self.assertEqual(restored.import_entries(backup)["added"], 2)
            self.assertEqual(restored.export(), backup)
            self.assertEqual(restored.summary(), {
                "total_entries": 2, "study_days": 1,
                "subjects": [{"subject": "模型推理", "entries": 2}],
                "days": [{"date": "2026-10-26", "entries": 2}],
            })
            omitted = {**backup["entries"][0], "id": "omitted-duration"}
            omitted.pop("minutes")
            restored.import_entries({"version": 1, "entries": [omitted]})
            self.assertIsNone(restored.get_entry("omitted-duration")["minutes"])
        finally:
            restored.close()

    def make_legacy_database(self, filename):
        path = Path(self.directory.name) / filename
        saved = self.entry(id="legacy-entry", content="旧版日志完整保留", minutes=38)
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute('''CREATE TABLE entries (
                id TEXT PRIMARY KEY, date TEXT NOT NULL, title TEXT NOT NULL,
                subject TEXT NOT NULL, minutes INTEGER NOT NULL CHECK(minutes BETWEEN 1 AND 1440),
                content TEXT NOT NULL, reflection TEXT NOT NULL, "next" TEXT NOT NULL,
                mood TEXT NOT NULL CHECK(mood IN ('great','good','okay','tired')),
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )''')
            connection.execute(f"INSERT INTO entries ({module.COLUMN_SQL}) VALUES ({','.join('?' for _ in module.COLUMNS)})", tuple(saved[key] for key in module.COLUMNS))
            connection.execute("CREATE INDEX legacy_title_idx ON entries(title)")
            connection.execute("CREATE TABLE agent_sessions (id TEXT PRIMARY KEY, turns TEXT NOT NULL)")
            connection.execute("INSERT INTO agent_sessions VALUES ('session-1', '[]')")
        return path, saved

    def test_legacy_migration_preserves_rows_indexes_sessions_and_is_repeatable(self):
        path, original = self.make_legacy_database("legacy.sqlite3")
        migrated = Store(path)
        self.assertEqual(migrated.get_entry(original["id"]), original)
        created = migrated.create_entry(dict(date="2026-10-26", title="对话摘要", subject="学习", content="不填写时长"))
        self.assertIsNone(created["minutes"])
        migrated.update_entry(original["id"], {"reflection": "补充收获"})
        self.assertEqual(migrated.get_entry(original["id"])["minutes"], 38)
        with closing(sqlite3.connect(path)) as connection, connection:
            self.assertEqual(connection.execute("SELECT turns FROM agent_sessions").fetchone()[0], "[]")
            self.assertIsNotNone(connection.execute("SELECT name FROM sqlite_master WHERE name = 'legacy_title_idx'").fetchone())
            self.assertEqual(next(row[3] for row in connection.execute("PRAGMA table_info(entries)") if row[1] == "minutes"), 0)
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        snapshot = migrated.export()
        migrated.close()
        reopened = Store(path)
        try:
            self.assertEqual(reopened.export(), snapshot)
        finally:
            reopened.close()

    def test_failed_migration_rolls_back_schema_and_rows(self):
        path, original = self.make_legacy_database("rollback.sqlite3")
        migration = Store._migrate_optional_duration

        def fail_after_schema_change(connection):
            migration(connection)
            raise RuntimeError("simulated migration interruption")

        with patch.object(Store, "_migrate_optional_duration", side_effect=fail_after_schema_change):
            with self.assertRaisesRegex(RuntimeError, "simulated migration interruption"):
                Store(path)
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.row_factory = sqlite3.Row
            self.assertEqual(dict(connection.execute("SELECT * FROM entries").fetchone()), original)
            self.assertEqual(next(row["notnull"] for row in connection.execute("PRAGMA table_info(entries)") if row["name"] == "minutes"), 1)
            self.assertIsNone(connection.execute("SELECT name FROM sqlite_master WHERE name = 'entries_optional_duration'").fetchone())
            self.assertIsNotNone(connection.execute("SELECT name FROM sqlite_master WHERE name = 'legacy_title_idx'").fetchone())
            self.assertEqual(connection.execute("SELECT turns FROM agent_sessions").fetchone()[0], "[]")
        retried = Store(path)
        try:
            self.assertEqual(retried.get_entry(original["id"]), original)
        finally:
            retried.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
