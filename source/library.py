"""Local image and Markdown storage, sharing the journal's transaction boundary."""
from __future__ import annotations

import base64
import binascii
import hashlib
import re
import struct
import uuid
import zlib


MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_DOCUMENT_BYTES = 2 * 1024 * 1024


def filename(value, markdown=False):
    if not isinstance(value, str) or not value.strip() or len(value) > 180:
        raise ValueError("文件名须为 1–180 个字符。")
    value = value.strip()
    if re.search(r'[\x00-\x1f\x7f/\\:<>"|?*]', value) or value in (".", ".."):
        raise ValueError("文件名不能包含路径或特殊字符。")
    if markdown and not value.lower().endswith((".md", ".markdown")):
        raise ValueError("请选择 .md 或 .markdown 文件。")
    return value


def document_content(value):
    if not isinstance(value, str):
        raise ValueError("Markdown 内容须为 UTF-8 文本。")
    try:
        encoded = value.encode("utf-8")
    except UnicodeError:
        raise ValueError("Markdown 内容须为有效的 UTF-8 文本。") from None
    if b"\0" in encoded or len(encoded) > MAX_DOCUMENT_BYTES:
        raise ValueError("Markdown 文件不能包含空字符，且不能超过 2 MiB。")
    return value, len(encoded)


def resource_id(value, asset=False):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}" if asset else r"[a-f0-9]{32}", value):
        raise ValueError("文件编号格式不正确。")
    return value


def image_mime(data):
    """Check raster structure, never trusting an extension or supplied MIME type."""
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError("图片不能为空，且不能超过 8 MiB。")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        position, has_header, has_pixels = 8, False, False
        while position + 12 <= len(data):
            length = int.from_bytes(data[position:position + 4], "big")
            kind = data[position + 4:position + 8]
            end = position + 12 + length
            if end > len(data):
                break
            payload = data[position + 8:end - 4]
            checksum = int.from_bytes(data[end - 4:end], "big")
            if zlib.crc32(kind + payload) & 0xffffffff != checksum:
                break
            if not has_header:
                if kind != b"IHDR" or length != 13 or not all(struct.unpack(">II", payload[:8])):
                    break
                has_header = True
            has_pixels = has_pixels or (kind == b"IDAT" and bool(length))
            if kind == b"IEND":
                if length == 0 and end == len(data) and has_pixels:
                    return "image/png"
                break
            position = end
    elif data[:6] in (b"GIF87a", b"GIF89a") and len(data) >= 14 and data[-1:] == b";":
        if all(struct.unpack("<HH", data[6:10])) and b"," in data[13:-1]:
            return "image/gif"
    elif data.startswith(b"\xff\xd8") and data.endswith(b"\xff\xd9"):
        position, frame = 2, False
        while position + 4 <= len(data):
            if data[position] != 255:
                break
            while position < len(data) and data[position] == 255:
                position += 1
            if position + 3 > len(data):
                break
            marker = data[position]
            position += 1
            length = int.from_bytes(data[position:position + 2], "big")
            if length < 2 or position + length > len(data):
                break
            if marker in (0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf):
                frame = length >= 8 and all(struct.unpack(">HH", data[position + 3:position + 7]))
            if marker == 0xda:
                if frame and position + length < len(data) - 2:
                    return "image/jpeg"
                break
            position += length
    elif (len(data) >= 26 and data.startswith(b"RIFF") and data[8:12] == b"WEBP"
          and int.from_bytes(data[4:8], "little") + 8 == len(data)):
        position, has_pixels = 12, False
        while position + 8 <= len(data):
            kind = data[position:position + 4]
            length = int.from_bytes(data[position + 4:position + 8], "little")
            if position + 8 + length > len(data):
                break
            payload = data[position + 8:position + 8 + length]
            has_pixels = has_pixels or (kind == b"VP8 " and len(payload) >= 10 and payload[3:6] == b"\x9d\x01\x2a") or (kind == b"VP8L" and len(payload) >= 5 and payload[0] == 0x2f) or (kind == b"ANMF" and len(payload) > 24)
            position += 8 + length + (length % 2)
        if position == len(data) and has_pixels:
            return "image/webp"
    raise ValueError("无法识别这张图片；请使用完整的 PNG、JPEG、GIF 或 WebP 图片。")


