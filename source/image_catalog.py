"""A rebuildable local image index; native actions only accept indexed identities."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import threading
import uuid

from library import image_mime, MAX_IMAGE_BYTES, resource_id

SUFFIXES = {'image/png': '.png', 'image/jpeg': '.jpg', 'image/gif': '.gif', 'image/webp': '.webp'}


class ImageCatalog:
    def __init__(self, data_dir, store):
        self.root = Path(data_dir).resolve()
        self.store = store
        self.lock = threading.RLock()
        self.items = {}

    def checked(self, path):
        path = Path(path)
        resolved = path.resolve()
        if self.root.resolve() != self.root or not any(resolved.is_relative_to(self.root / name) for name in ('images', 'documents')):
            raise ValueError('图片位置不在本应用资料文件夹内。')
        return path

    def write(self, path, data):
        path = self.checked(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.read_bytes() == data:
            return
        temp = self.checked(path.with_name('.' + uuid.uuid4().hex + '.tmp'))
        try:
            temp.write_bytes(data)
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)

    def refresh(self):
        with self.lock:
            items, skipped = {}, 0

            def add(path, data, name):
                mime = image_mime(data)
                identity = hashlib.sha256(data).hexdigest()
                item = items.setdefault(identity, {'id': identity, 'name': name, 'mime': mime, 'size': len(data), 'paths': [], 'url': '/api/images/' + identity + '/content'})
                if str(path) not in item['paths']:
                    item['paths'].append(str(path))

            # Materialize database-only illustrations without changing the database.
            for metadata in self.store.list_assets():
                asset = self.store.get_asset(metadata['id'])
                path = self.checked(self.root / 'images' / (asset['id'] + SUFFIXES[asset['mime']]))
                self.write(path, asset['data'])
                add(path, asset['data'], asset['name'])
            for folder in (self.root / 'images', self.root / 'documents'):
                if not folder.exists():
                    continue
                self.checked(folder)
                # Do not traverse junctions, symlinks, or document history copies.
                for base, directories, files in os.walk(folder, followlinks=False):
                    directories[:] = [d for d in directories if d != '历史版本' and not (Path(base) / d).is_symlink() and not getattr(os.path, 'isjunction', lambda p: False)(Path(base) / d)]
                    for name in sorted(files):
                        path = Path(base) / name
                        if path.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.gif', '.webp'):
                            continue
                        try:
                            self.checked(path)
                            if path.stat().st_size > MAX_IMAGE_BYTES:
                                raise ValueError('图片过大。')
                            add(path, path.read_bytes(), name)
                        except (OSError, ValueError):
                            skipped += 1
            self.items = items
            result = {'images': sorted(items.values(), key=lambda item: item['name'].casefold()),
                      'index_path': str(self.root / 'images' / '图片清单.json'), 'skipped': skipped}
            self.write(result['index_path'], json.dumps(result, ensure_ascii=False, indent=2).encode('utf-8'))
            return result

    def resolve(self, identity, location=0):
        resource_id(identity, asset=True)
        if type(location) is not int or location < 0:
            raise ValueError('图片位置编号无效。')
        with self.lock:
            if identity not in self.items:
                self.refresh()
            item = self.items.get(identity)
            if not item or location >= len(item['paths']):
                raise KeyError('图片或位置不存在，请刷新图片清单。')
            path = self.checked(item['paths'][location])
            if path.stat().st_size > MAX_IMAGE_BYTES:
                raise ValueError('图片已变更，请刷新清单。')
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != identity or image_mime(data) != item['mime']:
                raise ValueError('图片已变更，请刷新清单。')
            return path, data, item['mime']

    def open(self, identity, action, payload, desktop=False):
        if not desktop or os.name != 'nt':
            raise ValueError('请在 Windows 桌面版拾光中打开本机图片。')
        if set(payload) - {'location'}:
            raise ValueError('打开图片无需传入路径。')
        path, _, _ = self.resolve(identity, payload.get('location', 0))
        if action == 'open':
            os.startfile(str(path))
        elif action == 'reveal':
            explorer = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'explorer.exe'
            subprocess.Popen([str(explorer), '/select,', str(path)])
        else:
            raise ValueError('不支持的图片操作。')
        return {'opened': True, 'path': str(path)}
