#!/usr/bin/env python3
"""Build an offline architecture explorer from a reviewed JSON spec and explicit sources."""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import warnings


DEFAULT_TEMPLATE = Path(__file__).resolve().parent.parent / 'assets' / 'explorer.html'


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def positive_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 < value < float('inf')


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
        for view in views:
            context = f'{pid}.{view["id"]}'
            w, h = view.get('width'), view.get('height')
            require(positive_number(w) and positive_number(h), f'{context}: positive width and height required')
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


def build(root: Path, spec_path: Path, output: Path, template_path: Path) -> dict:
    root = root.resolve()
    spec_path, output, template_path = spec_path.resolve(), output.resolve(), template_path.resolve()
    require(root.is_dir(), f'Repo directory not found: {root}')
    spec = json.loads(spec_path.read_text(encoding='utf-8'))
    refs = validate_spec(spec)
    files, source_paths = snapshots(root, refs)
    require(output not in source_paths | {spec_path, template_path}, 'Output must not overwrite a source, spec, or template file')
    template = template_path.read_text(encoding='utf-8')
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
    args = parser.parse_args()
    try:
        result = build(args.repo, args.spec, args.output, args.template)
    except (ValueError, OSError, SyntaxError, TypeError) as error:
        print(f'Build failed: {error}', file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
