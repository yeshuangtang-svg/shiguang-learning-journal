"""Validated, transactional SQLite storage for a personal learning-log agent."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
import re
import sqlite3
import uuid

from workspace import WorkspaceMixin, create_workspace_tables
from library import LibraryMixin, create_tables, export_resources, import_resources, validate_backup
from future import FutureMixin, create_table, validate_future_backup, import_future


EDITABLE = ("date", "title", "subject", "minutes", "content", "reflection", "next", "mood")
COLUMNS = ("id", *EDITABLE, "created_at", "updated_at")
COLUMN_SQL = ", ".join('"' + column + '"' for column in COLUMNS)
MOODS = {"great", "good", "okay", "tired"}


def _date(value, label="日期"):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"{label}须使用 YYYY-MM-DD 格式。")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{label}不是有效的日历日期。") from None
    return value


def _text(value, label, maximum, required=False, trim=False):
    if not isinstance(value, str):
        raise ValueError(f"{label}须为文字。")
    if trim:
        value = value.strip()
    if required and not value.strip():
        raise ValueError(f"请填写{label}。")
    if len(value) > maximum:
        raise ValueError(f"{label}不能超过 {maximum} 个字符。")
    return value


def _identifier(value):
    return _text(value, "记录编号", 160, required=True, trim=True)


def _timestamp(value, label):
    if not isinstance(value, str) or "T" not in value:
        raise ValueError(f"{label}须为带时区的 ISO 时间。")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError()
        return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
    except (ValueError, OverflowError):
        raise ValueError(f"{label}须为有效且带时区的 ISO 时间。") from None


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _fields(raw):
    for name, label in (("date", "日期"), ("title", "标题"), ("subject", "科目"), ("content", "学习内容")):
        if name not in raw:
            raise ValueError(f"缺少{label}。")
    # Retain legacy durations for old backups, without inventing a duration for
    # a conversation log. New clients should omit this compatibility field.
    minutes = raw.get("minutes")
    if minutes is not None and (type(minutes) is not int or not 1 <= minutes <= 1440):
        raise ValueError("旧版分钟数字段须为空或 1–1440 之间的整数。")
    mood = raw.get("mood", "okay")
    if not isinstance(mood, str) or mood not in MOODS:
        raise ValueError("学习状态须为 great、good、okay 或 tired。")
    return {
        "date": _date(raw["date"]),
        "title": _text(raw["title"], "标题", 120, required=True, trim=True),
        "subject": _text(raw["subject"], "科目", 60, required=True, trim=True),
        "minutes": minutes,
        "content": _text(raw["content"], "学习内容", 100_000),
        "reflection": _text(raw.get("reflection", ""), "收获与思考", 100_000),
        "next": _text(raw.get("next", ""), "下一步计划", 100_000),
        "mood": mood,
    }


def _object(raw, allowed):
    if not isinstance(raw, dict):
        raise ValueError("学习记录须为 JSON 对象。")
    if any(key not in allowed for key in raw):
        raise ValueError("学习记录包含不支持的字段。")


class Store(WorkspaceMixin, LibraryMixin, FutureMixin):
    """Each operation opens and closes its own SQLite connection (5 s timeout)."""

    def __init__(self, db_path):
        self._keeper = None
        self._uri = str(db_path) == ":memory:"
        if self._uri:
            self.db_path = f"file:study-agent-{uuid.uuid4().hex}?mode=memory&cache=shared"
            self._keeper = sqlite3.connect(self.db_path, uri=True, timeout=5, check_same_thread=False)
        else:
            path = Path(db_path).expanduser().resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            self.db_path = str(path)
        with self._connection() as connection:
            # Explicit BEGIN also makes SQLite schema changes transactional.
            # Lock before inspecting so simultaneous launches cannot both migrate.
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("""
                CREATE TABLE IF NOT EXISTS entries (
                    id TEXT PRIMARY KEY,
                    date TEXT NOT NULL,
                    title TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    minutes INTEGER CHECK(minutes IS NULL OR minutes BETWEEN 1 AND 1440),
                    content TEXT NOT NULL,
                    reflection TEXT NOT NULL,
                    "next" TEXT NOT NULL,
                    mood TEXT NOT NULL CHECK(mood IN ('great', 'good', 'okay', 'tired')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            minutes_column = next(row for row in connection.execute("PRAGMA table_info(entries)") if row["name"] == "minutes")
            if minutes_column["notnull"]:
                self._migrate_optional_duration(connection)
            connection.execute("CREATE INDEX IF NOT EXISTS entries_date_idx ON entries(date)")
            connection.execute("CREATE INDEX IF NOT EXISTS entries_subject_idx ON entries(subject)")
            create_tables(connection)
            create_table(connection)
            create_workspace_tables(connection)

    @staticmethod
    def _migrate_optional_duration(connection):
        """Rebuild the legacy table inside the caller's transaction, preserving data."""
        schema_objects = [row[0] for row in connection.execute(
            "SELECT sql FROM sqlite_master WHERE tbl_name = 'entries' AND type IN ('index', 'trigger') AND sql IS NOT NULL"
        )]
        connection.execute("""
            CREATE TABLE entries_optional_duration (
                id TEXT PRIMARY KEY,
                date TEXT NOT NULL,
                title TEXT NOT NULL,
                subject TEXT NOT NULL,
                minutes INTEGER CHECK(minutes IS NULL OR minutes BETWEEN 1 AND 1440),
                content TEXT NOT NULL,
                reflection TEXT NOT NULL,
                "next" TEXT NOT NULL,
                mood TEXT NOT NULL CHECK(mood IN ('great', 'good', 'okay', 'tired')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        connection.execute(f"INSERT INTO entries_optional_duration ({COLUMN_SQL}) SELECT {COLUMN_SQL} FROM entries")
        connection.execute("DROP TABLE entries")
        connection.execute("ALTER TABLE entries_optional_duration RENAME TO entries")
        for sql in schema_objects:
            connection.execute(sql)

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.db_path, timeout=5, uri=self._uri)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def close(self):
        """Release the optional in-memory database keeper; file stores need no cleanup."""
        if self._keeper is not None:
            self._keeper.close()
            self._keeper = None

    def create_entry(self, data):
        _object(data, {*EDITABLE, "id"})
        entry = _fields(data)
        entry["id"] = _identifier(data["id"]) if "id" in data else str(uuid.uuid4())
        entry["created_at"] = entry["updated_at"] = _now()
        try:
            with self._connection() as connection:
                connection.execute(
                    f"INSERT INTO entries ({COLUMN_SQL}) VALUES ({', '.join('?' for _ in COLUMNS)})",
                    tuple(entry[column] for column in COLUMNS),
                )
        except sqlite3.IntegrityError:
            raise ValueError("记录编号已存在，请更新已有记录或使用新的编号。") from None
        return {column: entry[column] for column in COLUMNS}

    def get_entry(self, id):
        id = _identifier(id)
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM entries WHERE id = ?", (id,)).fetchone()
        if row is None:
            raise KeyError("没有找到这篇学习日志。")
        return dict(row)

    def update_entry(self, id, patch):
        id = _identifier(id)
        _object(patch, set(EDITABLE))
        with self._connection() as connection:
            # Lock before reading so concurrent partial updates preserve each other's fields.
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM entries WHERE id = ?", (id,)).fetchone()
            if row is None:
                raise KeyError("没有找到这篇学习日志。")
            previous = dict(row)
            if not patch:
                return previous
            entry = _fields({**previous, **patch})
            entry.update(id=id, created_at=previous["created_at"], updated_at=max(_now(), previous["updated_at"]))
            names = (*EDITABLE, "updated_at")
            assignments = ", ".join('"' + name + '" = ?' for name in names)
            connection.execute(f"UPDATE entries SET {assignments} WHERE id = ?", (*[entry[name] for name in names], id))
            return {column: entry[column] for column in COLUMNS}

    @staticmethod
    def _range(date_from=None, date_to=None):
        conditions, values = [], []
        if date_from is not None:
            conditions.append("date >= ?")
            values.append(_date(date_from, "起始日期"))
        if date_to is not None:
            conditions.append("date <= ?")
            values.append(_date(date_to, "结束日期"))
        if date_from is not None and date_to is not None and date_from > date_to:
            raise ValueError("起始日期不能晚于结束日期。")
        return conditions, values

    def entry_filter(self, date_from=None, date_to=None, subject=None, query=None):
        conditions, values = self._range(date_from, date_to)
        if subject is not None:
            conditions.append("subject = ?")
            values.append(_text(subject, "科目", 60, required=True, trim=True))
        if query is not None:
            query = _text(query, "搜索词", 1000, trim=True)
            if query:
                escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                fields = ("title", "subject", "content", "reflection", "next")
                conditions.append("(" + " OR ".join('"' + field + '" LIKE ? ESCAPE \'\\\'' for field in fields) + ")")
                values.extend([f"%{escaped}%"] * len(fields))
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        return where, values

    def list_entries(self, date_from=None, date_to=None, subject=None, query=None, limit=100):
        if type(limit) is not int or not 1 <= limit <= 10000:
            raise ValueError("查询数量须为 1–10000 之间的整数。")
        where, values = self.entry_filter(date_from, date_to, subject, query)
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT * FROM entries{where} ORDER BY date DESC, created_at DESC, id DESC LIMIT ?", (*values, limit)
            ).fetchall()
        return [dict(row) for row in rows]

    def summary(self, date_from=None, date_to=None):
        conditions, values = self._range(date_from, date_to)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        with self._connection() as connection:
            # One SELECT gives every aggregation the same database snapshot.
            rows = connection.execute(f"SELECT date, subject FROM entries{where}", values).fetchall()
        subjects, days = {}, {}
        for row in rows:
            for mapping, key, label in ((subjects, row["subject"], "subject"), (days, row["date"], "date")):
                item = mapping.setdefault(key, {label: key, "entries": 0})
                item["entries"] += 1
        return {
            "total_entries": len(rows),
            "study_days": len(days),
            "subjects": sorted(subjects.values(), key=lambda item: (-item["entries"], item["subject"])),
            "days": sorted(days.values(), key=lambda item: item["date"]),
        }

    def export(self):
        with self._connection() as connection:
            connection.execute("BEGIN")
            rows = connection.execute("SELECT * FROM entries ORDER BY date DESC, created_at DESC, id DESC").fetchall()
            assets, documents = export_resources(connection)
            future = [dict(row) for row in connection.execute('SELECT * FROM future_learning ORDER BY id')]
        result = {"version": 2 if assets or documents else 1, "entries": [dict(row) for row in rows]}
        if assets or documents:
            result.update(assets=assets, documents=documents)
        if future:
            result.update(version=3, future_learning=future)
        return result

    def import_entries(self, payload):
        if not isinstance(payload, dict) or type(payload.get("version")) is not int or payload["version"] not in (1, 2, 3):
            raise ValueError("请选择版本 1、2 或 3 的学习日志备份。")
        if not isinstance(payload.get("entries"), list):
            raise ValueError("备份中的记录列表格式不正确。")
        entries, seen = [], set()
        for index, raw in enumerate(payload["entries"], start=1):
            try:
                _object(raw, set(COLUMNS))
                entry = _fields(raw)
                if any(field not in raw for field in ("id", "created_at", "updated_at")):
                    raise ValueError("备份记录缺少编号或保存时间。")
                entry["id"] = _identifier(raw["id"])
                entry["created_at"] = _timestamp(raw["created_at"], "创建时间")
                entry["updated_at"] = _timestamp(raw["updated_at"], "更新时间")
                if entry["updated_at"] < entry["created_at"]:
                    raise ValueError("更新时间不能早于创建时间。")
                if entry["id"] in seen:
                    raise ValueError("同一份备份中存在重复的记录编号。")
            except ValueError as error:
                raise ValueError(f"第 {index} 条记录：{error}") from None
            seen.add(entry["id"])
            entries.append(entry)
        assets, documents = validate_backup(payload)
        future = validate_future_backup(payload)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = {row[0] for row in connection.execute("SELECT id FROM entries")}
            updated = sum(entry["id"] in existing for entry in entries)
            assignments = ", ".join('"' + column + '" = excluded."' + column + '"' for column in COLUMNS if column != "id")
            sql = f"INSERT INTO entries ({COLUMN_SQL}) VALUES ({', '.join('?' for _ in COLUMNS)}) ON CONFLICT(id) DO UPDATE SET {assignments}"
            connection.executemany(sql, [tuple(entry[column] for column in COLUMNS) for entry in entries])
            import_resources(connection, assets, documents)
            import_future(connection, future)
            total = connection.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
        result = {"added": len(entries) - updated, "updated": updated, "total": total}
        if payload["version"] == 2 or assets or documents:
            result.update(assets=len(assets), documents=len(documents))
        if payload['version'] == 3:
            result['future_learning'] = len(future)
        return result

    def delete_entry(self, id):
        return self.trash_resource("entry", _identifier(id))
