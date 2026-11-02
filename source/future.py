"""A separate, portable inbox for knowledge to learn later."""
import uuid
from urllib.parse import urlsplit

FIELDS = ('title', 'subject', 'content', 'url', 'status')
COLUMNS = ('id', *FIELDS, 'created_at', 'updated_at')
STATUSES = ('pending', 'learning', 'done')


def create_table(connection):
    connection.execute("""CREATE TABLE IF NOT EXISTS future_learning (
        id TEXT PRIMARY KEY, title TEXT NOT NULL, subject TEXT NOT NULL,
        content TEXT NOT NULL, url TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('pending','learning','done')),
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")


def fields(raw):
    from store import _text
    result = {key: _text(raw.get(key, ''), label, limit, required=key == 'title', trim=key != 'content')
              for key, label, limit in [('title', '知识点标题', 120), ('subject', '主题', 60),
                                        ('content', '备注', 20000), ('url', '资料链接', 4000)]}
    if result['url']:
        url = urlsplit(result['url'])
        if url.scheme not in ('http', 'https') or not url.hostname or any(c.isspace() for c in result['url']):
            raise ValueError('资料链接须为完整的 http:// 或 https:// 地址。')
    result['status'] = raw.get('status', 'pending')
    if result['status'] not in STATUSES:
        raise ValueError('学习状态须为 pending、learning 或 done。')
    return result


class FutureMixin:
    def list_future(self, query=None, status=None):
        from store import _text
        clauses, values = [], []
        if status:
            if status not in STATUSES:
                raise ValueError('学习状态不正确。')
            clauses.append('status = ?')
            values.append(status)
        if query:
            query = _text(query, '搜索词', 1000, trim=True)
            escaped = query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            clauses.append('(' + ' OR '.join(f"{key} LIKE ? ESCAPE '\\'" for key in ('title', 'subject', 'content', 'url')) + ')')
            values.extend(['%' + escaped + '%'] * 4)
        with self._connection() as connection:
            rows = connection.execute('SELECT * FROM future_learning' + (' WHERE ' + ' AND '.join(clauses) if clauses else '') +
                                      ' ORDER BY updated_at DESC, id DESC', values).fetchall()
        return [dict(row) for row in rows]

    def create_future(self, raw):
        from store import _now, _object
        _object(raw, set(FIELDS))
        result = fields(raw)
        result.update(id=uuid.uuid4().hex, created_at=_now())
        result['updated_at'] = result['created_at']
        with self._connection() as connection:
            connection.execute('INSERT INTO future_learning VALUES (?,?,?,?,?,?,?,?)', tuple(result[key] for key in COLUMNS))
        return result

    def get_future(self, identity):
        from library import resource_id
        with self._connection() as connection:
            row = connection.execute('SELECT * FROM future_learning WHERE id = ?', (resource_id(identity),)).fetchone()
        if row is None:
            raise KeyError('这条未来学习知识不存在。')
        return dict(row)

    def update_future(self, identity, patch):
        from library import resource_id
        from store import _now, _object
        _object(patch, set(FIELDS))
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT * FROM future_learning WHERE id = ?', (resource_id(identity),)).fetchone()
            if row is None:
                raise KeyError('这条未来学习知识不存在。')
            result = dict(row)
            result.update(fields({**result, **patch}))
            result['updated_at'] = max(_now(), result['updated_at'])
            connection.execute('UPDATE future_learning SET title=?,subject=?,content=?,url=?,status=?,updated_at=? WHERE id=?',
                               tuple(result[key] for key in (*FIELDS, 'updated_at', 'id')))
        return result

    def delete_future(self, identity):
        from library import resource_id
        return self.trash_resource('future', resource_id(identity))


def validate_future_backup(payload):
    from library import resource_id
    from store import _object, _timestamp
    items = payload.get('future_learning', [])
    if not isinstance(items, list):
        raise ValueError('未来学习知识须为列表。')
    if items and payload['version'] != 3:
        raise ValueError('含未来学习知识的备份须使用版本 3。')
    results, seen = [], set()
    for raw in items:
        _object(raw, set(COLUMNS))
        item = fields(raw)
        item['id'] = resource_id(raw.get('id'))
        item['created_at'] = _timestamp(raw.get('created_at'), '收藏时间')
        item['updated_at'] = _timestamp(raw.get('updated_at'), '更新时间')
        if item['id'] in seen or item['updated_at'] < item['created_at']:
            raise ValueError('未来学习知识的编号重复或时间不正确。')
        seen.add(item['id'])
        results.append(tuple(item[key] for key in COLUMNS))
    return results


def import_future(connection, items):
    connection.executemany('INSERT INTO future_learning VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET ' +
                           ','.join(f'{key}=excluded.{key}' for key in COLUMNS if key != 'id'), items)
