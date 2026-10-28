"""Native SVG regression tests. Set ARCHITECTURE_MATHJAX_MODULE_DIR to run."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills' / 'model-architecture-explorer'
MATHJAX = os.environ.get('ARCHITECTURE_MATHJAX_MODULE_DIR')


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, SKILL / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load_script('build_explorer')
checker = load_script('check_explorer')


@unittest.skipUnless(MATHJAX, 'Set ARCHITECTURE_MATHJAX_MODULE_DIR to node_modules containing mathjax-full')
class NativeSVGTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(prefix='architecture-vector-math-')
        cls.repo = Path(cls.folder.name)
        (cls.repo / 'model.py').write_text('class Projection:\n    def forward(self, x):\n        return x\n')
        reference = (SKILL / 'references' / 'page-spec.md').read_text()
        cls.spec = json.loads(reference.split('```json\n', 1)[1].split('\n```', 1)[0])
        cls.spec['subtitle'] = r'条件 \(C\) 与动作 \(x\) 独立。<img src=x onerror=alert(1)>'
        profile = cls.spec['profiles'][0]
        profile['controls'] = [{'id': 'B', 'label': 'Batch', 'value': 1, 'min': 1, 'max': 8}]
        profile['stats'] = [{'label': 'Batch', 'value': '{{B}}'}]
        profile['mechanism'] = {
            'title': '条件',
            'equations': [r'\[\begin{aligned}V^{\prime}&=VW_v+e_v\\C&=[V^{\prime}\Vert L^{\prime}]\end{aligned}\]'],
            'description': '符号公式固定；数值形状联动。',
        }
        profile['assumptions'] = r'单头 \(d_k=64\)；[{{B}},16,256]。'
        for module in profile['modules'].values():
            module.update(description='原始参数见源码。', input='[{{B}},16,768]', output='[{{B}},16,256]', params=[['实例', 'layers.0']])
        profile['modules']['linear']['operations'] = [
            r'\[S=\frac{QK^{\mathsf T}}{\sqrt{d_k}}\]',
            r'矩阵 \(W=\begin{bmatrix}1&2\\3&4\end{bmatrix}\)。',
            r'\[L=' + '+'.join(f'x_{{{i}}}^2' for i in range(50)) + r'\]',
        ]
        detail = profile['views'][1]
        detail.update(variant='operator', height=400)
        detail['notes'][0]['y'] = 350
        detail['nodes'][0].update(height=180, mathSize=19, lines=[
            r'\(S=\frac{QK^{\mathsf T}}{\sqrt{d_k}}\)', '[{{B}},16,256]'], foot='公式按实际高度排列')
        cls.spec_path = cls.repo / 'spec.json'
        cls.spec_path.write_text(json.dumps(cls.spec, ensure_ascii=False))
        cls.cache_path = cls.repo / 'math-svg.json'
        subprocess.run(['node', str(SKILL / 'scripts/render_math.mjs'), '--module-dir', MATHJAX,
                        '--spec', str(cls.spec_path), '--output', str(cls.cache_path)], check=True, capture_output=True)
        cls.output = cls.repo / 'visualization' / 'projection-architecture.html'
        builder.build(cls.repo, cls.spec_path, cls.output, builder.DEFAULT_TEMPLATE, cls.cache_path)
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.folder.cleanup()

    def setUp(self):
        self.page = self.browser.new_page(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
        self.errors = []
        self.page.on('pageerror', lambda e: self.errors.append(str(e)))
        self.page.context.set_offline(True)
        self.page.goto(self.output.as_uri())

    def tearDown(self):
        self.assertFalse(self.errors)
        self.page.close()

    def open_operator(self):
        self.page.locator('#graph .node').click()
        self.page.locator('#graph .node').click()

    def test_offline_glyphs_dimensions_and_mobile_fraction(self):
        self.assertEqual(self.page.locator('#subtitle .math-expression').count(), 2)
        self.assertEqual(self.page.locator('#subtitle img').count(), 0)
        self.assertEqual(self.page.locator('style#katex-styles').count(), 0)
        self.open_operator()
        checker.check_math(self.page, '#operator-content')
        self.assertGreater(self.page.locator('#operator-content [data-mml-node="mfrac"]').count(), 0)
        self.assertGreater(self.page.locator('#operator-content [data-mml-node="mtable"]').count(), 0)
        for svg in self.page.locator('#operator-content .math-expression>svg').all():
            self.assertTrue(svg.get_attribute('width').endswith('em'))
        self.page.keyboard.press('Escape')
        control = self.page.get_by_role('spinbutton', name='Batch')
        control.fill('3'); control.press('Tab')
        self.assertIn('[3,16,256]', self.page.locator('#graph').text_content())
        self.assertFalse(checker.check_formula_layout(self.page))
        self.page.set_viewport_size({'width':390,'height':844})
        self.page.locator('#graph .node').click()
        long_formula = self.page.locator('#operator-content .display-math').last
        self.assertTrue(long_formula.evaluate('(e)=>e.scrollWidth>e.clientWidth && getComputedStyle(e).overflowX==="auto"'))
        self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
        self.assertLessEqual(self.page.locator('#operator-modal').evaluate('(e)=>e.scrollWidth-e.clientWidth'), 1)

    def test_export_and_checker_rejects_formula_collisions(self):
        self.page.locator('#graph .node').click()
        self.assertFalse(checker.check_formula_layout(self.page))
        with self.page.expect_download() as pending:
            self.page.locator('#export').click()
        svg_path = self.repo / 'formula.svg'; pending.value.save_as(svg_path)
        markup = svg_path.read_text()
        self.assertNotIn('foreignObject', markup)
        self.assertNotIn('@font-face', markup)
        self.page.goto(svg_path.as_uri())
        self.assertEqual(self.page.locator('parsererror').count(), 0)
        self.assertGreater(self.page.locator('.math-label path').count(), 0)
        self.page.goto(self.output.as_uri()); self.page.locator('#graph .node').click()
        self.page.evaluate("document.querySelector('#graph .math-label').setAttribute('y','100')")
        self.assertTrue(checker.check_formula_layout(self.page))

    def test_missing_cache_dynamic_formulas_and_invalid_tex_fail(self):
        cache = json.loads(self.cache_path.read_text())
        missing_path = self.repo / 'missing.json'
        cache.pop(next(iter(cache))); missing_path.write_text(json.dumps(cache))
        with self.assertRaisesRegex(ValueError, 'missing expressions'):
            builder.build(self.repo, self.spec_path, self.repo/'bad.html', builder.DEFAULT_TEMPLATE, missing_path)
        dynamic = json.loads(json.dumps(self.spec)); dynamic['subtitle'] = r'\(B={{B}}\)'
        path = self.repo / 'dynamic.json'; path.write_text(json.dumps(dynamic))
        with self.assertRaisesRegex(ValueError, 'symbolic values'):
            builder.build(self.repo, path, self.repo/'bad.html', builder.DEFAULT_TEMPLATE, self.cache_path)
        for content in ([r'\notARealCommand{x}'], [r'B={{B}}']):
            path = self.repo / 'invalid.json'; path.write_text(json.dumps(content))
            result = subprocess.run(['node', str(SKILL/'scripts/render_math.mjs'), '--module-dir', MATHJAX,
                                     '--input', str(path), '--output', str(self.repo/'invalid-cache.json')], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)

    def test_formula_width_is_rejected_without_shrinking(self):
        message = self.page.evaluate(r'''() => {
          try { architectureMath.svg('\\(C\\)', 0, 0, 0.1, 18); return ''; }
          catch (error) { return error.message; }
        }''')
        self.assertIn('exceeds its diagram slot', message)

    def test_full_checker_supports_vector_formulas(self):
        result = json.loads(subprocess.check_output([sys.executable, str(SKILL/'scripts/check_explorer.py'), '--page', str(self.output)], text=True))
        self.assertEqual(result['status'], 'PASS')
        self.assertGreater(result['math_renders'], 0)


if __name__ == '__main__':
    unittest.main()
