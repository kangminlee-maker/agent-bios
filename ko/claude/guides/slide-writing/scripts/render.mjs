// Render only the sealed HTML and its sealed local assets. No slide styles are injected.
import {readFile, writeFile, mkdir, realpath} from 'node:fs/promises';
import {resolve, relative, isAbsolute, sep} from 'node:path';
import {pathToFileURL, fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';

const [htmlArg, outArg, sealedArg] = process.argv.slice(2);
if (!htmlArg || !outArg || !sealedArg) throw new Error('Usage: render.mjs SEALED_HTML OUTPUT_DIR SEALED_ROOT');
const modulePath = process.env.SLIDE_PLAYWRIGHT_MODULE;
const browserPath = process.env.SLIDE_BROWSER_EXECUTABLE;
if (!modulePath || !browserPath) throw new Error('SLIDE_PLAYWRIGHT_MODULE and SLIDE_BROWSER_EXECUTABLE are required');
const {chromium} = await import(pathToFileURL(resolve(modulePath)).href);
const require = createRequire(resolve(modulePath));
const {PDFDocument} = require('pdf-lib');
const html = await realpath(htmlArg), sealed = await realpath(sealedArg), out = resolve(outArg);
const inside = path => { const r = relative(sealed, path); return r !== '..' && !r.startsWith('..' + sep) && !isAbsolute(r); };
if (!inside(html)) throw new Error('HTML is outside sealed input root');
await mkdir(out, {recursive:true});
const browser = await chromium.launch({headless:true, executablePath:resolve(browserPath)});
try {
  const page = await browser.newPage({viewport:{width:1400,height:1000}, deviceScaleFactor:1});
  const blocked = [], errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.route('**/*', async route => {
    const u = route.request().url();
    if (u.startsWith('data:') || u.startsWith('about:')) return route.continue();
    if (u.startsWith('file:')) {
      try { if (inside(await realpath(fileURLToPath(u)))) return route.continue(); } catch {}
    }
    blocked.push(u); return route.abort();
  });
  await page.emulateMedia({media:'print'});
  await page.goto(pathToFileURL(html).href, {waitUntil:'networkidle'});
  await page.evaluate(() => document.fonts.ready);
  const pages = await page.evaluate(() => [...document.querySelectorAll('section.slide')].map((slide,i) => {
    const rect = slide.getBoundingClientRect(), texts = [], outside = [];
    const walker = document.createTreeWalker(slide, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      const value = node.textContent.trim(); if (!value) continue;
      const parent = node.parentElement, style = getComputedStyle(parent);
      if (style.visibility === 'hidden' || style.display === 'none') continue;
      const range = document.createRange(); range.selectNodeContents(node);
      const bounds = range.getBoundingClientRect(); if (!bounds.width || !bounds.height) continue;
      const transforms = [];
      for (let p=parent; p && p!==slide.parentElement; p=p.parentElement) {
        const transform = getComputedStyle(p).transform;
        if (transform !== 'none') transforms.push(transform);
      }
      const item = {text:value, font_px:parseFloat(style.fontSize), x:bounds.x-rect.x, y:bounds.y-rect.y,
        width:bounds.width, height:bounds.height, alignment:style.textAlign,
        declared_level:parent.closest('[data-level]')?.getAttribute('data-level') ?? null,
        font_family:style.fontFamily, font_weight:style.fontWeight, transforms};
      texts.push(item);
      if (item.x < -1 || item.y < -1 || item.x+item.width > rect.width+1 || item.y+item.height > rect.height+1) outside.push(item);
    }
    const regions = [...slide.querySelectorAll('[data-role]')].map(n => {
      const r=n.getBoundingClientRect(); return {role:n.dataset.role,x:r.x-rect.x,y:r.y-rect.y,width:r.width,height:r.height};
    });
    return {id:'p'+String(i+1).padStart(4,'0'), source_page:slide.dataset.sourcePage ?? '',
      title:slide.querySelector('[data-role="title"],h1,h2')?.textContent.trim() ?? '',
      width:rect.width,height:rect.height,text:texts,outside,regions};
  }));
  if (!pages.length) throw new Error('No section.slide pages were rendered');
  for (const p of pages) {
    if (!(Number.isFinite(p.width) && Number.isFinite(p.height) && p.width>0 && p.height>0)) throw new Error('Invalid page geometry');
    if (Math.abs(p.width-pages[0].width)>1 || Math.abs(p.height-pages[0].height)>1) throw new Error('Pages have different dimensions');
  }
  const slides = page.locator('section.slide');
  for (let i=0; i<pages.length; i++) await slides.nth(i).screenshot({path:resolve(out,`page-${String(i+1).padStart(4,'0')}.png`),animations:'disabled'});
  await page.pdf({path:resolve(out,'deck.pdf'),width:pages[0].width+'px',height:pages[0].height+'px',
    printBackground:true,preferCSSPageSize:false,margin:{top:0,right:0,bottom:0,left:0}});
  const pdf = await PDFDocument.load(await readFile(resolve(out,'deck.pdf')));
  if (pdf.getPageCount() !== pages.length) throw new Error(`PDF page count ${pdf.getPageCount()} differs from HTML page count ${pages.length}`);
  const pdfSizes=pdf.getPages().map(p=>p.getSize());
  for (const size of pdfSizes) if (Math.abs(size.width-pages[0].width*.75)>1 || Math.abs(size.height-pages[0].height*.75)>1) throw new Error('PDF dimensions differ from measured slide dimensions');
  const report={pages, pdf_page_count:pdf.getPageCount(), pdf_sizes_points:pdfSizes,
    font_metric:'font_px is computed CSS size; inspect glyph rectangles, transforms, font loading and actual image separately',
    blocked_requests:blocked, script_errors:errors};
  await writeFile(resolve(out,'measurements.json'),JSON.stringify(report,null,2)+'\n');
  process.stdout.write(JSON.stringify({pages:pages.length,pdf_pages:pdf.getPageCount(),blocked_requests:blocked.length,script_errors:errors.length})+'\n');
} finally { await browser.close(); }
