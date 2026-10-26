#!/usr/bin/env python3
"""Build an offline architecture explorer from a reviewed JSON spec and explicit sources."""
from __future__ import annotations

import argparse
import ast
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import warnings
import xml.etree.ElementTree as ET


DEFAULT_TEMPLATE = Path(__file__).resolve().parent.parent / 'assets' / 'explorer.html'
KATEX_ASSETS = DEFAULT_TEMPLATE.parent / 'katex'


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def positive_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 < value < float('inf')


def finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and -float('inf') < value < float('inf')


def validate_presentation(profile: dict, context: str) -> None:
    """Validate optional reading aids against this profile's actual modules."""
    modules = profile['modules']
    dimensions = profile.get('dimensions', {})
    require(isinstance(dimensions, dict) and all(
        re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', key) and finite_number(value)
        for key, value in dimensions.items()), f'{context}: dimensions need numeric named values')
    controls = profile.get('controls', [])
    require(isinstance(controls, list), f'{context}: controls must be an array')
    control_ids = set()
    for control in controls:
        require(isinstance(control, dict), f'{context}: each control must be an object')
        cid = control.get('id')
        require(isinstance(cid, str) and re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', cid)
                and cid not in control_ids, f'{context}: invalid/duplicate control id')
        control_ids.add(cid)
        value, low, high, step = [control.get(k, default) for k, default in
                                  [('value', None), ('min', 1), ('max', 4096), ('step', 1)]]
        require(all(finite_number(v) for v in (value, low, high, step)) and low <= value <= high
                and step > 0, f'{context}.{cid}: control needs value within min/max and positive step')
        require(isinstance(control.get('label', cid), str), f'{context}.{cid}: label must be text')
    layer_controls = profile.get('layerControls', [])
    require(isinstance(layer_controls, list), f'{context}: layerControls must be an array')
    view_ids = {view['id'] for view in profile['views']}
    for control in layer_controls:
        require(isinstance(control, dict), f'{context}: layer control must be an object')
        cid = control.get('id')
        require(isinstance(cid, str) and re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', cid)
                and cid not in control_ids, f'{context}: invalid/duplicate layer control id')
        control_ids.add(cid)
        value, high = control.get('value'), control.get('max')
        require(all(isinstance(v, int) and not isinstance(v, bool) for v in (value, high))
                and 1 <= value <= high, f'{context}.{cid}: layer value must be within 1..max')
        require(isinstance(control.get('label', cid), str), f'{context}.{cid}: label must be text')
        require('views' not in control or (isinstance(control['views'], list)
                and all(isinstance(v, str) and v in view_ids for v in control['views'])),
                f'{context}.{cid}: layer views must exist')
    stats = profile.get('stats', [])
    require(isinstance(stats, list) and all(isinstance(stat, dict)
            and isinstance(stat.get('label'), str)
            and (isinstance(stat.get('value'), str) or finite_number(stat.get('value')))
            and isinstance(stat.get('detail', ''), str) for stat in stats), f'{context}: invalid stats')
    if 'stats' in profile:
        require(bool(stats), f'{context}: stats must not be empty when provided')
    trace = profile.get('trace', [])
    require(isinstance(trace, list) and all(isinstance(mid, str) and mid in modules for mid in trace),
            f'{context}: trace must reference existing module ids')
    notes = profile.get('notes', [])
    require(isinstance(notes, list), f'{context}: notes must be an array')
    mechanism = profile.get('mechanism')
    if mechanism is not None:
        require(isinstance(mechanism, dict) and isinstance(mechanism.get('title'), str)
                and isinstance(mechanism.get('description', ''), str), f'{context}: invalid mechanism')
        equations = mechanism.get('equations', [])
        require(isinstance(equations, list) and all(isinstance(e, str) for e in equations),
                f'{context}: mechanism.equations must be strings')
    for note in notes:
        require(isinstance(note, dict) and all(isinstance(note.get(k), str) for k in ('title', 'text')),
                f'{context}: each note needs title/text')
    for item in notes + ([mechanism] if mechanism is not None else []):
        require('module' not in item or (isinstance(item['module'], str) and item['module'] in modules),
                f'{context}: mechanism/note links must reference existing modules')
    legend = profile.get('legend', [])
    require(isinstance(legend, list) and all(isinstance(item, dict)
            and all(isinstance(item.get(k), str) for k in ('kind', 'label')) for item in legend),
            f'{context}: legend needs kind/label entries')


