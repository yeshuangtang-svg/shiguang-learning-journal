"""Search, relationships, recoverable deletion and durable editing state."""
import json
import re
import uuid
from urllib.parse import quote

TABLES = {'entry': 'entries', 'document': 'documents', 'future': 'future_learning'}

def create_workspace_tables(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS resource_links (id TEXT PRIMARY KEY, a_kind TEXT NOT NULL, a_id TEXT NOT NULL, b_kind TEXT NOT NULL, b_id TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(a_kind,a_id,b_kind,b_id))')
    conn.execute('CREATE TABLE IF NOT EXISTS trash (id TEXT PRIMARY KEY, kind TEXT NOT NULL, resource_id TEXT NOT NULL, title TEXT NOT NULL, payload TEXT NOT NULL, deleted_at TEXT NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS drafts (key TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS reading_positions (id TEXT PRIMARY KEY, position TEXT NOT NULL)')

def kind_table(kind):
    if kind not in TABLES:
        raise ValueError('内容类型须为 entry、document 或 future。')
    return TABLES[kind]

def source_url(kind, identity):
    kind_table(kind)
    return '#resource/' + kind + '/' + quote(identity, safe='')

def snippet(content, query='', length=220):
    plain = re.sub(r'!\[[^\]]*\]\([^)]*\)', '[图片]', content or '')
    plain = re.sub(r'\s+', ' ', plain).strip()
    terms = query.strip().split()
    hits = [plain.lower().find(term.lower()) for term in terms]
    hit = min((n for n in hits if n >= 0), default=0)
    start = max(0, hit - 55)
    return ('…' if start else '') + plain[start:start+length] + ('…' if len(plain) > start+length else '')

class WorkspaceMixin:
    def resource(self, kind, identity):
        kind_table(kind)
        return {'entry': self.get_entry, 'document': self.get_document, 'future': self.get_future}[kind](identity)

    def search_all(self, query='', kind=None, limit=20, offset=0):
        from store import _text
        query = _text(query, '搜索词', 300, trim=True)
        if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or not 0 <= offset <= 1000000:
            raise ValueError('分页参数无效。')
        kinds = [kind] if kind else list(TABLES)
        parts, values = [], []
        for k in kinds:
            table = kind_table(k)
            title = 'name' if k == 'document' else 'title'
            subject = "''" if k == 'document' else 'subject'
            body = "content || ' ' || reflection || ' ' || \"next\"" if k == 'entry' else ('content || \' \' || url' if k == 'future' else 'content')
            clauses=[]
            for term in query.split()[:12]:
                escaped=term.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
                clauses.append(f"({title} || ' ' || {subject} || ' ' || {body}) LIKE ? ESCAPE '\\'")
                values.append('%'+escaped+'%')
            where=' WHERE '+' AND '.join(clauses) if clauses else ''
            parts.append(f"SELECT '{k}' AS kind, id, {title} AS title, {subject} AS subject, {body} AS content, updated_at FROM {table}{where}")
        sql=' UNION ALL '.join(parts)
        with self._connection() as conn:
            conn.execute('BEGIN')
            total=conn.execute('SELECT COUNT(*) FROM ('+sql+')',values).fetchone()[0]
            rows=conn.execute('SELECT * FROM ('+sql+') ORDER BY updated_at DESC,kind,id LIMIT ? OFFSET ?',(*values,limit,offset)).fetchall()
        items=[]
        for row in rows:
            item=dict(row); item['snippet']=snippet(item.pop('content'), query)
            item['url']=source_url(item['kind'],item['id']); items.append(item)
        return {'items':items,'total':total,'limit':limit,'offset':offset,'has_more':offset+len(items)<total}

    def read_source(self, kind, identity, query='', offset=0, limit=12000):
        if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=16000:
            raise ValueError('原文分页参数无效。')
        row=self.resource(kind,identity); content=row['content']
        if kind=='entry': content+='\n'+row['reflection']+'\n'+row['next']
        if kind=='future' and row['url']: content+='\n资料链接：'+row['url']
        if query and offset==0:
            from store import _text
            query=_text(query,'搜索词',300,trim=True)
            hit=content.casefold().find(query.casefold())
            if hit>=0: offset=max(0,content.rfind('\n#',0,hit))
        text=content[offset:offset+limit]
        return {'kind':kind,'id':identity,'title':row.get('title',row.get('name')),'content':text,
                'url':source_url(kind,identity),'offset':offset,'next_offset':offset+len(text) if offset+len(text)<len(content) else None,'total_characters':len(content)}

    def entries_page(self, **args):
        offset=args.pop('offset',0); limit=args.pop('limit',20)
        if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=100:
            raise ValueError('分页参数无效。')
        # Shared SQL predicate keeps count and page consistent, and sends excerpts only.
        where,values=self.entry_filter(**args)
        with self._connection() as conn:
            conn.execute('BEGIN')
            total=conn.execute('SELECT COUNT(*) FROM entries'+where,values).fetchone()[0]
            rows=conn.execute('SELECT id,date,title,subject,mood,created_at,updated_at,substr(content,1,360) AS content FROM entries'+where+' ORDER BY date DESC,created_at DESC,id DESC LIMIT ? OFFSET ?',(*values,limit,offset)).fetchall()
            subjects=[r[0] for r in conn.execute('SELECT DISTINCT subject FROM entries ORDER BY subject')]
        return {'entries':[dict(r) for r in rows],'total':total,'has_more':offset+len(rows)<total,'subjects':subjects,'offset':offset,'limit':limit}

    def add_link(self, raw):
        from store import _now, _object
        _object(raw, {'a_kind','a_id','b_kind','b_id'})
        a=(raw.get('a_kind'),raw.get('a_id')); b=(raw.get('b_kind'),raw.get('b_id'))
        for k,i in (a,b):
            kind_table(k)
            if not isinstance(i,str) or not i: raise ValueError('请提供关联内容编号。')
        if a==b: raise ValueError('不能关联内容本身。')
        a,b=sorted((a,b))
        with self._connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            for k,i in (a,b):
                if conn.execute('SELECT id FROM '+kind_table(k)+' WHERE id=?',(i,)).fetchone() is None: raise KeyError('关联内容不存在。')
            conn.execute('INSERT OR IGNORE INTO resource_links VALUES (?,?,?,?,?,?)',(uuid.uuid4().hex,*a,*b,_now()))
            return dict(conn.execute('SELECT * FROM resource_links WHERE a_kind=? AND a_id=? AND b_kind=? AND b_id=?',(*a,*b)).fetchone())

    def links_for(self, kind, identity):
        self.resource(kind,identity)
        with self._connection() as conn:
            links=conn.execute('SELECT * FROM resource_links WHERE (a_kind=? AND a_id=?) OR (b_kind=? AND b_id=?) ORDER BY created_at',(kind,identity,kind,identity)).fetchall()
            result=[]
            for link in links:
                other=(link['b_kind'],link['b_id']) if (link['a_kind'],link['a_id'])==(kind,identity) else (link['a_kind'],link['a_id'])
                row=conn.execute('SELECT * FROM '+kind_table(other[0])+' WHERE id=?',(other[1],)).fetchone()
                if row:
                    row=dict(row); result.append({'link_id':link['id'],'kind':other[0],'id':other[1],'title':row.get('title',row.get('name')),'snippet':snippet(row['content']),'url':source_url(*other)})
            return result

    def remove_link(self, identity):
        with self._connection() as conn:
            return conn.execute('DELETE FROM resource_links WHERE id=?',(identity,)).rowcount>0

    def trash_resource(self, kind, identity):
        from store import _now
        table=kind_table(kind)
        with self._connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row=conn.execute('SELECT * FROM '+table+' WHERE id=?',(identity,)).fetchone()
            if not row: return False
            row=dict(row)
            conn.execute('INSERT INTO trash VALUES (?,?,?,?,?,?)',(uuid.uuid4().hex,kind,identity,row.get('title',row.get('name')),json.dumps(row,ensure_ascii=False),_now()))
            conn.execute('DELETE FROM '+table+' WHERE id=?',(identity,))
            # Link rows and all associated files remain available for restoration.
            return True

    def list_trash(self):
        with self._connection() as conn:
            return [dict(r) for r in conn.execute('SELECT id,kind,resource_id,title,deleted_at FROM trash ORDER BY deleted_at DESC')]

    def restore_trash(self, identity):
        with self._connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row=conn.execute('SELECT * FROM trash WHERE id=?',(identity,)).fetchone()
            if not row: raise KeyError('回收站记录不存在。')
            table=kind_table(row['kind']); item=json.loads(row['payload'])
            if conn.execute('SELECT id FROM '+table+' WHERE id=?',(row['resource_id'],)).fetchone(): raise ValueError('同编号内容已存在，未覆盖当前内容。')
            columns=[r[1] for r in conn.execute('PRAGMA table_info('+table+')')]
            if set(item)!=set(columns): raise ValueError('回收站记录格式不兼容。')
            conn.execute('INSERT INTO '+table+' ('+','.join('"'+c+'"' for c in columns)+') VALUES ('+','.join('?' for _ in columns)+')',[item[c] for c in columns])
            conn.execute('DELETE FROM trash WHERE id=?',(identity,))
        return {'restored':True,'kind':row['kind'],'id':row['resource_id'],'url':source_url(row['kind'],row['resource_id'])}

    def save_draft(self,key,payload):
        from store import _now
        if not isinstance(key,str) or not re.fullmatch(r'(entry|document|future|chat):[A-Za-z0-9_-]{1,160}',key): raise ValueError('草稿编号无效。')
        if not isinstance(payload,dict): raise ValueError('草稿须为对象。')
        encoded=json.dumps(payload,ensure_ascii=False)
        if len(encoded.encode('utf-8'))>3*1024*1024: raise ValueError('草稿超过 3 MiB。')
        stamp=_now()
        with self._connection() as conn:
            conn.execute('INSERT INTO drafts VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at',(key,encoded,stamp))
        return {'key':key,'updated_at':stamp}

    def list_drafts(self):
        with self._connection() as conn:
            return [{'key':r['key'],'payload':json.loads(r['payload']),'updated_at':r['updated_at']} for r in conn.execute('SELECT * FROM drafts ORDER BY updated_at DESC')]

    def delete_draft(self,key):
        with self._connection() as conn: conn.execute('DELETE FROM drafts WHERE key=?',(key,))
        return {'deleted':True}

    def reading_position(self, identity, position=None):
        self.get_document(identity)
        with self._connection() as conn:
            if position is not None:
                if not isinstance(position,dict) or set(position)-{'heading','ratio'} or type(position.get('ratio')) not in (int,float) or not 0<=position['ratio']<=1 or type(position.get('heading','')) is not str or len(position.get('heading',''))>200:
                    raise ValueError('阅读位置无效。')
                conn.execute('INSERT INTO reading_positions VALUES (?,?) ON CONFLICT(id) DO UPDATE SET position=excluded.position',(identity,json.dumps(position)))
            row=conn.execute('SELECT position FROM reading_positions WHERE id=?',(identity,)).fetchone()
            return json.loads(row[0]) if row else {'heading':'','ratio':0}
    def create_linked_note(self, origin_kind, origin_id, kind, data):
        from store import _fields, _now, COLUMNS
        from library import filename, document_content
        if kind not in ('entry','document'): raise ValueError('笔记类型无效。')
        kind_table(origin_kind)
        if kind=='entry':
            row=_fields(data); row.update(id=str(uuid.uuid4()),created_at=_now()); row['updated_at']=row['created_at']; columns=COLUMNS
        else:
            content,size=document_content(data.get('content',''))
            row={'id':uuid.uuid4().hex,'name':filename(data.get('name',''),markdown=True),'content':content,'size':size,'created_at':_now()}; row['updated_at']=row['created_at']; columns=tuple(row)
        a,b=sorted(((origin_kind,origin_id),(kind,row['id'])))
        with self._connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            if not conn.execute('SELECT id FROM '+kind_table(origin_kind)+' WHERE id=?',(origin_id,)).fetchone(): raise KeyError('原收藏或笔记已不存在。')
            conn.execute('INSERT INTO '+kind_table(kind)+' ('+','.join('"'+c+'"' for c in columns)+') VALUES ('+','.join('?' for _ in columns)+')',[row[c] for c in columns])
            conn.execute('INSERT INTO resource_links VALUES (?,?,?,?,?,?)',(uuid.uuid4().hex,*a,*b,_now()))
        return row
