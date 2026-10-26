/* Requires an embedded application/json element named math-svg-data. */
window.architectureMath = (() => {
 const cache=JSON.parse(document.getElementById('math-svg-data').textContent);
 const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const pattern=/(\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)|(?<!\\)\$(?!\$)[^\n$]+?(?<!\\)\$)/g;
 const strip=token=>token.slice(token.startsWith('$$')||token.startsWith('\\')?2:1,token.startsWith('$$')||token.startsWith('\\')?-2:-1).trim();
 function formula(tex,display=false){
  const entry=cache[String(tex).trim()];
  if(!entry)throw Error('Uncompiled formula: '+tex);
  const [,top,w,h]=entry.viewBox.split(/\s+/).map(Number);
  const markup=entry.svg.replace(/^<svg[^>]*>/,`<svg xmlns="http://www.w3.org/2000/svg" width="${w/1000}em" height="${h/1000}em" viewBox="${entry.viewBox}" style="vertical-align:${-(top+h)/1000}em" role="img" aria-label="${escape(tex)}">`);
  return `<span class="math-expression ${display?'display-math':''}" data-latex="${escape(tex)}">${markup}</span>`;
 }
 function text(value){
  const source=String(value??'');let output='',at=0;pattern.lastIndex=0;
  for(const match of source.matchAll(pattern)){output+=escape(source.slice(at,match.index))+formula(strip(match[0]),match[0].startsWith('$$')||match[0].startsWith('\\['));at=match.index+match[0].length;}
  return output+escape(source.slice(at));
 }
 function hasMath(value){pattern.lastIndex=0;return pattern.test(String(value));}
 function equations(items){return items?.length?`<section class="equations" aria-label="计算公式">${items.map(tex=>`<div class="equation">${formula(tex,true)}</div>`).join('')}</section>`:'';}
 function dimensions(value,size=13){
  const match=String(value).match(pattern);if(!match||match.length!==1)throw Error('Expected one diagram formula');
  const entry=cache[strip(match[0])];if(!entry)throw Error('Uncompiled formula');
  const [,top,w,h]=entry.viewBox.split(/\s+/).map(Number);
  return {top:top/1000*size,width:w/1000*size,height:h/1000*size};
 }
 function svg(value,x,y,width,size=13,fill='#58756c'){
  const match=String(value).match(pattern);
  if(!match||match.length!==1||String(value).trim()!==match[0])throw Error('A diagram math label must contain one formula; put prose in a separate label');
  const tex=strip(match[0]),entry=cache[tex];if(!entry)throw Error('Uncompiled formula: '+tex);
  const [,top,w,h]=entry.viewBox.split(/\s+/).map(Number);
  const naturalWidth=w/1000*size,naturalHeight=h/1000*size;
  if(naturalWidth>width)throw Error('Formula exceeds its diagram slot; simplify it or widen the slot: '+tex);
  return entry.svg.replace(/^<svg[^>]*>/,`<svg class="math-label" data-latex="${escape(tex)}" x="${x}" y="${y+top/1000*size}" width="${naturalWidth}" height="${naturalHeight}" viewBox="${entry.viewBox}" style="color:${fill};overflow:visible" aria-label="${escape(tex)}">`);
 }
 return {formula,text,equations,hasMath,svg,dimensions,fitSVG:()=>{}};
})();
