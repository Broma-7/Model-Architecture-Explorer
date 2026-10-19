#!/usr/bin/env python3
"""Exercise the bundled explorer template's real click path using optional Playwright."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import xml.etree.ElementTree as ET


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
            checked_nodes = checked_sources = checked_views = 0
            for profile in spec['profiles']:
                page.locator('#profile-picker').select_option(profile['id'])
                for view in profile['views']:
                    # Select by the exact stored id, even when labels overlap.
                    tab = page.locator('#tabs button').all()[next(i for i, v in enumerate(profile['views']) if v['id'] == view['id'])]
                    tab.click()
                    assert tab.get_attribute('aria-selected') == 'true'
                    assert page.locator('#graph').get_attribute('viewBox') == f'0 0 {view["width"]} {view["height"]}'
                    overflow = page.evaluate('''() => {
                      const graph=document.querySelector('#graph'),v=graph.viewBox.baseVal;
                      return [...graph.querySelectorAll('text')].filter(t=>{const b=t.getBBox();return b.x<0||b.y<0||b.x+b.width>v.width||b.y+b.height>v.height}).map(t=>t.textContent);
                    }''')
                    assert not overflow, f'{profile["id"]}/{view["id"]}: labels outside viewBox: {overflow}'
                    node_overflow = page.evaluate('''() => [...document.querySelectorAll('#graph .node')].flatMap(n=>{
                      const r=n.querySelector('.box').getBBox();return [...n.querySelectorAll('text')].filter(t=>{const b=t.getBBox();return b.x<r.x||b.y<r.y||b.x+b.width>r.x+r.width||b.y+b.height>r.y+r.height}).map(t=>({node:n.dataset.node,text:t.textContent}));
                    })''')
                    assert not node_overflow, f'{profile["id"]}/{view["id"]}: node label overflow: {node_overflow}'
                    with TemporaryDirectory(prefix='architecture-svg-') as folder:
                        with page.expect_download() as pending:
                            page.locator('#export').click()
                        svg_path = Path(folder) / 'view.svg'
                        pending.value.save_as(svg_path)
                        svg = ET.fromstring(svg_path.read_text())
                        assert svg.attrib['width'] == str(view['width'])
                        assert svg.attrib['height'] == str(view['height'])
                    checked_views += 1
                    for index, node in enumerate(view['nodes']):
                        tab.click()
                        module = profile['modules'][node['module']]
                        element = page.locator('#graph .node').nth(index)
                        element.click()
                        checked_nodes += 1
                        target = module.get('expandTo')
                        if target and target != view['id']:
                            target_tab = page.locator('#tabs button').all()[next(i for i, v in enumerate(profile['views']) if v['id'] == target)]
                            assert target_tab.get_attribute('aria-selected') == 'true', f'{node["id"]}: did not expand'
                            assert not page.locator('#back').is_disabled()
                            page.locator('#back').click()
                            assert tab.get_attribute('aria-selected') == 'true', f'{node["id"]}: back failed'
                        else:
                            assert page.locator('#operator-modal').is_visible(), f'{node["id"]}: details did not open'
                            assert page.locator('#operator-title').inner_text() == module['title'] + ' · 计算详情'
                            assert page.locator('#operator-content .shape').all_text_contents() == [module['input'], module['output']]
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
            return {'status': 'PASS', 'profiles': len(spec['profiles']), 'views': checked_views, 'node_clicks': checked_nodes, 'source_ranges': checked_sources, 'page_errors': errors}
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
