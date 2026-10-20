"""Browser regression tests; run with Python, Playwright and Chromium installed."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills' / 'model-architecture-explorer'


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, SKILL / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load_script('build_explorer')
checker = load_script('check_explorer')


class MathRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(prefix='architecture-math-')
        cls.repo = Path(cls.folder.name)
        cls.source = 'class Projection:\n    def forward(self, x):\n        note = "$(source)$ </script>"\n        return x\n'
        (cls.repo / 'model.py').write_text(cls.source)
        reference = (SKILL / 'references' / 'page-spec.md').read_text()
        cls.spec = json.loads(reference.split('```json\n', 1)[1].split('\n```', 1)[0])
        cls.spec['subtitle'] = r'输入张量 \(X \in \mathbb{R}^{B \times N \times D}\)'
        profile = cls.spec['profiles'][0]
        profile['dimensions'] = {'N': 16, 'D': 256}
        profile['controls'] = [{'id': 'B', 'label': 'Batch', 'value': 1, 'min': 1, 'max': 8}]
        profile['stats'] = [{'label': 'Batch', 'value': '{{B}}'}, {'label': '宽度', 'value': '{{D}}'}]
        profile['mechanism'] = {
            'title': '残差投影', 'equations': [r'\(Y = X W^{\mathsf{T}}\)'],
            'description': r'当前批量大小 \(B={{B}}\)。', 'module': 'projection',
        }
        profile['notes'] = [{'title': '保留原始输入', 'text': r'skip 直接读取 \(X\)。', 'module': 'linear'}]
        profile['trace'] = ['projection', 'linear']
        profile['modules']['projection']['input'] = r'\(X \in \mathbb{R}^{ {{B}} \times {{N}} \times 768}\)'
        profile['views'][0]['flow'] = [{'label': '投影模块', 'modules': ['projection']}]
        profile['views'][1]['flow'] = [{'label': '线性 skip', 'modules': ['linear']}]
        profile['assumptions'] = r'行内 $d_k = 64$，独立公式 $$B = 2$$；费用 \(\$5\)。'
        module = profile['modules']['linear']
        module['description'] = r'缩放注意力 \(QK^{\mathsf{T}} / \sqrt{d_k}\)；<img src=x onerror=alert(1)>'
        module['params'] = [[r'每头维度 \(d_k\)', r'\(64\)'], ['实现', 'bias=False']]
        module['operations'] = [
            r'\[A = \operatorname{softmax}\left(\frac{QK^{\mathsf{T}}}{\sqrt{d_k}} + M\right)V\]',
            r'矩阵 $W = \begin{bmatrix}1 & 2 \\ 3 & 4\end{bmatrix}$',
            r'$$Y = X + \operatorname{MLP}(\operatorname{LN}(X))$$',
            r'\[L = ' + ' + '.join(f'x_{{{i}}}^2' for i in range(50)) + r'\]',
        ]
        plain = json.loads(json.dumps(profile))
        plain['id'], plain['label'] = 'plain', '普通文本配置'
        for m in plain['modules'].values():
            m.update(description='旧 spec 继续显示普通文本', input='[B, N, 768]',
                     output='[B, N, 256]', params=[['bias', False]], operations=['Linear(X)'])
        cls.spec['profiles'].append(plain)
        cls.spec_path = cls.repo / 'spec.json'
        cls.spec_path.write_text(json.dumps(cls.spec, ensure_ascii=False))
        cls.output = cls.repo / 'index.html'
        builder.build(cls.repo, cls.spec_path, cls.output, builder.DEFAULT_TEMPLATE)
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.folder.cleanup()

    def setUp(self):
        self.page = self.browser.new_page(viewport={'width': 1440, 'height': 1000})
        self.errors, self.requests = [], []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.page.on('request', lambda request: self.requests.append(request.url))
        self.page.route('http://**/*', lambda route: route.abort())
        self.page.route('https://**/*', lambda route: route.abort())
        self.page.context.set_offline(True)
        self.page.goto(self.output.as_uri())

    def tearDown(self):
        self.assertFalse(self.errors)
        self.page.close()

    def open_operator(self):
        self.page.locator('#graph .node').click()
        self.page.locator('#graph .node').click()
        self.assertTrue(self.page.locator('#operator-modal').is_visible())

    def test_offline_math_fonts_and_dynamic_details(self):
        self.assertEqual(self.page.locator('#subtitle .katex math').count(), 1)
        self.assertEqual(self.page.locator('#assumptions .katex math').count(), 3)
        self.assertIn('$5', self.page.locator('#assumptions').inner_text())
        self.open_operator()
        self.assertEqual(self.page.locator('#operator-content .katex math').count(), 9)
        self.assertGreater(self.page.locator('#operator-content .mfrac').count(), 0)
        self.assertGreater(self.page.locator('#operator-content .mtable').count(), 0)
        self.assertEqual(self.page.locator('#operator-content img').count(), 0)
        checker.check_math(self.page, '#operator-content')
        self.page.evaluate('document.fonts.ready')
        self.assertTrue(self.page.evaluate('document.fonts.check(\'16px "KaTeX_Main"\')'))
        self.assertFalse(self.page.evaluate('''() => [...document.fonts].some(f=>f.status==='error')'''))
        self.assertFalse([url for url in self.requests if url.startswith(('http:', 'https:'))])
        self.page.locator('#operator-source').click()
        lines = self.page.locator('#source-code .code-text').all_text_contents()
        self.assertEqual(lines, self.source.splitlines())
        self.assertEqual(self.page.locator('#source-code .katex').count(), 0)
        self.page.keyboard.press('Escape')
        self.page.locator('#profile-picker').select_option('plain')
        self.page.locator('#tabs button').nth(1).click()
        self.page.locator('#graph .node').click()
        self.assertEqual(self.page.locator('#operator-content .katex').count(), 0)
        self.assertEqual(self.page.locator('#operator-content .shape').all_text_contents(), ['[B, N, 768]', '[B, N, 256]'])
        self.page.keyboard.press('Escape')
        self.page.locator('#profile-picker').select_option('base')
        self.open_operator()
        self.assertEqual(self.page.locator('#operator-content .katex math').count(), 9)

    def test_mobile_long_formula_scrolls_inside_dialog(self):
        self.page.set_viewport_size({'width': 390, 'height': 844})
        self.open_operator()
        self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        long_formula = self.page.locator('#operator-content .katex-display').last
        self.assertTrue(long_formula.evaluate('(el)=>el.scrollWidth>el.clientWidth && getComputedStyle(el).overflowX==="auto"'))
        self.assertLessEqual(self.page.locator('#operator-modal').evaluate('(el)=>el.scrollWidth-el.clientWidth'), 1)

    def test_invalid_latex_is_visible_and_checker_fails(self):
        self.page.evaluate(r'''() => {
          profile.modules.linear.operations = ['\\[\\notARealCommand{x}\\]'];
        }''')
        self.open_operator()
        self.assertEqual(self.page.locator('#operator-content .math-error').count(), 1)
        self.assertIn(r'\notARealCommand', self.page.locator('#operator-content .math-error').inner_text())
        with self.assertRaisesRegex(AssertionError, 'invalid LaTeX'):
            checker.check_math(self.page, '#operator-content')

    def test_reading_sections_controls_trace_and_flow(self):
        self.assertEqual(self.page.locator('#summary-stats .stat').count(), 2)
        self.assertTrue(self.page.locator('#mechanism').is_visible())
        self.assertEqual(self.page.locator('#core-idea .katex math').count(), 2)
        self.assertEqual(self.page.locator('#tensor-body tr').count(), 2)
        control = self.page.get_by_role('spinbutton', name='Batch')
        control.fill('3')
        control.press('Tab')
        self.assertEqual(self.page.locator('#summary-stats strong').first.inner_text(), '3')
        self.assertIn('3 \\times 16', self.page.locator('#inspector-content .shape .math-text').first.get_attribute('data-math-source'))
        self.assertIn('3 \\times 16', self.page.locator('#tensor-body tr').first.locator('td').nth(1).locator('.math-text').get_attribute('data-math-source'))
        control.fill('99')
        control.press('Tab')
        self.assertEqual(control.input_value(), '3')
        self.page.locator('#play').click()
        self.assertEqual(self.page.locator('#graph .node.running').count(), 1)
        self.page.locator('#reset').click()
        self.assertEqual(self.page.locator('#graph .node.running').count(), 0)
        self.page.locator('#tensor-body button').first.click()
        self.assertTrue(self.page.locator('#source-modal').is_visible())
        self.page.keyboard.press('Escape')
        self.page.locator('#mechanism-open').click()
        self.assertEqual(self.page.locator('#tabs button[aria-selected="true"]').inner_text(), '投影内部')
        self.page.locator('#profile-picker').select_option('plain')
        self.assertEqual(control.input_value(), '1')

    def test_svg_formula_rendering_and_standalone_export(self):
        self.page.evaluate(r'''() => {
          view.nodes[0].lines = ['\\(QK^{\\mathsf{T}}\\)'];
          draw();
        }''')
        self.assertEqual(self.page.locator('#graph foreignObject .katex math').count(), 1)
        with self.page.expect_download() as pending:
            self.page.locator('#export').click()
        svg_path = self.repo / 'formula.svg'
        pending.value.save_as(svg_path)
        svg = svg_path.read_text()
        self.assertIn('data:font/woff2;base64,', svg)
        self.assertIn('foreignObject', svg)
        self.page.goto(svg_path.as_uri())
        self.assertEqual(self.page.locator('foreignObject math').count(), 1)
        self.assertEqual(self.page.locator('parsererror').count(), 0)

    def test_invalid_presentation_references_are_rejected(self):
        invalid = json.loads(json.dumps(self.spec))
        invalid['profiles'][0]['notes'][0]['module'] = 'missing'
        with self.assertRaisesRegex(ValueError, 'links must reference'):
            builder.validate_spec(invalid)
        invalid = json.loads(json.dumps(self.spec))
        invalid['profiles'][0]['views'][0]['flow'][0]['modules'] = ['linear']
        with self.assertRaisesRegex(ValueError, 'visible module ids'):
            builder.validate_spec(invalid)

    def test_bundled_checker_click_source_export_and_keyboard_paths(self):
        result = json.loads(subprocess.check_output([
            sys.executable, str(SKILL / 'scripts' / 'check_explorer.py'), '--page', str(self.output)
        ], text=True))
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['profiles'], 2)
        self.assertGreater(result['math_renders'], 0)


if __name__ == '__main__':
    unittest.main()
