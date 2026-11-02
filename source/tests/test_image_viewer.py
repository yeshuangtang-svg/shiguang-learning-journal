"""Opt-in image viewer browser tests using only an isolated in-memory page.

PowerShell: $env:RUN_BROWSER_TESTS='1'
python -m unittest discover -s tests -p test_image_viewer.py -v

Requires Playwright and Microsoft Edge. No application API or user files are used;
network traffic is blocked and local image hydration receives a generated PNG Blob.
"""
import os
from pathlib import Path
import re
import unittest

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

STATIC = Path(__file__).resolve().parents[1] / "static"
ASSET = "/api/assets/" + "b" * 64


@unittest.skipUnless(os.getenv("RUN_BROWSER_TESTS") == "1" and sync_playwright,
                     "Set RUN_BROWSER_TESTS=1 with Playwright and Edge installed")
class ImageViewerChecks(unittest.TestCase):
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
        self.context = self.browser.new_context(viewport={"width": 1280, "height": 900})
        self.context.route("**/*", lambda route: route.abort())
        self.page = self.context.new_page()
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        html = re.sub(r"<script\b[^>]*>.*?</script>", "", html, flags=re.I | re.S)
        html = re.sub(r"<link\b[^>]*>", "", html, flags=re.I)
        self.page.set_content(html)
        for stylesheet in ("style.css", "image-viewer.css"):
            self.page.add_style_tag(path=str(STATIC / stylesheet))
        self.page.add_style_tag(content="""
            .app-shell { display: none !important; }
            #test-preview { padding: 32px; }
            #test-preview img, #entry-image-fixture img { width: 220px; height: auto; }
        """)
        self.page.evaluate("""() => {
            const preview = document.createElement('article');
            preview.id = 'test-preview'; preview.className = 'markdown-body';
            document.body.append(preview);
        }""")
        for script in ("vendor/marked.min.js", "vendor/purify.min.js", "markdown.js", "image-viewer.js"):
            self.page.add_script_tag(path=str(STATIC / script))
        self.page.evaluate("""async () => {
            const canvas = document.createElement('canvas'); canvas.width = 1600; canvas.height = 900;
            const ctx = canvas.getContext('2d'); ctx.fillStyle = '#4d7055'; ctx.fillRect(0, 0, 1600, 900);
            ctx.fillStyle = '#ffffff'; ctx.font = '60px sans-serif'; ctx.fillText('Learning image', 100, 160);
            window.fixtureBlob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
            window.fixtureFetches = 0;
            window.fetch = async () => { fixtureFetches++; return new Response(fixtureBlob); };
        }""")
        self.addCleanup(self.context.close)

    def prepare_image(self, selector="#test-preview", linked=False, broken=False):
        markdown = f"![学习截图]({ASSET})"
        if linked:
            markdown = f"[{markdown}](https://example.invalid/do-not-open)"
        self.page.evaluate("""async ({selector, markdown, broken}) => {
            if (broken) window.fetch = async () => new Response(new Blob(['not a PNG'], {type:'image/png'}));
            const target = document.querySelector(selector);
            target.innerHTML = StudyMarkdown.render(markdown);
            await StudyMarkdown.hydrate(target, 'isolated-test-token');
            const image = target.querySelector('img');
            await new Promise(resolve => {
                if (image.complete) resolve();
                else { image.addEventListener('load', resolve, {once:true}); image.addEventListener('error', resolve, {once:true}); }
            });
        }""", {"selector": selector, "markdown": markdown, "broken": broken})
        return self.page.locator(selector + " img")

    def assert_viewer_open(self):
        self.page.wait_for_function("document.querySelector('#image-viewer')?.open === true")
        self.page.wait_for_function("document.querySelector('#image-viewer-image')?.naturalWidth > 0")

    def assert_viewer_closed(self):
        self.page.wait_for_function("!document.querySelector('#image-viewer')?.open")

    def scale(self):
        return float(re.search(r"[\d.]+", self.page.locator("#image-viewer-scale").inner_text()).group())

    def test_click_opens_large_local_blob_without_additional_request(self):
        image = self.prepare_image()
        original_src = image.get_attribute("src")
        self.assertTrue(original_src.startswith("blob:"))
        thumbnail_width = image.bounding_box()["width"]
        image.click()
        self.assert_viewer_open()
        large = self.page.locator("#image-viewer-image")
        self.assertEqual(large.get_attribute("src"), original_src)
        self.assertGreater(large.bounding_box()["width"], thumbnail_width)
        self.assertEqual(self.page.evaluate("fixtureFetches"), 1)
        self.assertIn("%", self.page.locator("#image-viewer-scale").inner_text())

    def test_keyboard_enter_and_space_open_and_escape_restores_focus(self):
        image = self.prepare_image()
        self.assertEqual(image.get_attribute("role"), "button")
        self.assertEqual(image.get_attribute("tabindex"), "0")
        for key in ("Enter", "Space"):
            with self.subTest(key=key):
                image.focus()
                image.press(key)
                self.assert_viewer_open()
                self.page.keyboard.press("Escape")
                self.assert_viewer_closed()
                self.assertTrue(image.evaluate("img => document.activeElement === img"))

    def test_zoom_controls_actual_and_fit(self):
        self.prepare_image().click()
        self.assert_viewer_open()
        initial = self.scale()
        initial_width = self.page.locator("#image-viewer-image").bounding_box()["width"]
        self.page.locator("#image-viewer-zoom-in").click()
        self.assertGreater(self.scale(), initial)
        self.assertGreater(self.page.locator("#image-viewer-image").bounding_box()["width"], initial_width)
        enlarged = self.scale()
        self.page.locator("#image-viewer-zoom-out").click()
        self.assertLess(self.scale(), enlarged)
        self.page.locator("#image-viewer-actual").click()
        self.assertEqual(self.scale(), 100)
        self.page.locator("#image-viewer-fit").click()
        self.assertLess(self.scale(), 100)
        self.assertAlmostEqual(self.scale(), initial, delta=1)

    def test_close_button_and_blank_stage_exit(self):
        image = self.prepare_image()
        image.click()
        self.assert_viewer_open()
        self.page.locator("#image-viewer-close").click()
        self.assert_viewer_closed()
        image.click()
        self.assert_viewer_open()
        self.page.locator("#image-viewer-stage").click(position={"x": 4, "y": 4})
        self.assert_viewer_closed()

    def test_wheel_zoom_drag_and_keyboard_pan_keep_viewer_open(self):
        self.prepare_image().click()
        self.assert_viewer_open()
        initial = self.scale()
        self.page.locator("#image-viewer-stage").hover()
        self.page.mouse.wheel(0, -160)
        self.page.wait_for_function("""previous => parseFloat(document.querySelector('#image-viewer-scale').value) > previous""", arg=initial)
        self.page.locator("#image-viewer-actual").click()
        large = self.page.locator("#image-viewer-image")
        original_left = large.evaluate("img => parseFloat(img.style.left)")
        self.page.keyboard.press("ArrowRight")
        panned_left = large.evaluate("img => parseFloat(img.style.left)")
        self.assertLess(panned_left, original_left)
        stage = self.page.locator("#image-viewer-stage").bounding_box()
        center_x, center_y = stage["x"] + stage["width"] / 2, stage["y"] + stage["height"] / 2
        self.page.mouse.move(center_x, center_y)
        self.page.mouse.down()
        self.page.mouse.move(center_x + 90, center_y, steps=5)
        self.page.mouse.up()
        self.assertGreater(large.evaluate("img => parseFloat(img.style.left)"), panned_left)
        self.assert_viewer_open()

    def test_save_shortcut_does_not_reach_underlying_editor(self):
        self.prepare_image().click()
        self.assert_viewer_open()
        self.page.evaluate("""() => {
            window.saved = 0;
            window.addEventListener('keydown', event => {
                if (event.ctrlKey && event.key.toLowerCase() === 's') { event.preventDefault(); saved++; }
            });
        }""")
        self.page.keyboard.press("Control+s")
        self.assertEqual(self.page.evaluate("saved"), 0)
        self.page.locator("#image-viewer-close").click()
        self.assert_viewer_closed()
        self.page.keyboard.press("Control+s")
        self.assertEqual(self.page.evaluate("saved"), 1)

    def test_viewer_over_entry_dialog_preserves_unsaved_input(self):
        self.page.evaluate("""() => {
            const dialog = document.querySelector('#entry-dialog');
            dialog.querySelector('[name=title]').value = '未保存的学习标题';
            dialog.querySelector('[name=content]').value = '未保存的正文';
            const preview = document.createElement('div'); preview.id = 'entry-image-fixture'; preview.className = 'markdown-body';
            dialog.querySelector('.modal-body').prepend(preview);
            dialog.showModal();
        }""")
        image = self.prepare_image("#entry-image-fixture")
        for close_action in ("escape", "button"):
            with self.subTest(close_action=close_action):
                image.click()
                self.assert_viewer_open()
                self.assertTrue(self.page.evaluate("""() => {
                    const img = document.querySelector('#image-viewer-image'); const box = img.getBoundingClientRect();
                    return !!document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2)?.closest('#image-viewer');
                }"""))
                if close_action == "escape":
                    self.page.keyboard.press("Escape")
                else:
                    self.page.locator("#image-viewer-close").click()
                self.assert_viewer_closed()
                self.assertTrue(self.page.locator("#entry-dialog").evaluate("dialog => dialog.open"))
                self.assertEqual(self.page.locator('#entry-dialog [name=title]').input_value(), "未保存的学习标题")
                self.assertEqual(self.page.locator('#entry-dialog [name=content]').input_value(), "未保存的正文")

    def test_link_wrapped_image_opens_viewer_without_navigation(self):
        image = self.prepare_image(linked=True)
        initial_url = self.page.url
        image.click()
        self.assert_viewer_open()
        self.assertEqual(self.page.url, initial_url)
        self.assertEqual(len(self.context.pages), 1)

    def test_broken_image_does_not_open_an_empty_viewer(self):
        image = self.prepare_image(broken=True)
        self.assertEqual(image.evaluate("img => img.naturalWidth"), 0)
        image.dispatch_event("click")
        self.page.wait_for_timeout(100)
        self.assert_viewer_closed()
        image.dispatch_event("keydown", {"key": "Enter", "bubbles": True})
        self.page.wait_for_timeout(100)
        self.assert_viewer_closed()


if __name__ == "__main__":
    unittest.main(verbosity=2)
