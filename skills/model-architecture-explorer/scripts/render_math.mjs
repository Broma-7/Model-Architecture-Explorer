#!/usr/bin/env node
// Compile reviewed, finite TeX expressions to self-contained SVG paths.
import {readFileSync, writeFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {resolve} from 'node:path';

const args = process.argv.slice(2);
const option = name => args[args.indexOf(name) + 1];
if (args.includes('--input') === args.includes('--spec') || !args.includes('--output')) {
  console.error('Usage: node render_math.mjs (--input formulas.json | --spec spec.json) --output math-svg.json [--module-dir /path/node_modules]');
  process.exit(1);
}
const pattern = /\$\$([\s\S]+?)\$\$|\\\[([\s\S]+?)\\\]|\\\(([\s\S]+?)\\\)|(?<!\\)\$([^$\n]+?)\$/g;
function collect(value) {
  if (typeof value === 'string') return [...value.matchAll(pattern)].map(m => m.slice(1).find(v => v !== undefined).trim());
  if (value && typeof value === 'object') return Object.values(value).flatMap(collect);
  return [];
}
const require = args.includes('--module-dir')
  ? createRequire(resolve(option('--module-dir'), '../package.json'))
  : createRequire(import.meta.url);
const {mathjax} = require('mathjax-full/js/mathjax.js');
const {TeX} = require('mathjax-full/js/input/tex.js');
const {SVG} = require('mathjax-full/js/output/svg.js');
const {liteAdaptor} = require('mathjax-full/js/adaptors/liteAdaptor.js');
const {RegisterHTMLHandler} = require('mathjax-full/js/handlers/html.js');
const {AllPackages} = require('mathjax-full/js/input/tex/AllPackages.js');
const adaptor = liteAdaptor();
RegisterHTMLHandler(adaptor);
const document = mathjax.document('', {
  InputJax: new TeX({
    packages: AllPackages.filter(name => !['noerrors', 'noundefined'].includes(name)),
    formatError: (_jax, error) => { throw error; },
  }),
  OutputJax: new SVG({fontCache: 'none'}),
});
const formulas = args.includes('--spec')
  ? collect(JSON.parse(readFileSync(option('--spec'), 'utf8')))
  : JSON.parse(readFileSync(option('--input'), 'utf8'));
if (!Array.isArray(formulas) || formulas.some(tex => typeof tex !== 'string')) {
  throw new Error('Input must be an array of TeX strings without delimiters');
}
const output = {};
for (const tex of new Set(formulas)) {
  if (tex.includes('{{')) throw new Error('Precompiled formulas must use symbolic values; keep dynamic dimensions in plain shape labels or use KaTeX: ' + tex);
  let node;
  try { node = document.convert(tex, {display: true}); }
  catch (error) { throw new Error(`Invalid TeX: ${tex}: ${error.message}`); }
  const svg = adaptor.firstChild(node);
  const markup = adaptor.outerHTML(svg);
  if (markup.includes('data-mml-node="merror"')) throw new Error(`Invalid TeX: ${tex}`);
  output[tex] = {
    svg: markup,
    viewBox: adaptor.getAttribute(svg, 'viewBox'),
  };
}
writeFileSync(option('--output'), JSON.stringify(output));
console.log(`Rendered ${Object.keys(output).length} formulas as standalone SVG paths`);
