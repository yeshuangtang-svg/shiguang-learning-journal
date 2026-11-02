"""Browser checks for the offline renderer; no application or user data is loaded.

Run with PowerShell (Playwright and Edge required):
    $env:RUN_BROWSER_TESTS='1'
    python -m unittest discover -s tests -p test_markdown_rendering.py -v

The opt-in keeps ordinary backend test discovery independent of browser setup.
All page network requests are aborted; hydration uses controlled fetch stubs.
"""
import os
from pathlib import Path
import unittest

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

STATIC = Path(__file__).resolve().parents[1] / "static"
ASSET = "/api/assets/" + "a" * 64


@unittest.skipUnless(os.getenv("RUN_BROWSER_TESTS") == "1" and sync_playwright,
                     "Set RUN_BROWSER_TESTS=1 with Playwright and Edge installed")
class MarkdownRenderingChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        try:
            cls.browser = cls.playwright.chromium.launch(channel="msedge", headless=True)
        except Exception:
            cls.playwright.stop()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.context = self.browser.new_context()
        self.context.route("**/*", lambda route: route.abort())
        self.page = self.context.new_page()
        self.page.set_content('<div id="preview"></div>')
        for script in ("vendor/marked.min.js", "vendor/purify.min.js", "markdown.js"):
            self.page.add_script_tag(path=str(STATIC / script))
        self.addCleanup(self.context.close)

    def render(self, source):
        return self.page.evaluate("""source => {
            const element = document.querySelector('#preview');
            element.innerHTML = StudyMarkdown.render(source);
            return element.innerHTML;
        }""", source)

    def test_markdown_features_and_legacy_plain_text_linebreaks(self):
        self.render("# 学习标题\n\n第一行\n第二行\n\n**重点**与~~删去~~\n\n"
                    "| 知识点 | 结论 |\n| --- | --- |\n| HTTP | 请求响应 |\n\n"
                    "- [x] 已完成\n- [ ] 待复习\n\n> 引用\n\n```python\nprint('<ok>')\n```")
        self.assertEqual(self.page.locator("h1").inner_text(), "学习标题")
        self.assertEqual(self.page.locator("strong").inner_text(), "重点")
        self.assertEqual(self.page.locator("del").inner_text(), "删去")
        self.assertEqual(self.page.locator("table tbody td").all_inner_texts(), ["HTTP", "请求响应"])
        self.assertEqual(self.page.locator("input[type=checkbox]:disabled").count(), 2)
        self.assertEqual(self.page.locator("input:checked").count(), 1)
        self.assertIn("第一行<br>", self.page.locator("#preview").inner_html())
        self.assertEqual(self.page.locator("blockquote").inner_text().strip(), "引用")
        self.assertIn("print('<ok>')", self.page.locator("pre code").inner_text())

    def test_raw_html_is_visible_text_and_never_executed(self):
        self.render('<script>window.compromised=1</script>\n\n'
                    '<img src=x onerror="window.compromised=2">\n\n'
                    '<svg onload="window.compromised=3"></svg>\n\n'
                    '<iframe srcdoc="<script>window.compromised=4</script>"></iframe>')
        self.assertEqual(self.page.locator("#preview script, #preview img, #preview svg, #preview iframe").count(), 0)
        self.assertIsNone(self.page.evaluate("window.compromised"))
        self.assertIn("<script>", self.page.locator("#preview").inner_text())

    def test_links_drop_unsafe_schemes_credentials_and_relative_paths(self):
        self.render("[one](javascript:alert%281%29) [two](data:text/html,payload) "
                    "[three](file:///C:/private.txt) [four](https://user:secret@example.com/) "
                    "[five](/api/config) [six](https://example.com/study) [seven](mailto:learn@example.com)")
        links = self.page.locator("#preview a").evaluate_all("nodes => nodes.map(a => ({href:a.getAttribute('href'),target:a.target,rel:a.rel}))")
        self.assertEqual([link["href"] for link in links[:5]], [None] * 5)
        self.assertEqual([link["href"] for link in links[5:]], ["https://example.com/study", "mailto:learn@example.com"])
        for link in links[5:]:
            self.assertEqual(link["target"], "_blank")
            self.assertIn("noopener", link["rel"])
            self.assertIn("noreferrer", link["rel"])

    def test_images_only_allow_uploaded_assets_and_external_web_images(self):
        self.render(f"![本地]({ASSET}) ![远端](https://example.com/picture.png) "
                    "![数据](data:image/png;base64,AA==) ![私密](/api/config) "
                    "![本机](http://127.0.0.1:8787/private.png) ![文件](file:///C:/private.png)")
        self.assertEqual(self.page.locator("#preview img").count(), 2)
        uploaded = self.page.locator("img[data-asset]")
        self.assertEqual(uploaded.get_attribute("data-asset"), ASSET)
        self.assertIsNone(uploaded.get_attribute("src"))
        external = self.page.locator("img[src]")
        self.assertEqual(external.get_attribute("src"), "https://example.com/picture.png")
        self.assertEqual(external.get_attribute("referrerpolicy"), "no-referrer")
        self.assertEqual(self.page.locator(".image-unavailable").count(), 4)

    def prepare_hydration(self):
        self.render(f"![学习截图]({ASSET})")
        self.page.evaluate("""() => {
            window.created = []; window.revoked = [];
            URL.createObjectURL = blob => { const url = 'blob:renderer-test/' + created.length; created.push({url,type:blob.type}); return url; };
            URL.revokeObjectURL = url => revoked.push(url);
        }""")

    def test_hydrate_uses_bearer_auth_and_dispose_revokes_object_urls(self):
        self.prepare_hydration()
        result = self.page.evaluate("""async () => {
            let request;
            window.fetch = async (path, options) => { request = {path,auth:options.headers.Authorization,credentials:options.credentials}; return new Response(new Blob(['image'], {type:'image/png'})); };
            const preview = document.querySelector('#preview');
            await StudyMarkdown.hydrate(preview, 'local-test-token');
            const src = preview.querySelector('img').getAttribute('src');
            StudyMarkdown.dispose(preview); StudyMarkdown.dispose(preview);
            return {request,src,created,revoked};
        }""")
        self.assertEqual(result["request"], {"path": ASSET, "auth": "Bearer local-test-token", "credentials": "same-origin"})
        self.assertEqual(result["src"], "blob:renderer-test/0")
        self.assertEqual(result["revoked"], [result["src"]])
        self.assertEqual(result["created"][0]["type"], "image/png")

    def test_dispose_aborts_pending_hydration_without_error_message(self):
        self.prepare_hydration()
        result = self.page.evaluate("""async () => {
            let aborted = false;
            window.fetch = (_path, options) => new Promise((_resolve, reject) => options.signal.addEventListener('abort', () => { aborted = true; reject(new DOMException('Cancelled', 'AbortError')); }));
            const preview = document.querySelector('#preview');
            const pending = StudyMarkdown.hydrate(preview, 'local-test-token');
            StudyMarkdown.dispose(preview); await pending;
            const img = preview.querySelector('img');
            return {aborted,src:img.getAttribute('src'),alt:img.alt,created};
        }""")
        self.assertTrue(result["aborted"])
        self.assertIsNone(result["src"])
        self.assertEqual(result["alt"], "学习截图")
        self.assertEqual(result["created"], [])

    def test_late_response_cannot_overwrite_newer_preview(self):
        self.prepare_hydration()
        result = self.page.evaluate("""async () => {
            const resolvers = [];
            window.fetch = () => new Promise(resolve => resolvers.push(resolve));
            const preview = document.querySelector('#preview');
            const first = StudyMarkdown.hydrate(preview, 'first');
            const second = StudyMarkdown.hydrate(preview, 'second');
            resolvers[1](new Response(new Blob(['new'], {type:'image/png'}))); await second;
            resolvers[0](new Response(new Blob(['stale'], {type:'image/jpeg'}))); await first;
            const src = preview.querySelector('img').getAttribute('src');
            StudyMarkdown.dispose(preview);
            return {src,created,revoked};
        }""")
        self.assertEqual(result["created"], [{"url": "blob:renderer-test/0", "type": "image/png"}])
        self.assertEqual(result["src"], "blob:renderer-test/0")
        self.assertEqual(result["revoked"], [result["src"]])

    def test_unauthorized_or_non_image_response_remains_unrendered(self):
        for response in ("new Response('denied', {status:401})",
                         "new Response('<script>bad</script>', {headers:{'Content-Type':'text/html'}})"):
            with self.subTest(response=response):
                self.prepare_hydration()
                result = self.page.evaluate("""async response => {
                    window.fetch = async () => (new Function('return ' + response))();
                    const preview = document.querySelector('#preview');
                    await StudyMarkdown.hydrate(preview);
                    const img = preview.querySelector('img');
                    return {src:img.getAttribute('src'),alt:img.alt,created,error:img.classList.contains('image-load-error')};
                }""", response)
                self.assertIsNone(result["src"])
                self.assertIn("加载失败", result["alt"])
                self.assertTrue(result["error"])
                self.assertEqual(result["created"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
