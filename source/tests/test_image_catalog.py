import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_library as fixtures


class ImageCatalogChecks(unittest.TestCase):
    setUp = fixtures.LibraryHTTPChecks.setUp
    tearDown = fixtures.LibraryHTTPChecks.tearDown
    request = fixtures.LibraryHTTPChecks.request

    def test_index_deduplicates_and_preserves_all_locations(self):
        asset = self.request('/api/assets', 'POST', fixtures.IMAGE)[2]
        folder = Path(self.directory.name) / 'documents' / 'example'
        folder.mkdir(parents=True)
        (folder / '流程图.png').write_bytes(fixtures.png())
        # A raster with a mistaken but still image-only extension remains usable.
        (folder / '另一副本.jpg').write_bytes(fixtures.png())
        (folder / '伪装.png').write_text('<html>not an image</html>')
        status, _, result = self.request('/api/images')
        self.assertEqual(status, 200)
        self.assertEqual(len(result['images']), 1)
        item = result['images'][0]
        self.assertEqual(item['name'], fixtures.IMAGE['name'])
        self.assertEqual(item['id'], asset['id'])
        self.assertEqual(len(item['paths']), 3)
        self.assertEqual(result['skipped'], 1)
        self.assertEqual(json.loads(Path(result['index_path']).read_text(encoding='utf-8')), result)
        self.assertEqual(self.request(item['url'])[2], fixtures.png())
        (folder / '流程图.png').unlink()
        self.assertEqual(len(self.request('/api/images')[2]['images'][0]['paths']), 2)

    def test_auth_and_native_actions_reject_arbitrary_paths_and_changed_bytes(self):
        self.request('/api/assets', 'POST', fixtures.IMAGE)
        self.assertEqual(self.request('/api/images', authenticated=False)[0], 401)
        item = self.request('/api/images')[2]['images'][0]
        endpoint = '/api/images/' + item['id']
        self.assertEqual(self.request(endpoint + '/content', authenticated=False)[0], 401)
        self.assertEqual(self.request(endpoint + '/open', 'POST', {})[0], 400)
        self.app.desktop = True
        with patch('image_catalog.os.startfile', create=True) as open_image, patch('image_catalog.subprocess.Popen') as reveal:
            self.assertEqual(self.request(endpoint + '/open', 'POST', {})[0], 200)
            open_image.assert_called_once_with(item['paths'][0])
            self.assertEqual(self.request(endpoint + '/reveal', 'POST', {'location':0})[0], 200)
            self.assertEqual(reveal.call_args[0][0][1:], ['/select,',item['paths'][0]])
            for payload in ({'path':'C:/Windows/notepad.exe'}, {'location':-1}, {'location':'0'}):
                self.assertEqual(self.request(endpoint + '/open', 'POST', payload)[0], 400)
            self.assertEqual(self.request(endpoint + '/open', 'POST', {}, headers={'Origin':'https://evil.invalid'})[0], 403)
            Path(item['paths'][0]).write_bytes(b'not an image')
            self.assertEqual(self.request(endpoint + '/open', 'POST', {})[0], 400)
            self.assertEqual(open_image.call_count, 1)
        with self.assertRaises(ValueError):
            self.app.image_catalog.checked(Path(self.directory.name).parent / 'escape.png')

    def test_empty_and_history_excluded(self):
        self.assertEqual(self.request('/api/images')[2]['images'], [])
        folder = Path(self.directory.name) / 'documents' / 'test' / '历史版本'
        folder.mkdir(parents=True)
        (folder / 'old.png').write_bytes(fixtures.png())
        self.assertEqual(self.request('/api/images')[2]['images'], [])
