"""Managed Markdown sources and companion PDFs; never open arbitrary paths."""
import base64
import binascii
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import uuid

from library import resource_id


class DocumentFiles:
    def __init__(self, data_dir, store):
        self.root = Path(data_dir).resolve() / 'documents'
        self.store = store
        self.lock = threading.RLock()

    def checked(self, path):
        # Reject symlinks/junctions that redirect a managed file outside the library.
        path = Path(path)
        if not path.resolve().is_relative_to(self.root) or self.root.resolve() != self.root:
            raise ValueError('文档资料路径不在本应用资料文件夹内。')
        return path

    def write(self, path, content):
        path = self.checked(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            previous = path.read_bytes()
            if previous == content:
                return
            # Retain old sources/PDFs, including external edits, before replacement.
            history = self.checked(path.parent / '历史版本' / (uuid.uuid4().hex + '-' + path.name))
            history.parent.mkdir(parents=True, exist_ok=True)
            history.write_bytes(previous)
        temporary = self.checked(path.with_name('.' + uuid.uuid4().hex + '.tmp'))
        try:
            temporary.write_bytes(content)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def paths(self, document):
        identity = resource_id(document['id'])
        # Windows device names and trailing dots/spaces must not become paths.
        stem = Path(document['name']).stem.rstrip(' .')[:100] or '文档'
        if re.match(r'^(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(?:\.|$)', stem, re.I):
            stem = '_' + stem
        folder = self.checked(self.root / identity)
        return folder, self.checked(folder / (stem + '.md')), self.checked(folder / (stem + '.pdf'))

    def source(self, document, folder):
        content = document['content']
        for identity in set(re.findall(r'/api/assets/([a-f0-9]{64})', content)):
            try:
                asset = self.store.get_asset(identity)
            except KeyError:
                continue
            suffix = {'image/png': '.png', 'image/jpeg': '.jpg', 'image/gif': '.gif', 'image/webp': '.webp'}[asset['mime']]
            relative = 'assets/' + identity + suffix
            self.write(folder / relative, asset['data'])
            content = content.replace('/api/assets/' + identity, relative)
        return content.encode('utf-8')

    def prepare(self, identity):
        with self.lock:
            document = self.store.get_document(identity)
            folder, md, pdf = self.paths(document)
            source = self.source(document, folder)
            self.write(md, source)
            digest = hashlib.sha256(source).hexdigest()
            manifest = self.checked(folder / '.pdf-source.json')
            try:
                saved = json.loads(manifest.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                saved = {}
            if not isinstance(saved, dict):
                saved = {}
            exists = pdf.is_file()
            verified = exists and saved.get('pdf') == pdf.name and saved.get('pdf_sha256') == hashlib.sha256(pdf.read_bytes()).hexdigest()
            return {'directory': str(folder), 'md_path': str(md), 'pdf_path': str(pdf),
                    'pdf_exists': exists, 'pdf_current': bool(verified and saved.get('source_sha256') == digest),
                    'source_sha256': digest}

    def sync_after_save(self, document):
        try:
            self.prepare(document['id'])
        except (OSError, ValueError, KeyError):
            return {**document, 'file_warning': '文档已保存，但源文件暂未同步。请检查资料文件夹写入权限后重新打开文档。'}
        return document

    def save_pdf(self, identity, payload):
        if set(payload) != {'data_base64', 'source_sha256'}:
            raise ValueError('请提供 PDF 的 data_base64 和对应源文件的 source_sha256。')
        encoded = payload['data_base64']
        if not isinstance(encoded, str) or len(encoded) > 12 * 1024 * 1024:
            raise ValueError('PDF 不能超过 8 MiB。')
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError('PDF 的 Base64 内容无效。') from None
        if len(data) > 8 * 1024 * 1024 or not data.startswith(b'%PDF-') or b'%%EOF' not in data[-1024:]:
            raise ValueError('请选择完整的 PDF 文件，且不超过 8 MiB。')
        with self.lock:
            info = self.prepare(identity)
            if payload['source_sha256'] != info['source_sha256']:
                raise ValueError('Markdown 源文件已更新，请使用最新源文件重新生成 PDF。')
            pdf = Path(info['pdf_path'])
            self.write(pdf, data)
            self.write(pdf.parent / '.pdf-source.json', json.dumps({
                'pdf': pdf.name, 'source_sha256': info['source_sha256'],
                'pdf_sha256': hashlib.sha256(data).hexdigest()
            }, ensure_ascii=False).encode('utf-8'))
            return self.prepare(identity)

    def open(self, identity, action, desktop=False):
        if not desktop or os.name != 'nt':
            raise ValueError('请在 Windows 桌面版拾光中打开本机文件。')
        with self.lock:
            info = self.prepare(identity)
            if action == 'open-pdf':
                if not info['pdf_exists']:
                    raise ValueError('这份文档还没有 PDF，请先制作并归档 PDF。')
                # Only a managed .pdf is passed to the system association.
                path = self.checked(info['pdf_path'])
                if not path.read_bytes().startswith(b'%PDF-'):
                    raise ValueError('这个文件不是有效的 PDF。')
                os.startfile(str(path))
            elif action == 'reveal-md':
                path = self.checked(info['md_path'])
                explorer = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'explorer.exe'
                subprocess.Popen([str(explorer), '/select,', str(path)])
            else:
                raise ValueError('不支持的文件操作。')
            return {'opened': True, 'path': str(path)}
    def history(self, identity):
        import datetime
        info=self.prepare(identity); folder=Path(info['directory']); current={info['md_path'],info['pdf_path']}
        items=[]
        for path in folder.rglob('*'):
            if path.is_file() and path.suffix.lower() in ('.md','.pdf') and str(path) not in current and path.resolve().is_relative_to(folder) and not path.is_symlink():
                relative=path.relative_to(folder).as_posix()
                items.append({'id':hashlib.sha256(relative.encode()).hexdigest(),'name':path.name,'type':path.suffix[1:],'size':path.stat().st_size,'modified':datetime.datetime.fromtimestamp(path.stat().st_mtime,datetime.timezone.utc).isoformat()})
        return sorted(items,key=lambda x:x['modified'],reverse=True)

    def history_content(self, identity, version):
        info=self.prepare(identity); folder=Path(info['directory'])
        if not re.fullmatch('[a-f0-9]{64}',version): raise ValueError('版本编号无效。')
        for item in self.history(identity):
            if item['id']==version:
                for path in folder.rglob('*'):
                    if path.is_file() and path.resolve().is_relative_to(folder) and hashlib.sha256(path.relative_to(folder).as_posix().encode()).hexdigest()==version:
                        return path.read_bytes(), 'application/pdf' if item['type']=='pdf' else 'text/markdown; charset=utf-8', item['name']
        raise KeyError('历史版本不存在。')