def symbol_ranges(tree: ast.AST, prefix: str = '') -> dict[str, list[int]]:
    result = {}
    for node in getattr(tree, 'body', []):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            name = prefix + node.name
            start = min([node.lineno] + [d.lineno for d in node.decorator_list])
            result[name] = [start, node.end_lineno]
            result.update(symbol_ranges(node, name + '.'))
    return result


def validate_spec(spec: dict) -> list[dict]:
    require(isinstance(spec, dict), 'Spec root must be an object')
    require(isinstance(spec.get('title'), str) and bool(spec['title'].strip()), 'A nonempty title is required')
    presentation = spec.get('presentation', {})
    require(isinstance(presentation, dict) and all(isinstance(presentation.get(k, ''), str)
            for k in ('brand', 'headline', 'eyebrow', 'signature', 'repository')), 'Invalid presentation text')
    profiles = spec.get('profiles')
    require(isinstance(profiles, list) and bool(profiles), 'At least one profile is required')
    profile_ids = set()
    source_refs = []
    for profile in profiles:
        require(isinstance(profile, dict), 'Each profile must be an object')
        pid = profile.get('id')
        require(isinstance(pid, str) and bool(pid) and pid not in profile_ids, f'Invalid/duplicate profile id: {pid}')
        profile_ids.add(pid)
        views = profile.get('views')
        modules = profile.get('modules')
        require(isinstance(views, list) and bool(views), f'{pid}: views must be a nonempty array')
        require(isinstance(modules, dict) and bool(modules), f'{pid}: modules must be a nonempty object')
        view_ids = set()
        for view in views:
            require(isinstance(view, dict), f'{pid}: each view must be an object')
            vid = view.get('id')
            require(isinstance(vid, str) and bool(vid) and vid not in view_ids, f'{pid}: invalid/duplicate view id: {vid}')
            view_ids.add(vid)
        require(profile.get('defaultView', views[0]['id']) in view_ids, f'{pid}: defaultView does not exist')
        view_lookup = {view['id']: view for view in views}
        for view in views:
            parent = view.get('parent')
            require(parent is None or (isinstance(parent, str) and parent in view_ids),
                    f'{pid}.{view["id"]}: parent view must exist')
        for view in views:
            parent = view.get('parent')
            visited = {view['id']}
            while parent is not None:
                require(parent not in visited, f'{pid}.{view["id"]}: cyclic view hierarchy')
                visited.add(parent)
                parent = view_lookup[parent].get('parent')
        for mid, module in modules.items():
            require(isinstance(module, dict), f'{pid}.{mid}: module must be an object')
            require(isinstance(module.get('title'), str) and bool(module['title']), f'{pid}.{mid}: title is required')
            require(isinstance(module.get('description'), str), f'{pid}.{mid}: description is required')
            for name in ('input', 'output'):
                require(isinstance(module.get(name), str), f'{pid}.{mid}: {name} must be a string')
            require(isinstance(module.get('params', []), list), f'{pid}.{mid}: params must be an array')
            for param in module.get('params', []):
                require(isinstance(param, list) and len(param) == 2, f'{pid}.{mid}: params entries need [label,value]')
            operations = module.get('operations', [])
            require(isinstance(operations, list) and all(isinstance(x, str) for x in operations), f'{pid}.{mid}: operations must be strings')
            if 'expandTo' in module:
                require(module['expandTo'] in view_ids, f'{pid}.{mid}: expandTo does not exist')
            source = module.get('source')
            require(isinstance(source, dict) and isinstance(source.get('file'), str) and bool(source['file']), f'{pid}.{mid}: source.file is required')
            if 'symbol' in source:
                require(isinstance(source['symbol'], str), f'{pid}.{mid}: source.symbol must be a string')
            source_refs.append(source)
        validate_presentation(profile, pid)
        for view in views:
            context = f'{pid}.{view["id"]}'
            w, h = view.get('width'), view.get('height')
            require(positive_number(w) and positive_number(h), f'{context}: positive width and height required')
            require(view.get('variant', 'overview') in ('overview', 'operator'), f'{context}: unknown diagram variant')
            require(positive_number(view.get('minWidth', 650)), f'{context}: invalid minWidth')
            require(all(isinstance(view.get(k, ''), str) for k in ('heading', 'description')),
                    f'{context}: heading/description must be text')
            nodes = view.get('nodes')
            require(isinstance(nodes, list) and bool(nodes), f'{context}: at least one node is required')
            node_ids = set()
            for node in nodes:
                require(isinstance(node, dict), f'{context}: node must be an object')
                nid = node.get('id')
                require(isinstance(nid, str) and bool(nid) and nid not in node_ids, f'{context}: invalid/duplicate node id: {nid}')
                node_ids.add(nid)
                require(node.get('module') in modules, f'{context}.{nid}: unknown module')
                x, y, nw, nh = [node.get(k) for k in ('x', 'y', 'width', 'height')]
                require(all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (x, y)), f'{context}.{nid}: numeric x/y required')
                require(positive_number(nw) and positive_number(nh), f'{context}.{nid}: positive node size required')
                require(0 <= x and 0 <= y and x + nw <= w and y + nh <= h, f'{context}.{nid}: node outside viewBox')
                require(isinstance(node.get('lines', []), list) and all(isinstance(v, str) for v in node.get('lines', [])), f'{context}.{nid}: lines must be strings')
                require(all(isinstance(node.get(k, ''), str) for k in ('title', 'foot', 'badge')),
                        f'{context}.{nid}: title/foot/badge must be strings')
                require(positive_number(node.get('titleSize', 13)), f'{context}.{nid}: invalid titleSize')
                require(positive_number(node.get('lineHeight', 20)), f'{context}.{nid}: invalid lineHeight')
                require(positive_number(node.get('fontSize', 11)), f'{context}.{nid}: invalid fontSize')
                require(isinstance(node.get('kind', ''), str), f'{context}.{nid}: invalid visual kind')
                blocks = node.get('blocks', [])
                require(isinstance(blocks, list) and all(isinstance(block, dict)
                        and isinstance(block.get('title'), str) and isinstance(block.get('text', ''), str)
                        and isinstance(block.get('kind', ''), str) for block in blocks), f'{context}.{nid}: invalid blocks')
                if blocks:
                    require(nw > 56 and nh >= 44 + (len(blocks)-1)*53 + 44 + (28 if node.get('foot') else 10),
                            f'{context}.{nid}: blocks need more node width/height')
            visible_modules = {node['module'] for node in nodes}
            require(view.get('defaultModule', nodes[0]['module']) in visible_modules,
                    f'{context}: defaultModule must appear in this view')
            flow = view.get('flow', [])
            require(isinstance(flow, list), f'{context}: flow must be an array')
            for step in flow:
                require(isinstance(step, dict) and isinstance(step.get('label'), str)
                        and isinstance(step.get('modules'), list) and bool(step['modules'])
                        and all(isinstance(mid, str) and mid in visible_modules for mid in step['modules']),
                        f'{context}: each flow step needs label and visible module ids')
            for group in view.get('groups', []):
                gx, gy, gw, gh = [group.get(k) for k in ('x', 'y', 'width', 'height')]
                require(all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (gx, gy)), f'{context}: group needs numeric x/y')
                require(positive_number(gw) and positive_number(gh), f'{context}: invalid group size')
                require(0 <= gx and 0 <= gy and gx + gw <= w and gy + gh <= h, f'{context}: group outside viewBox')
            for edge in view.get('edges', []):
                require(isinstance(edge, dict) and isinstance(edge.get('d'), str) and bool(edge['d']), f'{context}: edge.d must be an SVG path')
                if edge.get('label'):
                    require(all(isinstance(edge.get(k), (int, float)) for k in ('labelX', 'labelY')), f'{context}: edge label needs labelX/labelY')
            for note in view.get('notes', []):
                require(isinstance(note, dict) and isinstance(note.get('text'), str), f'{context}: note.text required')
                require(all(isinstance(note.get(k), (int, float)) for k in ('x', 'y')), f'{context}: note needs numeric x/y')
                require(0 <= note['x'] <= w and 0 <= note['y'] <= h, f'{context}: note outside viewBox')
    require(spec.get('defaultProfile', profiles[0]['id']) in profile_ids, 'defaultProfile does not exist')
    extra = spec.get('sourceFiles', [])
    require(isinstance(extra, list) and all(isinstance(f, str) for f in extra), 'sourceFiles must be strings')
    source_refs.extend({'file': filename} for filename in extra)
    return source_refs


