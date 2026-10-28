#!/usr/bin/env python3
"""Exercise the bundled explorer template's real click path using optional Playwright."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
import xml.etree.ElementTree as ET


def check_math(page, root: str) -> int:
    """Check rendered math in the current dynamic region, including parse failures."""
    region = page.locator(root)
    assert region.locator('.math-error, .katex-error, [data-mml-node="merror"]').count() == 0, f'{root}: invalid LaTeX formula'
    formula = re.compile(r'\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)|(?<!\\)\$[^$\n]+?\$')
    for element in region.locator('.math-text').all():
        source = element.get_attribute('data-math-source') or ''
        if formula.search(source):
            assert element.locator('.katex math, .math-expression svg path').count() > 0, f'{root}: LaTeX was not typeset: {source}'
    for element in region.locator('.math-expression, .math-label').all():
        assert element.get_attribute('data-latex'), f'{root}: vector formula lacks a TeX label'
        assert element.locator('path').count() > 0, f'{root}: vector formula has no glyph paths'
    return region.locator('.katex, .math-expression, .math-label').count()


def check_formula_layout(page) -> list:
    """Nested SVG getBBox uses local coordinates; compare rendered screen rectangles."""
    return page.evaluate("""() => [...document.querySelectorAll('#graph .node')].flatMap(node=>{
      const box=node.querySelector('.box').getBoundingClientRect();
      return [...node.querySelectorAll('.math-label')].flatMap(el=>{
        const r=el.getBoundingClientRect();
        const overflow=r.left<box.left-1||r.top<box.top-1||r.right>box.right+1||r.bottom>box.bottom+1;
        const peers=[...node.querySelectorAll('text,.math-label')].filter(t=>t!==el);
        const overlap=peers.some(t=>{const q=t.getBoundingClientRect();return Math.min(q.right,r.right)-Math.max(q.left,r.left)>2&&Math.min(q.bottom,r.bottom)-Math.max(q.top,r.top)>2;});
        return overflow||overlap?[{node:node.dataset.node,latex:el.dataset.latex,overflow,overlap}]:[];
      });
    })""")


def select_view(page, view_id: str) -> None:
    picker = page.locator('#view-picker')
    if picker.count() and picker.is_visible():
        picker.select_option(view_id)
    else:
        next(button for button in page.locator('#tabs button').all()
             if button.get_attribute('data-view') == view_id).click()


def active_view_id(page) -> str | None:
    return (page.locator('#current-view').get_attribute('data-view')
            or page.locator('#tabs button[aria-selected="true"]').get_attribute('data-view'))


def check_wires(page) -> list:
    """Find connections that leave the canvas or pass through unrelated nodes."""
    return page.evaluate('''() => {
      const graph=document.querySelector('#graph'),v=graph.viewBox.baseVal;
      const boxes=[...graph.querySelectorAll('.node')].map(n=>({id:n.dataset.node,b:n.querySelector('.box').getBBox()}));
      const inside=(p,b,m=0)=>p.x>b.x+m&&p.x<b.x+b.width-m&&p.y>b.y+m&&p.y<b.y+b.height-m;
      return [...graph.querySelectorAll('path.wire')].flatMap(path=>{
        const length=path.getTotalLength(),start=path.getPointAtLength(0),end=path.getPointAtLength(length);
        const unrelated=boxes.filter(({b})=>!inside(start,b,-2)&&!inside(end,b,-2));
        for(let d=0;d<=length;d+=3){const p=path.getPointAtLength(d);
          if(p.x<0||p.y<0||p.x>v.width||p.y>v.height)return [{path:path.getAttribute('d'),issue:'outside viewBox'}];
          const hit=unrelated.find(({b})=>inside(p,b,3));if(hit)return [{path:path.getAttribute('d'),issue:'crosses '+hit.id}];
        }return [];
      });
    }''')


def check(url: str, screenshot: Path | None = None, browser_path: str | None = None) -> dict:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        options = {'headless': True}
        if browser_path:
            options['executable_path'] = browser_path
        browser = playwright.chromium.launch(**options)
        try:
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(url)
            page.wait_for_selector('#graph .node')
            spec = json.loads(page.locator('#architecture-data').text_content())
            sources = json.loads(page.locator('#source-data').text_content())
            checked_nodes = checked_sources = checked_views = checked_math = 0
            checked_math += check_math(page, '#subtitle')
            for profile in spec['profiles']:
                page.locator('#profile-picker').select_option(profile['id'])
                checked_math += check_math(page, '#assumptions')
                for region in ('#summary-stats', '#core-idea', '#implementation-notes', '#tensor-body'):
                    if page.locator(region).count():
                        checked_math += check_math(page, region)
                for view in profile['views']:
                    # Select by the exact stored id, even when labels overlap.
                    select_view(page, view['id'])
                    page.evaluate('document.fonts.ready')
                    checked_math += check_math(page, '#inspector-content')
                    checked_math += check_math(page, '#graph')
                    for region in ('#module-inputs', '#module-outputs'):
                        if page.locator(region).count():
                            checked_math += check_math(page, region)
                    for index, port in enumerate(view.get('interface', {}).get('inputs', [])):
                        page.locator(f'#module-inputs [data-input="{index}"]').click()
                        focused = page.locator('#graph .input-focus').evaluate_all('(nodes)=>nodes.map(n=>n.dataset.module)')
                        assert set(focused) == set(port['targets']), f'{view["id"]}: input did not locate its target'
                        assert not page.locator('#operator-modal').is_visible(), 'Input location unexpectedly opened an operator'
                    for index, port in enumerate(view.get('interface', {}).get('outputs', [])):
                        page.locator(f'#module-outputs [data-output="{index}"]').click()
                        focused = page.locator('#graph .input-focus').evaluate_all('(nodes)=>nodes.map(n=>n.dataset.module)')
                        assert set(focused) == set(port['sources']), f'{view["id"]}: output did not locate its source'

                    assert active_view_id(page) == view['id']
                    assert page.locator('#graph').get_attribute('viewBox') == f'0 0 {view["width"]} {view["height"]}'
                    overflow = page.evaluate('''() => {
                      const graph=document.querySelector('#graph'),v=graph.viewBox.baseVal;
                      return [...graph.querySelectorAll('text,foreignObject')].filter(t=>{const b=t.getBBox();return b.x<0||b.y<0||b.x+b.width>v.width||b.y+b.height>v.height}).map(t=>t.textContent);
                    }''')
                    assert not overflow, f'{profile["id"]}/{view["id"]}: labels outside viewBox: {overflow}'
                    wires = check_wires(page)
                    assert not wires, f'{profile["id"]}/{view["id"]}: misleading connections: {wires}'
                    node_overflow = page.evaluate('''() => [...document.querySelectorAll('#graph .node')].flatMap(n=>{
                      const r=n.querySelector('.box').getBBox();return [...n.querySelectorAll('text,foreignObject')].filter(t=>{const b=t.getBBox();return b.x<r.x||b.y<r.y||b.x+b.width>r.x+r.width||b.y+b.height>r.y+r.height}).map(t=>({node:n.dataset.node,text:t.textContent}));
                    })''')
                    assert not node_overflow, f'{profile["id"]}/{view["id"]}: node label overflow: {node_overflow}'
                    collisions = check_formula_layout(page)
                    assert not collisions, f'{profile["id"]}/{view["id"]}: formula collisions: {collisions}'
                    clipped_math = page.locator('#graph .svg-math > div').evaluate_all('''elements=>elements.filter(
                        el=>el.scrollWidth>el.clientWidth+1||el.scrollHeight>el.clientHeight+1
                    ).map(el=>el.textContent)''')
                    assert not clipped_math, f'{profile["id"]}/{view["id"]}: clipped graph formulas: {clipped_math}'
                    with TemporaryDirectory(prefix='architecture-svg-') as folder:
                        with page.expect_download() as pending:
                            page.locator('#export').click()
                        svg_path = Path(folder) / 'view.svg'
                        pending.value.save_as(svg_path)
                        svg = ET.fromstring(svg_path.read_text())
                        assert svg.attrib['width'] == str(view['width'])
                        assert svg.attrib['height'] == str(view['height'])
                        if page.locator('#math-svg-data').count():
                            markup=svg_path.read_text()
                            assert 'foreignObject' not in markup and '@font-face' not in markup, 'Vector export depends on HTML or math fonts'
                            # Open the download independently; DOM existence alone is not visual rendering.
                            exported=browser.new_page(viewport={'width':1440,'height':1000})
                            try:
                                exported.goto(svg_path.as_uri())
                                assert exported.locator('parsererror').count()==0
                                assert exported.locator('.math-label').count()==page.locator('#graph .math-label').count()
                                for glyph in exported.locator('.math-label').all():
                                    assert glyph.locator('path').count()>0
                            finally:
                                exported.close()
                    checked_views += 1
                    for index, node in enumerate(view['nodes']):
                        select_view(page, view['id'])
                        module = profile['modules'][node['module']]
                        element = page.locator('#graph .node').nth(index)
                        element.click()
                        checked_math += check_math(page, '#inspector-content')
                        checked_nodes += 1
                        target = module.get('expandTo')
                        if target and target != view['id']:
                            assert active_view_id(page) == target, f'{node["id"]}: did not expand'
                            assert not page.locator('#back').is_disabled()
                            page.locator('#back').click()
                            assert active_view_id(page) == view['id'], f'{node["id"]}: back failed'
                        else:
                            assert page.locator('#operator-modal').is_visible(), f'{node["id"]}: details did not open'
                            assert page.locator('#operator-title').inner_text() == module['title'] + ' · 计算详情'
                            shapes = page.locator('#operator-content .shape')
                            raw_shapes = [(shape.locator('.math-text').get_attribute('data-math-template')
                                           or shape.locator('.math-text').get_attribute('data-math-source'))
                                          if shape.locator('.math-text').count() else shape.text_content()
                                          for shape in shapes.all()]
                            assert raw_shapes == [module['input'], module['output']]
                            checked_math += check_math(page, '#operator-content')
                            page.locator('#operator-source').click()
                            assert page.locator('#source-modal').is_visible()
                            source = module['source']
                            file = sources['files'][source['file']]
                            expected = file['symbols'].get(source.get('symbol'), [1, len(file['lines'])])
                            focused = page.locator('#source-code .focus').evaluate_all('(lines)=>lines.map(l=>Number(l.dataset.line))')
                            assert focused == list(range(expected[0], expected[1] + 1)), f'{node["id"]}: wrong source range'
                            checked_sources += 1
                            page.keyboard.press('Escape')
                            assert not page.locator('#source-modal').is_visible()
                            element.focus()
                            page.keyboard.press('Enter')
                            assert page.locator('#operator-modal').is_visible(), f'{node["id"]}: keyboard failed'
                            checked_math += check_math(page, '#operator-content')
                            page.keyboard.press('Escape')
            # Test real mobile clicks, including horizontal scrolling within the graph.
            page.set_viewport_size({'width': 390, 'height': 844})
            page.locator('#profile-picker').select_option(spec['profiles'][0]['id'])
            page.locator('#graph .node').first.click()
            if page.locator('#operator-modal').is_visible():
                page.keyboard.press('Escape')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile page overflows horizontally'
            if screenshot:
                page.set_viewport_size({'width': 1440, 'height': 1000})
                page.locator('#profile-picker').select_option(spec['profiles'][0]['id'])
                page.locator('#status').evaluate('(element)=>element.hidden=true')
                screenshot.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(screenshot), full_page=True)
            assert not errors, f'Browser errors: {errors}'
            return {'status': 'PASS', 'profiles': len(spec['profiles']), 'views': checked_views, 'node_clicks': checked_nodes, 'source_ranges': checked_sources, 'math_renders': checked_math, 'page_errors': errors}
        finally:
            browser.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--page', type=Path, help='Generated HTML file; checks offline file:// behavior')
    target.add_argument('--url', help='Actual served HTTP URL')
    parser.add_argument('--screenshot', type=Path)
    parser.add_argument('--browser', help='Optional Chromium executable path')
    args = parser.parse_args()
    url = args.page.resolve().as_uri() if args.page else args.url
    try:
        result = check(url, args.screenshot, args.browser)
    except ModuleNotFoundError as error:
        print(f'Optional browser dependency missing: {error}. Install Playwright and Chromium in a suitable environment.', file=sys.stderr)
        return 1
    except Exception as error:
        print(f'Browser check failed: {type(error).__name__}: {error}', file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
