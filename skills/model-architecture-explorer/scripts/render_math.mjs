#!/usr/bin/env node
// Compile reviewed, finite TeX expressions to self-contained SVG paths.
import {readFileSync, writeFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {resolve} from 'node:path';

const args = process.argv.slice(2);
const option = name => args[args.indexOf(name) + 1];
if (!args.includes('--input') || !args.includes('--output')) {
  console.error('Usage: node render_math.mjs --input formulas.json --output math-svg.json [--module-dir /path/node_modules]');
  process.exit(1);
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
const formulas = JSON.parse(readFileSync(option('--input'), 'utf8'));
if (!Array.isArray(formulas) || formulas.some(tex => typeof tex !== 'string')) {
  throw new Error('Input must be an array of TeX strings without delimiters');
}
const output = {};
for (const tex of new Set(formulas)) {
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