def snapshots(root: Path, refs: list[dict]) -> tuple[dict, set[Path]]:
    result = {}
    paths = set()
    for ref in refs:
        filename = ref['file']
        path = (root / filename).resolve()
        require(not Path(filename).is_absolute() and path.is_relative_to(root), f'Source must be inside repo: {filename}')
        require(path.is_file(), f'Source file does not exist: {filename}')
        paths.add(path)
        if filename not in result:
            source = path.read_text(encoding='utf-8')
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', SyntaxWarning)
                symbols = symbol_ranges(ast.parse(source, filename=filename)) if path.suffix == '.py' else {}
            result[filename] = {'lines': source.splitlines(), 'symbols': symbols, 'sha256': hashlib.sha256(source.encode()).hexdigest()}
        if ref.get('symbol'):
            require(ref['symbol'] in result[filename]['symbols'], f'Unknown Python symbol {filename}:{ref["symbol"]}; use a real AST-qualified definition')
    return result, paths


def inject(html: str, element_id: str, payload: dict) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False).replace('<', '\\u003c')
    pattern = rf'(<script id="{re.escape(element_id)}" type="application/json">).*?(</script>)'
    output, count = re.subn(pattern, lambda match: match[1] + encoded + match[2], html, flags=re.S)
    require(count == 1, f'Template needs exactly one JSON script element: {element_id}')
    return output