def decode_image(value):
    if not isinstance(value, str) or len(value) > ((MAX_IMAGE_BYTES + 2) // 3) * 4:
        raise ValueError("图片内容须为 Base64，且原文件不能超过 8 MiB。")
    try:
        data = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError("图片的 Base64 内容无效。") from None
    return data, image_mime(data)


def create_tables(connection):
    connection.execute("""CREATE TABLE IF NOT EXISTS assets (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, mime TEXT NOT NULL,
        data BLOB NOT NULL, created_at TEXT NOT NULL)""")
    connection.execute("""CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, content TEXT NOT NULL,
        size INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")


def asset_metadata(row):
    return {"id": row["id"], "name": row["name"], "mime": row["mime"],
            "size": len(row["data"]), "url": "/api/assets/" + row["id"]}


class LibraryMixin:
    def list_assets(self):
        with self._connection() as connection:
            rows = connection.execute('SELECT id, name, mime, length(data) AS size FROM assets ORDER BY created_at, id').fetchall()
        return [dict(row) for row in rows]

    def create_asset(self, raw):
        from store import _now, _object
        _object(raw, {"name", "data_base64"})
        name = filename(raw.get("name"))
        data, mime = decode_image(raw.get("data_base64"))
        identity = hashlib.sha256(data).hexdigest()
        with self._connection() as connection:
            connection.execute("INSERT OR IGNORE INTO assets VALUES (?, ?, ?, ?, ?)",
                               (identity, name, mime, data, _now()))
            row = connection.execute("SELECT * FROM assets WHERE id = ?", (identity,)).fetchone()
        return asset_metadata(row)

    def get_asset(self, identity):
        identity = resource_id(identity, asset=True)
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM assets WHERE id = ?", (identity,)).fetchone()
        if row is None:
            raise KeyError("图片不存在。")
        return dict(row)

    def list_documents(self, query=None):
        from store import _text
        values, where = [], ""
        if query is not None:
            query = _text(query, "搜索词", 1000, trim=True)
            if query:
                escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                values = ["%" + escaped + "%"] * 2
                where = " WHERE name LIKE ? ESCAPE '\\' OR content LIKE ? ESCAPE '\\'"
        with self._connection() as connection:
            rows = connection.execute("SELECT id, name, size, created_at, updated_at FROM documents" + where +
                                      " ORDER BY updated_at DESC, id DESC", values).fetchall()
        return [dict(row) for row in rows]

    def create_document(self, raw):
        from store import _now, _object
        _object(raw, {"name", "content"})
        name = filename(raw.get("name"), markdown=True)
        content, size = document_content(raw.get("content"))
        identity, now = uuid.uuid4().hex, _now()
        with self._connection() as connection:
            connection.execute("INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?)",
                               (identity, name, content, size, now, now))
        return {"id": identity, "name": name, "content": content, "size": size, "created_at": now, "updated_at": now}

    def get_document(self, identity):
        identity = resource_id(identity)
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM documents WHERE id = ?", (identity,)).fetchone()
        if row is None:
            raise KeyError("Markdown 文件不存在。")
        return dict(row)

    def update_document(self, identity, patch):
        from store import _now, _object
        identity = resource_id(identity)
        _object(patch, {"name", "content"})
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM documents WHERE id = ?", (identity,)).fetchone()
            if row is None:
                raise KeyError("Markdown 文件不存在。")
            if not patch:
                return dict(row)
            name = filename(patch.get("name", row["name"]), markdown=True)
            content, size = document_content(patch.get("content", row["content"]))
            now = max(_now(), row["updated_at"])
            connection.execute("UPDATE documents SET name = ?, content = ?, size = ?, updated_at = ? WHERE id = ?",
                               (name, content, size, now, identity))
        return {"id": identity, "name": name, "content": content, "size": size, "created_at": row["created_at"], "updated_at": now}

    def delete_document(self, identity):
        identity = resource_id(identity)
        with self._connection() as connection:
            return connection.execute("DELETE FROM documents WHERE id = ?", (identity,)).rowcount > 0


def export_resources(connection):
    assets = []
    for row in connection.execute("SELECT * FROM assets ORDER BY id"):
        assets.append({"id": row["id"], "name": row["name"], "mime": row["mime"],
                       "data_base64": base64.b64encode(row["data"]).decode("ascii"), "created_at": row["created_at"]})
    return assets, [dict(row) for row in connection.execute("SELECT * FROM documents ORDER BY id")]


def validate_backup(payload):
    from store import _object, _timestamp
    assets, documents = payload.get("assets", []), payload.get("documents", [])
    if not isinstance(assets, list) or not isinstance(documents, list):
        raise ValueError("备份中的图片和 Markdown 文件须为列表。")
    validated_assets, validated_documents, seen = [], [], set()
    for raw in assets:
        _object(raw, {"id", "name", "mime", "data_base64", "created_at"})
        identity = resource_id(raw.get("id"), asset=True)
        data, mime = decode_image(raw.get("data_base64"))
        if raw.get("mime") != mime or hashlib.sha256(data).hexdigest() != identity or identity in seen:
            raise ValueError("备份中的图片编号、格式或内容不一致，或存在重复图片。")
        seen.add(identity)
        validated_assets.append((identity, filename(raw.get("name")), mime, data, _timestamp(raw.get("created_at"), "图片创建时间")))
    seen.clear()
    for raw in documents:
        _object(raw, {"id", "name", "content", "size", "created_at", "updated_at"})
        identity = resource_id(raw.get("id"))
        content, size = document_content(raw.get("content"))
        created, updated = _timestamp(raw.get("created_at"), "文件创建时间"), _timestamp(raw.get("updated_at"), "文件更新时间")
        if raw.get("size") != size or updated < created or identity in seen:
            raise ValueError("备份中的 Markdown 文件大小、时间或编号不正确。")
        seen.add(identity)
        validated_documents.append((identity, filename(raw.get("name"), markdown=True), content, size, created, updated))
    return validated_assets, validated_documents


def import_resources(connection, assets, documents):
    # Images are content-addressed and immutable; importing cannot redirect an old log's image.
    connection.executemany("INSERT OR IGNORE INTO assets VALUES (?, ?, ?, ?, ?)", assets)
    connection.executemany("""INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET name=excluded.name, content=excluded.content,
        size=excluded.size, created_at=excluded.created_at, updated_at=excluded.updated_at""", documents)
