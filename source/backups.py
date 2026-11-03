"""Portable, checksummed learning-data backups with preview and rollback."""
from contextlib import closing
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone

MAX_ARCHIVE=512*1024*1024
MAX_EXPANDED=2*1024*1024*1024
TABLES={'entries','assets','documents','future_learning','resource_links','trash','drafts','reading_positions','agent_sessions','agent_requests'}

def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def snapshot(source,dest):
    with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(dest)) as dst: src.backup(dst)

class Backups:
    def __init__(self, app):
        self.app=app; self.data=Path(app.data_dir).resolve(); self.root=self.data/'backups'
        self.previews={}

    def archive_path(self, identity):
        if not isinstance(identity,str) or len(identity)!=32 or any(c not in '0123456789abcdef' for c in identity): raise ValueError('备份编号无效。')
        path=self.root/(identity+'.zip')
        if path.resolve().parent!=self.root.resolve() or self.root.resolve()!=self.root: raise ValueError('备份路径无效。')
        return path

    def create(self, include_config=False):
        if type(include_config) is not bool: raise ValueError('配置备份选项无效。')
        self.root.mkdir(parents=True,exist_ok=True)
        identity=uuid.uuid4().hex; target=self.archive_path(identity)
        stamp=datetime.now(timezone.utc).isoformat()
        with tempfile.TemporaryDirectory(dir=self.root) as temporary:
            db=Path(temporary)/'study.sqlite3'; snapshot(self.app.db_path,db)
            records={'study.sqlite3':db}
            for folder in ('documents','images'):
                directory=self.data/folder
                if directory.exists():
                    for path in directory.rglob('*'):
                        if path.is_symlink() or not path.resolve().is_relative_to(self.data) or path.name.endswith('.tmp'): continue
                        if path.is_file(): records[path.relative_to(self.data).as_posix()]=path
            if include_config and (self.data/'config.json').is_file(): records['config.json']=self.data/'config.json'
            manifest={'format':'shiguang-full-backup','version':1,'app_version':'1.6.0','created_at':stamp,'includes_config':include_config,'files':{}}
            total=0
            with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
                for name,path in records.items():
                    data=path.read_bytes(); total+=len(data)
                    if total>MAX_EXPANDED: raise ValueError('资料超过 2 GiB，请使用文件夹备份。')
                    archive.writestr(name,data)
                    manifest['files'][name]={'size':len(data),'sha256':hashlib.sha256(data).hexdigest()}
                archive.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False))
        if target.stat().st_size>MAX_ARCHIVE: target.unlink(); raise ValueError('压缩备份超过 512 MiB，请使用文件夹备份。')
        meta={'id':identity,'created_at':stamp,'size':target.stat().st_size,'files':len(records),'includes_config':include_config}
        target.with_suffix('.json').write_text(json.dumps(meta),encoding='utf-8')
        return meta

    def list(self):
        if not self.root.exists(): return []
        results=[]
        for path in self.root.glob('*.json'):
            try:
                item=json.loads(path.read_text(encoding='utf-8'))
                if self.archive_path(item['id']).is_file(): results.append(item)
            except (ValueError,KeyError,OSError): pass
        return sorted(results,key=lambda x:x['created_at'],reverse=True)

    def preview(self, raw):
        if len(raw)>MAX_ARCHIVE: raise ValueError('备份超过 512 MiB。')
        self.root.mkdir(parents=True,exist_ok=True)
        token=uuid.uuid4().hex; folder=self.root/('restore-'+token); folder.mkdir()
        try:
            archive_path=folder/'input.zip'; archive_path.write_bytes(raw)
            with zipfile.ZipFile(archive_path) as archive:
                infos=archive.infolist(); names=[i.filename for i in infos]
                if len(names)>10000 or len(names)!=len(set(names)) or sum(i.file_size for i in infos)>MAX_EXPANDED:
                    raise ValueError('备份文件数量、大小或重复路径无效。')
                if 'manifest.json' not in names or archive.getinfo('manifest.json').file_size>4*1024*1024: raise ValueError('备份清单缺失或过大。')
                manifest=json.loads(archive.read('manifest.json'))
                if manifest.get('format')!='shiguang-full-backup' or manifest.get('version')!=1: raise ValueError('请选择拾光完整资料 ZIP 备份。')
                files=manifest.get('files')
                if not isinstance(files,dict) or set(names)!={'manifest.json',*files} or 'study.sqlite3' not in files: raise ValueError('备份清单不完整。')
                for name,info in files.items():
                    path=PurePosixPath(name)
                    if '\\' in name or ':' in name or path.is_absolute() or any(p in ('..','.') for p in path.parts) or not path.parts:
                        raise ValueError('备份包含无效路径。')
                    if name not in ('study.sqlite3','config.json') and path.parts[0] not in ('documents','images'): raise ValueError('备份包含不支持的文件。')
                    data=archive.read(name)
                    if len(data)!=info.get('size') or hashlib.sha256(data).hexdigest()!=info.get('sha256'): raise ValueError('备份校验失败。')
                    target=folder/'files'/name; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(data)
            db=folder/'files/study.sqlite3'
            with closing(sqlite3.connect(db)) as conn:
                conn.execute('PRAGMA trusted_schema=OFF')
                if conn.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise ValueError('数据库完整性检查失败。')
                tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if tables-TABLES or not {'entries','assets','documents','future_learning','resource_links','trash','drafts','reading_positions'}.issubset(tables) or conn.execute("SELECT count(*) FROM sqlite_master WHERE type IN ('trigger','view')").fetchone()[0]:
                    raise ValueError('数据库结构与当前版本不兼容。')
                with closing(sqlite3.connect(self.app.db_path)) as current:
                    for table in tables:
                        expected=[tuple(r[1:]) for r in current.execute('PRAGMA table_info('+table+')')]
                        actual=[tuple(r[1:]) for r in conn.execute('PRAGMA table_info('+table+')')]
                        if expected!=actual: raise ValueError('数据库字段与当前版本不兼容。')
                counts={t:conn.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in sorted(tables)}
            self.previews[token]={'folder':folder,'manifest':manifest,'counts':counts}
            # Uploaded previews are short lived; remove older ones to bound disk usage.
            for old in list(self.previews)[:-3]: self.discard(old)
            return {'token':token,'created_at':manifest['created_at'],'counts':counts,'files':len(files),'pdfs':sum(n.lower().endswith('.pdf') for n in files),'includes_config':'config.json' in files,
                    'effect':'恢复会替换当前库内内容及备份中同名文件。当前资料先自动备份；备份未包含的归档文件保留。模型配置仅在勾选时恢复。'}
        except Exception:
            shutil.rmtree(folder)
            raise

    def discard(self,token):
        item=self.previews.pop(token,None)
        if item: shutil.rmtree(item['folder'],ignore_errors=True)

    def restore(self,token, restore_config=False):
        if type(restore_config) is not bool: raise ValueError('配置恢复选项无效。')
        item=self.previews.get(token)
        if not item: raise ValueError('恢复预览已过期，请重新选择备份。')
        before=self.create(include_config=True)
        folder=item['folder']; undo=folder/'undo'; undo.mkdir(exist_ok=True)
        touched=[]
        try:
            for name in item['manifest']['files']:
                if name=='study.sqlite3' or (name=='config.json' and not restore_config): continue
                target=self.data/name
                if not target.resolve().is_relative_to(self.data) or target.is_symlink(): raise ValueError('现有资料路径无效。')
                existed=target.exists()
                if existed:
                    previous=undo/name; previous.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(target,previous)
                touched.append((name,existed))
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(folder/'files'/name,target)
            snapshot(folder/'files/study.sqlite3',self.app.db_path)
        except Exception:
            for name,existed in reversed(touched):
                if existed: shutil.copy2(undo/name,self.data/name)
                else: (self.data/name).unlink(missing_ok=True)
            raise
        self.discard(token)
        return {'restored':True,'safety_backup':before,'reload':True}