def embed_math_assets(template: str) -> str:
    """Bundle KaTeX, its MIT notice and fonts without runtime network requests."""
    markers = ('<!-- KATEX_STYLES -->', '<!-- KATEX_SCRIPTS -->')
    if not any(marker in template for marker in markers):
        return template  # Preserve custom templates with their own math renderer.
    require(all(template.count(marker) == 1 for marker in markers),
            'Math-enabled templates need exactly one KATEX_STYLES and KATEX_SCRIPTS marker')
    css = (KATEX_ASSETS / 'katex.min.css').read_text(encoding='utf-8')

    def font_source(match: re.Match) -> str:
        font = re.search(r'url\((fonts/[^)]+\.woff2)\)', match[0])
        require(font is not None, 'Bundled KaTeX font is missing a WOFF2 source')
        data = base64.b64encode((KATEX_ASSETS / font[1]).read_bytes()).decode('ascii')
        return f'src:url(data:font/woff2;base64,{data}) format("woff2");'

    css = re.sub(r'src:[^;]+;', font_source, css)
    license_text = (KATEX_ASSETS / 'LICENSE').read_text(encoding='utf-8')
    template = template.replace(markers[0], f'<style id="katex-styles">\n/* KaTeX 0.16.22\n{license_text}*/\n{css}\n</style>')
    scripts = []
    for filename in ('katex.min.js', 'contrib/auto-render.min.js'):
        script = (KATEX_ASSETS / filename).read_text(encoding='utf-8')
        script = re.sub(r'</script', r'<\\/script', script, flags=re.I)
        scripts.append(f'<script>{script}</script>')
    return template.replace(markers[1], '\n'.join(scripts))


MATH_PATTERN = re.compile(r'\$\$([\s\S]+?)\$\$|\\\[([\s\S]+?)\\\]|\\\(([\s\S]+?)\\\)|(?<!\\)\$([^$\n]+?)\$')


def formula_strings(value):
    if isinstance(value, str):
        for match in MATH_PATTERN.finditer(value):
            yield next(group for group in match.groups() if group is not None).strip()
    elif isinstance(value, list):
        for item in value:
            yield from formula_strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from formula_strings(item)


def embed_vector_math(template: str, spec: dict, cache_path: Path) -> str:
    """Use a reviewed cache without requiring Node or font downloads at build/runtime."""
    cache = json.loads(cache_path.read_text(encoding='utf-8'))
    require(isinstance(cache, dict), 'SVG formula cache must be an object')
    formulas = set(formula_strings(spec))
    require(not any('{{' in tex for tex in formulas),
            'Precompiled formulas must use symbolic values; keep dynamic dimensions in plain shape labels or use KaTeX')
    missing = formulas - cache.keys()
    require(not missing, 'SVG formula cache is missing expressions; recompile with render_math.mjs --spec: ' + repr(sorted(missing)))
    for tex, entry in cache.items():
        require(isinstance(entry, dict) and isinstance(entry.get('svg'), str)
                and isinstance(entry.get('viewBox'), str), f'Invalid SVG formula cache entry: {tex}')
        bounds = [float(v) for v in entry['viewBox'].split()]
        require(len(bounds) == 4 and all(finite_number(v) for v in bounds)
                and bounds[2] > 0 and bounds[3] > 0, f'Invalid formula viewBox: {tex}')
        root = ET.fromstring(entry['svg'])
        tags = {el.tag.split('}')[-1] for el in root.iter()}
        require(root.tag.split('}')[-1] == 'svg' and root.get('viewBox') == entry['viewBox']
                and 'path' in tags and not tags & {'script', 'foreignObject', 'image', 'use', 'text'},
                f'Formula cache must contain self-contained glyph paths: {tex}')
    styles, scripts = '<!-- KATEX_STYLES -->', '<!-- KATEX_SCRIPTS -->'
    require(template.count(styles) == template.count(scripts) == 1,
            'The --math-svg option needs one KATEX_STYLES and KATEX_SCRIPTS marker in the template')
    # JSON is embedded as data, never as executable script text.
    payload = json.dumps(cache, ensure_ascii=False).replace('<', r'\u003c')
    helper = (DEFAULT_TEMPLATE.parent / 'svg-math.js').read_text(encoding='utf-8')
    return template.replace(styles, '').replace(scripts,
        '<script id="math-svg-data" type="application/json">' + payload + '</script>\n<script>' + helper + '</script>')


def build(root: Path, spec_path: Path, output: Path, template_path: Path, math_svg_path: Path | None = None) -> dict:
    root = root.resolve()
    spec_path, output, template_path = spec_path.resolve(), output.resolve(), template_path.resolve()
    require(root.is_dir(), f'Repo directory not found: {root}')
    spec = json.loads(spec_path.read_text(encoding='utf-8'))
    refs = validate_spec(spec)
    files, source_paths = snapshots(root, refs)
    require(output not in source_paths | {spec_path, template_path} | ({math_svg_path.resolve()} if math_svg_path else set()), 'Output must not overwrite a source, spec, or template file')
    raw_template = template_path.read_text(encoding='utf-8')
    template = embed_vector_math(raw_template, spec, math_svg_path) if math_svg_path else embed_math_assets(raw_template)
    spec.pop('revision', None)
    digest_input = json.dumps({'spec': spec, 'files': files, 'template': template}, ensure_ascii=False, sort_keys=True)
    spec['revision'] = hashlib.sha256(digest_input.encode()).hexdigest()[:12]
    source_payload = {'generated': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'files': files}
    html = inject(inject(template, 'architecture-data', spec), 'source-data', source_payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding='utf-8')
    return {'output': str(output), 'revision': spec['revision'], 'profiles': len(spec['profiles']), 'source_files': len(files)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True, type=Path)
    parser.add_argument('--spec', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--template', type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument('--math-svg', type=Path, help='Optional precompiled math-svg.json; use native SVG formulas instead of KaTeX')
    args = parser.parse_args()
    try:
        result = build(args.repo, args.spec, args.output, args.template, args.math_svg)
    except (ValueError, OSError, SyntaxError, TypeError, ET.ParseError) as error:
        print(f'Build failed: {error}', file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
